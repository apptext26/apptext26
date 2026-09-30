from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

DIMENSION_TOLERANCE = 0.02
REQUIRED_NORMALIZED_COLUMNS = [
    "Modelo", "Talla", "Pieza", "Cantidad", "Ancho", "Largo", "Unidad", "Confianza"
]


@dataclass
class LibraryIssue:
    code: str
    message: str
    row: int | None = None
    model: str | None = None
    size: str | None = None
    piece: str | None = None
    source: str | None = None
    critical: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "Codigo": self.code,
            "Mensaje": self.message,
            "Fila": self.row,
            "Modelo": self.model,
            "Talla": self.size,
            "Pieza": self.piece,
            "Origen": self.source,
            "Critico": self.critical,
        }


class LibraryNormalizationError(ValueError):
    """Error estructurado para normalización inválida de la biblioteca."""

    def __init__(self, issues: list[LibraryIssue]):
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame([issue.as_dict() for issue in self.issues])


def _decode(raw: bytes) -> str:
    return raw.decode("latin1", "ignore").replace("\r\n", "\n").replace("\r", "\n")


def _metadata_field(text: str, name: str) -> str | None:
    match = re.search(rf"^M,{re.escape(name)},([^,\n]*)", text, re.M | re.I)
    return match.group(1).strip() if match else None


def _dimensions_equivalent(a: tuple[float, float], b: tuple[float, float], tolerance: float) -> bool:
    return abs(a[0] - b[0]) <= tolerance and abs(a[1] - b[1]) <= tolerance


def _select_real_representative(group: pd.DataFrame, tolerance: float) -> tuple[pd.Series, bool, str]:
    """Selecciona una fila real. Nunca crea max(ancho) x max(largo)."""
    valid = group.dropna(subset=["Ancho", "Largo"]).copy()
    if valid.empty:
        return group.iloc[0], True, "No hay una instancia con ancho y largo válidos."

    valid["Ancho"] = pd.to_numeric(valid["Ancho"], errors="coerce")
    valid["Largo"] = pd.to_numeric(valid["Largo"], errors="coerce")
    valid = valid.dropna(subset=["Ancho", "Largo"])
    if valid.empty:
        return group.iloc[0], True, "Las dimensiones no son numéricas."

    pairs = list(zip(valid["Ancho"].astype(float), valid["Largo"].astype(float)))
    reference = pairs[0]
    conflict = any(not _dimensions_equivalent(reference, pair, tolerance) for pair in pairs[1:])

    # Representante conservador, pero siempre tomado de una misma instancia real.
    valid = valid.assign(_area=valid["Ancho"] * valid["Largo"])
    representative = valid.sort_values(["_area", "Ancho", "Largo"], ascending=False).iloc[0]
    detail = ""
    if conflict:
        variants = sorted({f"{width:.4f} x {length:.4f}" for width, length in pairs})
        detail = "Dimensiones discordantes: " + "; ".join(variants)
    return representative, conflict, detail


def build_library_from_instances(
    instances: pd.DataFrame,
    tolerance: float = DIMENSION_TOLERANCE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Construye biblioteca y conflictos conservando pares dimensionales reales."""
    columns = [
        "Modelo", "Talla", "Pieza", "InstanciasCUT", "RepeticionesTalla", "Cantidad",
        "Ancho", "Largo", "Unidad", "Confianza", "Origenes", "IDRepresentante",
        "DimensionStatus", "ConflictoCritico",
    ]
    if instances.empty:
        return pd.DataFrame(columns=columns), pd.DataFrame()

    rows: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    grouped = instances.groupby(["Modelo", "Talla", "Pieza"], dropna=False, sort=True)
    for (model, size, piece), group in grouped:
        representative, conflict, detail = _select_real_representative(group, tolerance)
        origins = sorted({str(value) for value in group.get("Archivo", pd.Series(dtype=str)).dropna()})
        status_values = set(group.get("Estado", pd.Series(["OK"])).astype(str))
        missing_geometry = "Sin geometría" in status_values or group[["Ancho", "Largo"]].isna().any().any()
        critical = bool(conflict or missing_geometry)

        rows.append({
            "Modelo": model,
            "Talla": size,
            "Pieza": piece,
            "InstanciasCUT": int(len(group)),
            "RepeticionesTalla": 1,
            "Cantidad": int(len(group)),
            "Ancho": round(float(representative["Ancho"]), 4) if pd.notna(representative.get("Ancho")) else None,
            "Largo": round(float(representative["Largo"]), 4) if pd.notna(representative.get("Largo")) else None,
            "Unidad": str(representative.get("Unidad", "IN")),
            "Confianza": 100 if not critical else 0,
            "Origenes": ", ".join(origins),
            "IDRepresentante": representative.get("ID"),
            "DimensionStatus": "CONFLICTO" if conflict else ("SIN_GEOMETRIA" if missing_geometry else "OK"),
            "ConflictoCritico": critical,
        })

        if critical:
            conflicts.append({
                "Codigo": "DIMENSION_CONFLICT" if conflict else "MISSING_GEOMETRY",
                "Modelo": model,
                "Talla": size,
                "Pieza": piece,
                "Origenes": ", ".join(origins),
                "Detalle": detail or "Falta geometría o dimensión válida.",
                "Critico": True,
            })

    return pd.DataFrame(rows, columns=columns), pd.DataFrame(conflicts)


def parse_cut(raw: bytes, name: str = "archivo") -> dict[str, Any]:
    text = _decode(raw)
    plot = text.split("\x0c", 1)[0]
    header = re.search(r"M20\*([^*]+?)/L=([0-9.]+)IN/W=([0-9.]+)IN", plot, re.I)
    marker = header.group(1).strip() if header else (_metadata_field(text, "Marker Name") or name)
    marker_length = float(header.group(2)) if header else None
    marker_width = float(header.group(3)) if header else None

    bounds = re.search(r"(?:^|\n)B,(\d+),(\d+)", text)
    scale = (int(bounds.group(2)) / marker_width) if bounds and marker_width else 100.0
    scale_valid = math.isfinite(scale) and scale > 0

    geometry: dict[int, dict[str, Any]] = {}
    starts = list(re.finditer(r"\*N(\d+)\*", plot))
    for index, match in enumerate(starts):
        segment = plot[match.end(): starts[index + 1].start() if index + 1 < len(starts) else len(plot)]
        parts = segment.split("*M15*")
        contour = parts[1] if len(parts) > 1 else segment
        points = [(int(x), int(y)) for x, y in re.findall(r"X(-?\d+)Y(-?\d+)", contour)]
        if points and scale_valid:
            xs = [x for x, _ in points]
            ys = [y for _, y in points]
            geometry_id = int(match.group(1))
            geometry[geometry_id] = {
                "points": points,
                "xmin": min(xs), "xmax": max(xs), "ymin": min(ys), "ymax": max(ys),
                # X = dirección longitudinal del marcador.
                # Y = dirección transversal, correspondiente al ancho de tela.
                "width": (max(ys) - min(ys)) / scale,
                "length": (max(xs) - min(xs)) / scale,
                "scale": scale,
                "source": name,
            }

    section = text[text.find("N,0001"):] if "N,0001" in text else text
    metadata_matches = list(re.finditer(r"(?:^|\n)L,(\d+)\s*\n", section))
    metadata: dict[int, dict[int, str]] = {}
    for index, match in enumerate(metadata_matches):
        block = section[match.end(): metadata_matches[index + 1].start() if index + 1 < len(metadata_matches) else len(section)]
        data = {int(key): value.strip() for key, value in re.findall(r"^D,(\d+),(.*)$", block, re.M)}
        if data:
            metadata[int(match.group(1))] = data

    instance_rows: list[dict[str, Any]] = []
    for geometry_id, data in sorted(metadata.items()):
        shape = geometry.get(geometry_id)
        size = (data.get(4) or "").replace("/R", "").strip()
        instance_rows.append({
            "Archivo": name,
            "ID": geometry_id,
            "Modelo": data.get(6) or "",
            "Talla": size,
            "Pieza": data.get(3) or "",
            "Lado": data.get(7) or "",
            "Orientacion": None,
            "Ancho": round(shape["width"], 4) if shape else None,
            "Largo": round(shape["length"], 4) if shape else None,
            "Unidad": "IN" if header else "DESCONOCIDA",
            "Puntos": len(shape["points"]) if shape else 0,
            "Estado": "OK" if shape else "Sin geometría",
        })

    instances = pd.DataFrame(instance_rows)
    library, conflicts = build_library_from_instances(instances)
    diagnostic = {
        "Archivo": name,
        "Marcador": marker,
        "Modelo": ", ".join(sorted(instances["Modelo"].dropna().unique())) if not instances.empty else "No detectado",
        "AnchoMarcador": marker_width,
        "LargoMarcador": marker_length,
        "Utilizacion": _metadata_field(text, "MARKER UTILTIZATION"),
        "Unidad": "IN" if header else "Desconocida",
        "Geometrias": len(geometry),
        "Metadatos": len(metadata),
        "Relacionados": sum(identifier in geometry for identifier in metadata),
        "Escala": scale if scale_valid else None,
        "ConflictosCriticos": int(len(conflicts)),
        "Estado": "Lectura completa" if geometry and len(geometry) == len(metadata) and conflicts.empty else "Revisar",
    }
    return {
        "diagnostic": diagnostic,
        "instances": instances,
        "library": library,
        "geometry": geometry,
        "conflicts": conflicts,
        "sha": hashlib.sha1(raw).hexdigest()[:12],
    }


def _integer_value(value: Any, label: str, row: int, identity: dict[str, str], positive: bool) -> tuple[int | None, LibraryIssue | None]:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number) or not float(number).is_integer():
        return None, LibraryIssue(
            code="INVALID_INTEGER",
            message=f"{label} debe ser un entero válido; se recibió {value!r}.",
            row=row, model=identity["Modelo"], size=identity["Talla"], piece=identity["Pieza"], source=identity["Origen"],
        )
    integer = int(number)
    if (positive and integer <= 0) or (not positive and integer < 0):
        rule = "mayor que cero" if positive else "no negativo"
        return None, LibraryIssue(
            code="INVALID_RANGE",
            message=f"{label} debe ser {rule}; se recibió {integer}.",
            row=row, model=identity["Modelo"], size=identity["Talla"], piece=identity["Pieza"], source=identity["Origen"],
        )
    return integer, None


def normalize_library(df: pd.DataFrame) -> pd.DataFrame:
    required = {"Modelo", "Talla", "Pieza", "InstanciasCUT", "RepeticionesTalla", "Ancho", "Largo"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise LibraryNormalizationError([LibraryIssue("MISSING_COLUMNS", f"Faltan columnas: {missing}")])

    output = df.copy()
    issues: list[LibraryIssue] = []
    quantities: list[int | None] = []

    for row_number, (_, row) in enumerate(output.iterrows(), start=1):
        identity = {
            "Modelo": str(row.get("Modelo", "")),
            "Talla": str(row.get("Talla", "")),
            "Pieza": str(row.get("Pieza", "")),
            "Origen": str(row.get("Origenes", row.get("Archivo", ""))),
        }
        instances, issue = _integer_value(row.get("InstanciasCUT"), "InstanciasCUT", row_number, identity, positive=False)
        if issue:
            issues.append(issue)
        repetitions, issue = _integer_value(row.get("RepeticionesTalla"), "RepeticionesTalla", row_number, identity, positive=True)
        if issue:
            issues.append(issue)

        width = pd.to_numeric(pd.Series([row.get("Ancho")]), errors="coerce").iloc[0]
        length = pd.to_numeric(pd.Series([row.get("Largo")]), errors="coerce").iloc[0]
        if pd.isna(width) or pd.isna(length) or float(width) <= 0 or float(length) <= 0:
            issues.append(LibraryIssue(
                "INVALID_DIMENSION", "Ancho y Largo deben ser numéricos y mayores que cero.",
                row_number, identity["Modelo"], identity["Talla"], identity["Pieza"], identity["Origen"],
            ))

        if bool(row.get("ConflictoCritico", False)):
            issues.append(LibraryIssue(
                "UNRESOLVED_CONFLICT", "La fila conserva un conflicto crítico sin resolver.",
                row_number, identity["Modelo"], identity["Talla"], identity["Pieza"], identity["Origen"],
            ))

        if instances is None or repetitions is None:
            quantities.append(None)
        elif instances % repetitions != 0:
            quantities.append(None)
            issues.append(LibraryIssue(
                "NON_EXACT_DIVISION",
                f"InstanciasCUT={instances} no es divisible exactamente entre RepeticionesTalla={repetitions}. Corrija las repeticiones.",
                row_number, identity["Modelo"], identity["Talla"], identity["Pieza"], identity["Origen"],
            ))
        else:
            quantities.append(instances // repetitions)

    if issues:
        raise LibraryNormalizationError(issues)

    output["Cantidad"] = quantities
    if "Unidad" not in output.columns:
        output["Unidad"] = "IN"
    if "Confianza" not in output.columns:
        output["Confianza"] = 100
    return output[REQUIRED_NORMALIZED_COLUMNS].copy()
