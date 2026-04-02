import pytest

pytest.importorskip("pandas")
pd = pytest.importorskip("pandas")
pytest.importorskip("geopandas")

from utils.field_mapping import FieldMappingError, apply_field_mapping, ensure_columns


def test_apply_field_mapping_renames_columns() -> None:
    df = pd.DataFrame({"osm_identifier": [1, 2], "class_name": ["a", "b"]})
    out = apply_field_mapping(df, {"osm_id": "osm_identifier", "fclass": "class_name"})
    assert "osm_id" in out.columns
    assert "fclass" in out.columns
    assert "osm_identifier" not in out.columns
    assert "class_name" not in out.columns


def test_ensure_columns_missing_required() -> None:
    df = pd.DataFrame({"a": [1]})
    with pytest.raises(FieldMappingError):
        ensure_columns(df, required=["a", "b"], context="osm")


def test_apply_field_mapping_missing_source_field() -> None:
    df = pd.DataFrame({"osm_identifier": [1, 2]})
    with pytest.raises(FieldMappingError):
        apply_field_mapping(df, {"osm_id": "missing_col"})
