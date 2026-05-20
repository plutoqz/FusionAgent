from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


DEFAULT_EVIDENCE_ROOT = REPO_ROOT / "runs" / "2026-05-18-track-b-national-evidence"
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "docs" / "superpowers" / "specs" / "2026-05-18-track-b-national-scale-evidence-freeze.json"
)
DEFAULT_REQUEST_BBOX = (28.976001, -4.698707, 30.884489, -2.30746)
DEFAULT_TARGET_CRS = "EPSG:32735"
DEFAULT_SOURCE_CONTRACT_REF = "docs/superpowers/specs/2026-05-18-track-b-national-source-matrix.md"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _repo_relative(path: Path, *, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(Path(repo_root).resolve()).as_posix()
    except ValueError:
        return str(path)


def _normalize_artifact_map(payload: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for source_id, details in payload.items():
        item = dict(details)
        artifact_path = item.get("artifact_path")
        if artifact_path:
            item["artifact_path"] = _repo_relative(Path(str(artifact_path)), repo_root=repo_root)
        normalized[source_id] = item
    return normalized


def _normalize_component_coverage(payload: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for source_id, details in payload.items():
        item = dict(details)
        path = item.get("path")
        if path:
            item["path"] = _repo_relative(Path(str(path)), repo_root=repo_root)
        normalized[source_id] = item
    return normalized


def _tile_metadata(tile_manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "manifest_mode": tile_manifest.get("manifest_mode"),
        "tile_count": int(tile_manifest.get("tile_count") or len(tile_manifest.get("tiles") or [])),
        "tile_width_m": tile_manifest.get("tile_width_m"),
        "tile_height_m": tile_manifest.get("tile_height_m"),
        "overlap_m": tile_manifest.get("overlap_m"),
        "bbox_crs": tile_manifest.get("bbox_crs"),
        "working_crs": tile_manifest.get("working_crs"),
    }


def _build_runtime_notes(runs: dict[str, dict[str, Any]]) -> list[str]:
    notes: list[str] = []

    road = runs.get("road")
    if road is not None:
        road_cov = road.get("component_coverage", {}).get("raw.overture.transportation", {})
        if road_cov.get("feature_count") == 0:
            notes.append(
                "road keeps raw.overture.transportation as the promoted second source, "
                "but the current bounded download still resolves to an empty optional reference bundle, "
                "so the claim stays national_scale_partial_reference."
            )
        else:
            notes.append(
                "road now materializes raw.overture.transportation with non-empty coverage "
                "alongside raw.osm.road under the national-scale utility."
            )

    water = runs.get("water")
    if water is not None:
        notes.append(
            "water uses raw.osm.water plus raw.hydrolakes.water as the selected polygon pair and "
            "keeps raw.hydrorivers.water as supplemental normalized evidence for the line-style reference."
        )

    poi = runs.get("poi")
    if poi is not None:
        notes.append(
            "poi uses raw.osm.poi plus raw.gns.poi as the selected national pair and "
            "keeps raw.rh.poi as a missing local supplement unless an operator preload is present."
        )

    notes.append("Raw national run directories stay under runs/ and are referenced here instead of being copied into docs/.")
    return notes


def _freeze_theme(theme_dir: Path, *, repo_root: Path) -> dict[str, Any]:
    selected_sources = _load_json(theme_dir / "selected_sources.json")
    inspection_summary = _load_json(theme_dir / "inspection_summary.json")
    normalization_summary = _load_json(theme_dir / "normalization_summary.json")
    stitched_artifact = _load_json(theme_dir / "stitched_artifact.json")
    tile_manifest = _load_json(theme_dir / "tile_manifest.json")
    tile_metadata = _tile_metadata(tile_manifest)

    component_coverage = _normalize_component_coverage(
        selected_sources.get("component_coverage") or {},
        repo_root=repo_root,
    )
    selected_normalized = _normalize_artifact_map(
        normalization_summary.get("selected_sources") or {},
        repo_root=repo_root,
    )
    supplemental_normalized = _normalize_artifact_map(
        normalization_summary.get("supplemental_sources") or {},
        repo_root=repo_root,
    )

    return {
        "theme": selected_sources["job_type"],
        "job_type": selected_sources["job_type"],
        "claim_state": inspection_summary["claim_state"],
        "selected_source_id": selected_sources["selected_source_id"],
        "component_source_ids": list(selected_sources.get("component_source_ids") or []),
        "tile_count": int(inspection_summary.get("tile_count") or stitched_artifact.get("tile_count") or 0),
        "tile_width_m": tile_metadata["tile_width_m"],
        "tile_height_m": tile_metadata["tile_height_m"],
        "overlap_m": tile_metadata["overlap_m"],
        "manifest_mode": tile_metadata["manifest_mode"],
        "tile_manifest_metadata": tile_metadata,
        "artifact_path": _repo_relative(Path(str(inspection_summary["artifact_path"])), repo_root=repo_root),
        "stitched_artifact": _repo_relative(theme_dir / "stitched_artifact.json", repo_root=repo_root),
        "inspection_summary": _repo_relative(theme_dir / "inspection_summary.json", repo_root=repo_root),
        "selected_sources": _repo_relative(theme_dir / "selected_sources.json", repo_root=repo_root),
        "source_profile_snapshot": _repo_relative(theme_dir / "source_profile_snapshot.json", repo_root=repo_root),
        "normalization_summary": _repo_relative(theme_dir / "normalization_summary.json", repo_root=repo_root),
        "tile_manifest": _repo_relative(theme_dir / "tile_manifest.json", repo_root=repo_root),
        "timing": _repo_relative(theme_dir / "timing.json", repo_root=repo_root),
        "artifact_metrics": dict(inspection_summary.get("artifact_metrics") or {}),
        "component_coverage": component_coverage,
        "selected_normalized_sources": selected_normalized,
        "supplemental_normalized_sources": supplemental_normalized,
    }


def freeze_track_b_national_evidence(
    *,
    evidence_root: Path,
    output_json: Path,
    captured_at: str,
    request_bbox: tuple[float, float, float, float],
    target_crs: str,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    evidence_root = Path(evidence_root)
    runs = {
        theme_dir.name: _freeze_theme(theme_dir, repo_root=repo_root)
        for theme_dir in sorted(evidence_root.iterdir())
        if theme_dir.is_dir()
    }
    ordered_runs = [runs[theme] for theme in ("road", "water", "poi") if theme in runs]

    payload = {
        "captured_at": captured_at,
        "scope": "Track B national-scale evidence freeze for the Burundi local-data matrix",
        "worktree": ".",
        "source_contract_ref": DEFAULT_SOURCE_CONTRACT_REF,
        "evidence_root": _repo_relative(evidence_root, repo_root=repo_root),
        "request_bbox": [float(value) for value in request_bbox],
        "request_bbox_crs": "EPSG:4326",
        "request_bbox_note": (
            "Shared Burundi bbox used to keep road/water/poi on the same country bundle boundary "
            "for the refreshed Track B national evidence freeze."
        ),
        "target_crs": target_crs,
        "tile_config_scope": "per_theme",
        "theme_tile_metadata": {
            theme: runs[theme]["tile_manifest_metadata"]
            for theme in ("road", "water", "poi")
            if theme in runs
        },
        "runtime_notes": _build_runtime_notes(runs),
        "runs": ordered_runs,
    }

    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze Track B national-scale evidence from repo-local run outputs.")
    parser.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--captured-at", default="2026-05-20")
    parser.add_argument(
        "--bbox",
        default="28.976001,-4.698707,30.884489,-2.30746",
        help="Shared national request bbox in EPSG:4326",
    )
    parser.add_argument("--target-crs", default=DEFAULT_TARGET_CRS)
    return parser


def _parse_bbox(value: str) -> tuple[float, float, float, float]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("--bbox must contain four comma-separated numbers")
    return (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    freeze_track_b_national_evidence(
        evidence_root=Path(args.evidence_root),
        output_json=Path(args.output_json),
        captured_at=str(args.captured_at),
        request_bbox=_parse_bbox(args.bbox),
        target_crs=str(args.target_crs),
        repo_root=REPO_ROOT,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
