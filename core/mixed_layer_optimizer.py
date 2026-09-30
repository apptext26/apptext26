"""Búsqueda acotada de planes con capas independientes por marcador.

Heurística, NO solucionador exacto. Reutiliza los packings 2D ya calculados:
1) Reduce capas de marcadores de un plan viable sin crear faltantes.
2) Intenta sustituir un marcador de cierre por marcadores residuales con
   menor número de capas y vuelve a minimizar el consumo.
3) Nunca presenta un plan incompleto como candidato viable.

La función objetivo principal es Σ (largo estimado del marker × capas).
Al trabajar con un único ancho de tela todos los planes son comparables;
se excluyen empalmes, extremos, encogimiento y otros consumos operativos.
"""
from __future__ import annotations

from dataclasses import replace
from time import perf_counter
from typing import Any, Callable

from .layer_optimizer import (
    LayerPlanAlternative, fabric_consumption, production_deviation,
    weighted_rectangular_efficiency,
)
from .plan_optimizer import MarkerPlan, ProposedMarker, PlanGenerationError


def demand_by_size(requirements) -> dict[str, int]:
    grouped = requirements.groupby(["Modelo", "Talla"], as_index=False)["Unidades"].sum()
    return {f"{row['Modelo']}|{row['Talla']}": int(row["Unidades"])
            for _, row in grouped.iterrows() if int(row["Unidades"]) > 0}


def production(markers: list[ProposedMarker]) -> dict[str, int]:
    result: dict[str, int] = {}
    for marker in markers:
        for key, count in marker.repetitions.items():
            result[key] = result.get(key, 0) + int(count) * int(marker.layers)
    return result


def _clone(markers: list[ProposedMarker]) -> list[ProposedMarker]:
    # El packing es inmutable para esta etapa: únicamente cambian las capas.
    return [replace(marker, repetitions=dict(marker.repetitions),
                    marker_id=f"MK-{index:03d}")
            for index, marker in enumerate(markers, 1)]


def _reduce_layers(markers: list[ProposedMarker], demand: dict[str, int],
                   min_layers: int, layer_step: int, strategy: str) -> list[ProposedMarker]:
    markers = _clone(markers)
    made = production(markers)
    if any(made.get(size, 0) < amount for size, amount in demand.items()):
        raise PlanGenerationError("Un plan de origen no cubre la demanda.")
    if strategy == "menor_eficiencia":
        order = sorted(range(len(markers)), key=lambda i: (markers[i].rectangular_efficiency, -markers[i].estimated_length))
    elif strategy == "menor_largo":
        order = sorted(range(len(markers)), key=lambda i: (markers[i].estimated_length, markers[i].rectangular_efficiency))
    else:  # mayor ahorro absoluto potencial
        order = sorted(range(len(markers)), key=lambda i: (-markers[i].estimated_length, markers[i].rectangular_efficiency))

    for i in order:
        marker = markers[i]
        slack_per_size = [
            (made.get(size, 0) - demand.get(size, 0)) // int(reps)
            for size, reps in marker.repetitions.items() if int(reps) > 0
        ]
        if not slack_per_size:
            continue
        max_reduction = min(int(marker.layers) - int(min_layers), *slack_per_size)
        legal_decrease = max(0, max_reduction // int(layer_step)) * int(layer_step)
        if legal_decrease:
            markers[i] = replace(marker, layers=marker.layers - legal_decrease)
            for size, reps in marker.repetitions.items():
                made[size] -= int(reps) * legal_decrease
    return markers


def _assemble(markers: list[ProposedMarker], requirements) -> MarkerPlan:
    markers = _clone(markers)
    demand = demand_by_size(requirements)
    delivered = production(markers)
    audit = []
    for key, amount in sorted(demand.items()):
        model, size = key.split("|", 1)
        qty = delivered.get(key, 0)
        audit.append({
            "Modelo": model, "Talla": size,
            "Repeticiones requeridas": None,  # No existe un ratio único con capas mixtas.
            "Repeticiones planificadas": sum(m.repetitions.get(key, 0) for m in markers),
            "Unidades requeridas": amount, "Unidades producidas": qty,
            "Faltante": max(0, amount - qty),
            "Sobreproducción": max(0, qty - amount),
            "Estado": "Completo" if qty >= amount else "Faltante",
        })
    plan = MarkerPlan(
        plan_id="PLAN-MIX", markers=markers, required_repetitions={},
        layers=0, total_length=sum(m.estimated_length for m in markers),
        average_efficiency=0.0,
        integrity_ok=all(m.integrity_ok for m in markers),
        coverage_ok=all(r["Faltante"] == 0 for r in audit), audit=audit,
    )
    plan.average_efficiency = weighted_rectangular_efficiency(plan)
    return plan


def _signature(markers: list[ProposedMarker]) -> tuple:
    return tuple(sorted((tuple(sorted(m.repetitions.items())), m.layers) for m in markers))


def _candidate(plan: MarkerPlan, origin: str) -> LayerPlanAlternative:
    shortage, excess = production_deviation(plan)
    return LayerPlanAlternative(
        plan_id="", layers=None if len({m.layers for m in plan.markers}) > 1 else plan.markers[0].layers,
        plan=plan, marker_count=len(plan.markers), total_length=plan.total_length,
        average_efficiency=weighted_rectangular_efficiency(plan),
        shortage=shortage, overproduction=excess, score=0,
        consumption=fabric_consumption(plan),
        mixed=len({m.layers for m in plan.markers}) > 1, origin=origin,
    )


def _tail_layers(demand: dict[str, int], min_layers: int,
                 max_layers: int, step: int, high: int) -> list[int]:
    legal = [n for n in range(min_layers, max_layers + 1, step) if n < high]
    if not legal:
        return []
    residual_max = max(demand.values())
    closest = min(legal, key=lambda x: (abs(x - residual_max), -x))
    half = min(legal, key=lambda x: (abs(x - high // 2), -x))
    return sorted({legal[0], half, closest}, reverse=True)


def generate_mixed_alternatives(
    uniform_alternatives: list[LayerPlanAlternative],
    plan_factory: Callable[..., MarkerPlan],
    library: Any, requirements: Any,
    layers_min: int, layers_max: int, layer_step: int,
    max_markers: int, allow_overproduction: bool,
    max_residual_trials: int = 6,
    **plan_kwargs: Any,
) -> tuple[list[LayerPlanAlternative], list[dict]]:
    """Devuelve alternativas mixtas (si son viables) y auditoría del esfuerzo.

    `plan_kwargs` contiene la configuración 2D original, con `packing_cache`
    compartida *únicamente dentro de la ejecución actual*.
    """
    wanted = demand_by_size(requirements)
    discovered: dict[tuple, LayerPlanAlternative] = {}
    trace: list[dict] = []
    started = perf_counter()
    for uniform in uniform_alternatives:
        if uniform.shortage or not uniform.plan.coverage_ok or not uniform.plan.integrity_ok:
            continue
        for preference in ("mayor_ahorro", "menor_eficiencia", "menor_largo"):
            lowered = _reduce_layers(uniform.plan.markers, wanted, layers_min, layer_step, preference)
            plan = _assemble(lowered, requirements)
            if (not allow_overproduction and production_deviation(plan)[1]) or not plan.integrity_ok:
                continue
            candidate = _candidate(plan, f"reducción {preference}; base {uniform.layers}")
            if candidate.mixed:
                key = _signature(plan.markers)
                if key not in discovered or discovered[key].consumption > candidate.consumption:
                    discovered[key] = candidate

    # La segunda fase conserva marcadores principales de muchas capas y
    # sustituye UN marker de cierre por un conjunto de residuales de pocas capas.
    # Las pruebas están acotadas: no se prueban todos los subconjuntos/ratios.
    attempts = 0
    seeds = sorted(
        [a for a in uniform_alternatives if not a.shortage and a.plan.integrity_ok],
        key=lambda x: (-int(x.layers or 0), x.consumption),
    )[:2]
    for seed in seeds:
        if attempts >= max_residual_trials or len(seed.plan.markers) < 1:
            break
        # Probar cierre último y peor eficiencia, si son distintos.
        seed_markers = seed.plan.markers
        drop_indices = {len(seed_markers) - 1,
                        min(range(len(seed_markers)), key=lambda i: seed_markers[i].rectangular_efficiency)}
        for drop in sorted(drop_indices):
            if attempts >= max_residual_trials:
                break
            kept = _clone([m for idx, m in enumerate(seed_markers) if idx != drop])
            made = production(kept)
            residual = {key: max(0, qty - made.get(key, 0)) for key, qty in wanted.items()}
            residual = {key: qty for key, qty in residual.items() if qty > 0}
            if not residual:
                continue
            for tail_layers in _tail_layers(residual, layers_min, layers_max, layer_step, int(seed.layers)):
                if attempts >= max_residual_trials:
                    break
                attempts += 1
                trial_start = perf_counter()
                residual_requirements = requirements.iloc[0:0].copy()
                residual_requirements = residual_requirements.reindex(range(len(residual)))
                for idx, (key, count) in enumerate(residual.items()):
                    model, size = key.split("|", 1)
                    residual_requirements.loc[idx, ["Modelo", "Talla", "Unidades"]] = [model, size, count]
                try:
                    tail = plan_factory(
                        library=library, requirements=residual_requirements,
                        layers=tail_layers, max_markers=max_markers - len(kept),
                        allow_overproduction=True,
                        **plan_kwargs,
                    )
                    markers = _clone(kept + tail.markers)
                    for preference in ("mayor_ahorro", "menor_eficiencia"):
                        lowered = _reduce_layers(markers, wanted, layers_min, layer_step, preference)
                        plan = _assemble(lowered, requirements)
                        shortage, excess = production_deviation(plan)
                        if shortage or not plan.integrity_ok or (excess and not allow_overproduction):
                            continue
                        candidate = _candidate(plan, f"principal {seed.layers}; cierre {tail_layers}")
                        if not candidate.mixed:
                            continue
                        key = _signature(plan.markers)
                        if key not in discovered or discovered[key].consumption > candidate.consumption:
                            discovered[key] = candidate
                    trace.append({"Fase": "cierre", "Base": seed.layers,
                                  "Capas cierre": tail_layers, "Marcador sustituido": drop + 1,
                                  "Estado": "factible", "Segundos": round(perf_counter() - trial_start, 4)})
                except (PlanGenerationError, ValueError) as error:
                    trace.append({"Fase": "cierre", "Base": seed.layers,
                                  "Capas cierre": tail_layers, "Marcador sustituido": drop + 1,
                                  "Estado": str(error)[:160], "Segundos": round(perf_counter() - trial_start, 4)})
    mixed = sorted(discovered.values(), key=lambda a: (a.shortage, a.consumption, a.overproduction, a.marker_count))
    for i, item in enumerate(mixed, 1):
        item.plan_id = f"MIX-{i:03d}"
        item.plan.plan_id = item.plan_id
    trace.append({"Fase": "total", "Alternativas mixtas": len(mixed),
                  "Pruebas residuales": attempts, "Segundos": round(perf_counter() - started, 4)})
    return mixed, trace
