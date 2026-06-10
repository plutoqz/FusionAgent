from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from schemas.experiment_evidence import ExperimentEvidenceManifest
from services.experiment_evidence_service import (
    build_experiment_manifest,
    verify_experiment_manifest,
)


def freeze_experiment(
    *,
    experiment_id: str,
    output_dir: Path,
    output_json: Path,
    commit_sha: str,
    seed_hash: str,
    runtime_settings_hash: str,
    metric_definition_hash: str,
) -> ExperimentEvidenceManifest:
    manifest = build_experiment_manifest(
        experiment_id=experiment_id,
        output_dir=output_dir,
        commit_sha=commit_sha,
        seed_hash=seed_hash,
        runtime_settings_hash=runtime_settings_hash,
        metric_definition_hash=metric_definition_hash,
    )
    failures = verify_experiment_manifest(manifest)
    if failures:
        raise RuntimeError("; ".join(failures))
    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest


def _current_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
    ).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze an experiment output directory for Freeze C."
    )
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--seed-hash", required=True)
    parser.add_argument("--runtime-settings-hash", required=True)
    parser.add_argument("--metric-definition-hash", required=True)
    parser.add_argument("--commit-sha", default="")
    args = parser.parse_args(argv)
    manifest = freeze_experiment(
        experiment_id=args.experiment_id,
        output_dir=Path(args.output_dir),
        output_json=Path(args.output_json),
        commit_sha=args.commit_sha or _current_commit(),
        seed_hash=args.seed_hash,
        runtime_settings_hash=args.runtime_settings_hash,
        metric_definition_hash=args.metric_definition_hash,
    )
    print(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
