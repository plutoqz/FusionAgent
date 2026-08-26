from pathlib import Path

from scripts.audit_benchmark_platform_p2 import audit_p2, load


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "docs/current/benchmark/platform/v1/implementation/p2_checkpoint.json"


def test_bp2_machine_audit_passes() -> None:
    result = audit_p2(ROOT, CHECKPOINT, probe=False)
    assert result["overall_passed"] is True
    assert result["required_failures"] == []
    assert result["next_stage"] == "P3/BP3"


def test_bp2_checkpoint_keeps_zero_call_accounting_and_no_output_root() -> None:
    checkpoint = load(CHECKPOINT)
    assert checkpoint["accounting"]["benchmark_instances_generated"] == 0
    assert checkpoint["accounting"]["provider_calls"] == 0
    assert checkpoint["accounting"]["judge_calls"] == 0
    assert not Path(checkpoint["paths"]["future_output_root"]).exists()
