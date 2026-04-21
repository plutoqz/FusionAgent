from pathlib import Path

from services.aoi_resolution_service import ResolvedAOI
from services.local_bundle_catalog import LocalBundleCatalogProvider
from services.raw_vector_source_service import MaterializedRawVectorSource


def test_building_catalog_falls_back_from_empty_microsoft_to_google(tmp_path):
    provider = _make_provider_with_component_counts(
        tmp_path,
        counts={
            "raw.osm.building": 10,
            "raw.microsoft.building": 0,
            "raw.google.building": 8,
        },
    )

    bundle = provider.materialize_with_fallback(
        source_id="catalog.earthquake.building",
        request_bbox=(2.48, 9.23, 2.77, 9.44),
        resolved_aoi=_make_resolved_aoi("Parakou, Benin"),
        target_dir=tmp_path / "bundle",
        target_crs="EPSG:32631",
    )

    assert bundle.source_id == "catalog.flood.building"
    assert bundle.fallback_from == "catalog.earthquake.building"
    assert bundle.component_coverage["raw.microsoft.building"].feature_count == 0
    assert bundle.component_coverage["raw.google.building"].feature_count == 8


def _make_provider_with_component_counts(tmp_path: Path, *, counts: dict[str, int]) -> LocalBundleCatalogProvider:
    return LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=_FakeRawVectorSourceService(counts),
    )


class _FakeRawVectorSourceService:
    def __init__(self, counts: dict[str, int]) -> None:
        self.counts = counts

    def current_version(self, source_id: str, **_kwargs) -> str:
        return f"{source_id}:{self.counts[source_id]}"

    def resolve(self, *, source_id: str, request_bbox, target_path: Path, target_crs: str, resolved_aoi=None):
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(b"zip")
        return MaterializedRawVectorSource(
            zip_path=target_path,
            bbox=request_bbox,
            target_crs=target_crs,
            source_id=source_id,
            source_mode="coverage_empty" if self.counts[source_id] == 0 else "downloaded",
            cache_hit=False,
            version_token=self.current_version(source_id),
            feature_count=self.counts[source_id],
        )


def _make_resolved_aoi(query: str) -> ResolvedAOI:
    return ResolvedAOI(
        query=query,
        display_name=query,
        country_name="Benin",
        country_code="bj",
        bbox=(2.48, 9.23, 2.77, 9.44),
        confidence=0.9,
        selection_reason="test",
        candidates=(),
    )
