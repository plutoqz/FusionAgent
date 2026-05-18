from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, Polygon

from services.artifact_registry import ArtifactRegistry
from services.aoi_resolution_service import ResolvedAOI
from services.raw_vector_source_service import RawVectorSourceService


def _write_frame(path: Path, gdf: gpd.GeoDataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path)


def _extract_bounds(bundle_zip: Path, *, output_crs: str = "EPSG:4326") -> list[float]:
    extract_dir = bundle_zip.parent / f"extract_{bundle_zip.stem}"
    with zipfile.ZipFile(bundle_zip, "r") as zf:
        zf.extractall(extract_dir)
    shp_path = next(extract_dir.glob("*.shp"))
    gdf = gpd.read_file(shp_path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    bounds = gdf.to_crs(output_crs).total_bounds.tolist()
    return [float(value) for value in bounds]


def _seed_raw_source_tree(root: Path) -> None:
    _write_frame(
        root / "Data" / "buildings" / "OSM" / "osm_buildings.shp",
        gpd.GeoDataFrame(
            {"osm_id": [1]},
            geometry=[Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root / "Data" / "burundi-260127-free.shp" / "gis_osm_water_a_free_1.shp",
        gpd.GeoDataFrame(
            {"water_id": [10]},
            geometry=[Polygon([(1, 1), (1, 3), (3, 3), (3, 1)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root / "Data" / "water" / "local_water.shp",
        gpd.GeoDataFrame(
            {"local_id": [20]},
            geometry=[Polygon([(2, 2), (2, 6), (6, 6), (6, 2)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root / "Data" / "roads" / "Overture" / "overture_roads.shp",
        gpd.GeoDataFrame(
            {"ov_road_id": [30]},
            geometry=[LineString([(36.7, -1.3), (36.9, -1.2)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root / "Data" / "water" / "HydroRIVERS" / "hydrorivers.shp",
        gpd.GeoDataFrame(
            {"river_id": [40]},
            geometry=[LineString([(36.6, -1.4), (37.0, -1.1)])],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        root / "Data" / "water" / "HydroLAKES" / "hydrolakes.shp",
        gpd.GeoDataFrame(
            {"lake_id": [50]},
            geometry=[Polygon([(36.7, -1.35), (36.7, -1.2), (36.9, -1.2), (36.9, -1.35)])],
            crs="EPSG:4326",
        ),
    )


def _resolved_nairobi_aoi() -> ResolvedAOI:
    return ResolvedAOI(
        query="Nairobi, Kenya",
        display_name="Nairobi, Nairobi County, Kenya",
        country_name="Kenya",
        country_code="ke",
        bbox=(36.65, -1.45, 37.10, -1.10),
        confidence=0.97,
        selection_reason="single_high_confidence_candidate",
        candidates=(),
    )


def test_raw_vector_source_service_supports_directory_exact_and_recursive_locators() -> None:
    script = textwrap.dedent(
        """
        import tempfile
        from pathlib import Path

        import geopandas as gpd
        from shapely.geometry import LineString, Point, Polygon

        from services.artifact_registry import ArtifactRegistry
        from services.raw_vector_source_service import RawVectorSourceService


        def write_frame(path: Path, gdf: gpd.GeoDataFrame) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            gdf.to_file(path)


        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            write_frame(
                tmp_path / "Data" / "buildings" / "OSM" / "osm_buildings.shp",
                gpd.GeoDataFrame(
                    {"osm_id": [1]},
                    geometry=[Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])],
                    crs="EPSG:4326",
                ),
            )
            write_frame(
                tmp_path / "Data" / "burundi-260127-free.shp" / "gis_osm_water_a_free_1.shp",
                gpd.GeoDataFrame(
                    {"water_id": [10]},
                    geometry=[Polygon([(1, 1), (1, 2), (2, 2), (2, 1)])],
                    crs="EPSG:4326",
                ),
            )
            write_frame(
                tmp_path / "Data" / "POI" / "sample_region" / "GNS.shp",
                gpd.GeoDataFrame(
                    {"gns_id": [20]},
                    geometry=[Point(1.5, 1.5)],
                    crs="EPSG:4326",
                ),
            )
            write_frame(
                tmp_path / "Data" / "roads" / "Overture" / "overture_roads.shp",
                gpd.GeoDataFrame(
                    {"ov_road_id": [30]},
                    geometry=[LineString([(0, 0), (1, 1)])],
                    crs="EPSG:4326",
                ),
            )
            service = RawVectorSourceService(
                root_dir=tmp_path,
                registry=ArtifactRegistry(index_path=tmp_path / "artifact_registry.json"),
                cache_dir=tmp_path / "cache",
            )
            building = service.resolve(
                source_id="raw.osm.building",
                request_bbox=None,
                target_path=tmp_path / "run" / "building.zip",
                target_crs="EPSG:4326",
            )
            water = service.resolve(
                source_id="raw.osm.water",
                request_bbox=None,
                target_path=tmp_path / "run" / "water.zip",
                target_crs="EPSG:4326",
            )
            poi = service.resolve(
                source_id="raw.gns.poi",
                request_bbox=None,
                target_path=tmp_path / "run" / "poi.zip",
                target_crs="EPSG:4326",
            )
            overture = service.resolve(
                source_id="raw.overture.road",
                request_bbox=None,
                target_path=tmp_path / "run" / "overture.zip",
                target_crs="EPSG:4326",
            )
            assert building.zip_path.exists()
            assert water.zip_path.exists()
            assert poi.zip_path.exists()
            assert overture.zip_path.exists()
            assert building.source_mode == "downloaded"
            assert water.source_mode == "downloaded"
            assert poi.source_mode == "downloaded"
            assert overture.source_mode == "downloaded"
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_raw_vector_source_service_reuses_cached_sources_when_version_matches_and_clips_bbox(tmp_path: Path) -> None:
    _seed_raw_source_tree(tmp_path)
    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    service = RawVectorSourceService(root_dir=tmp_path, registry=registry, cache_dir=tmp_path / "cache")

    initial = service.resolve(
        source_id="raw.osm.building",
        request_bbox=None,
        target_path=tmp_path / "run1" / "osm.zip",
        target_crs="EPSG:4326",
    )
    reused = service.resolve(
        source_id="raw.osm.building",
        request_bbox=(1.0, 1.0, 2.0, 2.0),
        target_path=tmp_path / "run2" / "osm.zip",
        target_crs="EPSG:4326",
    )

    assert initial.source_mode == "downloaded"
    assert reused.source_mode == "clip_reused"
    assert reused.cache_hit is True
    assert _extract_bounds(reused.zip_path) == [1.0, 1.0, 2.0, 2.0]

    payload = json.loads((tmp_path / "artifact_registry.json").read_text(encoding="utf-8"))
    raw_records = [
        record
        for record in payload.get("records", [])
        if record.get("meta", {}).get("artifact_role") == "raw_vector"
    ]
    assert len(raw_records) == 1


def test_raw_vector_source_service_falls_back_to_source_asset_service_when_local_data_is_missing(tmp_path: Path) -> None:
    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    remote_shp = tmp_path / "remote" / "roads.shp"
    _write_frame(
        remote_shp,
        gpd.GeoDataFrame(
            {"road_id": [1]},
            geometry=[Polygon([(36.7, -1.4), (36.7, -1.2), (36.9, -1.2), (36.9, -1.4)])],
            crs="EPSG:4326",
        ),
    )

    class _StubSourceAssetService:
        def can_materialize(self, source_id: str) -> bool:
            return source_id == "raw.osm.road"

        def resolve_raw_source_path(self, source_id: str, *, request_bbox=None, aoi=None):
            assert source_id == "raw.osm.road"
            assert request_bbox == _resolved_nairobi_aoi().bbox
            assert aoi == _resolved_nairobi_aoi()
            return type(
                "Resolution",
                (),
                {
                    "path": remote_shp,
                    "version_token": "remote-v1",
                    "source_mode": "asset_downloaded",
                    "cache_hit": False,
                    "bbox": request_bbox,
                    "feature_count": 1,
                },
            )()

    service = RawVectorSourceService(
        root_dir=tmp_path,
        registry=registry,
        cache_dir=tmp_path / "cache",
        source_asset_service=_StubSourceAssetService(),
    )

    resolved = service.resolve(
        source_id="raw.osm.road",
        request_bbox=_resolved_nairobi_aoi().bbox,
        target_path=tmp_path / "run" / "roads.zip",
        target_crs="EPSG:4326",
        resolved_aoi=_resolved_nairobi_aoi(),
    )

    assert resolved.zip_path.exists()
    assert resolved.version_token == "remote-v1"
    assert resolved.source_mode == "downloaded"
    assert resolved.cache_hit is False
    assert _extract_bounds(resolved.zip_path) == pytest.approx([36.7, -1.4, 36.9, -1.2], abs=1e-3)


def test_raw_vector_source_service_reuses_cached_water_source_and_clips_bbox(tmp_path: Path) -> None:
    _seed_raw_source_tree(tmp_path)
    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    service = RawVectorSourceService(root_dir=tmp_path, registry=registry, cache_dir=tmp_path / "cache")

    initial = service.resolve(
        source_id="raw.osm.water",
        request_bbox=None,
        target_path=tmp_path / "run1" / "water.zip",
        target_crs="EPSG:4326",
    )
    reused = service.resolve(
        source_id="raw.osm.water",
        request_bbox=(1.25, 1.25, 2.75, 2.75),
        target_path=tmp_path / "run2" / "water.zip",
        target_crs="EPSG:4326",
    )

    assert initial.source_mode == "downloaded"
    assert reused.source_mode == "clip_reused"
    assert reused.cache_hit is True
    assert reused.version_token == initial.version_token
    assert _extract_bounds(reused.zip_path) == [1.25, 1.25, 2.75, 2.75]


def test_raw_vector_source_service_preserves_tile_cache_metadata(tmp_path: Path) -> None:
    _seed_raw_source_tree(tmp_path)
    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    service = RawVectorSourceService(root_dir=tmp_path, registry=registry, cache_dir=tmp_path / "cache")

    resolved = service.resolve(
        source_id="raw.osm.building",
        request_bbox=(1.0, 1.0, 2.0, 2.0),
        target_path=tmp_path / "tile_001" / "osm.zip",
        target_crs="EPSG:4326",
    )

    assert resolved.coverage_status in {"available", "empty"}
    assert resolved.source_mode in {"downloaded", "clip_reused", "cache_reused"}

    payload = json.loads((tmp_path / "artifact_registry.json").read_text(encoding="utf-8"))
    raw_record = next(
        record
        for record in payload.get("records", [])
        if record.get("meta", {}).get("artifact_role") == "raw_vector"
    )
    assert raw_record["meta"]["tile_scope"] == "request_bbox"
    assert raw_record["meta"]["tile_bbox"] == [1.0, 1.0, 2.0, 2.0]
    assert raw_record["meta"]["tile_key"]


def test_raw_vector_source_service_materializes_local_water_source_with_stable_version_token(tmp_path: Path) -> None:
    _seed_raw_source_tree(tmp_path)
    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    service = RawVectorSourceService(root_dir=tmp_path, registry=registry, cache_dir=tmp_path / "cache")

    version_a = service.current_version("raw.local.water")
    version_b = service.current_version("raw.local.water")
    resolved = service.resolve(
        source_id="raw.local.water",
        request_bbox=(2.5, 2.5, 5.5, 5.5),
        target_path=tmp_path / "run" / "local_water.zip",
        target_crs="EPSG:4326",
    )

    assert version_a == version_b
    assert resolved.source_id == "raw.local.water"
    assert resolved.source_mode == "downloaded"
    assert resolved.cache_hit is False
    assert resolved.version_token == version_a
    assert _extract_bounds(resolved.zip_path) == [2.5, 2.5, 5.5, 5.5]


def test_raw_vector_source_service_materializes_track_b_manual_preload_road_and_water_refs(tmp_path: Path) -> None:
    _seed_raw_source_tree(tmp_path)
    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    service = RawVectorSourceService(root_dir=tmp_path, registry=registry, cache_dir=tmp_path / "cache")

    overture = service.resolve(
        source_id="raw.overture.road",
        request_bbox=(36.72, -1.31, 36.88, -1.21),
        target_path=tmp_path / "run" / "overture.zip",
        target_crs="EPSG:4326",
    )
    rivers = service.resolve(
        source_id="raw.hydrorivers.water",
        request_bbox=(36.65, -1.45, 37.02, -1.09),
        target_path=tmp_path / "run" / "hydrorivers.zip",
        target_crs="EPSG:4326",
    )
    lakes = service.resolve(
        source_id="raw.hydrolakes.water",
        request_bbox=(36.72, -1.34, 36.88, -1.21),
        target_path=tmp_path / "run" / "hydrolakes.zip",
        target_crs="EPSG:4326",
    )

    assert overture.source_id == "raw.overture.road"
    assert overture.source_mode == "downloaded"
    assert overture.cache_hit is False
    assert _extract_bounds(overture.zip_path) == pytest.approx([36.72, -1.29, 36.88, -1.21], abs=1e-3)

    assert rivers.source_id == "raw.hydrorivers.water"
    assert rivers.source_mode == "downloaded"
    assert rivers.cache_hit is False
    assert _extract_bounds(rivers.zip_path) == pytest.approx([36.65, -1.3625, 37.0, -1.1], abs=1e-3)

    assert lakes.source_id == "raw.hydrolakes.water"
    assert lakes.source_mode == "downloaded"
    assert lakes.cache_hit is False
    assert _extract_bounds(lakes.zip_path) == pytest.approx([36.72, -1.34, 36.88, -1.21], abs=1e-3)


def test_raw_vector_source_service_selects_gns_reference_by_resolved_aoi_country_hint(tmp_path: Path) -> None:
    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    _write_frame(
        tmp_path / "Data" / "POI" / "Kenya" / "GNS.shp",
        gpd.GeoDataFrame(
            {"gns_id": [1]},
            geometry=[Point(36.82, -1.29)],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "POI" / "Uganda" / "GNS.shp",
        gpd.GeoDataFrame(
            {"gns_id": [2]},
            geometry=[Point(32.58, 0.35)],
            crs="EPSG:4326",
        ),
    )
    service = RawVectorSourceService(root_dir=tmp_path, registry=registry, cache_dir=tmp_path / "cache")

    resolved = service.resolve(
        source_id="raw.gns.poi",
        request_bbox=None,
        target_path=tmp_path / "run" / "poi.zip",
        target_crs="EPSG:4326",
        resolved_aoi=_resolved_nairobi_aoi(),
    )

    assert resolved.zip_path.exists()
    extract_dir = tmp_path / "extract_gns_selected"
    with zipfile.ZipFile(resolved.zip_path, "r") as zf:
        zf.extractall(extract_dir)
    shp_path = next(extract_dir.glob("*.shp"))
    frame = gpd.read_file(shp_path)
    assert frame.iloc[0]["gns_id"] == 1


def test_raw_vector_source_service_raises_when_gns_reference_selection_is_ambiguous(tmp_path: Path) -> None:
    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    _write_frame(
        tmp_path / "Data" / "POI" / "shared" / "GNS.shp",
        gpd.GeoDataFrame(
            {"gns_id": [1]},
            geometry=[Point(36.82, -1.29)],
            crs="EPSG:4326",
        ),
    )
    _write_frame(
        tmp_path / "Data" / "POI" / "backup" / "GNS.shp",
        gpd.GeoDataFrame(
            {"gns_id": [2]},
            geometry=[Point(32.58, 0.35)],
            crs="EPSG:4326",
        ),
    )
    service = RawVectorSourceService(root_dir=tmp_path, registry=registry, cache_dir=tmp_path / "cache")

    with pytest.raises(ValueError, match="Ambiguous raw source match for raw.gns.poi"):
        service.resolve(
            source_id="raw.gns.poi",
            request_bbox=None,
            target_path=tmp_path / "run" / "poi.zip",
            target_crs="EPSG:4326",
        )
