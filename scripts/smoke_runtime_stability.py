from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.track_b_national_scale_service import TrackBNationalScaleService


def _parse_bbox(value: str) -> tuple[float, float, float, float]:
    parts = [float(item.strip()) for item in value.split(",")]
    if len(parts) != 4:
        raise ValueError("--bbox must be minx,miny,maxx,maxy")
    return (parts[0], parts[1], parts[2], parts[3])


def run_smoke(
    *,
    root_dir: Path,
    output_root: Path,
    bbox: tuple[float, float, float, float],
    target_crs: str,
    themes: Iterable[str],
) -> dict[str, object]:
    output_root.mkdir(parents=True, exist_ok=True)
    service = TrackBNationalScaleService(root_dir=root_dir, cache_dir=output_root / "_cache")
    theme_list = [str(theme) for theme in themes]
    runs = []
    failures = []
    for theme in theme_list:
        theme_output = output_root / theme
        try:
            summary = service.build_theme_evidence(
                job_type=theme,
                source_id=None,
                request_bbox=bbox,
                target_crs=target_crs,
                output_root=theme_output,
                tile_width_m=40_000.0,
                tile_height_m=40_000.0,
                overlap_m=0.0,
            )
            runs.append(summary)
            if not Path(str(summary.get("artifact_path") or "")).exists():
                failures.append({"job_type": theme, "reason": "artifact_missing"})
        except Exception as exc:  # noqa: BLE001
            failures.append({"job_type": theme, "reason": f"{type(exc).__name__}: {exc}"})

    payload = {
        "overall_status": "passed" if not failures else "failed",
        "themes": theme_list,
        "runs": runs,
        "failures": failures,
    }
    (output_root / "runtime_stability_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--bbox", required=True)
    parser.add_argument("--target-crs", default="EPSG:4326")
    parser.add_argument("--themes", nargs="+", default=["building", "road", "water", "poi"])
    args = parser.parse_args()
    payload = run_smoke(
        root_dir=args.root_dir,
        output_root=args.output_root,
        bbox=_parse_bbox(args.bbox),
        target_crs=args.target_crs,
        themes=args.themes,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if payload["overall_status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
