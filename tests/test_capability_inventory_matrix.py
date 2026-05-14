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
    assert building["building.scale_validation_source_profiling"]["claim_state"] == "research_utility"
    assert building["building.multisource_fusion_semantics"]["status"] == "optional"
    assert building["building.multisource_fusion_semantics"]["claim_state"] == "research_utility"

