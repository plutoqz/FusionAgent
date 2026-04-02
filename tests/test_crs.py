import pytest

from utils.crs import DEFAULT_TARGET_CRS, normalize_target_crs


def test_normalize_target_crs_default() -> None:
    assert normalize_target_crs(None) == DEFAULT_TARGET_CRS
    assert normalize_target_crs("") == DEFAULT_TARGET_CRS


def test_normalize_target_crs_upper() -> None:
    assert normalize_target_crs("epsg:4326") == "EPSG:4326"


def test_normalize_target_crs_invalid() -> None:
    with pytest.raises(ValueError):
        normalize_target_crs("32643")

