from __future__ import annotations

from schemas.degradation import DegradationContext, DegradationLevel
from schemas.task_kind import TaskKind
from services.quality_gate_service import _EXPECTED_GEOMETRIES
from services.source_acquisition_policy import classify_component_degradation


def test_no_location_specific_runtime_policy_names_are_required() -> None:
    generic_context = classify_component_degradation(
        {
            "raw.generic.available": {"feature_count": 1, "coverage_status": "available"},
            "raw.generic.external": {"feature_count": 0, "coverage_status": "missing", "fault_class": "UNAUTHORIZED"},
        }
    )

    assert generic_context.level == DegradationLevel.external_uncontrollable
    assert "London" not in repr(generic_context)
    assert "United Kingdom" not in repr(generic_context)


def test_task_geometry_contracts_remain_hard_boundaries() -> None:
    assert _EXPECTED_GEOMETRIES[TaskKind.water_polygon] == {"Polygon", "MultiPolygon"}
    assert _EXPECTED_GEOMETRIES[TaskKind.waterways] == {"LineString", "MultiLineString"}
    assert _EXPECTED_GEOMETRIES[TaskKind.poi] == {"Point", "MultiPoint"}


def test_degradation_context_external_only_property_rejects_system_failure() -> None:
    context = DegradationContext(
        degraded=True,
        level=DegradationLevel.system_failure,
        available_sources=["raw.a"],
        missing_sources=["raw.b"],
        external_uncontrollable_sources=["raw.b"],
        system_failure_sources=["raw.c"],
    )

    assert context.external_only is False
