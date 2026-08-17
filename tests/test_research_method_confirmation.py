import hashlib
import json
from pathlib import Path

from kg.inmemory_repository import InMemoryKGRepository
from schemas.research_case_manifest import load_research_case_manifest
from scripts.run_research_method_confirmation import (
    EXPECTED_CONDITIONS,
    build_freeze,
    prepare_confirmation_inputs,
)
from services.research_manifest_validation import validate_manifest_crosswalk


ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "docs/current/research-case-manifest-confirmation-v1.json"
REGISTRATION = ROOT / "docs/current/research-protocol-method-confirmation-v1.json"


def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_confirmation_manifest_is_independent_frozen_and_crosswalk_closed() -> None:
    manifest = load_research_case_manifest(MANIFEST)

    assert manifest.status == "frozen"
    assert [case.case_id for case in manifest.cases] == ["H07", "H08", "H09"]
    assert validate_manifest_crosswalk(
        manifest,
        InMemoryKGRepository(experience_policy="pinned_snapshot"),
    ) == []
    excluded = set(manifest.selection_governance["excluded_case_ids"])
    assert excluded == {
        "C01",
        "C02",
        "C03",
        "C04",
        "C05",
        "C06",
        "H01",
        "H02",
        "H03",
        "H04",
        "H05",
        "H06",
    }


def test_confirmation_schedule_is_exactly_27_new_cells_without_gold_leakage() -> None:
    _, schedule, prepared = prepare_confirmation_inputs(MANIFEST, REGISTRATION)

    assert len(schedule["items"]) == len(prepared) == 27
    assert set(schedule["cases"]) == {"H07", "H08", "H09"}
    assert set(schedule["knowledge_conditions"]) == EXPECTED_CONDITIONS
    assert {item["replicate"] for item in schedule["items"]} == {1, 2, 3}
    assert len({item["run_id"] for item in schedule["items"]}) == 27
    assert all("gold_rubric" not in item["payload"] for item in prepared)
    assert all(
        "gold_rubric" not in item["payload"].get("observable_facts", {})
        for item in prepared
    )


def test_method_b_projection_matches_frozen_case_mechanisms() -> None:
    _, _, prepared = prepare_confirmation_inputs(MANIFEST, REGISTRATION)
    by_case = {
        item["schedule"]["case_id"]: item["payload"]["contract_decision_context"]
        for item in prepared
        if item["schedule"]["knowledge_condition"]
        == "task_conditioned_contract_aware_kg"
    }

    h07 = {row["task_kind"]: row for row in by_case["H07"]["tasks"]}
    assert by_case["H07"]["task_precedence"] == ["poi", "road", "building"]
    assert h07["building"]["decision_constraints"]["preferred_delivery_state"] == "gap"
    assert h07["road"]["decision_constraints"]["preferred_delivery_state"] == "planned"
    assert h07["poi"]["decision_constraints"]["preferred_delivery_state"] == "planned"

    h08 = {row["task_kind"]: row for row in by_case["H08"]["tasks"]}
    assert h08["water_polygon"]["decision_constraints"]["preferred_delivery_state"] == "planned"
    assert h08["waterways"]["decision_constraints"]["preferred_delivery_state"] == "gap"
    assert h08["waterways"]["decision_constraints"]["allowed_source_ids"] == []
    assert h08["waterways"]["decision_constraints"]["delayed_source_ids"] == [
        "raw.osm.waterways"
    ]

    h09 = by_case["H09"]["tasks"][0]
    assert h09["task_kind"] == "poi"
    assert h09["observed_source_state"]["available"] == ["raw.gns.poi"]
    assert h09["decision_constraints"]["preferred_delivery_state"] == "degraded"
    assert "observed_quality_gate_rejection" in h09["decision_constraints"]["reason_codes"]


def test_protocol_preregisters_fixed_generation_metrics_review_and_stops() -> None:
    protocol = json.loads(REGISTRATION.read_text(encoding="utf-8"))

    assert protocol["protocol_status"] == "frozen"
    assert protocol["formal_ready"] is False
    assert protocol["design"]["call_count"] == 27
    assert protocol["generation"] == {
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "max_output_tokens": 16384,
        "request_timeout_seconds": 600,
        "batch_token_budget": 850000,
        "transport_retries": 0,
        "semantic_repairs": 0,
        "json_salvage": "forbidden",
        "fallback": "forbidden",
    }
    assert protocol["primary_metric"]["metric_id"] == "blinded_manual_run_pass_rate.v1"
    assert len(protocol["primary_metric"]["confirmation_success_rule"]) == 4
    assert len(protocol["manual_review"]["rubric"]) == 3
    assert protocol["manual_review"]["reviewers"] == 2
    assert protocol["stopping_conditions"]["terminal"]


def test_freeze_build_binds_27_inputs_and_stays_within_registered_budget(tmp_path: Path) -> None:
    revision = {
        "evidence_source": "test",
        "immutable": True,
        "issued_at": "2026-08-13T00:00:00Z",
        "model": "deepseek-v4-flash",
        "production_release": True,
        "provider": "deepseek_official",
        "revision": "7872f01b1d1fe23eabc4c98b48bffcef5a386062",
    }
    revision_path = tmp_path / "revision.json"
    _write_json(revision_path, revision)
    registration = json.loads(REGISTRATION.read_text(encoding="utf-8"))
    registration["provider"]["model_revision_evidence_file_sha256"] = _sha256(revision_path)
    registration_path = tmp_path / "registration.json"
    _write_json(registration_path, registration)

    protocol, schedule, prepared = build_freeze(
        manifest_path=MANIFEST,
        registration_path=registration_path,
        implementation_commit="test-implementation",
        model_revision_evidence_path=revision_path,
    )

    assert len(schedule["items"]) == len(prepared) == 27
    assert protocol["budget"]["paid_call_count"] == 27
    assert protocol["budget"]["conservative_batch_bound"] <= 850000
    assert protocol["budget"]["bound_within_budget"] is True
    assert protocol["formal_ready"] is True
