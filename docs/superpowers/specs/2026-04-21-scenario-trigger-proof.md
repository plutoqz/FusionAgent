# Scenario Trigger Proof

Date: 2026-04-21

## Scope

This proof covers the local scenario trigger inbox path. It does not add a polling daemon, external provider integration, webhook receiver, or remote disaster feed. Operators place JSON event files in a local inbox and run the watcher script once.

## Sample Event

```json
{
  "event_id": "usgs-2026-001",
  "event_type": "earthquake",
  "location": "Parakou, Benin",
  "requested_layers": ["building", "road"],
  "description": "M5 earthquake near Parakou"
}
```

`event_id` becomes the idempotency key. If `event_id` is absent, the trigger service derives a stable hash from the event payload.

## Inbox Command

```powershell
python scripts/watch_scenario_inbox.py `
  --inbox-dir .\runs\scenario_inbox `
  --processed-dir .\runs\scenario_processed `
  --failed-dir .\runs\scenario_failed `
  --output-root .\runs\scenarios
```

The script prints JSON:

```json
{"processed": ["scenario_<id>"]}
```

## Processed And Failed Directories

Valid JSON events are normalized into `ScenarioRunRequest` objects, processed or matched by idempotency key, and moved to `--processed-dir`.

Invalid JSON events move to `--failed-dir` when that option is provided. Runtime errors during normalization, idempotency lookup, or scenario creation also move the original event file to `--failed-dir` when provided.

If `--failed-dir` is omitted, the script preserves fail-fast behavior and raises the underlying error instead of suppressing it.

## Idempotency Behavior

Before creating a new scenario, the watcher reads the scenario registry under the target scenario output root and checks for an existing record with the same `idempotency_key`.

When a match exists, the watcher does not create a duplicate scenario. It moves the event file to the processed directory and returns the existing `scenario_id`.

Idempotency is persisted in the scenario registry. It does not depend on process memory.

## Expected Registry Fields

Scenario registry records include the existing scenario metadata plus trigger provenance:

```json
{
  "scenario_id": "scenario_<id>",
  "scenario_name": "Parakou, Benin earthquake",
  "phase": "succeeded",
  "output_dir": ".\\runs\\scenarios\\scenario_<id>",
  "child_run_ids": ["run-building", "run-road"],
  "created_at": "2026-04-21T00:00:00+00:00",
  "case_id": null,
  "idempotency_key": "usgs-2026-001",
  "trigger_event": {
    "event_id": "usgs-2026-001",
    "event_type": "earthquake",
    "location": "Parakou, Benin",
    "requested_layers": ["building", "road"],
    "description": "M5 earthquake near Parakou"
  }
}
```

## Expected Scenario Evidence Files

Each created scenario directory is expected to contain:

- `request.json`
- `scenario_summary.json`
- `evaluation.json`
- `kg_path_trace.json`
- `workflow_trace.json`
- `source_coverage.json`
- `documents/` with rendered scenario reports
- child run evidence referenced by `child_run_ids` and `final_outputs`

Failed event files remain visible in `--failed-dir`; they are not deleted or hidden.

