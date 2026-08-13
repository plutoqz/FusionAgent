import json
from pathlib import Path

from schemas.research_llm_pilot import build_research_llm_formal_schedule
from scripts.freeze_research_formal_protocol import build_formal_freeze, verify_formal_freeze, write_formal_freeze


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"


def test_formal_schedule_is_seeded_18_call_six_case_cross_product() -> None:
    first = build_research_llm_formal_schedule(schedule_seed=20260813)
    second = build_research_llm_formal_schedule(schedule_seed=20260813)

    assert [item.run_id for item in first.items] == [item.run_id for item in second.items]
    assert len(first.items) == 18
    assert {(item.case_id, item.knowledge_condition) for item in first.items} == {
        (case_id, condition)
        for case_id in ("C01", "C02", "C03", "C04", "C05", "C06")
        for condition in ("llm_only", "llm_capability_kg", "llm_full_contract_kg")
    }
    assert first.metadata["stability_claim_eligible"] is False


def test_formal_freeze_hashes_assets_and_keeps_immutable_model_blocker(tmp_path: Path) -> None:
    payload = build_formal_freeze(manifest_path=MANIFEST, implementation_commit="commit-under-test")
    output = tmp_path / "formal-freeze"
    write_formal_freeze(output, payload)
    audit = verify_formal_freeze(output)

    assert payload["protocol"]["design"]["llm_call_count"] == 18
    assert payload["protocol"]["budget"]["bound_within_budget"] is True
    assert payload["protocol"]["formal_ready"] is False
    assert payload["protocol"]["formal_blockers"] == [
        "provider_immutable_model_revision_not_evidenced"
    ]
    assert payload["protocol"]["provider"]["model_registry_probe"] == {
        "observed_on": "2026-08-13",
        "endpoint": "/models",
        "id": "deepseek-v4-flash",
        "object": "model",
        "owned_by": "deepseek",
        "created": None,
        "immutable_revision_field_present": False,
    }
    assert audit["checks"]["schedule_hash"] is True
    assert audit["checks"]["prepared_inputs_hash"] is True
    assert audit["checks"]["immutable_model_revision"] is False
    assert audit["passed"] is False


def test_formal_freeze_accepts_and_hashes_provider_revision_evidence(tmp_path: Path) -> None:
    evidence = {
        "provider": "deepseek_official",
        "model": "deepseek-v4-flash",
        "revision": "provider-revision-2026-08-13",
        "immutable": True,
        "production_release": True,
        "evidence_source": "provider-issued model release record",
        "issued_at": "2026-08-13T00:00:00Z",
    }
    evidence_path = tmp_path / "provider-evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    payload = build_formal_freeze(
        manifest_path=MANIFEST,
        implementation_commit="commit-under-test",
        model_revision_evidence_path=evidence_path,
    )
    output = tmp_path / "formal-freeze"
    write_formal_freeze(output, payload)
    audit = verify_formal_freeze(output)

    assert payload["protocol"]["formal_ready"] is True
    assert payload["protocol"]["formal_blockers"] == []
    assert payload["protocol"]["provider"]["model_revision"] == evidence["revision"]
    assert audit["checks"]["immutable_model_revision"] is True
    assert audit["passed"] is True


def test_formal_freeze_rejects_unqualified_revision_evidence(tmp_path: Path) -> None:
    evidence_path = tmp_path / "provider-evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "provider": "deepseek_official",
                "model": "deepseek-v4-flash",
                "revision": "mutable-alias",
                "immutable": False,
                "production_release": True,
                "evidence_source": "provider response",
                "issued_at": "2026-08-13T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    try:
        build_formal_freeze(
            manifest_path=MANIFEST,
            implementation_commit="commit-under-test",
            model_revision_evidence_path=evidence_path,
        )
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("Expected unqualified revision evidence to be rejected")
