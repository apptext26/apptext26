"""Evaluación de capas uniformes. La comparación prioriza consumo físico.

El total de longitudes de marcadores por sí solo no equivale al consumo:
consumo (unidades lineales de entrada) = Σ largo_marcador × capas_marcador.
No se aplican conversiones de unidad ni desperdicios de extremos de tendido.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from time import perf_counter


@dataclass
class LayerPlanAlternative:
    plan_id: str
    layers: int | None
    plan: Any
    marker_count: int
    total_length: float
    average_efficiency: float
    shortage: int
    overproduction: int
    score: float
    consumption: float = 0.0
    mixed: bool = False
    origin: str = "uniforme"


def production_deviation(plan) -> tuple[int, int]:
    shortage = sum(int(row.get("Faltante", 0)) for row in plan.audit)
    excess = sum(int(row.get("Sobreproducción", 0)) for row in plan.audit)
    return shortage, excess


def fabric_consumption(plan) -> float:
    return sum(float(m.estimated_length) * int(m.layers) for m in plan.markers)


def weighted_rectangular_efficiency(plan, fabric_width: float | None = None) -> float:
    """Pondera por tela realmente extendida, no por promedio de marcadores."""
    total_bbox_area = 0.0
    total_fabric_area = 0.0
    for marker in plan.markers:
        width = float(fabric_width or marker.packing.fabric_width)
        area = width * float(marker.estimated_length) * int(marker.layers)
        total_fabric_area += area
        total_bbox_area += area * float(marker.rectangular_efficiency)
    return total_bbox_area / total_fabric_area if total_fabric_area else 0.0


def sample_layers(layers_min: int, layers_max: int, layer_step: int, limit: int | None) -> list[int]:
    """Muestra acotada pero incluye extremos y valores próximos al máximo."""
    values = list(range(int(layers_min), int(layers_max) + 1, int(layer_step)))
    if not values or not limit or len(values) <= limit:
        return values
    limit = max(2, int(limit))
    indices = {0, len(values) - 1}
    if limit >= 4:
        indices.update({len(values) - 2, len(values) - 3})
    for i in range(limit):
        indices.add(round(i * (len(values) - 1) / (limit - 1)))
    # Dar preferencia a extremos, valor alto y diversidad cuando sobran índices.
    if len(indices) > limit:
        essentials = {0, len(values) - 1}
        if limit >= 4:
            essentials.update({len(values) - 2, len(values) - 3})
        extras = sorted(indices - essentials, key=lambda i: (-min(i, len(values) - 1 - i), -i))
        indices = essentials | set(extras[:limit - len(essentials)])
    return [values[i] for i in sorted(indices)]


def _sort_key(item: LayerPlanAlternative) -> tuple:
    return (
        bool(item.shortage), item.shortage, round(item.consumption, 7),
        item.overproduction, item.marker_count, -item.average_efficiency,
    )


def evaluate_layer_range(
    plan_factory: Callable[..., Any],
    layers_min: int,
    layers_max: int,
    layer_step: int,
    top_k: int = 5,
    max_layer_trials: int | None = None,
    diagnostics: list[dict] | None = None,
    **plan_kwargs,
) -> list[LayerPlanAlternative]:
    """Genera planes uniformes y los compara por consumo estimado de tela."""
    if layers_min <= 0 or layers_max < layers_min or layer_step <= 0:
        raise ValueError("Rango de capas inválido.")
    if top_k <= 0:
        raise ValueError("top_k debe ser positivo.")
    attempts = sample_layers(layers_min, layers_max, layer_step, max_layer_trials)
    alternatives: list[LayerPlanAlternative] = []
    for layers in attempts:
        started = perf_counter()
        try:
            plan = plan_factory(layers=layers, **plan_kwargs)
        except (ValueError, RuntimeError) as error:
            if diagnostics is not None:
                diagnostics.append({"Fase": "uniforme", "Capas": layers,
                                    "Estado": "inviable", "Razón": str(error)[:240],
                                    "Segundos": round(perf_counter() - started, 4),
                                    "Cache packings": len(plan_kwargs.get("packing_cache") or {})})
            continue
        shortage, overproduction = production_deviation(plan)
        consumption = fabric_consumption(plan)
        if diagnostics is not None:
            diagnostics.append({"Fase": "uniforme", "Capas": layers,
                                "Estado": "viable" if not shortage else "faltante",
                                "Marcadores": len(plan.markers),
                                "Consumo estimado": round(consumption, 5),
                                "Faltante": shortage, "Sobreproducción": overproduction,
                                "Segundos": round(perf_counter() - started, 4),
                                "Cache packings": len(plan_kwargs.get("packing_cache") or {})})
        alternative = LayerPlanAlternative(
            plan_id="", layers=layers, plan=plan,
            marker_count=len(plan.markers), total_length=float(plan.total_length),
            average_efficiency=weighted_rectangular_efficiency(plan),
            shortage=shortage, overproduction=overproduction,
            score=0.0, consumption=consumption,
        )
        alternatives.append(alternative)
    if not alternatives:
        raise ValueError("Ninguna cantidad de capas produjo un plan viable.")
    alternatives.sort(key=_sort_key)
    best_consumption = min(a.consumption for a in alternatives if a.shortage == 0) if any(a.shortage == 0 for a in alternatives) else None
    for alt in alternatives:
        # Solo para compatibilidad con UI antigua, NO se usa en la elección.
        alt.score = round(100.0 * (best_consumption / alt.consumption), 2) if best_consumption and alt.consumption and not alt.shortage else 0.0
    selected = alternatives[: int(top_k)]
    for i, alt in enumerate(selected, 1):
        alt.plan_id = f"UNI-{i:03d}"
    return selected
