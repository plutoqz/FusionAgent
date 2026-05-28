from pathlib import Path

import pytest

from services.aoi_resolution_service import ResolvedAOI
from services.local_bundle_catalog import LocalBundleCatalogProvider
from services.raw_vector_source_service import MaterializedRawVectorSource


def test_building_catalog_does_not_auto_fallback_to_manual_google(tmp_path):
    provider = _make_provider_with_component_counts(
        tmp_path,
        counts={
            "raw.osm.building": 10,
            "raw.microsoft.building": 0,
            "raw.google.building": 8,
        },
    )

    with pytest.raises(ValueError, match="AOI-scoped bundle has empty source coverage for catalog\\.earthquake\\.building"):
        provider.materialize_with_fallback(
            source_id="catalog.earthquake.building",
            request_bbox=(2.48, 9.23, 2.77, 9.44),
            resolved_aoi=_make_resolved_aoi("Parakou, Benin"),
            target_dir=tmp_path / "bundle",
            target_crs="EPSG:32631",
        )

    assert "raw.google.building" not in provider.raw_source_service.resolved_source_ids


def test_water_catalog_accepts_empty_reference_when_osm_has_coverage(tmp_path):
    provider = _make_provider_with_component_counts(
        tmp_path,
        counts={
            "raw.osm.water": 12,
            "raw.hydrolakes.water": 0,
        },
    )

    bundle = provider.materialize_with_fallback(
        source_id="catalog.flood.water",
        request_bbox=(36.66, -1.44, 37.10, -1.16),
        resolved_aoi=_make_resolved_aoi("Nairobi, Kenya", country_name="Kenya", country_code="ke"),
        target_dir=tmp_path / "water-bundle",
        target_crs="EPSG:32737",
    )

    assert bundle.source_id == "catalog.flood.water"
    assert bundle.fallback_from is None
    assert bundle.component_coverage["raw.osm.water"].feature_count == 12
    assert bundle.component_coverage["raw.hydrolakes.water"].feature_count == 0


def test_poi_catalog_accepts_empty_reference_when_osm_has_coverage(tmp_path):
    provider = _make_provider_with_component_counts(
        tmp_path,
        counts={
            "raw.osm.poi": 25,
            "raw.gns.poi": 0,
        },
    )

    bundle = provider.materialize_with_fallback(
        source_id="catalog.generic.poi",
        request_bbox=(36.66, -1.44, 37.10, -1.16),
        resolved_aoi=_make_resolved_aoi("Nairobi, Kenya", country_name="Kenya", country_code="ke"),
        target_dir=tmp_path / "poi-bundle",
        target_crs="EPSG:32737",
    )

    assert bundle.source_id == "catalog.generic.poi"
    assert bundle.fallback_from is None
    assert bundle.component_coverage["raw.osm.poi"].feature_count == 25
    assert bundle.component_coverage["raw.gns.poi"].feature_count == 0


def test_road_catalog_accepts_missing_overture_reference_when_osm_has_coverage(tmp_path):
    provider = _make_provider_with_component_counts(
        tmp_path,
        counts={
            "raw.osm.road": 25,
            "raw.overture.transportation": 0,
        },
    )

    bundle = provider.materialize_with_fallback(
        source_id="catalog.flood.road",
        request_bbox=(36.66, -1.44, 37.10, -1.16),
        resolved_aoi=_make_resolved_aoi("Nairobi, Kenya", country_name="Kenya", country_code="ke"),
        target_dir=tmp_path / "road-bundle",
        target_crs="EPSG:32737",
    )

    assert bundle.source_id == "catalog.flood.road"
    assert bundle.fallback_from is None
    assert bundle.component_coverage["raw.osm.road"].feature_count == 25
    assert bundle.component_coverage["raw.overture.transportation"].feature_count == 0


def _make_provider_with_component_counts(tmp_path: Path, *, counts: dict[str, int]) -> LocalBundleCatalogProvider:
    return LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=_FakeRawVectorSourceService(counts),
    )


class _FakeRawVectorSourceService:
    def __init__(self, counts: dict[str, int]) -> None:
        self.counts = counts
        self.resolved_source_ids: list[str] = []

    def current_version(self, source_id: str, **_kwargs) -> str:
        return f"{source_id}:{self.counts.get(source_id, 0)}"

    def resolve(self, *, source_id: str, request_bbox, target_path: Path, target_crs: str, resolved_aoi=None):
        feature_count = self.counts.get(source_id, 0)
        self.resolved_source_ids.append(source_id)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(b"zip")
        return MaterializedRawVectorSource(
            zip_path=target_path,
            bbox=request_bbox,
            target_crs=target_crs,
            source_id=source_id,
            source_mode="coverage_empty" if feature_count == 0 else "downloaded",
            cache_hit=False,
            version_token=self.current_version(source_id),
            feature_count=feature_count,
        )


def _make_resolved_aoi(
    query: str,
    *,
    country_name: str = "Benin",
    country_code: str = "bj",
) -> ResolvedAOI:
    return ResolvedAOI(
        query=query,
        display_name=query,
        country_name=country_name,
        country_code=country_code,
        bbox=(2.48, 9.23, 2.77, 9.44),
        confidence=0.9,
        selection_reason="test",
        candidates=(),
    )
