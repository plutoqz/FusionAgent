from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys

# This repo is not installed as a package in CI/dev by default. Ensure the
# project root is importable when pytest uses importlib import mode.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.artifact_registry import ArtifactLookupRequest, ArtifactRecord, ArtifactRegistry


def test_find_reusable_returns_fresh_matching_and_filters_others(tmp_path: Path) -> None:
    index_path = tmp_path / "artifact_index.json"
    registry = ArtifactRegistry(index_path=index_path)

    now = datetime(2026, 4, 7, 0, 0, 0, tzinfo=timezone.utc)

    registry.register(
        ArtifactRecord(
            artifact_id="artifact-fresh-match",
            artifact_path=str(tmp_path / "fresh.zip"),
            job_type="building",
            disaster_type="flood",
            created_at=(now - timedelta(minutes=5)).isoformat(),
            output_fields=["geom", "height", "name"],
            bbox=(0.0, 0.0, 10.0, 10.0),
        )
    )
    registry.register(
        ArtifactRecord(
            artifact_id="artifact-stale",
            artifact_path=str(tmp_path / "stale.zip"),
            job_type="building",
            disaster_type="flood",
            created_at=(now - timedelta(days=10)).isoformat(),
            output_fields=["geom", "height", "name"],
            bbox=(0.0, 0.0, 10.0, 10.0),
        )
    )
    registry.register(
        ArtifactRecord(
            artifact_id="artifact-wrong-job",
            artifact_path=str(tmp_path / "wrong_job.zip"),
            job_type="road",
            disaster_type="flood",
            created_at=(now - timedelta(minutes=2)).isoformat(),
            output_fields=["geom", "height", "name"],
            bbox=(0.0, 0.0, 10.0, 10.0),
        )
    )
    registry.register(
        ArtifactRecord(
            artifact_id="artifact-missing-fields",
            artifact_path=str(tmp_path / "missing_fields.zip"),
            job_type="building",
            disaster_type="flood",
            created_at=(now - timedelta(minutes=1)).isoformat(),
            output_fields=["geom", "name"],
            bbox=(0.0, 0.0, 10.0, 10.0),
        )
    )
    registry.register(
        ArtifactRecord(
            artifact_id="artifact-bbox-too-small",
            artifact_path=str(tmp_path / "bbox_small.zip"),
            job_type="building",
            disaster_type="flood",
            created_at=(now - timedelta(minutes=3)).isoformat(),
            output_fields=["geom", "height", "name"],
            bbox=(0.0, 0.0, 1.0, 1.0),
        )
    )

    assert index_path.exists()

    request = ArtifactLookupRequest(
        job_type="building",
        disaster_type="flood",
        max_age_seconds=3600,
        required_fields=["height"],
        bbox=(0.0, 0.0, 2.0, 2.0),
    )

    selected = registry.find_reusable(request, now=now)
    assert selected is not None
    assert selected.artifact_id == "artifact-fresh-match"

    # Prove the stale candidate is filtered out with a tighter freshness requirement.
    none_selected = registry.find_reusable(
        ArtifactLookupRequest(
            job_type="building",
            disaster_type="flood",
            max_age_seconds=60,
            required_fields=["height"],
            bbox=(0.0, 0.0, 2.0, 2.0),
        ),
        now=now,
    )
    assert none_selected is None


def test_find_reusable_rejects_output_type_and_crs_mismatches(tmp_path: Path) -> None:
    index_path = tmp_path / "artifact_index.json"
    registry = ArtifactRegistry(index_path=index_path)

    now = datetime(2026, 4, 9, 0, 0, 0, tzinfo=timezone.utc)

    registry.register(
        ArtifactRecord(
            artifact_id="artifact-wrong-output-type",
            artifact_path=str(tmp_path / "wrong_output_type.zip"),
            job_type="building",
            disaster_type="flood",
            created_at=(now - timedelta(minutes=1)).isoformat(),
            output_fields=["geometry", "confidence"],
            bbox=(0.0, 0.0, 10.0, 10.0),
            output_data_type="dt.building.bundle",
            target_crs="EPSG:4326",
        )
    )
    registry.register(
        ArtifactRecord(
            artifact_id="artifact-compatible",
            artifact_path=str(tmp_path / "compatible.zip"),
            job_type="building",
            disaster_type="flood",
            created_at=(now - timedelta(minutes=5)).isoformat(),
            output_fields=["geometry", "confidence"],
            bbox=(0.0, 0.0, 10.0, 10.0),
            output_data_type="dt.building.fused",
            target_crs="EPSG:32643",
        )
    )

    selected = registry.find_reusable(
        ArtifactLookupRequest(
            job_type="building",
            disaster_type="flood",
            max_age_seconds=3600,
            required_fields=["confidence"],
            bbox=(1.0, 1.0, 2.0, 2.0),
            required_output_type="dt.building.fused",
            required_target_crs="EPSG:32643",
        ),
        now=now,
    )

    assert selected is not None
    assert selected.artifact_id == "artifact-compatible"
