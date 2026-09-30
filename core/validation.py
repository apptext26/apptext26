"""Validación de datos de entrada y una estimación rápida de factibilidad.

`validate` bloquea el cálculo si faltan columnas o hay datos imposibles
(anchos/largos <= 0, tallas requeridas que no existen en la biblioteca).

`estimate_feasibility` es distinta: NO bloquea nada. Da una señal temprana,
antes de correr el packing 2D completo (que puede tardar), de si el volumen
de la demanda luce incompatible con los parámetros configurados. Es una
estimación optimista (asume una eficiencia de empaque razonable y reparto
perfecto entre marcadores), así que solo advierte cuando el faltante
proyectado es grande. La búsqueda real (`core.adaptive_planner`) es siempre
la que decide de verdad.
"""
from __future__ import annotations

from typing import Any

REQUIRED_LIBRARY_COLUMNS = ["Modelo", "Talla", "Pieza", "Cantidad", "Ancho", "Largo"]
REQUIRED_REQUIREMENT_COLUMNS = ["Modelo", "Talla", "Unidades"]

# Margen de empaque asumido para la estimación rápida (no es la eficiencia
# real del packing 2D, que depende de la geometría de cada pieza).
_ASSUMED_PACKING_EFFICIENCY = 0.85


def validate(library: Any, requirements: Any) -> list[str]:
    """Verifica columnas, valores mínimos y correspondencia entre tablas."""
    errors: list[str] = []

    for column in REQUIRED_LIBRARY_COLUMNS:
        if column not in library:
            errors.append(f"Falta la columna '{column}' en la biblioteca de piezas.")
    for column in REQUIRED_REQUIREMENT_COLUMNS:
        if column not in requirements:
            errors.append(f"Falta la columna '{column}' en los requerimientos.")
    if errors:
        # Sin las columnas base no tiene sentido validar el contenido.
        return errors

    if library.empty:
        errors.append("La biblioteca de piezas está vacía.")
    if requirements.empty:
        errors.append("La tabla de requerimientos está vacía.")
    if errors:
        return errors

    for column in ["Cantidad", "Ancho", "Largo"]:
        try:
            invalid = (library[column].astype(float) <= 0).any()
        except (TypeError, ValueError):
            errors.append(f"La columna '{column}' de la biblioteca tiene valores no numéricos.")
            continue
        if invalid:
            errors.append(f"Hay valores en '{column}' de la biblioteca que no son mayores que cero.")

    try:
        if (requirements["Unidades"].astype(float) < 0).any():
            errors.append("Hay unidades negativas en los requerimientos.")
    except (TypeError, ValueError):
        errors.append("La columna 'Unidades' de los requerimientos tiene valores no numéricos.")

    if errors:
        return errors

    library_keys = {
        (str(row["Modelo"]), str(row["Talla"]))
        for _, row in library.iterrows()
    }
    missing = sorted({
        f"{row['Modelo']}|{row['Talla']}"
        for _, row in requirements.iterrows()
        if float(row["Unidades"]) > 0
        and (str(row["Modelo"]), str(row["Talla"])) not in library_keys
    })
    if missing:
        shown = ", ".join(missing[:8]) + ("…" if len(missing) > 8 else "")
        errors.append(
            "Estas combinaciones de requerimientos no existen en la biblioteca de piezas: "
            f"{shown}."
        )

    return errors


def estimate_feasibility(
    library: Any,
    requirements: Any,
    fabric_width: float,
    max_marker_length: float,
    layers_max: int,
    max_markers: int,
) -> list[str]:
    """Avisos no bloqueantes sobre factibilidad, calculados antes del packing 2D."""
    warnings: list[str] = []

    for column in REQUIRED_LIBRARY_COLUMNS:
        if column not in library:
            return warnings
    for column in REQUIRED_REQUIREMENT_COLUMNS:
        if column not in requirements:
            return warnings
    if library.empty or requirements.empty:
        return warnings

    too_wide = library[library["Ancho"].astype(float) > float(fabric_width) + 1e-9]
    if not too_wide.empty:
        examples = ", ".join(
            f"{row['Modelo']}|{row['Talla']}|{row['Pieza']}"
            for _, row in too_wide.head(5).iterrows()
        )
        warnings.append(
            f"Hay piezas más anchas que el ancho de tela configurado ({float(fabric_width):.2f}): "
            f"{examples}. Ningún plan podrá acomodarlas mientras esto no se corrija — "
            "esta es una restricción física, no una preferencia."
        )

    area_per_repetition: dict[tuple[str, str], float] = {}
    for _, row in library.iterrows():
        key = (str(row["Modelo"]), str(row["Talla"]))
        area_per_repetition[key] = area_per_repetition.get(key, 0.0) + (
            float(row["Cantidad"]) * float(row["Ancho"]) * float(row["Largo"])
        )
    if not area_per_repetition:
        return warnings

    marker_capacity = float(fabric_width) * float(max_marker_length) * _ASSUMED_PACKING_EFFICIENCY
    if marker_capacity <= 0 or int(layers_max) <= 0:
        return warnings

    grouped = requirements.groupby(["Modelo", "Talla"], as_index=False)["Unidades"].sum()
    total_repetitions_at_max_layers = 0.0
    for _, row in grouped.iterrows():
        key = (str(row["Modelo"]), str(row["Talla"]))
        units = float(row["Unidades"])
        if units <= 0 or key not in area_per_repetition:
            continue
        total_repetitions_at_max_layers += units / float(layers_max)

    if total_repetitions_at_max_layers <= 0:
        return warnings

    avg_area = sum(area_per_repetition.values()) / len(area_per_repetition)
    estimated_markers = (total_repetitions_at_max_layers * avg_area) / marker_capacity

    if estimated_markers > float(max_markers) * 1.15:
        warnings.append(
            f"Con {int(layers_max)} capas (el máximo configurado) se estiman de forma "
            f"optimista ~{estimated_markers:.0f} marcadores necesarios para cubrir toda "
            f"la demanda, por encima del máximo permitido ({int(max_markers)}). Considere "
            "subir 'Capas máximas' o 'Máximo de marcadores del plan', o deje que la app "
            "relaje estos límites automáticamente al calcular."
        )

    return warnings
