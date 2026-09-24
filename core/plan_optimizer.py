from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Tuple
import math

from .rectangle_packer import PackingResult, RectItem, pack_rectangles


@dataclass
class ProposedMarker:
    marker_id: str
    repetitions: Dict[str, int]
    packing: PackingResult
    strategy: str
    layers: int
    estimated_length: float
    rectangular_efficiency: float
    piece_count: int
    distinct_sizes: int
    integrity_ok: bool = True

    @property
    def production(self) -> Dict[str, int]:
        return {
            key: repetitions * self.layers
            for key, repetitions in self.repetitions.items()
        }

    @property
    def candidate_id(self) -> str:
        return self.marker_id

    @property
    def demand_compliance(self) -> float:
        return 1.0 if self.integrity_ok else 0.0

    @property
    def blocks(self) -> list:
        """
        Compatibilidad temporal con consumidores antiguos.

        El packing 2D ya no utiliza bloques por filas. La interfaz nueva debe
        visualizar `packing.placements` mediante `packing_figure()`.
        """
        return []


@dataclass
class MarkerPlan:
    plan_id: str
    markers: List[ProposedMarker]
    required_repetitions: Dict[str, int]
    layers: int
    total_length: float
    average_efficiency: float
    integrity_ok: bool
    coverage_ok: bool
    audit: List[dict] = field(default_factory=list)


class PlanGenerationError(ValueError):
    pass


def _clean_repetitions(repetitions: Dict[str, int]) -> Dict[str, int]:
    return {
        key: int(value)
        for key, value in repetitions.items()
        if int(value) > 0
    }


def _size_from_key(key: str) -> str:
    return key.split("|", 1)[1] if "|" in key else key


def _required_repetitions(
    requirements,
    layers: int,
    allow_overproduction: bool,
) -> Dict[str, int]:
    grouped = requirements.groupby(
        ["Modelo", "Talla"],
        as_index=False,
    )["Unidades"].sum()

    result: Dict[str, int] = {}
    for _, row in grouped.iterrows():
        units = int(row["Unidades"])
        raw_repetitions = units / layers

        if allow_overproduction:
            repetitions = math.ceil(raw_repetitions)
        else:
            repetitions = math.floor(raw_repetitions)

        if repetitions <= 0 and units > 0:
            repetitions = 1

        result[f"{row['Modelo']}|{row['Talla']}"] = int(repetitions)

    return result


def expand_rectangles(
    library,
    repetitions: Dict[str, int],
) -> List[RectItem]:
    """
    Expande cada repetición en piezas rectangulares individuales.

    `Ancho` representa la dimensión transversal sobre la tela.
    `Largo` representa la dimensión longitudinal del marcador.
    """
    items: List[RectItem] = []
    counters: Dict[str, int] = {}

    for _, row in library.iterrows():
        repetition_key = f"{row['Modelo']}|{row['Talla']}"
        repetitions_for_size = int(repetitions.get(repetition_key, 0))
        quantity_per_repetition = int(row["Cantidad"])
        total_instances = repetitions_for_size * quantity_per_repetition

        base = f"{repetition_key}|{row['Pieza']}"
        counters.setdefault(base, 0)

        for _ in range(total_instances):
            counters[base] += 1
            items.append(
                RectItem(
                    uid=f"{base}|{counters[base]}",
                    model=str(row["Modelo"]),
                    size=str(row["Talla"]),
                    piece=str(row["Pieza"]),
                    width=float(row["Ancho"]),
                    length=float(row["Largo"]),
                )
            )

    return items


def _expected_piece_counts(
    library,
    repetitions: Dict[str, int],
) -> Dict[Tuple[str, str, str], int]:
    expected: Dict[Tuple[str, str, str], int] = {}

    for _, row in library.iterrows():
        repetition_key = f"{row['Modelo']}|{row['Talla']}"
        repetitions_for_size = int(repetitions.get(repetition_key, 0))
        if repetitions_for_size <= 0:
            continue

        piece_key = (
            str(row["Modelo"]),
            str(row["Talla"]),
            str(row["Pieza"]),
        )
        expected[piece_key] = (
            repetitions_for_size * int(row["Cantidad"])
        )

    return expected


def _actual_piece_counts(
    packing: PackingResult,
) -> Dict[Tuple[str, str, str], int]:
    actual: Dict[Tuple[str, str, str], int] = {}

    for placement in packing.placements:
        item = placement.item
        key = (str(item.model), str(item.size), str(item.piece))
        actual[key] = actual.get(key, 0) + 1

    return actual


def _integrity_ok(
    library,
    repetitions: Dict[str, int],
    packing: PackingResult,
) -> bool:
    return _expected_piece_counts(
        library,
        repetitions,
    ) == _actual_piece_counts(packing)


def _evaluate_marker(
    library,
    repetitions: Dict[str, int],
    fabric_width: float,
    layers: int,
    random_iterations: int,
    max_marker_length: float,
    marker_id: str = "TEMP",
    packing_budget: int = 8,
    packing_cache: dict | None = None,
) -> ProposedMarker:
    repetitions = _clean_repetitions(repetitions)
    items = expand_rectangles(library, repetitions)

    if not items:
        raise PlanGenerationError(
            "El marcador propuesto no contiene piezas."
        )

    packing_key = (
        tuple(sorted(repetitions.items())),
        float(fabric_width),
        float(max_marker_length),
        int(random_iterations),
        int(packing_budget),
    )
    if packing_cache is not None and packing_key in packing_cache:
        packing = packing_cache[packing_key]
        if packing is None:
            raise PlanGenerationError("No existe un packing factible para esta combinación.")
    else:
        try:
            packing = pack_rectangles(
                items=items,
                fabric_width=float(fabric_width),
                max_length=float(max_marker_length),
                random_iterations=int(random_iterations),
                max_evaluations=int(packing_budget),
            )
        except ValueError as error:
            if packing_cache is not None:
                if len(packing_cache) >= 256:
                    packing_cache.pop(next(iter(packing_cache)))
                packing_cache[packing_key] = None
            raise PlanGenerationError(str(error)) from error
        if packing_cache is not None:
            if len(packing_cache) >= 256:
                packing_cache.pop(next(iter(packing_cache)))
            packing_cache[packing_key] = packing

    integrity = _integrity_ok(library, repetitions, packing)

    return ProposedMarker(
        marker_id=marker_id,
        repetitions=repetitions,
        packing=packing,
        strategy=packing.heuristic,
        layers=int(layers),
        estimated_length=float(packing.used_length),
        rectangular_efficiency=float(packing.efficiency),
        piece_count=len(items),
        distinct_sizes=len(repetitions),
        integrity_ok=integrity,
    )


def _candidate_priority(
    current: ProposedMarker | None,
    candidate: ProposedMarker,
    remaining_for_key: int,
    total_remaining: int,
    target_length: float,
) -> tuple:
    """
    Prioriza el crecimiento hacia el largo objetivo con buena eficiencia 2D.

    La prioridad considera simultáneamente:
    - Cercanía al largo objetivo.
    - Eficiencia rectangular 2D.
    - Incremento de largo.
    - Urgencia de la talla pendiente.
    - Cantidad de tallas diferentes.
    """
    previous_length = current.estimated_length if current else 0.0
    length_growth = candidate.estimated_length - previous_length

    if target_length > 0:
        target_gap = abs(target_length - candidate.estimated_length) / target_length
    else:
        target_gap = 0.0

    urgency = remaining_for_key / max(total_remaining, 1)

    return (
        target_gap,
        -candidate.rectangular_efficiency,
        length_growth,
        -urgency,
        candidate.distinct_sizes,
        candidate.piece_count,
    )


def generate_marker_plan(
    library,
    requirements,
    fabric_width: float,
    layers: int,
    max_marker_length: float,
    max_distinct_sizes: int,
    target_marker_length: float | None = None,
    max_markers: int = 20,
    random_iterations: int = 8,
    allow_overproduction: bool = True,
    packing_budget: int = 8,
    packing_cache: dict | None = None,
) -> MarkerPlan:
    """
    Genera un plan de marcadores mediante packing rectangular 2D.

    Reglas duras:
    - Cada marcador respeta `fabric_width`.
    - Cada marcador respeta `max_marker_length`.
    - Cada marcador contiene como máximo `max_distinct_sizes` tallas.
    - Cada repetición mantiene todas sus piezas en el mismo marcador.
    - Cada pieza se coloca exactamente una vez.
    - No se permite rotación automática.
    """
    if int(layers) <= 0:
        raise PlanGenerationError(
            "La cantidad de capas debe ser mayor que cero."
        )
    if float(fabric_width) <= 0:
        raise PlanGenerationError(
            "El ancho de tela debe ser mayor que cero."
        )
    if float(max_marker_length) <= 0:
        raise PlanGenerationError(
            "El largo máximo debe ser mayor que cero."
        )
    if int(max_distinct_sizes) <= 0:
        raise PlanGenerationError(
            "El máximo de tallas debe ser mayor que cero."
        )
    if int(max_markers) <= 0:
        raise PlanGenerationError(
            "El máximo de marcadores debe ser mayor que cero."
        )

    target_marker_length = float(
        target_marker_length or float(max_marker_length) * 0.90
    )
    target_marker_length = min(
        target_marker_length,
        float(max_marker_length),
    )

    required = _required_repetitions(
        requirements,
        int(layers),
        bool(allow_overproduction),
    )
    remaining = dict(required)
    marker_cache: Dict[tuple, ProposedMarker | None] = {}
    if packing_cache is None:
        packing_cache = {}
    markers: List[ProposedMarker] = []

    def evaluate(
        repetitions: Dict[str, int],
    ) -> ProposedMarker | None:
        cleaned = _clean_repetitions(repetitions)
        cache_key = tuple(sorted(cleaned.items()))

        if cache_key not in marker_cache:
            try:
                marker_cache[cache_key] = _evaluate_marker(
                    library=library,
                    repetitions=cleaned,
                    fabric_width=float(fabric_width),
                    layers=int(layers),
                    random_iterations=int(random_iterations),
                    max_marker_length=float(max_marker_length),
                    packing_budget=int(packing_budget),
                    packing_cache=packing_cache,
                )
            except PlanGenerationError:
                marker_cache[cache_key] = None

        return marker_cache[cache_key]

    while any(value > 0 for value in remaining.values()):
        if len(markers) >= int(max_markers):
            raise PlanGenerationError(
                "La demanda requiere más marcadores que el máximo permitido. "
                "Aumente el máximo de marcadores, el largo máximo o revise "
                "el rango de capas."
            )

        current_repetitions: Dict[str, int] = {}
        current_marker: ProposedMarker | None = None

        while True:
            feasible = []
            active_sizes = set(current_repetitions)
            total_remaining = sum(remaining.values())

            for key, balance in remaining.items():
                if balance <= 0:
                    continue

                if (
                    key not in active_sizes
                    and len(active_sizes) >= int(max_distinct_sizes)
                ):
                    continue

                proposal = dict(current_repetitions)
                proposal[key] = proposal.get(key, 0) + 1
                tested = evaluate(proposal)

                if tested is None:
                    continue
                if tested.estimated_length > float(max_marker_length) + 1e-9:
                    continue
                if tested.distinct_sizes > int(max_distinct_sizes):
                    continue
                if not tested.integrity_ok:
                    continue

                priority = _candidate_priority(
                    current=current_marker,
                    candidate=tested,
                    remaining_for_key=balance,
                    total_remaining=total_remaining,
                    target_length=target_marker_length,
                )
                feasible.append((priority, key, tested))

            if not feasible:
                break

            feasible.sort(key=lambda item: item[0])
            _, chosen_key, chosen_marker = feasible[0]

            current_repetitions = dict(chosen_marker.repetitions)
            current_marker = chosen_marker
            remaining[chosen_key] -= 1

            if current_marker.estimated_length >= target_marker_length:
                break

        if current_marker is None:
            pending = [
                key
                for key, value in remaining.items()
                if value > 0
            ]
            failing_key = pending[0] if pending else "desconocido"
            single = evaluate({failing_key: 1})

            if single is None:
                raise PlanGenerationError(
                    f"Una repetición de {failing_key} no puede acomodarse "
                    f"dentro de ancho {fabric_width:.2f} y largo máximo "
                    f"{max_marker_length:.2f}."
                )

            raise PlanGenerationError(
                f"No fue posible continuar con {failing_key}. "
                "Revise restricciones, capas y dimensiones."
            )

        # `evaluate()` cachea por ratio. No reutilizar el mismo objeto mutable
        # para dos tendidos: provocaba IDs duplicados en el reporte y al seleccionar.
        final_marker = replace(
            current_marker,
            marker_id=f"MK-{len(markers) + 1:03d}",
            repetitions=dict(current_marker.repetitions),
        )
        markers.append(final_marker)

    audit = []
    delivered = {key: 0 for key in required}

    for marker in markers:
        for key, repetitions in marker.repetitions.items():
            delivered[key] = (
                delivered.get(key, 0) + int(repetitions)
            )

    for key, required_reps in required.items():
        model, size = key.split("|", 1)
        delivered_reps = delivered.get(key, 0)
        units_required = int(
            requirements.loc[
                (
                    requirements["Modelo"].astype(str) == model
                )
                & (
                    requirements["Talla"].astype(str) == size
                ),
                "Unidades",
            ].sum()
        )
        units_produced = delivered_reps * int(layers)

        audit.append(
            {
                "Modelo": model,
                "Talla": size,
                "Repeticiones requeridas": required_reps,
                "Repeticiones planificadas": delivered_reps,
                "Unidades requeridas": units_required,
                "Unidades producidas": units_produced,
                "Faltante": max(0, units_required - units_produced),
                "Sobreproducción": max(0, units_produced - units_required),
                "Estado": (
                    "Completo"
                    if delivered_reps == required_reps
                    else "Revisar"
                ),
            }
        )

    total_length = sum(
        marker.estimated_length
        for marker in markers
    )
    total_marker_area = sum(
        float(fabric_width) * marker.estimated_length
        for marker in markers
    )
    total_piece_area = sum(
        marker.rectangular_efficiency
        * float(fabric_width)
        * marker.estimated_length
        for marker in markers
    )
    average_efficiency = (
        total_piece_area / total_marker_area
        if total_marker_area
        else 0.0
    )

    coverage_ok = all(
        row["Estado"] == "Completo"
        for row in audit
    )
    integrity_ok = all(
        marker.integrity_ok
        for marker in markers
    )

    return MarkerPlan(
        plan_id="PLAN-TEMP",
        markers=markers,
        required_repetitions=required,
        layers=int(layers),
        total_length=float(total_length),
        average_efficiency=float(average_efficiency),
        integrity_ok=integrity_ok,
        coverage_ok=coverage_ok,
        audit=audit,
    )


def marker_summary(plan: MarkerPlan) -> List[dict]:
    rows = []

    for marker in plan.markers:
        combination = ", ".join(
            f"{_size_from_key(key)} x {value}"
            for key, value in sorted(marker.repetitions.items())
        )

        rows.append(
            {
                "Marcador": marker.marker_id,
                "Combinación": combination,
                "Capas": marker.layers,
                "Tallas diferentes": marker.distinct_sizes,
                "Repeticiones": sum(marker.repetitions.values()),
                "Piezas": marker.piece_count,
                "Largo estimado": marker.estimated_length,
                "Eficiencia %": (
                    marker.rectangular_efficiency * 100
                ),
                "Integridad": (
                    "Completa"
                    if marker.integrity_ok
                    else "Inválida"
                ),
                "Método": marker.strategy,
            }
        )

    return rows
