from pathlib import Path

from scripts.audit_benchmark_platform_p6 import audit_p6, load


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "docs/current/benchmark/platform/v1/implementation/p6_checkpoint.json"


def test_bp6_machine_audit_passes() -> None:
    result = audit_p6(ROOT, CHECKPOINT)
    assert result["overall_passed"] is True
    assert result["required_failures"] == []
    assert result["next_stage"] == "P7/BP7"


def test_bp6_checkpoint_stops_before_implementation_freeze() -> None:
    checkpoint = load(CHECKPOINT)
    assert checkpoint["next_stage"] == {"stage": "P7", "gate": "BP7", "automatic_progression": False}
    assert checkpoint["scope"]["p7_freeze_allowed"] is False
    assert checkpoint["accounting"]["benchmark_instances_generated"] == 0
