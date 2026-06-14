from pathlib import Path

import pytest

from schemas.degradation import DegradationLevel
from services.aoi_resolution_service import ResolvedAOI
from services.local_bundle_catalog import LocalBundleCatalogProvider
from services.raw_vector_source_service import MaterializedRawVectorSource
from services.source_asset_service import SourceCoverageStatus
from services.source_acquisition_policy import (
    classify_component_degradation,
    required_full_closure_source_ids,
    source_component_candidates,
)


def test_task6_required_full_closure_source_ids_are_complete() -> None:
    assert required_full_closure_source_ids("catalog.flood.road") == ["raw.osm.road", "raw.microsoft.road"]
    assert required_full_closure_source_ids("catalog.earthquake.road") == ["raw.osm.road", "raw.microsoft.road"]
    assert required_full_closure_source_ids("catalog.typhoon.road") == ["raw.osm.road", "raw.microsoft.road"]
    assert required_full_closure_source_ids("catalog.flood.water") == ["raw.osm.water", "raw.hydrolakes.water"]
    assert required_full_closure_source_ids("catalog.flood.water_polygon") == ["raw.osm.water", "raw.hydrolakes.water"]
    assert required_full_closure_source_ids("catalog.flood.waterways") == [
        "raw.osm.waterways",
        "raw.hydrorivers.water",
    ]


def test_task6_road_candidate_policy_covers_all_road_catalogs() -> None:
    for source_id in ("catalog.flood.road", "catalog.earthquake.road", "catalog.typhoon.road"):
        assert source_component_candidates(source_id, ("raw.osm.road", "raw.overture.transportation")) == [
            "raw.osm.road",
            "raw.microsoft.road",
        ]


def test_classify_component_degradation_detects_external_only_missing_sources() -> None:
    context = classify_component_degradation(
        {
            "raw.gns.poi": {"coverage_status": "available", "feature_count": 12},
            "raw.google.poi": {
                "coverage_status": "missing",
                "feature_count": 0,
                "fault_class": "UNAUTHORIZED",
            },
        }
    )

    assert context.degraded is True
    assert context.level == DegradationLevel.external_uncontrollable
    assert context.available_sources == ["raw.gns.poi"]
    assert context.external_uncontrollable_sources == ["raw.google.poi"]
    assert context.system_failure_sources == []


def test_classify_component_degradation_detects_system_provider_failures() -> None:
    context = classify_component_degradation(
        {
            "raw.osm.road": {"coverage_status": "missing", "feature_count": 0, "fault_class": "SOURCE_MISSING"},
            "raw.microsoft.road": {
                "coverage_status": "missing",
                "feature_count": 0,
                "fault_class": "MISSING_PROVIDER",
            },
        }
    )

    assert context.degraded is True
    assert context.level == DegradationLevel.system_failure
    assert context.system_failure_sources == ["raw.microsoft.road"]


def test_classify_component_degradation_treats_empty_coverage_as_degraded_missing_evidence() -> None:
    context = classify_component_degradation({})

    assert context.degraded is True
    assert context.level == DegradationLevel.partial_source
    assert context.reason == "no component coverage evidence"
    assert context.available_sources == []
    assert context.missing_sources == []
    assert context.external_uncontrollable_sources == []
    assert context.system_failure_sources == []


def test_classify_component_degradation_reads_fault_class_from_attribute_payload() -> None:
    context = classify_component_degradation(
        {
            "raw.google.poi": SourceCoverageStatus(
                source_id="raw.google.poi",
                source_mode="unauthorized",
                feature_count=False,
                coverage_status=" Missing ",
                fault_class="UNAUTHORIZED",
                external_uncontrollable=True,
            )
        }
    )

    assert context.degraded is True
    assert context.level == DegradationLevel.external_uncontrollable
    assert context.available_sources == []
    assert context.missing_sources == ["raw.google.poi"]
    assert context.external_uncontrollable_sources == ["raw.google.poi"]
    assert context.system_failure_sources == []


def test_classify_component_degradation_reads_external_flag_from_attribute_payload() -> None:
    context = classify_component_degradation(
        {
            "raw.google.poi": SourceCoverageStatus(
                source_id="raw.google.poi",
                source_mode="unauthorized",
                feature_count=0,
                coverage_status="missing",
                fault_class=None,
                external_uncontrollable=True,
            )
        }
    )

    assert context.degraded is True
    assert context.level == DegradationLevel.external_uncontrollable
    assert context.external_uncontrollable_sources == ["raw.google.poi"]
    assert context.system_failure_sources == []


def test_classify_component_degradation_does_not_treat_false_string_as_external() -> None:
    context = classify_component_degradation(
        {
            "raw.google.poi": {
                "coverage_status": "missing",
                "feature_count": 0,
                "external_uncontrollable": "false",
            }
        }
    )

    assert context.degraded is True
    assert context.level == DegradationLevel.partial_source
    assert context.external_uncontrollable_sources == []


def test_building_catalog_records_google_attempt_but_keeps_missing_microsoft_degraded(tmp_path):
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

    assert "raw.google.building" in provider.raw_source_service.resolved_source_ids
    assert "raw.microsoft.building" in provider.raw_source_service.resolved_source_ids
    assert bundle.component_coverage["raw.google.building"].feature_count == 8
    assert bundle.component_coverage["raw.microsoft.building"].feature_count == 0
    assert any(
        attempt["source_id"] == "raw.microsoft.building" and attempt["status"] == "empty"
        for attempt in bundle.provider_attempts
    )


def test_building_catalog_records_full_task6_candidate_attempts_without_task7_routing(tmp_path):
    provider = _make_provider_with_component_counts(
        tmp_path,
        counts={
            "raw.google.building": 0,
            "raw.microsoft.building": 8,
            "raw.osm.building": 10,
            "raw.osm.road": 4,
            "raw.openbuildingmap.building": 0,
        },
    )

    bundle = provider.materialize_with_fallback(
        source_id="catalog.flood.building",
        request_bbox=(2.48, 9.23, 2.77, 9.44),
        resolved_aoi=_make_resolved_aoi("Parakou, Benin"),
        target_dir=tmp_path / "building-bundle",
        target_crs="EPSG:32631",
    )

    assert [attempt["source_id"] for attempt in bundle.provider_attempts] == [
        "raw.google.building",
        "raw.microsoft.building",
        "raw.osm.building",
        "raw.osm.road",
        "raw.openbuildingmap.building",
    ]
    assert bundle.osm_zip_path.name == "osm.zip"
    assert bundle.ref_zip_path.name == "ref.zip"
    assert set(bundle.component_coverage) >= {
        "raw.google.building",
        "raw.microsoft.building",
        "raw.osm.building",
        "raw.osm.road",
        "raw.openbuildingmap.building",
    }
    assert [attempt["attempt_no"] for attempt in bundle.provider_attempts] == [1, 2, 3, 4, 5]


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
            "raw.google.poi": 0,
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
    assert provider.raw_source_service.resolved_source_ids == ["raw.gns.poi", "raw.google.poi", "raw.osm.poi"]
    assert bundle.component_coverage["raw.osm.poi"].feature_count == 25
    assert bundle.component_coverage["raw.gns.poi"].feature_count == 0
    assert bundle.component_coverage["raw.google.poi"].feature_count == 0
    assert [attempt["source_id"] for attempt in bundle.provider_attempts] == [
        "raw.gns.poi",
        "raw.google.poi",
        "raw.osm.poi",
    ]
    assert [attempt["attempt_no"] for attempt in bundle.provider_attempts] == [1, 2, 3]
    assert bundle.provider_attempts[1]["status"] == "empty"


def test_poi_catalog_records_google_poi_attempt_when_remote_is_unauthorized(tmp_path):
    provider = _make_provider_with_component_counts(
        tmp_path,
        counts={
            "raw.gns.poi": 0,
            "raw.osm.poi": 25,
        },
        errors={"raw.google.poi": PermissionError("Google POI persistence authorization manifest is required.")},
    )

    bundle = provider.materialize_with_fallback(
        source_id="catalog.generic.poi",
        request_bbox=(36.66, -1.44, 37.10, -1.16),
        resolved_aoi=_make_resolved_aoi("Nairobi, Kenya", country_name="Kenya", country_code="ke"),
        target_dir=tmp_path / "poi-bundle-unauthorized-google",
        target_crs="EPSG:32737",
    )

    assert bundle.source_id == "catalog.generic.poi"
    assert provider.raw_source_service.resolved_source_ids == ["raw.gns.poi", "raw.google.poi", "raw.osm.poi"]
    assert bundle.component_coverage["raw.google.poi"].coverage_status == "missing"
    assert bundle.component_coverage["raw.google.poi"].source_mode == "unauthorized"
    assert bundle.component_coverage["raw.google.poi"].fault_class == "UNAUTHORIZED"
    assert bundle.component_coverage["raw.google.poi"].external_uncontrollable is True
    attempts = {attempt["source_id"]: attempt for attempt in bundle.provider_attempts}
    assert attempts["raw.google.poi"]["status"] == "unauthorized"
    assert attempts["raw.google.poi"]["fault_class"] == "UNAUTHORIZED"
    assert attempts["raw.osm.poi"]["status"] == "available"
    assert [attempt["attempt_no"] for attempt in bundle.provider_attempts] == [1, 2, 3]


def test_road_catalog_records_task6_osm_and_microsoft_road_attempts(tmp_path):
    provider = _make_provider_with_component_counts(
        tmp_path,
        counts={
            "raw.osm.road": 25,
            "raw.microsoft.road": 0,
        },
    )

    bundle = provider.materialize_with_fallback(
        source_id="catalog.flood.road",
        request_bbox=(36.66, -1.44, 37.10, -1.16),
        resolved_aoi=_make_resolved_aoi("Nairobi, Kenya", country_name="Kenya", country_code="ke"),
        target_dir=tmp_path / "road-bundle",
        target_crs="EPSG:32737",
    )

    assert [attempt["source_id"] for attempt in bundle.provider_attempts] == ["raw.osm.road", "raw.microsoft.road"]
    assert bundle.component_coverage["raw.osm.road"].feature_count == 25
    assert bundle.component_coverage["raw.microsoft.road"].feature_count == 0
    assert [attempt["attempt_no"] for attempt in bundle.provider_attempts] == [1, 2]


def test_earthquake_and_typhoon_road_catalogs_record_task6_osm_and_microsoft_attempts(tmp_path):
    for source_id in ("catalog.earthquake.road", "catalog.typhoon.road"):
        provider = _make_provider_with_component_counts(
            tmp_path,
            counts={
                "raw.osm.road": 25,
                "raw.microsoft.road": 5,
            },
        )

        bundle = provider.materialize_with_fallback(
            source_id=source_id,
            request_bbox=(36.66, -1.44, 37.10, -1.16),
            resolved_aoi=_make_resolved_aoi("Nairobi, Kenya", country_name="Kenya", country_code="ke"),
            target_dir=tmp_path / source_id.replace(".", "_"),
            target_crs="EPSG:32737",
        )

        assert [attempt["source_id"] for attempt in bundle.provider_attempts] == [
            "raw.osm.road",
            "raw.microsoft.road",
        ]
        assert [attempt["attempt_no"] for attempt in bundle.provider_attempts] == [1, 2]
        assert bundle.component_coverage["raw.microsoft.road"].feature_count == 5


def test_water_catalog_records_task6_polygon_and_line_attempts(tmp_path):
    provider = _make_provider_with_component_counts(
        tmp_path,
        counts={
            "raw.osm.water": 12,
            "raw.hydrolakes.water": 0,
            "raw.osm.waterways": 3,
            "raw.hydrorivers.water": 1,
        },
    )

    bundle = provider.materialize_with_fallback(
        source_id="catalog.flood.water",
        request_bbox=(36.66, -1.44, 37.10, -1.16),
        resolved_aoi=_make_resolved_aoi("Nairobi, Kenya", country_name="Kenya", country_code="ke"),
        target_dir=tmp_path / "water-bundle-full",
        target_crs="EPSG:32737",
    )

    assert [attempt["source_id"] for attempt in bundle.provider_attempts] == [
        "raw.osm.water",
        "raw.hydrolakes.water",
        "raw.osm.waterways",
        "raw.hydrorivers.water",
    ]
    assert set(bundle.component_coverage) >= {
        "raw.osm.water",
        "raw.hydrolakes.water",
        "raw.osm.waterways",
        "raw.hydrorivers.water",
    }
    assert [attempt["attempt_no"] for attempt in bundle.provider_attempts] == [1, 2, 3, 4]


def test_waterways_catalog_records_task6_line_and_polygon_attempts_with_fallback_preserved(tmp_path):
    provider = _make_provider_with_component_counts(
        tmp_path,
        counts={
            "raw.osm.waterways": 0,
            "raw.hydrorivers.water": 0,
            "raw.osm.water": 12,
            "raw.hydrolakes.water": 2,
        },
    )

    bundle = provider.materialize_with_fallback(
        source_id="catalog.flood.waterways",
        request_bbox=(36.66, -1.44, 37.10, -1.16),
        resolved_aoi=_make_resolved_aoi("Nairobi, Kenya", country_name="Kenya", country_code="ke"),
        target_dir=tmp_path / "waterways-bundle-full",
        target_crs="EPSG:32737",
    )

    assert [attempt["source_id"] for attempt in bundle.provider_attempts][:4] == [
        "raw.osm.waterways",
        "raw.hydrorivers.water",
        "raw.osm.water",
        "raw.hydrolakes.water",
    ]
    assert bundle.source_id in {"catalog.flood.waterways", "catalog.flood.water"}
    assert set(bundle.component_coverage) >= {
        "raw.osm.waterways",
        "raw.hydrorivers.water",
        "raw.osm.water",
        "raw.hydrolakes.water",
    }


def test_policy_candidate_bundle_keeps_evidence_when_only_non_primary_candidate_has_coverage(tmp_path):
    provider = _make_provider_with_component_counts(
        tmp_path,
        counts={
            "raw.osm.road": 0,
            "raw.microsoft.road": 9,
        },
    )

    bundle = provider.materialize_with_fallback(
        source_id="catalog.flood.road",
        request_bbox=(36.66, -1.44, 37.10, -1.16),
        resolved_aoi=_make_resolved_aoi("Nairobi, Kenya", country_name="Kenya", country_code="ke"),
        target_dir=tmp_path / "road-only-ms",
        target_crs="EPSG:32737",
    )

    assert bundle.osm_zip_path.name == "osm.zip"
    assert bundle.ref_zip_path.name == "ref.zip"
    assert bundle.component_coverage["raw.osm.road"].feature_count == 0
    assert bundle.component_coverage["raw.microsoft.road"].feature_count == 9
    assert [attempt["source_id"] for attempt in bundle.provider_attempts] == ["raw.osm.road", "raw.microsoft.road"]
    assert [attempt["attempt_no"] for attempt in bundle.provider_attempts] == [1, 2]


def test_policy_candidate_value_error_is_recorded_and_later_candidates_continue(tmp_path):
    provider = _make_provider_with_component_counts(
        tmp_path,
        counts={
            "raw.google.building": 0,
            "raw.microsoft.building": 7,
            "raw.osm.building": 9,
            "raw.osm.road": 3,
            "raw.openbuildingmap.building": 0,
        },
        errors={"raw.google.building": ValueError("Ambiguous raw source match for raw.google.building")},
    )

    bundle = provider.materialize_with_fallback(
        source_id="catalog.flood.building",
        request_bbox=(2.48, 9.23, 2.77, 9.44),
        resolved_aoi=_make_resolved_aoi("Parakou, Benin"),
        target_dir=tmp_path / "building-value-error",
        target_crs="EPSG:32631",
    )

    assert provider.raw_source_service.resolved_source_ids == [
        "raw.google.building",
        "raw.microsoft.building",
        "raw.osm.building",
        "raw.osm.road",
        "raw.openbuildingmap.building",
    ]
    attempts = {attempt["source_id"]: attempt for attempt in bundle.provider_attempts}
    assert attempts["raw.google.building"]["status"] == "provider_failed"
    assert attempts["raw.google.building"]["fault_class"] == "PROVIDER_UNAVAILABLE"
    assert attempts["raw.microsoft.building"]["status"] == "available"
    assert [attempt["attempt_no"] for attempt in bundle.provider_attempts] == [1, 2, 3, 4, 5]


def test_road_catalog_accepts_missing_microsoft_reference_when_osm_has_coverage(tmp_path):
    provider = _make_provider_with_component_counts(
        tmp_path,
        counts={
            "raw.osm.road": 25,
            "raw.microsoft.road": 0,
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
    assert bundle.component_coverage["raw.microsoft.road"].feature_count == 0


def _make_provider_with_component_counts(
    tmp_path: Path,
    *,
    counts: dict[str, int],
    errors: dict[str, Exception] | None = None,
) -> LocalBundleCatalogProvider:
    return LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=_FakeRawVectorSourceService(counts, errors=errors),
    )


class _FakeRawVectorSourceService:
    def __init__(self, counts: dict[str, int], *, errors: dict[str, Exception] | None = None) -> None:
        self.counts = counts
        self.errors = dict(errors or {})
        self.resolved_source_ids: list[str] = []

    def current_version(self, source_id: str, **_kwargs) -> str:
        return f"{source_id}:{self.counts.get(source_id, 0)}"

    def resolve(self, *, source_id: str, request_bbox, target_path: Path, target_crs: str, resolved_aoi=None):
        self.resolved_source_ids.append(source_id)
        if source_id in self.errors:
            raise self.errors[source_id]
        feature_count = self.counts.get(source_id, 0)
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
