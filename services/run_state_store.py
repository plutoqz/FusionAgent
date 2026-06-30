from __future__ import annotations

import json
from pathlib import Path

from schemas.agent import RunCreateRequest, RunEvent, RunStatus, WorkflowPlan
from services.plan_grounding_service import ensure_plan_grounding_report


class RunStateStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)

    def run_dir(self, run_id: str) -> Path:
        return self.base_dir / run_id

    def plan_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "plan.json"

    def validation_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "validation.json"

    def audit_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "audit.jsonl"

    def persist_status(self, status: RunStatus) -> None:
        run_dir = self.run_dir(status.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        data = status.model_dump(mode="json")
        (run_dir / "run.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_status(self, run_id: str) -> RunStatus | None:
        path = self.run_dir(run_id) / "run.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return RunStatus.model_validate(payload)

    @staticmethod
    def persist_request(path: Path, request: RunCreateRequest) -> None:
        path.write_text(json.dumps(request.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def persist_plan(path: Path, plan: WorkflowPlan, *, revision: int) -> None:
        ensure_plan_grounding_report(plan)
        payload = json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2)
        path.write_text(payload, encoding="utf-8")
        if revision > 0:
            path.with_name(f"plan-revision-{revision}.json").write_text(payload, encoding="utf-8")

    @staticmethod
    def persist_validation(path: Path, plan: WorkflowPlan) -> None:
        payload = plan.validation.model_dump(mode="json") if plan.validation is not None else {}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def append_audit_event(self, status: RunStatus, event: RunEvent) -> None:
        path = Path(status.audit_path) if status.audit_path else self.audit_path(status.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False))
            handle.write("\n")
        status.audit_path = str(path)
        status.event_count += 1
        status.last_event = event
