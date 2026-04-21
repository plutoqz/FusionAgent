from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class RunRegistryService:
    def __init__(self, *, runs_root: Path) -> None:
        self.runs_root = Path(runs_root)

    def list_records(
        self,
        *,
        limit: int = 50,
        phase: Optional[str] = None,
        job_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        bounded_limit = min(limit, 100)
        if bounded_limit <= 0 or not self.runs_root.exists():
            return []

        candidates: List[Tuple[float, Path]] = []
        for run_json_path in self.runs_root.glob("*/run.json"):
            try:
                candidates.append((run_json_path.stat().st_mtime, run_json_path))
            except OSError:
                continue
        candidates.sort(key=lambda item: item[0], reverse=True)

        records: List[Dict[str, Any]] = []
        for _, run_json_path in candidates:
            try:
                record = json.loads(run_json_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                continue
            if not isinstance(record, dict):
                continue
            if phase is not None and record.get("phase") != phase:
                continue
            if job_type is not None and record.get("job_type") != job_type:
                continue
            payload = dict(record)
            payload["run_dir"] = str(run_json_path.parent.resolve())
            records.append(payload)
            if len(records) >= bounded_limit:
                break
        return records
