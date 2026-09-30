"""Pruebas de PATCH-003 sin dependencia de Streamlit."""
import io
import json
from zipfile import ZipFile

import pandas as pd

from core.layer_optimizer import LayerPlanAlternative, evaluate_layer_range, fabric_consumption
from core.mixed_layer_optimizer import generate_mixed_alternatives, production
from core.packing_visualization import packing_figure
from core.plan_optimizer import MarkerPlan, ProposedMarker
from core.rectangle_packer import PackingResult, Placement, RectItem
from exports.diagnostics import build_diagnostic_zip


def make_fixture():
    item = RectItem(uid="A-M-1", model="AA", size="M", piece="FT", width=20, length=40)
    placement = Placement(item, 0, 0, 20, 40)
    packing = PackingResult([placement], 60, 40, 1 / 3, "fixture", [])
    markers = [
        ProposedMarker("MK-001", {"AA|M": 1}, packing, "fixture", 100, 40., .9, 1, 1),
        ProposedMarker("MK-002", {"AA|M": 1}, packing, "fixture", 100, 70., .7, 1, 1),
    ]
    audit = [{"Modelo": "AA", "Talla": "M", "Unidades requeridas": 150,
              "Unidades producidas": 200, "Faltante": 0,
              "Sobreproducción": 50, "Estado": "Completo"}]
    base_plan = MarkerPlan("UNI-001", markers, {"AA|M": 2}, 100, 110., .8, True, True, audit)
    alt = LayerPlanAlternative("UNI-001", 100, base_plan, 2, 110., .8, 0, 50, 0,
                               consumption=fabric_consumption(base_plan))
    lib = pd.DataFrame([{"Modelo": "AA", "Talla": "M", "Pieza": "FT",
                         "Cantidad": 1, "Ancho": 20, "Largo": 40}])
    req = pd.DataFrame([{"Modelo": "AA", "Talla": "M", "Unidades": 150}])
    return alt, lib, req


def test_mixed_adjusts_layers_without_shortage_and_saves_fabric():
    alt, lib, req = make_fixture()
    mixed, trace = generate_mixed_alternatives(
        [alt], plan_factory=lambda **kwargs: None, library=lib, requirements=req,
        layers_min=40, layers_max=100, layer_step=10, max_markers=5,
        allow_overproduction=True, max_residual_trials=0,
    )
    assert mixed
    choice = mixed[0]
    assert choice.mixed
    assert choice.shortage == 0
    assert choice.consumption < alt.consumption
    assert set(m.layers for m in choice.plan.markers) == {50, 100}
    assert production(choice.plan.markers)["AA|M"] == 150
    assert choice.plan.audit[0]["Faltante"] == 0
    assert trace[-1]["Pruebas residuales"] == 0


def test_no_fictitious_material_saving_when_demand_requires_both_markers_full():
    alt, lib, req = make_fixture()
    req.loc[0, "Unidades"] = 200
    mixed, _ = generate_mixed_alternatives(
        [alt], plan_factory=lambda **kwargs: None, library=lib, requirements=req,
        layers_min=40, layers_max=100, layer_step=10, max_markers=5,
        allow_overproduction=True, max_residual_trials=0,
    )
    assert not mixed


def test_uniform_ranking_uses_length_times_layers_not_sum_of_marker_lengths():
    alt, _, _ = make_fixture()
    def factory(layers, **_):
        from dataclasses import replace
        # 50 capas: 150 de largo -> 7,500; 100 capas: 100 -> 10,000.
        length = 150 if layers == 50 else 100
        marker = replace(alt.plan.markers[0], layers=layers, estimated_length=length)
        return MarkerPlan("TEMP", [marker], {}, layers, length, .8, True, True,
                          [{"Faltante": 0, "Sobreproducción": 0}])
    results = evaluate_layer_range(factory, 50, 100, 50, top_k=2)
    assert [r.layers for r in results] == [50, 100]
    assert [r.consumption for r in results] == [7500, 10000]


def test_horizontal_plot_swaps_coordinates_only_in_display():
    alt, _, _ = make_fixture()
    pack = alt.plan.markers[0].packing
    fig = packing_figure(pack)
    assert fig.layout.xaxis.title.text.startswith("Largo")
    assert fig.layout.yaxis.title.text.startswith("Ancho")
    assert list(fig.data[0].x) == [0, 40, 40, 0, 0]
    assert list(fig.data[0].y) == [0, 0, 20, 20, 0]
    assert pack.placements[0].width == 20  # Sin rotar datos internos.


def test_diagnostic_zip_contains_inputs_plan_details_and_feedback_template():
    alt, lib, req = make_fixture()
    content = build_diagnostic_zip(lib, req, [alt], {"fabric_width": 60}, [{"Fase": "test"}])
    with ZipFile(io.BytesIO(content)) as z:
        expected = {"LEEME.txt", "parametros_y_traza.json", "resumen_planes.csv",
                    "marcadores.csv", "cobertura.csv", "colocaciones.csv",
                    "biblioteca.csv", "requerimientos.csv", "resultados_accunest_plantilla.csv"}
        assert expected.issubset(set(z.namelist()))
        manifest = json.loads(z.read("parametros_y_traza.json"))
        assert manifest["schema"] == "minerva-diagnostics-1.0"
        assert manifest["placements_exported"] == 2
        assert manifest["settings"]["fabric_width"] == 60
        csv_text = z.read("resumen_planes.csv").decode("utf-8-sig")
        assert "11000" in csv_text
        assert "Unidades" in z.read("requerimientos.csv").decode("utf-8-sig")


def test_repeated_identical_markers_keep_independent_ids():
    from core.plan_optimizer import generate_marker_plan
    lib = pd.DataFrame([{"Modelo": "AA", "Talla": "M", "Pieza": "FT",
                         "Cantidad": 1, "Ancho": 22.0, "Largo": 31.0}])
    req = pd.DataFrame([{"Modelo": "AA", "Talla": "M", "Unidades": 500}])
    plan = generate_marker_plan(
        lib, req, fabric_width=40, layers=100,
        max_marker_length=33, max_distinct_sizes=1, max_markers=10,
        target_marker_length=31, random_iterations=0, packing_budget=4,
    )
    assert len(plan.markers) == 5
    assert len(set(m.marker_id for m in plan.markers)) == 5
    assert plan.audit[0]["Unidades producidas"] == 500


def test_uniform_diagnostics_record_runtime_and_rejected_scenarios():
    from core.layer_optimizer import sample_layers
    values = sample_layers(40, 100, 1, 7)
    assert values[0] == 40 and values[-1] == 100 and len(values) == 7
    trace = []
    def fake_factory(layers, **_):
        if layers == 100:
            raise ValueError("Restricción de largo")
        plan = make_fixture()[0].plan
        return plan
    alternatives = evaluate_layer_range(fake_factory, 90, 100, 10,
                                        top_k=2, diagnostics=trace)
    assert len(alternatives) == 1
    assert [r["Estado"] for r in trace] == ["viable", "inviable"]
    assert all(r["Segundos"] >= 0 for r in trace)


def test_integrated_mixed_plan_can_save_material_and_preserve_geometry():
    """Caso sintético, no evidencia sobre CUT reales ni garantía de óptimo."""
    from core.plan_optimizer import generate_marker_plan
    from core.rectangle_packer import validate_no_overlap
    pieces = pd.DataFrame([
        {"Modelo": "AA", "Talla": size, "Pieza": piece,
         "Cantidad": count, "Ancho": width * scale, "Largo": length * scale}
        for size, scale in [("S", .91), ("M", 1.), ("L", 1.07), ("XL", 1.13)]
        for piece, count, width, length in [("BK", 1, 22, 29),
                                            ("FT", 1, 21, 32),
                                            ("SL", 2, 13, 23)]
    ])
    demand = pd.DataFrame([
        {"Modelo": "AA", "Talla": size, "Unidades": units}
        for size, units in [("S", 1010), ("M", 1420), ("L", 1289), ("XL", 750)]
    ])
    config = dict(library=pieces, requirements=demand, fabric_width=72.,
                  max_marker_length=410., max_distinct_sizes=4,
                  target_marker_length=380., max_markers=20,
                  random_iterations=0, packing_budget=4, packing_cache={})
    uniform = evaluate_layer_range(generate_marker_plan, 40, 100, 10,
                                   top_k=7, max_layer_trials=7, **config)
    mixed, _ = generate_mixed_alternatives(
        uniform, generate_marker_plan, pieces, demand,
        40, 100, 10, 20, True, max_residual_trials=4,
        **{key: val for key, val in config.items()
           if key not in ("library", "requirements", "max_markers")},
    )
    assert mixed
    assert mixed[0].consumption < min(a.consumption for a in uniform if not a.shortage)
    for marker in mixed[0].plan.markers:
        assert validate_no_overlap(marker.packing)
        assert marker.layers in range(40, 101, 10)
        assert marker.estimated_length <= 410 + 1e-9
    assert mixed[0].shortage == 0
    assert mixed[0].plan.integrity_ok
