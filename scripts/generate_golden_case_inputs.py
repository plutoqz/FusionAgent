from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Polygon


REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_ROOT = REPO_ROOT / "tests" / "golden_cases"


def _zip_shapefile(shp_path: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for suffix in [".shp", ".shx", ".dbf", ".prj", ".cpg"]:
            candidate = shp_path.with_suffix(suffix)
            if candidate.exists():
                zf.write(candidate, arcname=candidate.name)


def _write_building_bundle(zip_path: Path, *, kind: str) -> None:
    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)
        shp_path = temp_dir / f"{kind}.shp"
        if kind == "osm":
            rows = [
                {
                    "osm_id": 1,
                    "fclass": "building",
                    "name": "sample_osm_building",
                    "type": "residential",
                    "geometry": Polygon([(0, 0), (0, 12), (12, 12), (12, 0)]),
                }
            ]
        else:
            rows = [
                {
                    "confidence": 0.93,
                    "geometry": Polygon([(1, 1), (1, 11), (11, 11), (11, 1)]),
                }
            ]
        gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:32643").to_file(shp_path)
        _zip_shapefile(shp_path, zip_path)


def _write_road_bundle(zip_path: Path, *, kind: str) -> None:
    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)
        shp_path = temp_dir / f"{kind}.shp"
        if kind == "osm":
            rows = [
                {
                    "osm_id": 1,
                    "fclass": "primary",
                    "geometry": LineString([(0, 0), (10, 0), (20, 0)]),
                }
            ]
        else:
            rows = [
                {
                    "FID_1": 1,
                    "geometry": LineString([(0, 1), (10, 1), (20, 1)]),
                }
            ]
        gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:32643").to_file(shp_path)
        _zip_shapefile(shp_path, zip_path)


def main() -> int:
    building_cases = [
        GOLDEN_ROOT / "building_disaster_flood" / "input",
        GOLDEN_ROOT / "building_user_query" / "input",
    ]
    road_cases = [
        GOLDEN_ROOT / "road_disaster_earthquake" / "input",
        GOLDEN_ROOT / "road_user_query" / "input",
    ]

    for input_dir in building_cases:
        input_dir.mkdir(parents=True, exist_ok=True)
        _write_building_bundle(input_dir / "osm.zip", kind="osm")
        _write_building_bundle(input_dir / "ref.zip", kind="ref")

    for input_dir in road_cases:
        input_dir.mkdir(parents=True, exist_ok=True)
        _write_road_bundle(input_dir / "osm.zip", kind="osm")
        _write_road_bundle(input_dir / "ref.zip", kind="ref")

    print("Golden case input bundles regenerated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
