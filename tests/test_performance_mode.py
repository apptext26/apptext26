"""Regresión: preservar factibilidad al acelerar el pre-nesting 2D."""

import pandas as pd
import core.rectangle_packer as rectangle_packer
import core.plan_optimizer as plan_optimizer


def pieces(count=40):
    dims = [(23, 31), (28, 29), (14, 23), (8, 12)]
    return [
        rectangle_packer.RectItem(
            str(i), "MODEL", ("S", "M", "L", "XL")[i % 4],
            ("FT", "BK", "SL", "CL")[i % 4], *dims[i % 4],
        )
        for i in range(count)
    ]


def test_budgeted_packing_respects_geometry_and_length():
    result = rectangle_packer.pack_rectangles(
        pieces(40), fabric_width=72, max_length=600,
        random_iterations=8, max_evaluations=8,
    )
    assert len(result.placements) == 40
    assert rectangle_packer.validate_no_overlap(result)
    assert result.used_length <= 600
    assert 0 < result.efficiency <= 1


def test_budget_limits_feasible_search(monkeypatch):
    original = rectangle_packer._pack_order
    calls = []

    def instrumented(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(rectangle_packer, "_pack_order", instrumented)
    result = rectangle_packer.pack_rectangles(
        pieces(40), 72, 600, random_iterations=8, max_evaluations=4,
    )
    assert rectangle_packer.validate_no_overlap(result)
    assert 1 <= len(calls) <= 4


def test_budget_does_not_create_false_infeasibility(monkeypatch):
    original = rectangle_packer._pack_order
    calls = []

    def first_attempt_fails(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return None
        return original(*args, **kwargs)

    monkeypatch.setattr(rectangle_packer, "_pack_order", first_attempt_fails)
    result = rectangle_packer.pack_rectangles(
        pieces(20), 72, 600, random_iterations=0, max_evaluations=1,
    )
    assert rectangle_packer.validate_no_overlap(result)
    assert len(calls) > 1


def test_packing_is_reused_across_layer_counts(monkeypatch):
    library = pd.DataFrame([
        {"Modelo": "M1", "Talla": size, "Pieza": piece, "Cantidad": qty, "Ancho": w, "Largo": l}
        for size in ("S", "M")
        for piece, qty, w, l in (("FT", 1, 23, 31), ("BK", 1, 28, 29), ("SL", 2, 14, 23))
    ])
    req = pd.DataFrame([
        {"Modelo": "M1", "Talla": "S", "Unidades": 90},
        {"Modelo": "M1", "Talla": "M", "Unidades": 90},
    ])
    original = plan_optimizer.pack_rectangles
    calls = []

    def instrumented(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(plan_optimizer, "pack_rectangles", instrumented)
    shared = {}
    common = dict(
        library=library, requirements=req, fabric_width=72, max_marker_length=300,
        max_distinct_sizes=2, target_marker_length=150, max_markers=10,
        random_iterations=0, packing_budget=4, packing_cache=shared,
    )
    first = plan_optimizer.generate_marker_plan(layers=45, **common)
    calls_after_first = len(calls)
    second = plan_optimizer.generate_marker_plan(layers=46, **common)
    assert first.integrity_ok and second.integrity_ok
    assert first.coverage_ok and second.coverage_ok
    assert calls_after_first > 0
    assert len(calls) == calls_after_first
