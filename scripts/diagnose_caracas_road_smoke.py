"""Read-only geometry and prompt-size diagnostics; never change acceptance gates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Do not overwrite prior diagnostics")
    import geopandas as gpd
    from shapely.geometry import LineString, box
    from shapely.ops import unary_union
    from agent.planner import planning_action_snapshot
    from schemas.agent import WorkflowPlan
    from services.artifact_evaluation_service import _topology_quality_metrics

    root = args.run_root.resolve()
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    run = root / "runs" / summary["run_id"]
    manifest = json.loads((ROOT / "docs/thesis/manifests/2026-07-20-c02-c04-c06-real-data.json").read_text(encoding="utf-8"))
    sources = {s["source_id"]: s["original_path"] for s in manifest["sources"]}
    quality = json.loads((run / "quality-failures/revision-2/quality_report.json").read_text(encoding="utf-8"))
    paths = {
        "osm": sources["raw.osm.road"],
        "microsoft": sources["raw.microsoft.road"],
        "fused": quality["artifact_path"],
    }
    rows = []
    for name, path in paths.items():
        frame = gpd.read_file(path).to_crs("EPSG:32619")
        clip_geometry = gpd.GeoSeries(
            [box(-67.17, 10.38, -66.86, 10.57)], crs="EPSG:4326",
        ).to_crs(frame.crs).iloc[0]
        for scope, subset in [("stored", frame), ("request_bbox_clipped", gpd.clip(frame, clip_geometry))]:
            metrics = _topology_quality_metrics(subset, sliver_area_threshold_sq_m=0)
            rows.append({
                "dataset": name, "scope": scope, "feature_count": len(subset),
                "dangle_count": metrics["dangle_endpoint_count"],
                "dangle_per_100km": metrics["dangle_endpoint_rate_per_100km"],
            })
    junction = gpd.GeoDataFrame(
        geometry=[LineString([(0, 0), (2, 0)]), LineString([(1, 0), (1, 1)])],
        crs="EPSG:32619",
    )
    noded = gpd.GeoDataFrame(geometry=list(unary_union(junction.geometry).geoms), crs=junction.crs)
    junction_counts = {
        label: _topology_quality_metrics(frame, sliver_area_threshold_sq_m=0)["dangle_endpoint_count"]
        for label, frame in [("same_t_junction_unsplit", junction), ("same_t_junction_split", noded)]
    }
    sizes = []
    for path in sorted((root / "provider-calls").glob("*-input.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        previous = payload["context"].get("execution_hints", {}).get("previous_plan")
        if previous is None:
            continue
        compact = planning_action_snapshot(WorkflowPlan.model_validate(previous))
        before = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        previous_size = len(json.dumps(previous, ensure_ascii=False).encode("utf-8"))
        payload["context"]["execution_hints"]["previous_plan"] = compact
        after = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        sizes.append({
            "call": path.name, "request_bytes_before": before,
            "previous_plan_bytes_before": previous_size, "request_bytes_after": after,
            "saved_percent": 100 * (1 - after / before),
        })
    result = {
        "evidence_kind": "offline_real_data_diagnostic",
        "same_metric_crs": "EPSG:32619",
        "topology": rows, "segmentation_counterexample": junction_counts,
        "historical_input_projection": sizes,
        "boundary": "No gate changes, no new LLM calls, byte savings are not measured token/latency savings.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
