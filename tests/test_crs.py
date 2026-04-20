import pytest

from utils.crs import (
    DEFAULT_TARGET_CRS,
    derive_default_target_crs,
    normalize_explicit_target_crs,
    normalize_target_crs,
    resolve_target_crs,
)


def test_normalize_target_crs_default() -> None:
    assert normalize_target_crs(None) == DEFAULT_TARGET_CRS
    assert normalize_target_crs("") == DEFAULT_TARGET_CRS


def test_normalize_target_crs_upper() -> None:
    assert normalize_target_crs("epsg:4326") == "EPSG:4326"


def test_normalize_target_crs_invalid() -> None:
    with pytest.raises(ValueError):
        normalize_target_crs("32643")


def test_derive_default_target_crs_uses_utm_zone_for_nairobi() -> None:
    assert derive_default_target_crs((36.65, -1.45, 37.10, -1.10)) == "EPSG:32737"


def test_derive_default_target_crs_uses_utm_zone_for_gilgit() -> None:
    assert derive_default_target_crs((74.0, 35.7, 75.0, 36.2)) == "EPSG:32643"


def test_derive_default_target_crs_falls_back_without_bbox() -> None:
    assert derive_default_target_crs(None) == DEFAULT_TARGET_CRS


def test_resolve_target_crs_preserves_explicit_value() -> None:
    assert resolve_target_crs("epsg:4326", bbox=(36.65, -1.45, 37.10, -1.10)) == "EPSG:4326"


def test_normalize_explicit_target_crs_returns_none_for_omitted_values() -> None:
    assert normalize_explicit_target_crs(None) is None
    assert normalize_explicit_target_crs("") is None

