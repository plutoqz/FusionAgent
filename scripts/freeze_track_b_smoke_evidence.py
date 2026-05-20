from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.smoke_agentic_region import _write_evidence_bundle


DEFAULT_EVIDENCE_ROOT = REPO_ROOT / "runs" / "2026-05-18-smoke-evidence"
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "docs" / "superpowers" / "specs" / "2026-05-18-track-b-smoke-evidence-freeze-8010.json"
)


@dataclass(frozen=True)
class SmokeSnapshot:
    theme: str
    inspection_json: Path
    evidence_dir_name: str


DEFAULT_SNAPSHOTS = (
    SmokeSnapshot("building", REPO_ROOT / "runs" / "smoke-building-gitega-city-inspection-8012.json", "building"),
    SmokeSnapshot("road", REPO_ROOT / "runs" / "smoke-road-gilgit-city-inspection-8012.json", "road-aoi"),
    SmokeSnapshot("water", REPO_ROOT / "runs" / "smoke-water-nairobi-inspection-8012.json", "water"),
    SmokeSnapshot("poi", REPO_ROOT / "runs" / "smoke-poi-nairobi-inspection-8012.json", "poi"),
)


def _repo_relative(path: Path, *, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(Path(repo_root).resolve()).as_posix()
    except ValueError:
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def freeze_track_b_smoke_evidence(
    *,
    evidence_root: Path,
    output_json: Path,
    captured_at: str,
    snapshots: tuple[SmokeSnapshot, ...] = DEFAULT_SNAPSHOTS,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    evidence_root = Path(evidence_root)
    evidence_root.mkdir(parents=True, exist_ok=True)

    runs: list[dict[str, Any]] = []
    for snapshot in snapshots:
        inspection = _load_json(snapshot.inspection_json)
        evidence_dir = evidence_root / snapshot.evidence_dir_name
        _write_evidence_bundle(evidence_dir, inspection)

        selected_sources = _load_json(evidence_dir / "selected_sources.json")
        inspection_summary = _load_json(evidence_dir / "inspection_summary.json")
        run_payload = inspection.get("run") or {}
        trigger = run_payload.get("trigger") or {}

        runs.append(
            {
                "theme": snapshot.theme,
                "job_type": run_payload.get("job_type"),
                "query": trigger.get("content"),
                "run_id": run_payload.get("run_id"),
                "claim_state": inspection_summary.get("claim_state"),
                "status": run_payload.get("phase"),
                "evidence_dir": _repo_relative(evidence_dir, repo_root=repo_root),
                "inspection_summary": _repo_relative(evidence_dir / "inspection_summary.json", repo_root=repo_root),
                "artifact_path": str((run_payload.get("artifact") or {}).get("path") or ""),
                "selected_source_id": selected_sources.get("selected_source_id"),
                "selected_pattern_id": inspection_summary.get("selected_pattern_id"),
                "source_mode": selected_sources.get("source_mode"),
                "cache_hit": bool(selected_sources.get("cache_hit", False)),
                "component_source_ids": list(selected_sources.get("component_source_ids") or []),
            }
        )

    payload = {
        "captured_at": captured_at,
        "scope": "Track B bounded smoke evidence freeze rebuilt from repo-local inspection snapshots",
        "worktree": ".",
        "evidence_root": _repo_relative(evidence_root, repo_root=repo_root),
        "runtime_notes": [
            "Repo-local smoke evidence bundles were rebuilt from checked-in inspection snapshots to restore freeze path integrity.",
            "The refreshed smoke bundle keeps building, road, water, and poi on one operator-readable evidence contract without requiring a live 8010 runtime replay.",
        ],
        "runs": runs,
    }

    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rebuild Track B smoke evidence bundles and freeze JSON from saved inspections.")
    parser.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--captured-at", default="2026-05-20")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    freeze_track_b_smoke_evidence(
        evidence_root=Path(args.evidence_root),
        output_json=Path(args.output_json),
        captured_at=str(args.captured_at),
        repo_root=REPO_ROOT,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
