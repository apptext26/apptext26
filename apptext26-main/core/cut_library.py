from __future__ import annotations

from typing import Any
import pandas as pd

from .cut_parser import DIMENSION_TOLERANCE, _dimensions_equivalent


def consolidate_cut_libraries(
    parsed_files: list[dict[str, Any]],
    tolerance: float = DIMENSION_TOLERANCE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Consolida CUT alternativos sin mezclar dimensiones ni sumar cantidades."""
    libraries = []
    inherited_conflicts = []
    for parsed in parsed_files:
        library = parsed.get("library", pd.DataFrame()).copy()
        if not library.empty:
            source = parsed.get("diagnostic", {}).get("Archivo", "")
            if "Origenes" not in library.columns:
                library["Origenes"] = source
            libraries.append(library)
        conflicts = parsed.get("conflicts", pd.DataFrame())
        if isinstance(conflicts, pd.DataFrame) and not conflicts.empty:
            inherited_conflicts.append(conflicts)

    if not libraries:
        return pd.DataFrame(), pd.concat(inherited_conflicts, ignore_index=True) if inherited_conflicts else pd.DataFrame()

    combined = pd.concat(libraries, ignore_index=True)
    rows = []
    conflicts = list(pd.concat(inherited_conflicts, ignore_index=True).to_dict("records")) if inherited_conflicts else []

    for (model, size, piece), group in combined.groupby(["Modelo", "Talla", "Pieza"], dropna=False, sort=True):
        representative = group.iloc[0].copy()
        dimensions = [(float(row.Ancho), float(row.Largo)) for row in group.itertuples() if pd.notna(row.Ancho) and pd.notna(row.Largo)]
        counts = sorted({int(value) for value in group["InstanciasCUT"].dropna()})
        origins = sorted({origin.strip() for cell in group["Origenes"].astype(str) for origin in cell.split(",") if origin.strip()})

        dimension_conflict = any(
            not _dimensions_equivalent(dimensions[0], pair, tolerance)
            for pair in dimensions[1:]
        ) if dimensions else True
        count_conflict = len(counts) > 1
        inherited = bool(group.get("ConflictoCritico", pd.Series(False, index=group.index)).astype(bool).any())
        critical = dimension_conflict or count_conflict or inherited

        representative["Origenes"] = ", ".join(origins)
        representative["ConflictoCritico"] = critical
        representative["DimensionStatus"] = "CONFLICTO" if critical else "OK"
        representative["Confianza"] = 0 if critical else int(group.get("Confianza", pd.Series([100])).min())
        # Se conserva un par real completo de la primera definición compatible.
        rows.append(representative.to_dict())

        if dimension_conflict:
            variants = sorted({f"{width:.4f} x {length:.4f}" for width, length in dimensions})
            conflicts.append({
                "Codigo": "MULTI_FILE_DIMENSION_CONFLICT",
                "Modelo": model, "Talla": size, "Pieza": piece,
                "Origenes": ", ".join(origins),
                "Detalle": "Dimensiones entre archivos: " + "; ".join(variants),
                "Critico": True,
            })
        if count_conflict:
            conflicts.append({
                "Codigo": "MULTI_FILE_COUNT_CONFLICT",
                "Modelo": model, "Talla": size, "Pieza": piece,
                "Origenes": ", ".join(origins),
                "Detalle": f"Conteos InstanciasCUT incompatibles: {counts}",
                "Critico": True,
            })

    return pd.DataFrame(rows), pd.DataFrame(conflicts).drop_duplicates()
