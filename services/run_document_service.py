from __future__ import annotations

from pathlib import Path, PurePosixPath

from schemas.ui_assets import RunDocumentEntry, RunMarkdownDocumentResponse


class RunDocumentService:
    def __init__(self, *, runs_root: Path) -> None:
        self.runs_root = Path(runs_root).resolve()

    def list_documents(self, run_id: str) -> list[RunDocumentEntry]:
        documents_dir = self._documents_dir(run_id)
        entries: list[RunDocumentEntry] = []
        for path in sorted(documents_dir.rglob("*.md"), key=lambda item: item.relative_to(documents_dir).as_posix()):
            filename = path.relative_to(documents_dir).as_posix()
            entries.append(
                RunDocumentEntry(
                    filename=filename,
                    path=self._document_api_path(run_id, filename),
                    size_bytes=path.stat().st_size,
                    language=_infer_language(filename),
                )
            )
        return entries

    def read_document(self, run_id: str, filename: str) -> RunMarkdownDocumentResponse:
        documents_dir = self._documents_dir(run_id)
        path = self._resolve_document_path(documents_dir, filename)
        normalized_filename = path.relative_to(documents_dir).as_posix()
        return RunMarkdownDocumentResponse(
            run_id=run_id,
            filename=normalized_filename,
            path=self._document_api_path(run_id, normalized_filename),
            content=path.read_text(encoding="utf-8"),
            size_bytes=path.stat().st_size,
            language=_infer_language(normalized_filename),
        )

    def _documents_dir(self, run_id: str) -> Path:
        normalized_run_id = _normalize_run_id(run_id)
        run_dir = (self.runs_root / normalized_run_id).resolve()
        try:
            run_dir.relative_to(self.runs_root)
        except ValueError as exc:
            raise FileNotFoundError(f"Run not found: {run_id}") from exc
        if not (run_dir / "run.json").exists():
            raise FileNotFoundError(f"Run not found: {run_id}")
        documents_dir = run_dir / "documents"
        if not documents_dir.exists() or not documents_dir.is_dir():
            raise FileNotFoundError(f"Run documents not found: {run_id}")
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
    def _document_api_path(run_id: str, filename: str) -> str:
        return f"/api/v2/runs/{run_id}/documents/{filename}"


def _normalize_run_id(run_id: str) -> str:
    normalized = PurePosixPath((run_id or "").replace("\\", "/"))
    if normalized.is_absolute() or len(normalized.parts) != 1:
        raise FileNotFoundError(f"Run not found: {run_id}")
    part = normalized.parts[0]
    if part in {"", ".", ".."}:
        raise FileNotFoundError(f"Run not found: {run_id}")
    return part


def _normalize_filename(filename: str) -> PurePosixPath:
    normalized = PurePosixPath((filename or "").replace("\\", "/"))
    if not normalized.parts or normalized.is_absolute():
        raise FileNotFoundError(f"Document not found: {filename}")
    if any(part in {"", ".", ".."} for part in normalized.parts):
        raise FileNotFoundError(f"Document not found: {filename}")
    return normalized


def _infer_language(filename: str) -> str | None:
    parts = Path(filename).name.split(".")
    if len(parts) >= 3 and parts[-2] in {"zh", "en"}:
        return parts[-2]
    return None
