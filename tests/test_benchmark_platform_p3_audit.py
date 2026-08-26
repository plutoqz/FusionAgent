from pathlib import Path

from scripts.audit_benchmark_platform_p3 import audit_p3, load


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "docs/current/benchmark/platform/v1/implementation/p3_checkpoint.json"


def test_bp3_machine_audit_passes() -> None:
    result = audit_p3(ROOT, CHECKPOINT)
    assert result["overall_passed"] is True
    assert result["required_failures"] == []
    assert result["next_stage"] == "P4/BP4"


def test_bp3_checkpoint_has_no_external_execution_accounting() -> None:
    checkpoint = load(CHECKPOINT)
    assert checkpoint["accounting"]["benchmark_instances_generated"] == 0
    assert checkpoint["accounting"]["provider_calls"] == 0
    assert checkpoint["accounting"]["judge_calls"] == 0
