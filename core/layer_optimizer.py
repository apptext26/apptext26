from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any


@dataclass
class LayerPlanAlternative:
    plan_id: str
    layers: int
    plan: Any
    marker_count: int
    total_length: float
    average_efficiency: float
    shortage: int
    overproduction: int
    score: float


def _production_deviation(plan) -> tuple[int, int]:
    shortage = 0
    overproduction = 0
    for row in plan.audit:
        required = int(row.get("Unidades requeridas", 0))
        produced = int(row.get("Unidades producidas", 0))
        shortage += max(0, required - produced)
        overproduction += max(0, produced - required)
    return shortage, overproduction


def evaluate_layer_range(
    plan_factory: Callable[..., Any],
    layers_min: int,
    layers_max: int,
    layer_step: int,
    top_k: int = 5,
    length_weight: float = 0.35,
    efficiency_weight: float = 0.30,
    marker_weight: float = 0.15,
    overproduction_weight: float = 0.20,
    **plan_kwargs,
) -> list[LayerPlanAlternative]:
    """Evalúa cada cantidad de capas y devuelve una lista corta no redundante."""
    if layers_min <= 0 or layers_max < layers_min or layer_step <= 0:
        raise ValueError("Rango de capas inválido.")

    raw = []
    for layers in range(int(layers_min), int(layers_max) + 1, int(layer_step)):
        try:
            plan = plan_factory(layers=layers, **plan_kwargs)
        except (ValueError, RuntimeError):
            continue
        shortage, overproduction = _production_deviation(plan)
        raw.append((layers, plan, shortage, overproduction))

    if not raw:
        raise ValueError("Ninguna cantidad de capas produjo un plan viable.")

    max_length = max(float(plan.total_length) for _, plan, _, _ in raw) or 1.0
    max_markers = max(len(plan.markers) for _, plan, _, _ in raw) or 1
    max_over = max(over for _, _, _, over in raw) or 1

    alternatives = []
    for layers, plan, shortage, overproduction in raw:
        length_score = 1.0 - float(plan.total_length) / max_length
        efficiency_score = float(plan.average_efficiency)
        marker_score = 1.0 - len(plan.markers) / max_markers
        over_score = 1.0 - overproduction / max_over
        score = 100 * (
            length_weight * length_score
            + efficiency_weight * efficiency_score
            + marker_weight * marker_score
            + overproduction_weight * over_score
        )
        # Los planes con faltante no se consideran recomendados.
        if shortage:
            score -= 1000 + shortage
        alternatives.append(LayerPlanAlternative(
            plan_id="",
            layers=layers,
            plan=plan,
            marker_count=len(plan.markers),
            total_length=float(plan.total_length),
            average_efficiency=float(plan.average_efficiency),
            shortage=shortage,
            overproduction=overproduction,
            score=score,
        ))

    alternatives.sort(key=lambda item: (-item.score, item.shortage, item.total_length, item.overproduction))
    selected = alternatives[: max(1, int(top_k))]
    for index, alternative in enumerate(selected, 1):
        alternative.plan_id = f"PLAN-{index:03d}"
    return selected
