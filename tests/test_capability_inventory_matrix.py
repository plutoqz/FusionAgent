import json
from pathlib import Path


def test_capability_matrix_tracks_status_and_evidence() -> None:
    payload = json.loads(
        Path("docs/superpowers/specs/2026-05-06-capability-matrix.json").read_text(
            encoding="utf-8"
        )
    )

    assert "building" in payload["themes"]
    assert "core_next" in payload["status_vocab"]
    assert "evidence_contract" in payload["required_fields"]

