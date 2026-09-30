import pandas as pd

from core.cut_library import consolidate_cut_libraries


def parsed(source, width=10.0, length=30.0, count=2):
    library = pd.DataFrame([{
        "Modelo": "M1", "Talla": "L", "Pieza": "FT",
        "InstanciasCUT": count, "RepeticionesTalla": 1, "Cantidad": count,
        "Ancho": width, "Largo": length, "Unidad": "IN", "Confianza": 100,
        "Origenes": source, "IDRepresentante": 1,
        "DimensionStatus": "OK", "ConflictoCritico": False,
    }])
    return {"diagnostic": {"Archivo": source}, "library": library, "conflicts": pd.DataFrame()}


def test_compatible_files_do_not_duplicate_quantity():
    library, conflicts = consolidate_cut_libraries([parsed("a.cut"), parsed("b.cut")])
    assert conflicts.empty
    assert len(library) == 1
    assert library.loc[0, "InstanciasCUT"] == 2
    assert set(library.loc[0, "Origenes"].split(", ")) == {"a.cut", "b.cut"}


def test_incompatible_dimensions_report_sources_and_piece():
    library, conflicts = consolidate_cut_libraries([
        parsed("a.cut", 10, 30),
        parsed("b.cut", 30, 10),
    ])
    assert bool(library.loc[0, "ConflictoCritico"])
    assert not conflicts.empty
    conflict = conflicts.iloc[0]
    assert conflict["Modelo"] == "M1"
    assert conflict["Talla"] == "L"
    assert conflict["Pieza"] == "FT"
    assert "a.cut" in conflict["Origenes"] and "b.cut" in conflict["Origenes"]
    assert (library.loc[0, "Ancho"], library.loc[0, "Largo"]) != (30.0, 30.0)


def test_incompatible_counts_report_conflict_instead_of_maximum():
    library, conflicts = consolidate_cut_libraries([
        parsed("a.cut", count=2),
        parsed("b.cut", count=4),
    ])
    assert bool(library.loc[0, "ConflictoCritico"])
    assert "MULTI_FILE_COUNT_CONFLICT" in set(conflicts["Codigo"])
