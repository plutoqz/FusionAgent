# KG Seed Externalization And Versioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Prefer `gpt-5.5` workers. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move FusionAgent from hardcoded KG seed data toward versioned, validated, diffable KG manifests without breaking the current in-memory and Neo4j bootstrap paths.

**Architecture:** Keep `kg/seed.py` as the compatibility source for this slice. Add manifest schemas, an export script that serializes current Python seed data into JSON, a loader that validates and reconstructs the same dataclass objects, and parity tests proving manifest-loaded KG content matches the existing seed. Later slices can flip runtime defaults after parity is stable.

**Tech Stack:** Python, dataclasses, Pydantic v2, pytest, JSON first for deterministic stdlib support, existing `kg.models`, `kg.seed`, `kg.source_catalog`, `fusion_algorithms.registry_metadata`, `InMemoryKGRepository`, and `Neo4jKGRepository`.

---

## Phase 0: Documentation Discovery

### Sources Consulted

- `kg/seed.py`
  - Defines hardcoded `DATA_TYPES`, `TASKS`, `SCENARIO_PROFILES`, `ALGORITHMS`, `PARAMETER_SPECS`, `WORKFLOW_PATTERNS`, `DATA_SOURCES`, and `OUTPUT_SCHEMA_POLICIES`.
  - Imports FusionCode registry data at the end and merges it into the seed module.
- `kg/source_catalog.py`
  - Builds raw data source catalog entries used by `DATA_SOURCES`.
- `fusion_algorithms/registry_metadata.py`
  - Defines FusionCode data types, algorithms, parameter specs, and workflow patterns, then gets merged into `kg/seed.py`.
- `kg/models.py`
  - Dataclass definitions are the canonical runtime model for KG entities.
- `kg/inmemory_repository.py`
  - Loads seed module content into repository state.
- `kg/bootstrap.py`
  - Bootstraps KG nodes and relationships into Neo4j-style storage.
- `tests/test_kg_repository_enhancements.py`
  - Existing repository behavior tests.
- `tests/test_kg_graph_service.py`
  - Existing graph surface tests assume stable KG entity ids and relationships.

### Allowed APIs

- Use JSON manifests in this plan because the stdlib can parse them deterministically.
- Include `schema_version` and `content_hash` in manifest metadata.
- Export from existing Python seed first; do not hand-convert the seed manually.
- Load manifests into existing dataclasses; do not create a parallel runtime model.
- Keep `kg/seed.py` as fallback until parity is proven.

### Anti-Pattern Guards

- Do not remove or rewrite `kg/seed.py` in this slice.
- Do not make YAML parsing a new dependency unless the project already has a pinned YAML dependency.
- Do not hand-maintain duplicate seed data in Python and JSON without an export parity test.
- Do not change algorithm ids, data source ids, workflow pattern ids, or output schema policy ids.
- Do not alter runtime claim states as part of this migration.

## File Structure

- Create: `schemas/kg_seed_manifest.py`
- Create: `kg/seed_manifest.py`
- Create: `scripts/export_kg_seed_manifest.py`
- Create: `kg/seed_manifest.generated.json`
- Modify: `kg/inmemory_repository.py`
- Modify: `docs/no-ui-agent-operations.md`
- Test: `tests/test_kg_seed_manifest.py`
- Test: `tests/test_kg_repository_enhancements.py`

---

### Task 1: Define KG Seed Manifest Schema

**Files:**
- Create: `schemas/kg_seed_manifest.py`
- Test: `tests/test_kg_seed_manifest.py`

- [ ] **Step 1: Write failing schema tests**

Create `tests/test_kg_seed_manifest.py`:

```python
from __future__ import annotations

from schemas.kg_seed_manifest import KgSeedManifest, KgSeedManifestMetadata


def test_kg_seed_manifest_requires_versioned_metadata() -> None:
    manifest = KgSeedManifest(
        metadata=KgSeedManifestMetadata(
            schema_version="1.0.0",
            generated_from="kg.seed",
            content_hash="sha256:test",
        ),
        data_types=[],
        tasks=[],
        scenario_profiles=[],
        algorithms=[],
        parameter_specs=[],
        workflow_patterns=[],
        data_sources=[],
        output_schema_policies=[],
    )

    payload = manifest.model_dump(mode="json")

    assert payload["metadata"]["schema_version"] == "1.0.0"
    assert payload["metadata"]["content_hash"] == "sha256:test"
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_kg_seed_manifest.py::test_kg_seed_manifest_requires_versioned_metadata -q
```

Expected: FAIL because `schemas.kg_seed_manifest` does not exist.

- [ ] **Step 3: Implement manifest schemas**

Create `schemas/kg_seed_manifest.py`:

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class KgSeedManifestMetadata(BaseModel):
    schema_version: str
    generated_from: str = "kg.seed"
    content_hash: str
    generated_at: str | None = None
    notes: list[str] = Field(default_factory=list)


class KgSeedManifest(BaseModel):
    metadata: KgSeedManifestMetadata
    data_types: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    scenario_profiles: list[dict[str, Any]] = Field(default_factory=list)
    task_bundles: list[dict[str, Any]] = Field(default_factory=list)
    output_requirements: list[dict[str, Any]] = Field(default_factory=list)
    qos_policies: list[dict[str, Any]] = Field(default_factory=list)
    data_needs: list[dict[str, Any]] = Field(default_factory=list)
    repair_strategies: list[dict[str, Any]] = Field(default_factory=list)
    algorithms: list[dict[str, Any]] = Field(default_factory=list)
    parameter_specs: list[dict[str, Any]] = Field(default_factory=list)
    workflow_patterns: list[dict[str, Any]] = Field(default_factory=list)
    data_sources: list[dict[str, Any]] = Field(default_factory=list)
    output_schema_policies: list[dict[str, Any]] = Field(default_factory=list)
```

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_kg_seed_manifest.py::test_kg_seed_manifest_requires_versioned_metadata -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add schemas/kg_seed_manifest.py tests/test_kg_seed_manifest.py
git commit -m "feat: define kg seed manifest schema"
```

### Task 2: Export Current Python Seed To Deterministic Manifest

**Files:**
- Create: `kg/seed_manifest.py`
- Create: `scripts/export_kg_seed_manifest.py`
- Create: `kg/seed_manifest.generated.json`
- Test: `tests/test_kg_seed_manifest.py`

- [ ] **Step 1: Add failing export tests**

Append:

```python
import json
from pathlib import Path

from kg.seed_manifest import build_seed_manifest_payload


def test_build_seed_manifest_payload_contains_current_seed_ids() -> None:
    payload = build_seed_manifest_payload()

    algorithm_ids = {item["algo_id"] for item in payload["algorithms"]}
    data_source_ids = {item["source_id"] for item in payload["data_sources"]}

    assert "algo.fusion.building.v1" in algorithm_ids
    assert "raw.osm.building" in data_source_ids
    assert payload["metadata"]["schema_version"] == "1.0.0"
    assert payload["metadata"]["content_hash"].startswith("sha256:")
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_kg_seed_manifest.py::test_build_seed_manifest_payload_contains_current_seed_ids -q
```

Expected: FAIL because `kg.seed_manifest` does not exist.

- [ ] **Step 3: Implement exporter helpers**

Create `kg/seed_manifest.py`:

```python
from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from kg import seed


SCHEMA_VERSION = "1.0.0"


def build_seed_manifest_payload() -> dict[str, Any]:
    payload = {
        "metadata": {
            "schema_version": SCHEMA_VERSION,
            "generated_from": "kg.seed",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "content_hash": "",
        },
        "data_types": _sorted_dict_values(seed.DATA_TYPES, "type_id"),
        "tasks": _sorted_dict_values(seed.TASKS, "task_id"),
        "scenario_profiles": _sorted_list(seed.SCENARIO_PROFILES, "profile_id"),
        "task_bundles": _sorted_list(seed.TASK_BUNDLES, "bundle_id") if hasattr(seed, "TASK_BUNDLES") else [],
        "output_requirements": _sorted_dict_values(seed.OUTPUT_REQUIREMENTS, "requirement_id") if hasattr(seed, "OUTPUT_REQUIREMENTS") else [],
        "qos_policies": _sorted_dict_values(seed.QOS_POLICIES, "policy_id") if hasattr(seed, "QOS_POLICIES") else [],
        "data_needs": _sorted_list(seed.DATA_NEEDS, "need_id") if hasattr(seed, "DATA_NEEDS") else [],
        "repair_strategies": _sorted_list(seed.REPAIR_STRATEGIES, "strategy_id") if hasattr(seed, "REPAIR_STRATEGIES") else [],
        "algorithms": _sorted_dict_values(seed.ALGORITHMS, "algo_id"),
        "parameter_specs": _flatten_parameter_specs(seed.PARAMETER_SPECS),
        "workflow_patterns": _sorted_list(seed.WORKFLOW_PATTERNS, "pattern_id"),
        "data_sources": _sorted_list(seed.DATA_SOURCES, "source_id"),
        "output_schema_policies": _sorted_dict_values(seed.OUTPUT_SCHEMA_POLICIES, "policy_id"),
    }
    payload["metadata"]["content_hash"] = "sha256:" + _content_hash({**payload, "metadata": {**payload["metadata"], "content_hash": ""}})
    return payload


def _to_plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {key: _to_plain(item) for key, item in dataclasses.asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _to_plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    return value
```

Add deterministic sort helpers and `_content_hash()` using `json.dumps(sort_keys=True, ensure_ascii=False)`.

- [ ] **Step 4: Add export script**

Create `scripts/export_kg_seed_manifest.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path

from kg.seed_manifest import build_seed_manifest_payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="kg/seed_manifest.generated.json")
    args = parser.parse_args(argv)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = build_seed_manifest_payload()
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run it once to create `kg/seed_manifest.generated.json`.

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_kg_seed_manifest.py -q
python scripts/export_kg_seed_manifest.py --output kg/seed_manifest.generated.json
git add kg/seed_manifest.py scripts/export_kg_seed_manifest.py kg/seed_manifest.generated.json tests/test_kg_seed_manifest.py
git commit -m "feat: export versioned kg seed manifest"
```

### Task 3: Load Manifest Back Into KG Dataclasses

**Files:**
- Modify: `kg/seed_manifest.py`
- Test: `tests/test_kg_seed_manifest.py`

- [ ] **Step 1: Add failing loader parity tests**

Append:

```python
from kg.seed_manifest import load_seed_manifest_payload


def test_load_seed_manifest_payload_reconstructs_core_dataclasses() -> None:
    payload = build_seed_manifest_payload()
    loaded = load_seed_manifest_payload(payload)

    assert "algo.fusion.building.v1" in loaded["algorithms"]
    assert loaded["algorithms"]["algo.fusion.building.v1"].algo_id == "algo.fusion.building.v1"
    assert loaded["workflow_patterns"]
    assert loaded["output_schema_policies"]
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_kg_seed_manifest.py::test_load_seed_manifest_payload_reconstructs_core_dataclasses -q
```

Expected: FAIL because the loader does not exist.

- [ ] **Step 3: Implement loader**

In `kg/seed_manifest.py`, import dataclasses from `kg.models` and add:

```python
def load_seed_manifest_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _validate_hash(payload)
    return {
        "data_types": {item["type_id"]: DataTypeNode(**item) for item in payload.get("data_types", [])},
        "tasks": {item["task_id"]: TaskNode(**item) for item in payload.get("tasks", [])},
        "scenario_profiles": [ScenarioProfileNode(**item) for item in payload.get("scenario_profiles", [])],
        "algorithms": {item["algo_id"]: AlgorithmNode(**item) for item in payload.get("algorithms", [])},
        "parameter_specs": _load_parameter_specs(payload.get("parameter_specs", [])),
        "workflow_patterns": [_load_workflow_pattern(item) for item in payload.get("workflow_patterns", [])],
        "data_sources": [DataSourceNode(**item) for item in payload.get("data_sources", [])],
        "output_schema_policies": {
            item["output_type"]: OutputSchemaPolicy(**_coerce_job_type(item))
            for item in payload.get("output_schema_policies", [])
        },
    }
```

Implement `_load_workflow_pattern()` to rebuild `PatternStep` objects and coerce `job_type` strings back to `JobType`.

- [ ] **Step 4: Add hash validation**

`_validate_hash()` must recompute the manifest hash with `metadata.content_hash` blanked and raise `ValueError` on mismatch.

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_kg_seed_manifest.py -q
git add kg/seed_manifest.py tests/test_kg_seed_manifest.py
git commit -m "feat: load kg seed manifests"
```

### Task 4: Add Optional Manifest-Backed InMemory Repository

**Files:**
- Modify: `kg/inmemory_repository.py`
- Test: `tests/test_kg_repository_enhancements.py`

- [ ] **Step 1: Add failing repository parity test**

Append:

```python
def test_inmemory_repository_can_load_seed_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "seed.json"
    manifest_path.write_text(
        json.dumps(build_seed_manifest_payload(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    repo = InMemoryKGRepository(seed_manifest_path=manifest_path)

    assert repo.get_algorithm("algo.fusion.building.v1") is not None
    assert repo.get_candidate_patterns(job_type=JobType.building, disaster_type="flood")
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_kg_repository_enhancements.py::test_inmemory_repository_can_load_seed_manifest -q
```

Expected: FAIL because `seed_manifest_path` is unsupported.

- [ ] **Step 3: Update constructor**

In `kg/inmemory_repository.py`, add optional constructor parameter:

```python
def __init__(self, *, seed_manifest_path: Path | None = None) -> None:
```

When `seed_manifest_path` is provided, read and load manifest payload. Otherwise preserve the existing `kg.seed` path exactly.

- [ ] **Step 4: Add environment hook only if already used locally**

If repository construction already reads environment variables in a factory, add `GEOFUSION_KG_SEED_MANIFEST`. If there is no central factory, do not add global environment behavior in this task; keep the constructor path testable.

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_kg_repository_enhancements.py tests/test_kg_seed_manifest.py -q
git add kg/inmemory_repository.py tests/test_kg_repository_enhancements.py
git commit -m "feat: allow manifest backed kg repository"
```

### Task 5: Parity Guard And Operations Documentation

**Files:**
- Modify: `scripts/export_kg_seed_manifest.py`
- Modify: `docs/no-ui-agent-operations.md`
- Test: `tests/test_kg_seed_manifest.py`
- Test: `tests/test_no_ui_operations_docs.py`

- [ ] **Step 1: Add failing stale-manifest test**

Add a test that reads `kg/seed_manifest.generated.json`, recomputes `build_seed_manifest_payload()` ignoring `generated_at`, and asserts stable entity id sets match.

Required id sets:

- data type ids
- algorithm ids
- workflow pattern ids
- data source ids
- output schema policy ids

- [ ] **Step 2: Add `--check` mode**

Update `scripts/export_kg_seed_manifest.py`:

```powershell
python scripts/export_kg_seed_manifest.py --check --output kg/seed_manifest.generated.json
```

The command must return non-zero if the checked-in generated manifest is stale.

- [ ] **Step 3: Document KG seed governance**

Add to `docs/no-ui-agent-operations.md`:

- `kg/seed.py` remains compatibility source for now
- `kg/seed_manifest.generated.json` is generated, versioned, hash-checked seed evidence
- new KG ids must update seed and rerun export check
- runtime flip to manifest default is a later decision after parity

- [ ] **Step 4: Run verification**

```powershell
py -3.13 -m pytest tests/test_kg_seed_manifest.py tests/test_kg_repository_enhancements.py tests/test_no_ui_operations_docs.py -q
python scripts/export_kg_seed_manifest.py --check --output kg/seed_manifest.generated.json
```

Expected: PASS and no stale manifest error.

- [ ] **Step 5: Commit**

```powershell
git add scripts/export_kg_seed_manifest.py docs/no-ui-agent-operations.md tests/test_kg_seed_manifest.py tests/test_no_ui_operations_docs.py
git commit -m "docs: govern kg seed manifest parity"
```

---

## Final Verification

Run:

```powershell
py -3.13 -m pytest tests/test_kg_seed_manifest.py tests/test_kg_repository_enhancements.py tests/test_kg_graph_service.py tests/test_no_ui_operations_docs.py -q
python scripts/export_kg_seed_manifest.py --check --output kg/seed_manifest.generated.json
rg -n "schema_version|content_hash|seed_manifest.generated.json|GEOFUSION_KG_SEED_MANIFEST" kg schemas scripts tests docs
$patterns = @('TO'+'DO','TB'+'D','\.'+'\.'+'\.','place'+'holder','FIX'+'ME','X'+'XX')
Select-String -Path docs/superpowers/plans/2026-06-04-kg-seed-externalization-and-versioning.md -Pattern $patterns
```

Expected:

- Manifest export and check are deterministic.
- Manifest-backed repository preserves core KG behavior.
- Existing seed remains available.
- Documentation clearly says the runtime default has not been flipped yet unless that is implemented in Task 4.

## Integration Commit

After all tasks pass:

```powershell
git status --short
git log --oneline -5
```

Then merge and push according to the active superpowers branch-finishing workflow.
