from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.scenario_output import resolve_scenario_output_root
from services.scenario_registry_service import ScenarioRegistryService
from services.scenario_run_service import scenario_run_service
from services.scenario_trigger_service import normalize_trigger_event


def process_inbox_once(
    inbox_dir: Path,
    processed_dir: Path,
    output_root: Optional[str] = None,
    failed_dir: Optional[Path] = None,
) -> list[str]:
    inbox_dir = Path(inbox_dir)
    processed_dir = Path(processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    failed_path = Path(failed_dir) if failed_dir is not None else None
    scenario_ids: list[str] = []
    for event_path in sorted(inbox_dir.glob("*.json")):
        try:
            event = json.loads(event_path.read_text(encoding="utf-8"))
            request = normalize_trigger_event(event)
            if output_root is not None:
                request = request.model_copy(update={"output_root": output_root})

            registry = ScenarioRegistryService(output_root=resolve_scenario_output_root(request.output_root))
            existing = registry.find_by_idempotency_key(str(request.metadata.get("idempotency_key") or ""))
            if existing is not None:
                scenario_ids.append(str(existing["scenario_id"]))
                _move_event_file(event_path, processed_dir)
                continue

            response = scenario_run_service.create_scenario_run(request)
            scenario_ids.append(response.scenario_id)
            _move_event_file(event_path, processed_dir)
        except Exception:
            if failed_path is None:
                raise
            _move_event_file(event_path, failed_path)
    return scenario_ids


def _move_event_file(event_path: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(event_path), str(target_dir / event_path.name))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Process scenario trigger JSON files from a local inbox once.")
    parser.add_argument("--inbox-dir", required=True, help="Directory containing trigger event JSON files.")
    parser.add_argument("--processed-dir", required=True, help="Directory where processed event files are moved.")
    parser.add_argument("--failed-dir", default=None, help="Optional directory where invalid or failed event files are moved.")
    parser.add_argument("--output-root", default=None, help="Optional scenario output root.")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    processed = process_inbox_once(
        Path(args.inbox_dir),
        Path(args.processed_dir),
        output_root=args.output_root,
        failed_dir=Path(args.failed_dir) if args.failed_dir is not None else None,
    )
    print(json.dumps({"processed": processed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
