import pandas as pd

PIECE_COLUMNS = ["Modelo", "Talla", "Pieza", "Cantidad", "Ancho", "Largo"]
REQ_COLUMNS = ["Modelo", "Talla", "Unidades", "AnchoTela", "CapasMin", "CapasMax"]

def validate_inputs(pieces: pd.DataFrame, requirements: pd.DataFrame):
    errors, warnings = [], []
    missing_p = [c for c in PIECE_COLUMNS if c not in pieces.columns]
    missing_r = [c for c in REQ_COLUMNS if c not in requirements.columns]
    if missing_p:
        errors.append(f"Biblioteca: faltan columnas {missing_p}")
    if missing_r:
        errors.append(f"Requerimientos: faltan columnas {missing_r}")
    if errors:
        return errors, warnings

    for c in ["Cantidad", "Ancho", "Largo"]:
        if pd.to_numeric(pieces[c], errors="coerce").isna().any():
            errors.append(f"Biblioteca: {c} contiene valores no numéricos.")
        elif (pd.to_numeric(pieces[c]) <= 0).any():
            errors.append(f"Biblioteca: {c} debe ser mayor que cero.")
    for c in ["Unidades", "AnchoTela", "CapasMin", "CapasMax"]:
        if pd.to_numeric(requirements[c], errors="coerce").isna().any():
            errors.append(f"Requerimientos: {c} contiene valores no numéricos.")
    if errors:
        return errors, warnings
    if (requirements["CapasMin"] > requirements["CapasMax"]).any():
        errors.append("Hay filas con CapasMin mayor que CapasMax.")
    if requirements.duplicated(["Modelo", "Talla"]).any():
        warnings.append("Hay requerimientos duplicados por Modelo y Talla; serán sumados.")
    known = set(zip(pieces["Modelo"].astype(str), pieces["Talla"].astype(str)))
    for model, size in zip(requirements["Modelo"].astype(str), requirements["Talla"].astype(str)):
        if (model, size) not in known:
            errors.append(f"No hay piezas para {model} / {size}.")
    return errors, warnings
