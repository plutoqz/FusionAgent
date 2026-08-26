from pathlib import Path

from scripts.audit_benchmark_platform_p4 import audit_p4, load


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "docs/current/benchmark/platform/v1/implementation/p4_checkpoint.json"


def test_bp4_machine_audit_passes() -> None:
    result = audit_p4(ROOT, CHECKPOINT)
    assert result["overall_passed"] is True
    assert result["required_failures"] == []
    assert result["next_stage"] == "P5/BP5"


def test_bp4_checkpoint_stops_before_store() -> None:
    checkpoint = load(CHECKPOINT)
    assert checkpoint["next_stage"]["stage"] == "P5"
    assert checkpoint["next_stage"]["automatic_progression"] is False
    assert checkpoint["accounting"]["benchmark_instances_generated"] == 0
