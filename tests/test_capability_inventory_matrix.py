import json
from pathlib import Path


def test_capability_matrix_tracks_status_and_evidence() -> None:
    payload = json.loads(
        Path("docs/superpowers/specs/2026-05-06-capability-matrix.json").read_text(
            encoding="utf-8"
        )
    )
    building = {
        item["capability_id"]: item for item in payload["themes"]["building"]
    }

    assert "building" in payload["themes"]
    assert "core_next" in payload["status_vocab"]
    assert "evidence_contract" in payload["required_fields"]
    assert building["building.large_aoi_tiled_runtime"]["claim_state"] == "runtime_supported"
    assert "selected_sources.json" in building["building.large_aoi_tiled_runtime"]["evidence_contract"]
    assert "stitched_artifact.json" in building["building.large_aoi_tiled_runtime"]["evidence_contract"]
    assert building["building.scale_validation_source_profiling"]["claim_state"] == "research_utility"
    assert building["building.scale_validation_cleanup_rules"]["claim_state"] == "research_utility"
    assert building["building.multisource_fusion_semantics"]["status"] == "optional"
    assert building["building.multisource_fusion_semantics"]["claim_state"] == "research_utility"
    assert "inspection_summary.json" in building["building.multisource_fusion_semantics"]["evidence_contract"]
    assert "stitched_artifact.json" in building["building.multisource_fusion_semantics"]["evidence_contract"]
    assert "docs/v2-operations.md" in building["building.multisource_fusion_semantics"]["owner_files"]
    runtime = building["building.multisource_height_raster_runtime"]
    assert runtime["status"] == "core"
    assert runtime["claim_state"] == "bounded_supported"
    assert "source_semantic_contract.json" in runtime["evidence_contract"]
    assert "height_final_source" in runtime["evidence_contract"]


def test_capability_matrix_tracks_runtime_hardening_evidence_boundary() -> None:
    payload = json.loads(
        Path("docs/superpowers/specs/2026-05-06-capability-matrix.json").read_text(
            encoding="utf-8"
        )
    )
    evidence = {
        item["capability_id"]: item for item in payload["themes"]["evidence"]
    }

    item = evidence["evidence.tool_contracts_grounding_recovery"]
    assert item["status"] in {"core_next", "core"}
    assert "tool_contract_report" in item["evidence_contract"]
    assert "grounding_report" in item["evidence_contract"]
    assert "recovery_hint" in item["evidence_contract"]

    redispatch = evidence["evidence.recovery_redispatch"]
    assert redispatch["status"] == "core"
    assert redispatch["claim_state"] == "runtime_supported"
    assert "recovery.history.jsonl" in redispatch["evidence_contract"]
    assert "geofusion.recovery_tick" in redispatch["evidence_contract"]

    semantics = evidence["source_semantics.runtime_binding"]
    assert semantics["status"] == "core"
    assert semantics["claim_state"] == "runtime_supported"
    assert "source_semantic_contract.json" in semantics["evidence_contract"]

