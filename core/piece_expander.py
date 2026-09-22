import pandas as pd
from models import PieceInstance

def expand_pieces(library: pd.DataFrame, repetitions: dict):
    output = []
    counters = {}
    for _, row in library.iterrows():
        key = f"{row['Modelo']}|{row['Talla']}"
        reps = int(repetitions.get(key, 0))
        total = reps * int(row["Cantidad"])
        base = f"{row['Modelo']}-{row['Talla']}-{row['Pieza']}"
        counters.setdefault(base, 0)
        for _ in range(total):
            counters[base] += 1
            output.append(PieceInstance(
                uid=f"{base}-{counters[base]}", model=str(row["Modelo"]),
                size=str(row["Talla"]), piece=str(row["Pieza"]),
                width=float(row["Ancho"]), length=float(row["Largo"]),
                rotation_allowed=bool(row.get("RotacionPermitida", False))))
    return output
