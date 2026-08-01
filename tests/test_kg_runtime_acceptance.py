from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agent.planner import WorkflowPlanner
from kg.inmemory_repository import InMemoryKGRepository
from kg.knowledge_release import DEFAULT_ENTITIES_PATH, get_knowledge_identity
from kg.policy_registry import default_policy_registry
from kg.seed_manifest import seal_manifest_payload
from llm.providers.base import LLMProvider
from schemas.agent import RunTrigger, RunTriggerType
from schemas.fusion import JobType
from services.local_bundle_catalog import LocalBundleCatalogProvider
from services.raw_vector_source_service import MaterializedRawVectorSource


class _FailingPlannerProvider(LLMProvider):
    def generate_workflow_plan(self, system_prompt, context):
        raise RuntimeError("force deterministic KG fallback")


def _plan(repo: InMemoryKGRepository):
    return WorkflowPlanner(repo, _FailingPlannerProvider()).create_plan(
        run_id="run-k4-perturbation",
        job_type=JobType.building,
        trigger=RunTrigger(
            type=RunTriggerType.disaster_event,
            content="flood building response",
            disaster_type="flood",
        ),
    )


def test_kg_only_pattern_change_alters_runtime_plan_and_records_decision_basis(tmp_path: Path) -> None:
    baseline = _plan(InMemoryKGRepository(experience_policy="pinned_snapshot"))

    entities = json.loads(DEFAULT_ENTITIES_PATH.read_text(encoding="utf-8"))
    for pattern in entities["workflow_patterns"]:
        if pattern["pattern_id"] == "wp.flood.building.safe":
            pattern["success_rate"] = 1.0
    mutated_path = tmp_path / "entities.json"
    mutated_path.write_text(
        json.dumps(seal_manifest_payload(entities), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    changed = _plan(InMemoryKGRepository(seed_manifest_path=mutated_path))

    assert baseline.context["selected_pattern_id"] == "wp.flood.building.default"
    assert changed.context["selected_pattern_id"] == "wp.flood.building.safe"
    assert baseline.tasks[0].algorithm_id == "algo.fusion.building.v1"
    assert changed.tasks[0].algorithm_id == "algo.fusion.building.safe"
    assert baseline.context["knowledge_identity"] == get_knowledge_identity()
    assert changed.context["knowledge_identity"]["semantic_hash"].startswith("sha256:")
    assert changed.context["selection_reason"] == (
        "selected_wp.flood.building.safe_via_kg_fallback"
    )
    selected_candidate = next(
        item
        for item in changed.context["retrieval"]["candidate_patterns"]
        if item["pattern_id"] == changed.context["selected_pattern_id"]
    )
    assert selected_candidate["ranking_rationale"]


class _FallbackPolicyRegistry:
    def source_bundle_policy(self, source_id: str, *, required: bool = False):
        policies = {
            "catalog.flood.water": {
                "source_id": "catalog.flood.water",
                "component_candidates": ["raw.osm.water"],
                "required_full_closure": [],
                "allows_partial_coverage": True,
                "fallback_source_ids": ["catalog.flood.water_polygon"],
            },
            "catalog.flood.water_polygon": {
                "source_id": "catalog.flood.water_polygon",
                "component_candidates": ["raw.osm.water", "raw.hydrolakes.water"],
                "required_full_closure": [],
                "allows_partial_coverage": True,
                "fallback_source_ids": [],
            },
        }
        if source_id in policies:
            return policies[source_id]
        if required:
            raise KeyError(source_id)
        return None

    @staticmethod
    def empty_coverage_status(source_id: str) -> str:
        return default_policy_registry().empty_coverage_status(source_id)


class _EmptyThenMaterializedSource:
    def __init__(self) -> None:
        self.osm_calls = 0
        self.first_payload_hash = ""

    def resolve(self, *, source_id, request_bbox, target_path, target_crs, resolved_aoi=None):
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if source_id == "raw.osm.water":
            self.osm_calls += 1
            payload = b"stale-primary-artifact" if self.osm_calls == 1 else b"fresh-fallback-osm"
            feature_count = 0 if self.osm_calls == 1 else 1
        else:
            payload = b"fresh-fallback-reference"
            feature_count = 1
        target_path.write_bytes(payload)
        if self.osm_calls == 1 and source_id == "raw.osm.water":
            self.first_payload_hash = hashlib.sha256(payload).hexdigest()
        return MaterializedRawVectorSource(
            zip_path=target_path,
            bbox=request_bbox,
            target_crs=target_crs,
            source_id=source_id,
            source_mode="test",
            cache_hit=False,
            version_token=f"{source_id}:{self.osm_calls}",
            feature_count=feature_count,
        )


def test_source_fallback_rematerializes_artifacts_instead_of_relabeling(tmp_path: Path) -> None:
    source_service = _EmptyThenMaterializedSource()
    provider = LocalBundleCatalogProvider(
        tmp_path,
        raw_source_service=source_service,
        policy_registry=_FallbackPolicyRegistry(),
    )

    bundle = provider.materialize_with_fallback(
        source_id="catalog.flood.water",
        request_bbox=(10.0, 10.0, 11.0, 11.0),
        target_dir=tmp_path / "bundle",
        target_crs="EPSG:4326",
    )

    assert bundle.fallback_from == "catalog.flood.water"
    assert bundle.source_id == "catalog.flood.water_polygon"
    assert bundle.attempted_sources == [
        "catalog.flood.water",
        "catalog.flood.water_polygon",
    ]
    assert source_service.osm_calls == 2
    assert bundle.osm_zip_path.read_bytes() == b"fresh-fallback-osm"
    assert hashlib.sha256(bundle.osm_zip_path.read_bytes()).hexdigest() != source_service.first_payload_hash
