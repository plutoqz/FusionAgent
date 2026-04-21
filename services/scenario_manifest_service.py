from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from schemas.scenario import ScenarioRunRequest
from schemas.scenario_manifest import ScenarioEvalCase, ScenarioEvalManifest


def load_scenario_manifest(path: Path) -> ScenarioEvalManifest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    manifest = ScenarioEvalManifest.model_validate(payload)
    if not manifest.cases:
        raise ValueError("Scenario manifest must contain at least one case.")
    return manifest


def scenario_case_to_request(case: ScenarioEvalCase, *, output_root: Optional[str] = None) -> ScenarioRunRequest:
    metadata = dict(case.metadata)
    metadata["case_id"] = case.case_id
    metadata["expected_phase"] = list(case.expected_phase)
    metadata["tags"] = list(case.tags)
    return ScenarioRunRequest(
        scenario_name=case.scenario_name,
        trigger_content=case.trigger_content,
        disaster_type=case.disaster_type,
        job_types=list(case.job_types),
        output_root=output_root,
        target_crs=case.target_crs,
        metadata=metadata,
    )
