import pandas as pd
import pytest

from core.cut_parser import (
    LibraryNormalizationError,
    build_library_from_instances,
    normalize_library,
)


def instance_rows(dimensions):
    return pd.DataFrame([
        {
            "Archivo": "fixture.cut", "ID": index + 1, "Modelo": "M1", "Talla": "L",
            "Pieza": "FT", "Lado": "L", "Orientacion": None,
            "Ancho": width, "Largo": length, "Unidad": "IN", "Puntos": 4, "Estado": "OK",
        }
        for index, (width, length) in enumerate(dimensions)
    ])


def editable_row(instances=4, repetitions=2, **overrides):
    row = {
        "Modelo": "M1", "Talla": "L", "Pieza": "FT",
        "InstanciasCUT": instances, "RepeticionesTalla": repetitions,
        "Ancho": 10.0, "Largo": 30.0, "Unidad": "IN", "Confianza": 100,
        "Origenes": "fixture.cut", "ConflictoCritico": False,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_dimension_pair_is_never_synthesized_from_independent_maxima():
    library, conflicts = build_library_from_instances(instance_rows([(10, 30), (30, 10)]))
    assert len(conflicts) == 1
    assert bool(library.loc[0, "ConflictoCritico"])
    assert (library.loc[0, "Ancho"], library.loc[0, "Largo"]) in {(10.0, 30.0), (30.0, 10.0)}
    assert (library.loc[0, "Ancho"], library.loc[0, "Largo"]) != (30.0, 30.0)


def test_homogeneous_instances_create_valid_library():
    library, conflicts = build_library_from_instances(instance_rows([(10.00, 30.00), (10.01, 30.01)]))
    assert conflicts.empty
    assert not bool(library.loc[0, "ConflictoCritico"])
    assert library.loc[0, "InstanciasCUT"] == 2


def test_exact_division_is_accepted():
    normalized = normalize_library(editable_row(4, 2))
    assert normalized.loc[0, "Cantidad"] == 2


def test_non_exact_division_is_rejected_without_rounding():
    with pytest.raises(LibraryNormalizationError) as error:
        normalize_library(editable_row(5, 2))
    assert any(issue.code == "NON_EXACT_DIVISION" for issue in error.value.issues)


@pytest.mark.parametrize("value", [0, -1, "texto", None])
def test_invalid_repetitions_are_rejected(value):
    with pytest.raises(LibraryNormalizationError):
        normalize_library(editable_row(4, value))


def test_missing_dimension_is_rejected():
    with pytest.raises(LibraryNormalizationError) as error:
        normalize_library(editable_row(4, 2, Ancho=None))
    assert any(issue.code == "INVALID_DIMENSION" for issue in error.value.issues)


def test_unresolved_conflict_is_rejected():
    with pytest.raises(LibraryNormalizationError) as error:
        normalize_library(editable_row(4, 2, ConflictoCritico=True))
    assert any(issue.code == "UNRESOLVED_CONFLICT" for issue in error.value.issues)
