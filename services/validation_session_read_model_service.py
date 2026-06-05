from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from schemas.engineering_validation import EngineeringValidationSummary
from schemas.evidence_lifecycle import ValidationSessionManifest


def resolve_validation_output_root(output_root: Path | str | None = None) -> Path:
    if output_root is not None:
        return Path(output_root)
    return Path(os.getenv("GEOFUSION_VALIDATION_OUTPUT_ROOT", "runs/engineering-validation"))


class ValidationSessionReadModelService:
    def __init__(self, *, output_root: Path | str | None = None) -> None:
        self.output_root = resolve_validation_output_root(output_root).resolve()

    def list_sessions(self, *, limit: int = 50) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        if not self.output_root.exists():
            return records

        for manifest_path in self.output_root.rglob("validation_session.json"):
            record = self._load_record(manifest_path)
            if record is not None:
                records.append(record)

        records.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return records[:limit]

    def get_session(self, session_id: str) -> dict[str, Any]:
        for record in self.list_sessions(limit=1000):
            if record.get("session_id") == session_id:
                return record
        raise FileNotFoundError(session_id)

    def _load_record(self, manifest_path: Path) -> dict[str, Any] | None:
        manifest_payload = self._read_json_object(manifest_path)
        if manifest_payload is None:
            return None

        try:
            manifest = ValidationSessionManifest.model_validate(manifest_payload)
        except Exception:  # noqa: BLE001
            return None

        summary_path = self._resolve_summary_path(manifest_path, manifest)
        if summary_path is None:
            return None

        summary_payload = self._read_json_object(summary_path)
        if summary_payload is None:
            return None

        try:
            summary = EngineeringValidationSummary.model_validate(summary_payload)
        except Exception:  # noqa: BLE001
            return None
        if summary.session_id != manifest.session_id:
            return None

        return {
            "session_id": manifest.session_id,
            "created_at": manifest.created_at,
            "git_commit": manifest.git_commit,
            "matrix_path": manifest.matrix_path,
            "output_dir": str(manifest_path.parent),
            "manifest_path": str(manifest_path),
            "summary_path": str(summary_path),
            "markdown_summary_path": manifest.markdown_summary_path,
            "runtime": manifest.runtime,
            "metadata": manifest.metadata,
            "summary": summary.model_dump(mode="json"),
        }

    def _resolve_summary_path(self, manifest_path: Path, manifest: ValidationSessionManifest) -> Path | None:
        session_dir = manifest_path.parent.resolve()
        candidates: list[Path] = []
        if manifest.summary_path:
            candidates.append(Path(manifest.summary_path))
        else:
            candidates.append(Path("validation_summary.json"))

        for candidate in candidates:
            resolved = (candidate if candidate.is_absolute() else session_dir / candidate).resolve()
            if self._is_allowed_summary_path(resolved, session_dir) and resolved.is_file():
                return resolved
        return None

    def _is_allowed_summary_path(self, resolved_path: Path, session_dir: Path) -> bool:
        try:
            resolved_path.relative_to(session_dir)
            return True
        except ValueError:
            pass

        try:
            resolved_path.relative_to(self.output_root)
        except ValueError:
            return False
        return resolved_path.name == "validation_summary.json"

    @staticmethod
    def _read_json_object(path: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        return payload if isinstance(payload, dict) else None
