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

from services.scenario_run_service import scenario_run_service
from services.scenario_trigger_service import normalize_trigger_event


def process_inbox_once(inbox_dir: Path, processed_dir: Path, output_root: Optional[str] = None) -> list[str]:
    inbox_dir = Path(inbox_dir)
    processed_dir = Path(processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    scenario_ids: list[str] = []
    for event_path in sorted(inbox_dir.glob("*.json")):
        event = json.loads(event_path.read_text(encoding="utf-8"))
        request = normalize_trigger_event(event)
        if output_root is not None:
            request = request.model_copy(update={"output_root": output_root})
        response = scenario_run_service.create_scenario_run(request)
        scenario_ids.append(response.scenario_id)
        shutil.move(str(event_path), str(processed_dir / event_path.name))
    return scenario_ids


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Process scenario trigger JSON files from a local inbox once.")
    parser.add_argument("--inbox-dir", required=True, help="Directory containing trigger event JSON files.")
    parser.add_argument("--processed-dir", required=True, help="Directory where processed event files are moved.")
    parser.add_argument("--output-root", default=None, help="Optional scenario output root.")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    processed = process_inbox_once(Path(args.inbox_dir), Path(args.processed_dir), output_root=args.output_root)
    print(json.dumps({"processed": processed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
