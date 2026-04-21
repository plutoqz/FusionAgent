from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class ScenarioRegistryService:
    def __init__(self, *, output_root: Path) -> None:
        self.output_root = Path(output_root)
        self.index_path = self.output_root / "scenario_runs_index.jsonl"

    def record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        self.output_root.mkdir(parents=True, exist_ok=True)
        payload = dict(record)
        with self.index_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return payload

    def list_records(self, *, limit: int = 50, phase: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.index_path.exists() or limit <= 0:
            return []

        records: List[Dict[str, Any]] = []
        for line in self.index_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if phase is not None and record.get("phase") != phase:
                continue
            records.append(record)
            if len(records) >= limit:
                break
        return records

    def get_summary(self, scenario_id: str) -> Dict[str, Any]:
        summary_path = self.output_root / scenario_id / "scenario_summary.json"
        return json.loads(summary_path.read_text(encoding="utf-8"))
