from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from services.run_registry_service import RunRegistryService
from services.scenario_registry_service import ScenarioRegistryService


class OperatorReadModelService:
    def __init__(self, *, runs_root: Path, scenario_output_root: Path) -> None:
        self.runs_root = Path(runs_root)
        self.scenario_output_root = Path(scenario_output_root)

    def runtime_summary(self, *, limit: int = 10) -> Dict[str, Any]:
        recent_runs = RunRegistryService(runs_root=self.runs_root).list_records(limit=limit)
        recent_scenarios = ScenarioRegistryService(output_root=self.scenario_output_root).list_records(limit=limit)

        evidence_gaps: List[str] = []
        if not recent_runs:
            evidence_gaps.append("No persisted runs found.")
        if not recent_scenarios:
            evidence_gaps.append("No persisted scenario runs found.")

        return {
            "runtime": {
                "kg_backend": os.getenv("GEOFUSION_KG_BACKEND"),
                "llm_provider": os.getenv("GEOFUSION_LLM_PROVIDER"),
                "celery_eager": os.getenv("GEOFUSION_CELERY_EAGER"),
                "api_port": os.getenv("GEOFUSION_API_PORT"),
            },
            "recent_runs": recent_runs,
            "recent_scenarios": recent_scenarios,
            "evidence_gaps": evidence_gaps,
        }
