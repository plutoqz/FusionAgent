# AOI-Driven Output CRS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `task_driven_auto` runs automatically choose a projected output CRS from the resolved AOI when the caller does not explicitly provide `target_crs`, while preserving explicit user overrides.

**Architecture:** Keep CRS normalization in `utils/crs.py`, but split "validate an explicit CRS" from "derive a default CRS". The API and request model must preserve whether `target_crs` was omitted, and `AgentRunService` should resolve the effective CRS only after AOI resolution is available, then propagate the final CRS into status, audit events, input acquisition, and execution.

**Tech Stack:** FastAPI, Pydantic, GeoPandas / pyproj, pytest

**Completion Status:** Completed and merged via PR #2 on 2026-04-20. Final verification on `main`: `python -m pytest -q` passed with `158 passed, 1 skipped, 6 warnings`.

---

## File Map

- Modify: `utils/crs.py`
  Responsibility: explicit CRS validation plus AOI/bbox-driven default CRS derivation.
- Modify: `schemas/agent.py`
  Responsibility: let `RunCreateRequest` carry an omitted `target_crs` without collapsing it to `EPSG:32643` too early.
- Modify: `api/routers/runs_v2.py`
  Responsibility: preserve "omitted vs explicit" `target_crs` semantics at the HTTP boundary.
- Modify: `services/agent_run_service.py`
  Responsibility: compute the effective runtime CRS after AOI resolution and thread it into queued/planning/running/succeeded state.
- Modify: `scripts/smoke_agentic_region.py`
  Responsibility: stop forcing `EPSG:32643` for natural-language AOI smoke runs unless the operator explicitly asks for an override.
- Modify: `tests/test_crs.py`
  Responsibility: cover auto CRS derivation and fallback behavior.
- Modify: `tests/test_agent_run_service_enhancements.py`
  Responsibility: prove runtime CRS selection uses Nairobi AOI when omitted and preserves explicit overrides.
- Modify: `tests/test_api_v2_integration.py`
  Responsibility: prove API request parsing + inspection/audit output reflect the effective CRS.
- Modify: `tests/test_smoke_agentic_region.py`
  Responsibility: prove smoke form generation omits `target_crs` unless explicitly provided.
- Modify: `docs/v2-operations.md`
  Responsibility: document auto CRS behavior and explicit override semantics for operators.

### Task 1: Add AOI-Driven CRS Resolution Utility

**Files:**
- Modify: `utils/crs.py`
- Test: `tests/test_crs.py`

- [x] **Step 1: Write the failing CRS derivation tests**

Add these tests to `tests/test_crs.py`:

```python
import pytest

from utils.crs import (
    DEFAULT_TARGET_CRS,
    derive_default_target_crs,
    normalize_explicit_target_crs,
    resolve_target_crs,
)


def test_derive_default_target_crs_uses_utm_zone_for_nairobi() -> None:
    assert derive_default_target_crs((36.65, -1.45, 37.10, -1.10)) == "EPSG:32737"


def test_derive_default_target_crs_uses_utm_zone_for_gilgit() -> None:
    assert derive_default_target_crs((74.0, 35.7, 75.0, 36.2)) == "EPSG:32643"


def test_derive_default_target_crs_falls_back_without_bbox() -> None:
    assert derive_default_target_crs(None) == DEFAULT_TARGET_CRS


def test_resolve_target_crs_preserves_explicit_value() -> None:
    assert resolve_target_crs("epsg:4326", bbox=(36.65, -1.45, 37.10, -1.10)) == "EPSG:4326"
```

- [x] **Step 2: Run the focused CRS test file and confirm it fails**

Run:

```powershell
python -m pytest -q tests\test_crs.py
```

Expected: failure because `derive_default_target_crs`, `normalize_explicit_target_crs`, and `resolve_target_crs` do not exist yet.

- [x] **Step 3: Implement the CRS helper split in `utils/crs.py`**

Replace the one-function module with explicit validation plus default derivation:

```python
from __future__ import annotations

import math
import re
from typing import Sequence


DEFAULT_TARGET_CRS = "EPSG:32643"


def normalize_explicit_target_crs(crs: str | None) -> str | None:
    if crs is None:
        return None
    value = crs.strip().upper()
    if not value:
        return None
    if not re.match(r"^EPSG:\d+$", value):
        raise ValueError(f"Invalid CRS format: {crs}. Expected like EPSG:32643.")
    return value


def derive_default_target_crs(bbox: Sequence[float] | None) -> str:
    if bbox is None or len(bbox) != 4:
        return DEFAULT_TARGET_CRS
    minx, miny, maxx, maxy = (float(item) for item in bbox)
    lon = (minx + maxx) / 2.0
    lat = (miny + maxy) / 2.0
    if not math.isfinite(lon) or not math.isfinite(lat):
        return DEFAULT_TARGET_CRS
    zone = int((lon + 180.0) // 6.0) + 1
    zone = min(60, max(1, zone))
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    return f"EPSG:{epsg}"


def resolve_target_crs(crs: str | None, *, bbox: Sequence[float] | None = None) -> str:
    explicit = normalize_explicit_target_crs(crs)
    if explicit is not None:
        return explicit
    return derive_default_target_crs(bbox)


def normalize_target_crs(crs: str | None) -> str:
    return resolve_target_crs(crs)
```

- [x] **Step 4: Re-run the focused CRS test file and confirm it passes**

Run:

```powershell
python -m pytest -q tests\test_crs.py
```

Expected: PASS.

- [x] **Step 5: Commit the utility-only slice**

```powershell
git add utils/crs.py tests/test_crs.py
git commit -m "feat: derive default target crs from aoi bbox"
```

### Task 2: Thread Optional Target CRS Through API And Runtime

**Files:**
- Modify: `schemas/agent.py`
- Modify: `api/routers/runs_v2.py`
- Modify: `services/agent_run_service.py`
- Modify: `scripts/smoke_agentic_region.py`
- Test: `tests/test_agent_run_service_enhancements.py`
- Test: `tests/test_api_v2_integration.py`
- Test: `tests/test_smoke_agentic_region.py`

- [x] **Step 1: Add failing tests for omitted-vs-explicit CRS behavior**

Extend the existing AOI/runtime tests with these expectations:

```python
def test_agent_run_service_auto_selects_target_crs_from_nairobi_aoi_when_omitted(...):
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="fuse building and road data for Nairobi, Kenya"),
        target_crs=None,
        field_mapping={},
        debug=False,
        input_strategy=RunInputStrategy.task_driven_auto,
    )
    ...
    assert latest.target_crs == "EPSG:32737"
    assert resolved_event.details["target_crs"] == "EPSG:32737"


def test_agent_run_service_preserves_explicit_target_crs_override(...):
    request = RunCreateRequest(..., target_crs="EPSG:4326", input_strategy=RunInputStrategy.task_driven_auto)
    ...
    assert latest.target_crs == "EPSG:4326"


def test_v2_run_task_driven_auto_nairobi_query_uses_auto_target_crs_when_form_omits_target_crs(...):
    resp = client.post(
        "/api/v2/runs",
        data={
            "job_type": "building",
            "trigger_type": "user_query",
            "trigger_content": "fuse building and road data for Nairobi, Kenya",
            "input_strategy": "task_driven_auto",
            "field_mapping": "{}",
            "debug": "false",
        },
    )
    ...
    assert inspection["run"]["target_crs"] == "EPSG:32737"


def test_smoke_agentic_region_omits_target_crs_when_not_provided() -> None:
    parsed = parse_args(["--base-url", "http://127.0.0.1:8010", "--query", "fuse building data for Nairobi, Kenya"])
    payload = build_create_run_form(parsed)
    assert "target_crs" not in payload
```

- [x] **Step 2: Run the focused runtime/API/smoke tests and confirm they fail**

Run:

```powershell
python -m pytest -q tests\test_agent_run_service_enhancements.py tests\test_api_v2_integration.py tests\test_smoke_agentic_region.py
```

Expected: failure because omitted `target_crs` is still collapsed to `EPSG:32643`, and the smoke script still forces `target_crs`.

- [x] **Step 3: Preserve omitted-vs-explicit semantics at the request boundary**

Make the request model and router stop forcing the default too early:

```python
# schemas/agent.py
class RunCreateRequest(BaseModel):
    job_type: JobType
    trigger: RunTrigger
    target_crs: str | None = None
    field_mapping: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    debug: bool = False
    input_strategy: RunInputStrategy = RunInputStrategy.uploaded
```

```python
# api/routers/runs_v2.py
from utils.crs import normalize_explicit_target_crs

...
target_crs: Optional[str] = Form(None),
...
try:
    normalized_crs = normalize_explicit_target_crs(target_crs)
except ValueError as exc:
    raise HTTPException(status_code=422, detail=str(exc)) from exc
...
request = RunCreateRequest(
    ...,
    target_crs=normalized_crs,
    ...,
)
```

```python
# scripts/smoke_agentic_region.py
parser.add_argument("--target-crs", default="", help="Optional explicit target CRS override.")

def build_create_run_form(args: argparse.Namespace) -> dict[str, str]:
    payload = {
        "job_type": args.job_type,
        "trigger_type": "user_query",
        "trigger_content": args.query,
        "input_strategy": "task_driven_auto",
        "field_mapping": "{}",
        "debug": "false",
    }
    if args.target_crs:
        payload["target_crs"] = args.target_crs
    return payload
```

- [x] **Step 4: Resolve the effective target CRS after AOI resolution**

In `services/agent_run_service.py`, compute the final CRS only when AOI context is available:

```python
from utils.crs import DEFAULT_TARGET_CRS, resolve_target_crs

...
def run_planning_stage(self, run_id: str, request: RunCreateRequest) -> WorkflowPlan:
    resolved_aoi: ResolvedAOI | None = None
    ...
    effective_target_crs = resolve_target_crs(
        request.target_crs,
        bbox=(resolved_aoi.bbox if resolved_aoi is not None else None),
    )
    self._update_status(
        run_id,
        RunPhase.planning,
        progress=14,
        target_crs=effective_target_crs,
        event_kind="target_crs_resolved",
        event_message=f"Resolved target CRS {effective_target_crs}.",
        event_details={
            "target_crs": effective_target_crs,
            "source": "explicit" if request.target_crs else "resolved_aoi_default",
        },
    )
    ...
```

Also update every execution/input-acquisition path that currently uses `normalize_target_crs(request.target_crs)` so it instead uses the already-resolved runtime value, for example:

```python
effective_target_crs = self.get_run(run_id).target_crs
...
target_crs=effective_target_crs,
```

And add `target_crs` into `task_inputs_resolved` details so inspection output carries the effective value.

- [x] **Step 5: Re-run the focused tests and confirm they pass**

Run:

```powershell
python -m pytest -q tests\test_crs.py tests\test_agent_run_service_enhancements.py tests\test_api_v2_integration.py tests\test_smoke_agentic_region.py
```

Expected: PASS, including Nairobi auto-selecting `EPSG:32737` when omitted and explicit `EPSG:4326` surviving unchanged.

- [x] **Step 6: Commit the runtime/API slice**

```powershell
git add schemas/agent.py api/routers/runs_v2.py services/agent_run_service.py scripts/smoke_agentic_region.py tests/test_agent_run_service_enhancements.py tests/test_api_v2_integration.py tests/test_smoke_agentic_region.py
git commit -m "feat: auto-select output crs from resolved aoi"
```

### Task 3: Update Operator Docs And Final Verification

**Files:**
- Modify: `docs/v2-operations.md`

- [x] **Step 1: Update the operator docs**

Add an explicit note to `docs/v2-operations.md` near the AOI smoke section:

```markdown
- when `task_driven_auto` resolves an AOI and the caller omits `target_crs`, the runtime now derives a projected UTM CRS from the AOI bbox centroid
- explicit `target_crs` still wins; pass `target_crs=EPSG:4326` only when you intentionally want geographic output
```

Update the smoke example so the default command does not force `EPSG:32643`:

```powershell
python scripts/smoke_agentic_region.py `
  --base-url http://127.0.0.1:8000 `
  --query "fuse building and road data for Nairobi, Kenya" `
  --timeout 1200
```

- [x] **Step 2: Run the full test suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS with the existing warning profile only.

- [x] **Step 3: Commit the doc + verification slice**

```powershell
git add docs/v2-operations.md
git commit -m "docs: describe aoi-driven target crs defaults"
```

- [x] **Step 4: Push the branch**

```powershell
git push -u origin codex/agentic-output-crs
```

- [x] **Step 5: Open the stacked PR**

Create a PR with:

```text
base: codex/agentic-any-region-fusion
title: feat: auto-select output crs from resolved aoi
```

## Notes

- Do not change uploaded-run semantics: if no AOI is available, the default fallback remains `EPSG:32643`.
- Do not silently override an explicit `target_crs`, even if the AOI implies a "better" UTM zone.
- Treat Nairobi as the canonical southern-hemisphere regression: the expected auto CRS is `EPSG:32737`, not `EPSG:32643`.
