from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from schemas.experiment_evidence import ExperimentEvidenceManifest


def render_tables(manifest_paths: list[Path], *, output_markdown: Path) -> dict[str, Any]:
    manifests = [
        ExperimentEvidenceManifest.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
        for path in manifest_paths
    ]
    payload = {
        "experiment_count": len(manifests),
        "experiments": [manifest.model_dump(mode="json") for manifest in manifests],
    }
    output_markdown = Path(output_markdown)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.write_text(_render_markdown(payload), encoding="utf-8")
    return payload


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Thesis Evidence Tables",
        "",
        "| Experiment | Commit | Seed Hash | Runtime Settings Hash | Metric Definition Hash | File Count |",
        "| --- | --- | --- | --- | --- | ---: |",
    ]
    for experiment in payload["experiments"]:
        lines.append(
            "| {experiment_id} | {commit_sha} | {seed_hash} | {runtime_settings_hash} | {metric_definition_hash} | {file_count} |".format(
                experiment_id=experiment["experiment_id"],
                commit_sha=experiment["commit_sha"],
                seed_hash=experiment["seed_hash"],
                runtime_settings_hash=experiment["runtime_settings_hash"],
                metric_definition_hash=experiment["metric_definition_hash"],
                file_count=len(experiment["files"]),
            )
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render thesis tables from Freeze C experiment manifests."
    )
    parser.add_argument("--manifest", action="append", required=True)
    parser.add_argument("--output-markdown", required=True)
    args = parser.parse_args(argv)
    print(
        json.dumps(
            render_tables(
                [Path(item) for item in args.manifest],
                output_markdown=Path(args.output_markdown),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
