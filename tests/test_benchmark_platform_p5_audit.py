from pathlib import Path

from scripts.audit_benchmark_platform_p5 import audit_p5, load


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "docs/current/benchmark/platform/v1/implementation/p5_checkpoint.json"


def test_bp5_machine_audit_passes() -> None:
    result = audit_p5(ROOT, CHECKPOINT)
    assert result["overall_passed"] is True
    assert result["required_failures"] == []
    assert result["next_stage"] == "P6/BP6"


def test_bp5_checkpoint_stops_before_cli() -> None:
    checkpoint = load(CHECKPOINT)
    assert checkpoint["next_stage"] == {"stage": "P6", "gate": "BP6", "automatic_progression": False}
    assert checkpoint["scope"]["cli_allowed"] is False
    assert checkpoint["accounting"]["benchmark_instances_generated"] == 0
