from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from services.run_registry_service import RunRegistryService
from services.scenario_registry_service import ScenarioRegistryService
from worker.celery_app import describe_beat_schedule
from worker.tasks import recovery_tick_control_state, scheduled_tick_control_state


ACTIVE_PHASES = {"queued", "planning", "validating", "running", "healing"}


class OperatorReadModelService:
    def __init__(self, *, runs_root: Path, scenario_output_root: Path) -> None:
        self.runs_root = Path(runs_root)
        self.scenario_output_root = Path(scenario_output_root)

    def runtime_summary(self, *, limit: int = 10) -> Dict[str, Any]:
        recent_runs = RunRegistryService(runs_root=self.runs_root).list_records(limit=limit)
        recent_scenarios = ScenarioRegistryService(output_root=self.scenario_output_root).list_records(limit=limit)
        beat_schedule = describe_beat_schedule()
        active_runs = [record for record in recent_runs if str(record.get("phase") or "").strip() in ACTIVE_PHASES]
        active_phase_counts = self._active_phase_counts()

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
                "worker_controls": {
                    "scheduled_tick": {
                        **scheduled_tick_control_state(),
                        "beat_entry": "scheduled-run-producer",
                        "beat_interval_seconds": beat_schedule.get("scheduled-run-producer", {}).get(
                            "beat_interval_seconds",
                            0.0,
                        ),
                    },
                    "recovery_tick": {
                        **recovery_tick_control_state(),
                        "beat_entry": "recovery-run-producer",
                        "beat_interval_seconds": beat_schedule.get("recovery-run-producer", {}).get(
                            "beat_interval_seconds",
                            0.0,
                        ),
                    },
                },
                "queue_state": {
                    "broker": os.getenv("GEOFUSION_CELERY_BROKER", "redis://localhost:6379/0"),
                    "backend": os.getenv(
                        "GEOFUSION_CELERY_BACKEND",
                        os.getenv("GEOFUSION_CELERY_BROKER", "redis://localhost:6379/0"),
                    ),
                    "active_phase_counts": active_phase_counts,
                    "active_runs": active_runs,
                },
            },
            "recent_runs": recent_runs,
            "recent_scenarios": recent_scenarios,
            "evidence_gaps": evidence_gaps,
        }

    def _active_phase_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        if not self.runs_root.exists():
            return counts

        for run_json_path in self.runs_root.glob("*/run.json"):
            try:
                payload = run_json_path.read_text(encoding="utf-8")
            except OSError:
                continue
            phase = self._phase_from_json(payload)
            if phase not in ACTIVE_PHASES:
                continue
            counts[phase] = counts.get(phase, 0) + 1
        return counts

    @staticmethod
    def _phase_from_json(payload: str) -> str:
        import json

        try:
            record = json.loads(payload)
        except json.JSONDecodeError:
            return ""
        if not isinstance(record, dict):
            return ""
        return str(record.get("phase") or "").strip()
