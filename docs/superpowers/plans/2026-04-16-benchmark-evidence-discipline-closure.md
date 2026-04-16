# Benchmark Evidence Discipline Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the current evidence-hardening batch so benchmark summaries, runtime metadata, and related docs all reflect the actual runtime state and the latest clean micro-benchmark rerun.

**Architecture:** Add one narrow v2 API endpoint for non-sensitive runtime metadata, let `scripts/eval_harness.py` prefer runtime-reported metadata over shell-only env capture, then update durable evidence docs and master tracking docs to reflect the clean `2026-04-16` rerun and the repo-standard local runtime conventions. Keep this batch constrained to evidence capture, documentation, and targeted verification only.

**Tech Stack:** Python 3.9+, FastAPI, Pydantic, pytest, existing eval harness, existing v2 API, Markdown and JSON evidence artifacts

---

## File Structure

- `E:\vscode\fusionAgent\schemas\agent.py`
  Defines API response models. This batch adds a small runtime metadata response model.
- `E:\vscode\fusionAgent\api\routers\runs_v2.py`
  Exposes v2 run-related endpoints. This batch adds `/api/v2/runtime`.
- `E:\vscode\fusionAgent\scripts\eval_harness.py`
  Builds benchmark summary JSON. This batch merges runtime-reported metadata into `environment`.
- `E:\vscode\fusionAgent\tests\test_api_v2_integration.py`
  API contract coverage for the new runtime metadata endpoint.
- `E:\vscode\fusionAgent\tests\test_eval_harness.py`
  Harness coverage showing that runtime metadata is used when local shell env is absent.
- `E:\vscode\fusionAgent\docs\superpowers\specs\2026-04-16-building-micro-alignment-result.json`
  Durable tracked result from the clean `2026-04-16` isolated rerun.
- `E:\vscode\fusionAgent\docs\superpowers\specs\2026-04-08-benchmark-followup-summary.md`
  Historical summary, updated so the old queued run is treated as historical environment drift.
- `E:\vscode\fusionAgent\docs\superpowers\plans\2026-04-08-benchmark-followup-and-runtime-alignment.md`
  Historical follow-up plan, updated to record the later clean rerun.
- `E:\vscode\fusionAgent\docs\superpowers\plans\2026-04-07-fusion-agent-v2-implementation.md`
  Master tracker, updated so evidence-hardening progress is recorded.
- `E:\vscode\fusionAgent\README.md`
- `E:\vscode\fusionAgent\README.en.md`
- `E:\vscode\fusionAgent\docs\v2-operations.md`
- `E:\vscode\fusionAgent\docs\local-direct-run.md`
  User-facing runtime and evidence docs that must stay synchronized with the code.

## Task 1: Add Runtime Metadata API Surface

**Files:**
- Modify: `E:\vscode\fusionAgent\schemas\agent.py`
- Modify: `E:\vscode\fusionAgent\api\routers\runs_v2.py`
- Test: `E:\vscode\fusionAgent\tests\test_api_v2_integration.py`

- [x] **Step 1: Write the failing API test**

```python
def test_v2_runtime_metadata_endpoint_reports_current_environment(client: TestClient) -> None:
    resp = client.get("/api/v2/runtime")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "kg_backend": "memory",
        "llm_provider": "mock",
        "celery_eager": "1",
        "api_port": "8000",
    }
```

- [x] **Step 2: Run the test to verify it fails**

Run: `python -m pytest -q tests/test_api_v2_integration.py -k runtime_metadata_endpoint_reports_current_environment`

Expected: FAIL with `404 Not Found` because `/api/v2/runtime` does not exist yet.

- [x] **Step 3: Add the minimal response model**

```python
class RuntimeMetadataResponse(BaseModel):
    kg_backend: Optional[str] = None
    llm_provider: Optional[str] = None
    celery_eager: Optional[str] = None
    api_port: Optional[str] = None
```

- [x] **Step 4: Add the minimal endpoint**

```python
def _build_runtime_metadata_response() -> RuntimeMetadataResponse:
    return RuntimeMetadataResponse(
        kg_backend=os.getenv("GEOFUSION_KG_BACKEND"),
        llm_provider=os.getenv("GEOFUSION_LLM_PROVIDER"),
        celery_eager=os.getenv("GEOFUSION_CELERY_EAGER"),
        api_port=os.getenv("GEOFUSION_API_PORT"),
    )


@router.get("/runtime", response_model=RuntimeMetadataResponse)
async def get_runtime_metadata() -> RuntimeMetadataResponse:
    return _build_runtime_metadata_response()
```

- [x] **Step 5: Run the test to verify it passes**

Run: `python -m pytest -q tests/test_api_v2_integration.py -k runtime_metadata_endpoint_reports_current_environment`

Expected: PASS

## Task 2: Make Harness Prefer Runtime-Reported Metadata

**Files:**
- Modify: `E:\vscode\fusionAgent\scripts\eval_harness.py`
- Test: `E:\vscode\fusionAgent\tests\test_eval_harness.py`

- [x] **Step 1: Write the failing harness test**

```python
def test_evaluate_cases_uses_runtime_metadata_when_local_env_is_unset(tmp_path: Path, monkeypatch) -> None:
    case_a = tmp_path / "case_a"
    _write_case(case_a, case_id="case_a")

    monkeypatch.setattr(eval_harness, "_detect_git_commit_sha", lambda: "abc123")
    monkeypatch.delenv("GEOFUSION_KG_BACKEND", raising=False)
    monkeypatch.delenv("GEOFUSION_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GEOFUSION_CELERY_EAGER", raising=False)

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"kg_backend":"neo4j","llm_provider":"mock","celery_eager":"0","api_port":"8010"}'

    def fake_urlopen(request, timeout=0):
        assert request.full_url == "http://unit.test/api/v2/runtime"
        assert timeout == 5
        return _FakeResponse()

    monkeypatch.setattr(eval_harness.urllib.request, "urlopen", fake_urlopen)

    summary = eval_harness.evaluate_cases(
        case_dirs=[case_a],
        base_url="http://unit.test",
        timeout_sec=12.0,
        request_builder=lambda case_dir: {"case_id": case_dir.name, "expected_plan_checks": {}, "artifact_checks": {}},
        runner=lambda case_dir, *, base_url, timeout_sec: {"run_id": "run-case_a", "artifact_size": 123, "plan": {}, "artifact_entries": []},
        validator=lambda result, *, expected_plan_checks, artifact_checks: None,
    )

    assert summary["environment"] == {
        "kg_backend": "neo4j",
        "llm_provider": "mock",
        "celery_eager": "0",
    }
```

- [x] **Step 2: Run the test to verify it fails**

Run: `python -m pytest -q tests/test_eval_harness.py -k uses_runtime_metadata_when_local_env_is_unset`

Expected: FAIL because `summary["environment"]` is still all `None`.

- [x] **Step 3: Add a narrow runtime fetch helper**

```python
def _fetch_runtime_environment(base_url: str) -> dict[str, Any]:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", "api/v2/runtime")
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        "kg_backend": payload.get("kg_backend"),
        "llm_provider": payload.get("llm_provider"),
        "celery_eager": payload.get("celery_eager"),
    }
```

- [x] **Step 4: Merge runtime metadata into summary construction**

```python
environment = {
    "kg_backend": os.getenv("GEOFUSION_KG_BACKEND"),
    "llm_provider": os.getenv("GEOFUSION_LLM_PROVIDER"),
    "celery_eager": os.getenv("GEOFUSION_CELERY_EAGER"),
}
runtime_environment = _fetch_runtime_environment(base_url)
for key, value in runtime_environment.items():
    if value is not None:
        environment[key] = value
```

- [x] **Step 5: Run the test to verify it passes**

Run: `python -m pytest -q tests/test_eval_harness.py -k uses_runtime_metadata_when_local_env_is_unset`

Expected: PASS

## Task 3: Refresh Durable Evidence And Historical Summaries

**Files:**
- Create: `E:\vscode\fusionAgent\docs\superpowers\specs\2026-04-16-building-micro-alignment-result.json`
- Modify: `E:\vscode\fusionAgent\docs\superpowers\specs\2026-04-08-benchmark-followup-summary.md`
- Modify: `E:\vscode\fusionAgent\docs\superpowers\plans\2026-04-08-benchmark-followup-and-runtime-alignment.md`
- Modify: `E:\vscode\fusionAgent\docs\superpowers\plans\2026-04-07-fusion-agent-v2-implementation.md`
- Modify: `E:\vscode\fusionAgent\docs\superpowers\plans\2026-04-12-reproducible-micro-building-benchmark.md`

- [x] **Step 1: Save the clean rerun result as a tracked JSON artifact**

```json
{
  "generated_at": "2026-04-16T08:19:14Z",
  "command_mode": "manifest",
  "base_url": "http://127.0.0.1:8010",
  "totals": { "total": 1, "passed": 1, "failed": 0, "skipped": 0 },
  "cases": [
    {
      "case_id": "building_gitega_micro_agent",
      "status": "passed",
      "duration_ms": 194896,
      "run_id": "7117ef6fd95a44aa97d438cb7b3a9bee"
    }
  ]
}
```

- [x] **Step 2: Update the historical summary so the old queued run is treated as historical drift**

Write a short new section that says:

```markdown
## Clean Rerun On `2026-04-16`

- The same micro case was rerun on a clean isolated runtime at `http://127.0.0.1:8010`.
- Result: `passed`.
- New run id: `7117ef6fd95a44aa97d438cb7b3a9bee`.
- Durable result path: `docs/superpowers/specs/2026-04-16-building-micro-alignment-result.json`.
```

- [x] **Step 3: Update the historical plans so they no longer claim queued is the current blocker**

Replace wording like:

```markdown
- the micro run ... still stalls at `queued`
```

with wording like:

```markdown
- the old queued run is preserved as historical environment drift
- the clean isolated rerun on `2026-04-16` passed on current `main`
```

- [x] **Step 4: Normalize stale worktree path references in historical plan docs**

Replace stale path prefixes like:

```text
C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/...
```

with current repo paths like:

```text
E:/vscode/fusionAgent/...
```

## Task 4: Sync User-Facing Runtime And Evidence Docs

**Files:**
- Modify: `E:\vscode\fusionAgent\README.md`
- Modify: `E:\vscode\fusionAgent\README.en.md`
- Modify: `E:\vscode\fusionAgent\docs\v2-operations.md`
- Modify: `E:\vscode\fusionAgent\docs\local-direct-run.md`

- [x] **Step 1: Update runtime convention wording**

Add or keep wording equivalent to:

```markdown
- default day-to-day API port: `8000`
- reserve `8010` for isolated real-data benchmarks
- reserve `8011` for isolated fast-confidence checks
- use `8012+` only for temporary diagnostics
```

- [x] **Step 2: Document the new runtime metadata evidence path**

Add wording equivalent to:

```markdown
- `scripts/eval_harness.py` now prefers `/api/v2/runtime` for non-sensitive runtime metadata
- saved summary `environment` values therefore reflect the actual runtime more reliably than shell-only env capture
```

- [x] **Step 3: Verify docs mention the clean micro rerun accurately**

The final wording should say:

```markdown
- `building_gitega_micro_agent` is input-reproducible from the tracked manifest
- it also passes on a clean isolated `8010` full-loop runtime
- the earlier queued outcome is historical environment drift, not the current default expectation
```

## Task 5: Verify And Prepare For Execution

**Files:**
- Test: `E:\vscode\fusionAgent\tests\test_eval_harness.py`
- Test: `E:\vscode\fusionAgent\tests\test_api_v2_integration.py`
- Evidence: `E:\vscode\fusionAgent\docs\superpowers\specs\2026-04-16-building-micro-alignment-result.json`

- [x] **Step 1: Run targeted tests**

Run: `python -m pytest -q tests/test_eval_harness.py tests/test_api_v2_integration.py`

Expected: PASS

- [x] **Step 2: Run diff hygiene check**

Run: `git diff --check`

Expected: no whitespace or patch-format errors

- [x] **Step 3: Verify the new evidence file exists**

Run: `Get-Item docs\\superpowers\\specs\\2026-04-16-building-micro-alignment-result.json`

Expected: file exists

- [x] **Step 4: Commit**

```bash
git add schemas/agent.py api/routers/runs_v2.py scripts/eval_harness.py tests/test_api_v2_integration.py tests/test_eval_harness.py README.md README.en.md docs/v2-operations.md docs/local-direct-run.md docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md docs/superpowers/plans/2026-04-07-fusion-agent-v2-implementation.md docs/superpowers/plans/2026-04-08-benchmark-followup-and-runtime-alignment.md docs/superpowers/plans/2026-04-12-reproducible-micro-building-benchmark.md docs/superpowers/specs/2026-04-16-building-micro-alignment-result.json
git commit -m "docs: harden benchmark evidence discipline"
```

## Self-Review

### Spec coverage

- Covers the missing runtime metadata evidence path.
- Covers the current doc drift around local ports and historical queued micro-benchmark conclusions.
- Covers durable storage of the latest clean rerun result.

### Placeholder scan

- No `TODO`, `TBD`, or vague “fix later” steps remain.
- Every task points to exact files, tests, or commands.

### Type consistency

- API model, router response, harness summary keys, and tests all use the same field names: `kg_backend`, `llm_provider`, `celery_eager`, `api_port`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-16-benchmark-evidence-discipline-closure.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
