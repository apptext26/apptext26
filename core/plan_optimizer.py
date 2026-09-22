from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import math

from .optimizer import expand, distributions


@dataclass
class ProposedMarker:
    marker_id: str
    repetitions: Dict[str, int]
    blocks: list
    strategy: str
    layers: int
    estimated_length: float
    rectangular_efficiency: float
    piece_count: int
    distinct_sizes: int
    integrity_ok: bool = True

    @property
    def production(self) -> Dict[str, int]:
        return {key: repetitions * self.layers for key, repetitions in self.repetitions.items()}

    @property
    def candidate_id(self) -> str:
        # Compatibilidad con candidate_figure del visualizador existente.
        return self.marker_id

    @property
    def demand_compliance(self) -> float:
        return 1.0 if self.integrity_ok else 0.0


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
    return {key: int(value) for key, value in repetitions.items() if int(value) > 0}


def _size_from_key(key: str) -> str:
    return key.split("|", 1)[1] if "|" in key else key


def _required_repetitions(requirements, layers: int, allow_overproduction: bool) -> Dict[str, int]:
    grouped = requirements.groupby(["Modelo", "Talla"], as_index=False)["Unidades"].sum()
    result = {}
    for _, row in grouped.iterrows():
        units = int(row["Unidades"])
        raw = units / layers
        repetitions = math.ceil(raw) if allow_overproduction else math.floor(raw)
        if repetitions <= 0 and units > 0:
            repetitions = 1
        result[f"{row['Modelo']}|{row['Talla']}"] = int(repetitions)
    return result


def _expected_piece_counts(library, repetitions: Dict[str, int]) -> Dict[Tuple[str, str, str], int]:
    expected = {}
    for _, row in library.iterrows():
        key = f"{row['Modelo']}|{row['Talla']}"
        repetitions_for_size = int(repetitions.get(key, 0))
        if repetitions_for_size <= 0:
            continue
        piece_key = (str(row["Modelo"]), str(row["Talla"]), str(row["Pieza"]))
        expected[piece_key] = repetitions_for_size * int(row["Cantidad"])
    return expected


def _actual_piece_counts(blocks) -> Dict[Tuple[str, str, str], int]:
    actual = {}
    for block in blocks:
        for piece in block.pieces:
            key = (str(piece.model), str(piece.size), str(piece.piece))
            actual[key] = actual.get(key, 0) + 1
    return actual


def _integrity_ok(library, repetitions: Dict[str, int], blocks) -> bool:
    return _expected_piece_counts(library, repetitions) == _actual_piece_counts(blocks)


def _evaluate_marker(
    library,
    repetitions: Dict[str, int],
    fabric_width: float,
    layers: int,
    random_iterations: int,
    marker_id: str = "TEMP",
) -> ProposedMarker:
    repetitions = _clean_repetitions(repetitions)
    pieces = expand(library, repetitions)
    if not pieces:
        raise PlanGenerationError("El marcador propuesto no contiene piezas.")

    best = None
    for strategy, blocks in distributions(pieces, fabric_width, random_iterations):
        length = sum(float(block.length) for block in blocks)
        area = sum(float(piece.area) for piece in pieces)
        efficiency = area / (fabric_width * length) if length > 0 else 0.0
        score = (length, -efficiency, len(blocks))
        if best is None or score < best[0]:
            best = (score, strategy, blocks, length, efficiency)

    _, strategy, blocks, length, efficiency = best
    integrity = _integrity_ok(library, repetitions, blocks)
    return ProposedMarker(
        marker_id=marker_id,
        repetitions=repetitions,
        blocks=blocks,
        strategy=strategy,
        layers=int(layers),
        estimated_length=float(length),
        rectangular_efficiency=float(efficiency),
        piece_count=len(pieces),
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
    previous_length = current.estimated_length if current else 0.0
    delta_length = candidate.estimated_length - previous_length
    target_ratio = candidate.estimated_length / target_length if target_length > 0 else 0.0

    # Se prioriza: acercarse al largo objetivo sin excederlo, buena eficiencia,
    # menor crecimiento marginal y consumir tallas con mayor saldo.
    target_gap = abs(1.0 - min(target_ratio, 1.0))
    urgency = remaining_for_key / max(total_remaining, 1)
    return (
        target_gap,
        -candidate.rectangular_efficiency,
        delta_length,
        -urgency,
        candidate.distinct_sizes,
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
) -> MarkerPlan:
    """
    Divide la demanda en una lista pequeña de marcadores completos.

    Reglas duras por marcador:
    - Largo estimado <= max_marker_length.
    - Tallas diferentes <= max_distinct_sizes.
    - Cada repetición incluye todas sus piezas completas.
    - Cada pieza aparece exactamente una vez dentro del marcador.
    """
    if layers <= 0:
        raise PlanGenerationError("La cantidad de capas debe ser mayor que cero.")
    if max_marker_length <= 0:
        raise PlanGenerationError("El largo máximo debe ser mayor que cero.")
    if max_distinct_sizes <= 0:
        raise PlanGenerationError("El máximo de tallas debe ser mayor que cero.")

    target_marker_length = float(target_marker_length or max_marker_length * 0.90)
    target_marker_length = min(target_marker_length, float(max_marker_length))

    required = _required_repetitions(requirements, int(layers), allow_overproduction)
    remaining = dict(required)
    cache = {}
    markers = []

    def evaluate(repetitions):
        cleaned = _clean_repetitions(repetitions)
        cache_key = tuple(sorted(cleaned.items()))
        if cache_key not in cache:
            cache[cache_key] = _evaluate_marker(
                library,
                cleaned,
                float(fabric_width),
                int(layers),
                int(random_iterations),
            )
        return cache[cache_key]

    while any(value > 0 for value in remaining.values()):
        if len(markers) >= int(max_markers):
            raise PlanGenerationError(
                "La demanda requiere más marcadores que el máximo permitido. "
                "Aumente Max. marcadores o el largo máximo."
            )

        current_repetitions = {}
        current_marker = None

        while True:
            feasible = []
            active_sizes = set(current_repetitions)
            total_remaining = sum(remaining.values())

            for key, balance in remaining.items():
                if balance <= 0:
                    continue
                if key not in active_sizes and len(active_sizes) >= int(max_distinct_sizes):
                    continue

                proposal = dict(current_repetitions)
                proposal[key] = proposal.get(key, 0) + 1
                tested = evaluate(proposal)

                if tested.estimated_length > float(max_marker_length) + 1e-9:
                    continue
                if tested.distinct_sizes > int(max_distinct_sizes):
                    continue
                if not tested.integrity_ok:
                    continue

                priority = _candidate_priority(
                    current_marker,
                    tested,
                    balance,
                    total_remaining,
                    target_marker_length,
                )
                feasible.append((priority, key, tested))

            if not feasible:
                break

            feasible.sort(key=lambda item: item[0])
            _, chosen_key, chosen_marker = feasible[0]
            current_repetitions = dict(chosen_marker.repetitions)
            current_marker = chosen_marker
            remaining[chosen_key] -= 1

            # Cuando alcanza el objetivo se cierra el marcador. Esto evita un
            # único marcador enorme y mantiene una lista operativa compacta.
            if current_marker.estimated_length >= target_marker_length:
                break

        if current_marker is None:
            pending = [key for key, value in remaining.items() if value > 0]
            failing_key = pending[0] if pending else "desconocido"
            single = evaluate({failing_key: 1})
            raise PlanGenerationError(
                f"Una repetición de {failing_key} necesita aproximadamente "
                f"{single.estimated_length:.2f}, superior al límite de "
                f"{max_marker_length:.2f}."
            )

        current_marker.marker_id = f"MK-{len(markers) + 1:03d}"
        markers.append(current_marker)

    audit = []
    delivered = {key: 0 for key in required}
    for marker in markers:
        for key, repetitions in marker.repetitions.items():
            delivered[key] = delivered.get(key, 0) + int(repetitions)

    for key, required_reps in required.items():
        model, size = key.split("|", 1)
        delivered_reps = delivered.get(key, 0)
        audit.append(
            {
                "Modelo": model,
                "Talla": size,
                "Repeticiones requeridas": required_reps,
                "Repeticiones planificadas": delivered_reps,
                "Unidades requeridas": int(
                    requirements.loc[
                        (requirements["Modelo"].astype(str) == model)
                        & (requirements["Talla"].astype(str) == size),
                        "Unidades",
                    ].sum()
                ),
                "Unidades producidas": delivered_reps * int(layers),
                "Estado": "Completo" if delivered_reps == required_reps else "Revisar",
            }
        )

    total_length = sum(marker.estimated_length for marker in markers)
    total_marker_area = sum(fabric_width * marker.estimated_length for marker in markers)
    total_piece_area = sum(
        marker.rectangular_efficiency * fabric_width * marker.estimated_length
        for marker in markers
    )
    average_efficiency = total_piece_area / total_marker_area if total_marker_area else 0.0
    coverage_ok = all(row["Estado"] == "Completo" for row in audit)
    integrity_ok = all(marker.integrity_ok for marker in markers)

    return MarkerPlan(
        plan_id="PLAN-00001",
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
                "Tallas diferentes": marker.distinct_sizes,
                "Repeticiones": sum(marker.repetitions.values()),
                "Piezas": marker.piece_count,
                "Bloques": len(marker.blocks),
                "Largo estimado": marker.estimated_length,
                "Eficiencia %": marker.rectangular_efficiency * 100,
                "Integridad": "Completa" if marker.integrity_ok else "Inválida",
                "Estrategia": marker.strategy,
            }
        )
    return rows
