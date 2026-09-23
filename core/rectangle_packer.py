from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import random


@dataclass(frozen=True)
class RectItem:
    uid: str
    model: str
    size: str
    piece: str
    width: float
    length: float

    @property
    def area(self) -> float:
        return self.width * self.length


@dataclass(frozen=True)
class FreeRect:
    x: float
    y: float
    width: float
    length: float


@dataclass(frozen=True)
class Placement:
    item: RectItem
    x: float
    y: float
    width: float
    length: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def top(self) -> float:
        return self.y + self.length


@dataclass
class PackingResult:
    placements: list[Placement]
    fabric_width: float
    used_length: float
    efficiency: float
    heuristic: str
    free_rectangles: list[FreeRect]

    @property
    def piece_count(self) -> int:
        return len(self.placements)


def _intersects(a: FreeRect, p: Placement, eps: float = 1e-9) -> bool:
    return not (
        p.right <= a.x + eps
        or p.x >= a.x + a.width - eps
        or p.top <= a.y + eps
        or p.y >= a.y + a.length - eps
    )


def _contains(a: FreeRect, b: FreeRect, eps: float = 1e-9) -> bool:
    return (
        b.x >= a.x - eps
        and b.y >= a.y - eps
        and b.x + b.width <= a.x + a.width + eps
        and b.y + b.length <= a.y + a.length + eps
    )


def _split_free_rect(free: FreeRect, placed: Placement) -> list[FreeRect]:
    if not _intersects(free, placed):
        return [free]

    output: list[FreeRect] = []
    free_right = free.x + free.width
    free_top = free.y + free.length

    if placed.x > free.x:
        output.append(FreeRect(free.x, free.y, placed.x - free.x, free.length))
    if placed.right < free_right:
        output.append(FreeRect(placed.right, free.y, free_right - placed.right, free.length))
    if placed.y > free.y:
        output.append(FreeRect(free.x, free.y, free.width, placed.y - free.y))
    if placed.top < free_top:
        output.append(FreeRect(free.x, placed.top, free.width, free_top - placed.top))

    return [rect for rect in output if rect.width > 1e-8 and rect.length > 1e-8]


def _prune_free_rectangles(rectangles: list[FreeRect]) -> list[FreeRect]:
    unique: list[FreeRect] = []
    for rect in rectangles:
        if any(_contains(other, rect) for other in rectangles if other is not rect):
            continue
        if not any(
            abs(rect.x - saved.x) < 1e-8
            and abs(rect.y - saved.y) < 1e-8
            and abs(rect.width - saved.width) < 1e-8
            and abs(rect.length - saved.length) < 1e-8
            for saved in unique
        ):
            unique.append(rect)
    return unique


def _score(free: FreeRect, item: RectItem, heuristic: str, current_length: float) -> tuple:
    leftover_w = free.width - item.width
    leftover_l = free.length - item.length
    short_side = min(leftover_w, leftover_l)
    long_side = max(leftover_w, leftover_l)
    area_waste = free.width * free.length - item.area
    resulting_length = max(current_length, free.y + item.length)
    length_growth = resulting_length - current_length

    if heuristic == "best_short_side":
        return short_side, long_side, length_growth, free.y, free.x
    if heuristic == "best_long_side":
        return long_side, short_side, length_growth, free.y, free.x
    if heuristic == "best_area":
        return area_waste, length_growth, short_side, free.y, free.x
    if heuristic == "bottom_left":
        return free.y + item.length, free.x, area_waste, short_side
    if heuristic == "length_aware":
        return length_growth, area_waste, short_side, free.y, free.x
    raise ValueError(f"Heurística desconocida: {heuristic}")


def _pack_order(
    items: list[RectItem],
    fabric_width: float,
    max_length: float,
    heuristic: str,
) -> PackingResult | None:
    free_rectangles = [FreeRect(0.0, 0.0, fabric_width, max_length)]
    placements: list[Placement] = []
    used_length = 0.0

    for item in items:
        feasible = []
        for free in free_rectangles:
            if item.width <= free.width + 1e-9 and item.length <= free.length + 1e-9:
                feasible.append((_score(free, item, heuristic, used_length), free))
        if not feasible:
            return None

        _, chosen = min(feasible, key=lambda pair: pair[0])
        placed = Placement(item, chosen.x, chosen.y, item.width, item.length)
        placements.append(placed)
        used_length = max(used_length, placed.top)

        split: list[FreeRect] = []
        for free in free_rectangles:
            split.extend(_split_free_rect(free, placed))
        free_rectangles = _prune_free_rectangles(split)

    total_area = sum(item.area for item in items)
    efficiency = total_area / (fabric_width * used_length) if used_length else 0.0
    return PackingResult(
        placements=placements,
        fabric_width=fabric_width,
        used_length=used_length,
        efficiency=efficiency,
        heuristic=heuristic,
        free_rectangles=free_rectangles,
    )


def pack_rectangles(
    items: Iterable[RectItem],
    fabric_width: float,
    max_length: float,
    random_iterations: int = 12,
    seed: int = 42,
) -> PackingResult:
    """MaxRects multiheurístico para strip packing rectangular sin rotación."""
    items = list(items)
    if not items:
        raise ValueError("No hay piezas para acomodar.")
    if fabric_width <= 0 or max_length <= 0:
        raise ValueError("Ancho y largo máximo deben ser mayores que cero.")
    too_wide = [item.uid for item in items if item.width > fabric_width + 1e-9]
    if too_wide:
        raise ValueError(f"Piezas más anchas que la tela: {too_wide[:5]}")

    orders = [
        ("area_desc", sorted(items, key=lambda p: (p.area, p.length, p.width), reverse=True)),
        ("length_desc", sorted(items, key=lambda p: (p.length, p.width), reverse=True)),
        ("width_desc", sorted(items, key=lambda p: (p.width, p.length), reverse=True)),
        ("max_side_desc", sorted(items, key=lambda p: (max(p.width, p.length), p.area), reverse=True)),
    ]
    rng = random.Random(seed)
    for index in range(random_iterations):
        shuffled = list(items)
        rng.shuffle(shuffled)
        orders.append((f"random_{index + 1}", shuffled))

    heuristics = ["best_short_side", "best_long_side", "best_area", "bottom_left", "length_aware"]
    candidates: list[PackingResult] = []
    for order_name, order in orders:
        for heuristic in heuristics:
            result = _pack_order(order, fabric_width, max_length, heuristic)
            if result is not None:
                result.heuristic = f"maxrects_{heuristic}_{order_name}"
                candidates.append(result)

    if not candidates:
        raise ValueError("No se encontró una acomodación rectangular dentro de los límites.")
    return min(candidates, key=lambda result: (result.used_length, -result.efficiency))


def validate_no_overlap(result: PackingResult, eps: float = 1e-8) -> bool:
    for index, first in enumerate(result.placements):
        if first.x < -eps or first.y < -eps or first.right > result.fabric_width + eps:
            return False
        for second in result.placements[index + 1:]:
            overlap = not (
                first.right <= second.x + eps
                or second.right <= first.x + eps
                or first.top <= second.y + eps
                or second.top <= first.y + eps
            )
            if overlap:
                return False
    return True
