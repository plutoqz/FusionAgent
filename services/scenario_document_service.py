from __future__ import annotations

from pathlib import Path, PurePosixPath

from schemas.ui_assets import MarkdownDocumentResponse, ScenarioDocumentEntry


class ScenarioDocumentService:
    def __init__(self, *, output_root: Path) -> None:
        self.output_root = Path(output_root).resolve()

    def list_documents(self, scenario_id: str) -> list[ScenarioDocumentEntry]:
        documents_dir = self._documents_dir(scenario_id)
        entries: list[ScenarioDocumentEntry] = []
        for path in sorted(documents_dir.rglob("*.md"), key=lambda item: item.relative_to(documents_dir).as_posix()):
            filename = path.relative_to(documents_dir).as_posix()
            entries.append(
                ScenarioDocumentEntry(
                    filename=filename,
                    path=self._document_api_path(scenario_id, filename),
                    size_bytes=path.stat().st_size,
                    language=_infer_language(filename),
                )
            )
        return entries

    def read_document(self, scenario_id: str, filename: str) -> MarkdownDocumentResponse:
        documents_dir = self._documents_dir(scenario_id)
        path = self._resolve_document_path(documents_dir, filename)
        normalized_filename = path.relative_to(documents_dir).as_posix()
        return MarkdownDocumentResponse(
            scenario_id=scenario_id,
            filename=normalized_filename,
            path=self._document_api_path(scenario_id, normalized_filename),
            content=path.read_text(encoding="utf-8"),
            size_bytes=path.stat().st_size,
            language=_infer_language(normalized_filename),
        )

    def _documents_dir(self, scenario_id: str) -> Path:
        normalized_scenario_id = _normalize_scenario_id(scenario_id)
        scenario_dir = (self.output_root / normalized_scenario_id).resolve()
        try:
            scenario_dir.relative_to(self.output_root)
        except ValueError as exc:
            raise FileNotFoundError(f"Scenario run not found: {scenario_id}") from exc
        summary_path = scenario_dir / "scenario_summary.json"
        if not summary_path.exists():
            raise FileNotFoundError(f"Scenario run not found: {scenario_id}")
        documents_dir = scenario_dir / "documents"
        if not documents_dir.exists() or not documents_dir.is_dir():
            raise FileNotFoundError(f"Scenario documents not found: {scenario_id}")
        return documents_dir.resolve()

    def _resolve_document_path(self, documents_dir: Path, filename: str) -> Path:
        normalized = _normalize_filename(filename)
        candidate = (documents_dir / Path(*normalized.parts)).resolve()
        try:
            candidate.relative_to(documents_dir)
        except ValueError as exc:
            raise FileNotFoundError(f"Document not found: {filename}") from exc
        if not candidate.exists() or not candidate.is_file() or candidate.suffix.lower() != ".md":
            raise FileNotFoundError(f"Document not found: {filename}")
        return candidate

    @staticmethod
    def _document_api_path(scenario_id: str, filename: str) -> str:
        return f"/api/v2/scenario-runs/{scenario_id}/documents/{filename}"


def _normalize_filename(filename: str) -> PurePosixPath:
    normalized = PurePosixPath((filename or "").replace("\\", "/"))
    if not normalized.parts or normalized.is_absolute():
        raise FileNotFoundError(f"Document not found: {filename}")
    if any(part in {"", ".", ".."} for part in normalized.parts):
        raise FileNotFoundError(f"Document not found: {filename}")
    return normalized


def _normalize_scenario_id(scenario_id: str) -> str:
    normalized = PurePosixPath((scenario_id or "").replace("\\", "/"))
    if normalized.is_absolute() or len(normalized.parts) != 1:
        raise FileNotFoundError(f"Scenario run not found: {scenario_id}")
    part = normalized.parts[0]
    if part in {"", ".", ".."}:
        raise FileNotFoundError(f"Scenario run not found: {scenario_id}")
    return part


def _infer_language(filename: str) -> str | None:
    parts = Path(filename).name.split(".")
    if len(parts) >= 3 and parts[-2] in {"zh", "en"}:
        return parts[-2]
    return None
