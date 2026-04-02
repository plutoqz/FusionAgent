from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd


def test_golden_case_zip_inputs_are_readable_shapefiles() -> None:
    root = Path("tests/golden_cases")
    zip_paths = sorted(root.glob("*/input/*.zip"))

    assert zip_paths

    for zip_path in zip_paths:
        with tempfile.TemporaryDirectory() as td:
            target_dir = Path(td)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(target_dir)
            shp_files = sorted(target_dir.glob("*.shp"))
            assert shp_files, f"No shapefile found in {zip_path}"
            frame = gpd.read_file(shp_files[0])
            assert not frame.empty, f"Shapefile in {zip_path} should contain at least one feature"
