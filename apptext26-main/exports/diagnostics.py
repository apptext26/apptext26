"""Paquete de diagnóstico reproducible y compatible con Excel (CSV UTF-8 BOM).

Se crea bajo demanda para evitar reconstruir miles de coordenadas en cada rerun.
NO exporta el ZIP completo del código ni los CUT originales; incluye la
biblioteca normalizada usada por el motor y las entradas de planificación.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from zipfile import ZIP_DEFLATED, ZipFile

from core.layer_optimizer import fabric_consumption, weighted_rectangular_efficiency


MAX_PLACEMENTS = 50000
REPORT_SCHEMA_VERSION = "minerva-diagnostics-1.0"


def _csv_bytes(rows: list[dict], fieldnames: list[str] | None = None) -> bytes:
    fields = fieldnames or list(dict.fromkeys(key for row in rows for key in row))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        # Evita interpretación de fórmulas de Excel en nombres CUT arbitrarios.
        safe = {key: ("'" + value if isinstance(value, str)
                      and value.startswith(("=", "+", "-", "@", "\t", "\r"))
                      else value) for key, value in row.items()}
        writer.writerow(safe)
    return output.getvalue().encode("utf-8-sig")


def build_diagnostic_zip(library, requirements, alternatives,
                         settings: dict, trace: list[dict] | None = None,
                         max_placements: int = MAX_PLACEMENTS) -> bytes:
    plan_rows = []
    marker_rows = []
    coverage_rows = []
    placement_rows = []
    feedback_rows = []
    placements_truncated = False
    for alt in alternatives:
        plan = alt.plan
        plan_rows.append({
            "Plan": alt.plan_id, "Tipo": "Mixto" if alt.mixed else "Uniforme",
            "Origen": alt.origin, "Marcadores": len(plan.markers),
            "Capas mín": min(m.layers for m in plan.markers),
            "Capas máx": max(m.layers for m in plan.markers),
            "Suma largos markers": round(plan.total_length, 5),
            "Consumo lineal estimado": round(fabric_consumption(plan), 5),
            "Eficiencia rectangular ponderada %": round(weighted_rectangular_efficiency(plan) * 100, 3),
            "Faltante": alt.shortage, "Sobreproducción": alt.overproduction,
            "Integridad OK": plan.integrity_ok, "Cobertura OK": plan.coverage_ok,
        })
        for marker in plan.markers:
            marker_rows.append({
                "Plan": alt.plan_id, "Marker": marker.marker_id,
                "Capas": marker.layers, "Ratio": "; ".join(f"{k}:{v}" for k, v in sorted(marker.repetitions.items())),
                "Piezas": marker.piece_count, "Tallas": marker.distinct_sizes,
                "Largo 2D": round(marker.estimated_length, 5),
                "Consumo lineal": round(marker.layers * marker.estimated_length, 5),
                "Eficiencia rectangular %": round(marker.rectangular_efficiency * 100, 3),
                "Método": marker.strategy, "Integridad": marker.integrity_ok,
            })
            feedback_rows.append({
                "Plan": alt.plan_id, "Marker": marker.marker_id,
                "Ancho tela": marker.packing.fabric_width,
                "Capas": marker.layers, "Largo estimado": marker.estimated_length,
                "Eficiencia 2D estimada %": round(marker.rectangular_efficiency * 100, 3),
                "Largo REAL AccuNest": "", "Eficiencia REAL AccuNest %": "",
                "Fecha de prueba": "", "Comentarios": "",
            })
            for place in marker.packing.placements:
                if len(placement_rows) >= max_placements:
                    placements_truncated = True
                    break
                item = place.item
                placement_rows.append({
                    "Plan": alt.plan_id, "Marker": marker.marker_id,
                    "ID pieza": item.uid, "Modelo": item.model,
                    "Talla": item.size, "Pieza": item.piece,
                    "X transversal": place.x, "Y longitudinal": place.y,
                    "Ancho": place.width, "Largo": place.length,
                    "X final": place.right, "Y final": place.top,
                })
        for audit_row in plan.audit:
            coverage_rows.append({"Plan": alt.plan_id, **audit_row})
    raw_library = _csv_bytes(library.to_dict(orient="records"), list(library.columns))
    raw_demand = _csv_bytes(requirements.to_dict(orient="records"), list(requirements.columns))
    manifest = {
        "schema": REPORT_SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "library_sha256": hashlib.sha256(raw_library).hexdigest(),
        "demand_sha256": hashlib.sha256(raw_demand).hexdigest(),
        "settings": settings,
        "plans": len(alternatives),
        "placements_exported": len(placement_rows),
        "placements_truncated": placements_truncated,
        "warnings": [
            "La eficiencia es rectangular, no la eficiencia real de AccuNest.",
            "Unidades de longitud idénticas a las entradas, sin conversión automática.",
            "Consumo estimado = suma(largo marker × capas); no incluye extremos ni empalmes.",
            "La búsqueda de capas mixtas es heurística y no demuestra optimalidad global.",
        ],
        "trace": trace or [],
    }
    guide = (
        "MINERVA - Diagnóstico para analizar decisiones de corte\n"
        "1) parametros_y_traza.json: versión, inputs, tiempo y escenarios rechazados.\n"
        "2) resumen_planes.csv: compara consumo estimado y servicio al pedido.\n"
        "3) marcadores.csv: ratios y capas independientes de cada marker.\n"
        "4) cobertura.csv: unidades requeridas/producidas por talla.\n"
        "5) colocaciones.csv: posición de cada rectángulo (ejes internos X ancho, Y largo).\n"
        "6) biblioteca.csv y requerimientos.csv: entradas exactas de esta corrida.\n"
        "7) resultados_accunest_plantilla.csv: llene largo y eficiencia reales para calibración.\n"
        "No adjunte datos industriales confidenciales sin autorización.\n"
    )
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as out:
        out.writestr("LEEME.txt", guide.encode("utf-8-sig"))
        out.writestr("parametros_y_traza.json", json.dumps(manifest, ensure_ascii=False, indent=2, default=str))
        out.writestr("resumen_planes.csv", _csv_bytes(plan_rows))
        out.writestr("marcadores.csv", _csv_bytes(marker_rows))
        out.writestr("cobertura.csv", _csv_bytes(coverage_rows))
        out.writestr("colocaciones.csv", _csv_bytes(placement_rows))
        out.writestr("biblioteca.csv", raw_library)
        out.writestr("requerimientos.csv", raw_demand)
        out.writestr("resultados_accunest_plantilla.csv", _csv_bytes(feedback_rows))
    return buffer.getvalue()
