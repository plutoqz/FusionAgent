from __future__ import annotations

import json
import subprocess
import sys


def test_freeze_a_runtime_contract_check_outputs_passing_report() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/freeze_a_runtime_contract_check.py", "--json"],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)

    assert payload["ok"] is True
    assert payload["deprecated_algorithm_guard"]["ok"] is True
    assert payload["tool_registry_guard"]["ok"] is True
    assert payload["workflow_pattern_guard"]["ok"] is True
    assert payload["validator_mode"]["default"] == "enforce"
