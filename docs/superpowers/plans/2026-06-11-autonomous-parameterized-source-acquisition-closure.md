# Autonomous Parameterized Source Acquisition Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make FusionAgent autonomously acquire and fuse city/county-to-national building, road, POI, waterway, and lake/water-polygon data by extending KG parameter specs and the existing input acquisition pipeline instead of adding parallel abstractions.

**Architecture:** Do not introduce `FusionSlotContract` or `SourceAttemptPlanner`. Extend `AlgorithmParameterSpec` to carry conditional defaults and provenance, and enhance `InputAcquisitionService` / `SourceAssetService` so source attempts, coverage degradation, Google source promotion, and fusion-path selection are first-class evidence in the current runtime.

**Tech Stack:** Python, dataclasses, Pydantic, GeoPandas, pyogrio, existing KG repositories, existing `InputAcquisitionService`, `SourceAssetService`, `LocalBundleCatalogProvider`, `TrackBNationalScaleService`, pytest, PowerShell on Windows.

---

## Design Rules From User Review

- Do not create a new `FusionSlotContract` abstraction.
- Treat KG `AlgorithmParameterSpec` as the canonical place for algorithm input/parameter slots, static defaults, conditional defaults, and provenance.
- Do not create a new `SourceAttemptPlanner` module.
- Enhance `InputAcquisitionService` and existing provider services to record all candidate source attempts, classify failure reasons, support partial-but-explainable degradation, and write evidence.
- Google building and Google POI are required automatic acquisition targets.
- Building core geometry sources are Google, Microsoft, and OSM; OBM is optional supplemental source. OSM road is a required building-conflict constraint.
- POI full path requires GNS/GeoNames, Google POI, and OSM POI in the order expected by the algorithm: `GNG`, `GOOGLE`, `OSM`.

## Phase 0: Documentation And Code Discovery

### Sources Already Consulted

- `kg/models.py`
  - `AlgorithmParameterSpec` is defined here, not in `schemas/agent.py`.
  - Current fields: `spec_id`, `algo_id`, `key`, `label`, `param_type`, `default`, `min_value`, `max_value`, `unit`, `description`, `required`, `choices`, `tunable`, `optimization_tags`, `order`.
- `kg/seed.py`
  - `PARAMETER_SPECS` seeds static parameter values.
- `kg/bootstrap.py`
  - `_build_parameter_spec_section()` writes `AlgorithmParameterSpec` nodes to Neo4j.
- `kg/neo4j_repository.py`
  - `get_parameter_specs()` maps Neo4j nodes back to `AlgorithmParameterSpec`.
- `services/input_acquisition_service.py`
  - Already owns `MaterializedInputBundle`, `ResolvedRunInputs`, `provider_attempts`, `component_coverage`, and `source_materialization_manifest.json` writing.
- `services/source_asset_service.py`
  - Already owns raw source materialization for OSM, Microsoft buildings, Overture transportation, HydroRIVERS, HydroLAKES, and GNS POI. This plan promotes Microsoft road materialization for the road fusion closure path.
- `services/local_bundle_catalog.py`
  - Already owns catalog bundle materialization and fallback. Currently only water adds supplemental `raw.osm.waterways` and `raw.hydrorivers.water`.
- `services/source_acquisition_policy.py`
  - Already owns `SourceAcquisitionAttempt`, recoverable fault classification, fallback candidates, and complete-pair policy.
- `services/track_b_national_scale_service.py`
  - Already owns national-scale evidence for building, road, water, waterways, and POI.
- `adapters/fusioncode_poi_adapter.py`
  - Current POI adapter accepts `context.named_vectors` and falls back to `{"OSM": base, "GNG": target}`.

### Allowed APIs And Patterns

- Use `KGRepository.get_parameter_specs(algo_id)` as the read path for parameter specs.
- Use `InputAcquisitionService.resolve_task_driven_inputs(...)` as the task-driven input entry point.
- Use `LocalBundleCatalogProvider.materialize_with_fallback(...)` for catalog bundles.
- Use `RawVectorSourceService.resolve(...)` and `SourceAssetService.resolve_raw_source_path(...)` for raw vectors.
- Use `SourceAcquisitionAttempt` from `schemas/source_acquisition.py` for source attempt payloads.
- Use `source_materialization_manifest.json` as the current evidence file and extend its schema version only if needed.

### Anti-Pattern Guards

- Do not add `FusionSlotContract`.
- Do not add `SourceAttemptPlanner`.
- Do not make Google sources look successful when API credentials, authorization manifest, upstream coverage, or network access are absent.
- Do not silently treat Google POI absence as a full POI success.
- Do not keep `raw.google.building` as `manual_preload_required` after this plan; it must become an automatic acquisition target with coverage-aware failure classification.
- Do not hide component coverage in internal logs only; final run evidence must expose it.

---

## File Structure

- Modify: `kg/models.py`
  - Extend `AlgorithmParameterSpec` with conditional defaults and provenance fields.
- Modify: `kg/seed.py`
  - Add conditional default examples for building, road, water, and POI algorithms.
  - Promote Google building and Google POI source metadata.
- Modify: `kg/bootstrap.py`
  - Persist new parameter spec fields into Neo4j.
- Modify: `kg/neo4j_repository.py`
  - Read new parameter spec fields from Neo4j.
- Modify: `tests/test_kg_parameter_specs.py`
  - Cover conditional defaults and provenance on in-memory KG.
- Modify: `tests/test_neo4j_repository.py`
  - Cover conditional defaults and provenance mapping from fake Neo4j rows.
- Create: `services/conditional_parameter_service.py`
  - Resolve effective parameter values from `AlgorithmParameterSpec` using source combination, region, AOI, and durable-learning context.
- Create: `tests/test_conditional_parameter_service.py`
  - Unit tests for source-combination, region, and provenance precedence.
- Modify: `agent/semantic_parameter_binding.py`
  - Bind conditional parameter defaults through KG specs without inventing unsupported keys.
- Modify: `services/source_acquisition_policy.py`
  - Add normalized source attempt statuses and fault classes.
- Modify: `schemas/source_acquisition.py`
  - Add optional `coverage_status`, `feature_count`, `selected_for_fusion`, and `external_uncontrollable` fields to `SourceAcquisitionAttempt`.
- Modify: `services/input_acquisition_service.py`
  - Record all candidate source attempts, merge provider attempt payloads, classify failures, and write `source_attempts.json`.
- Modify: `services/source_materialization_manifest_service.py`
  - Include `source_attempts_path`, `coverage_state`, and `degradation` in the manifest.
- Modify: `services/local_bundle_catalog.py`
  - Attempt all configured component and supplemental sources for building, road, water, waterways, and POI without failing on optional-source absence.
- Modify: `services/source_asset_service.py`
  - Add Google Open Buildings automatic vector materialization and Google POI materialization.
- Modify: `kg/source_catalog.py`
  - Add `raw.google.poi`; promote `raw.google.building` or `raw.google.open_buildings.vector` to automatic acquisition metadata; keep OBM optional.
- Modify: `kg/track_b_source_contract.py`
  - Update Track B source contracts to reflect Google building and Google POI automatic targets.
- Modify: `services/track_b_source_normalization.py`
  - Normalize Google POI fields into canonical POI schema and Google building fields into canonical building schema.
- Modify: `adapters/fusioncode_poi_adapter.py`
  - Ensure named vector order supports `GNG`, `GOOGLE`, `OSM`.
- Modify: `services/track_b_national_scale_service.py`
  - Include Google building and Google POI in selected/supplemental national evidence and success classification.
- Create: `services/autonomous_fusion_readiness_service.py`
  - Summarize whether a run meets autonomous full-closure criteria per task.
- Create: `tests/test_autonomous_fusion_readiness_service.py`
  - Cover full success, degraded success, and external-uncontrollable failure.
- Modify: `scripts/build_track_b_national_evidence.py`
  - Add options for Google authorization manifest and full-closure evidence mode.
- Create: `docs/superpowers/specs/2026-06-11-autonomous-source-acquisition-contract.md`
  - Human-readable contract for source attempts, conditional parameters, Google authorization, and claim boundaries.

---

## Task 1: Extend AlgorithmParameterSpec With Conditional Defaults

**Files:**
- Modify: `kg/models.py`
- Modify: `kg/seed.py`
- Modify: `kg/bootstrap.py`
- Modify: `kg/neo4j_repository.py`
- Test: `tests/test_kg_parameter_specs.py`
- Test: `tests/test_neo4j_repository.py`

- [ ] **Step 1: Add failing in-memory KG test**

Append to `tests/test_kg_parameter_specs.py`:

```python
def test_parameter_specs_support_conditional_defaults_and_provenance() -> None:
    repo = InMemoryKGRepository()

    spec = next(
        item
        for item in repo.get_parameter_specs("algo.fusion.building.v1")
        if item.key == "match_similarity_threshold"
    )

    assert spec.default is not None
    assert spec.conditional_defaults, "Expected conditional defaults on building match threshold."
    assert {
        "when",
        "value",
        "provenance",
    }.issubset(spec.conditional_defaults[0])
    assert spec.default_provenance["source"] == "static_seed"
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
py -3.13 -m pytest tests/test_kg_parameter_specs.py::test_parameter_specs_support_conditional_defaults_and_provenance -q
```

Expected: FAIL because `AlgorithmParameterSpec` has no `conditional_defaults` or `default_provenance`.

- [ ] **Step 3: Extend the model**

In `kg/models.py`, change `AlgorithmParameterSpec` to:

```python
@dataclass
class AlgorithmParameterSpec:
    spec_id: str
    algo_id: str
    key: str
    label: str
    param_type: str
    default: Optional[Any] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    unit: Optional[str] = None
    description: str = ""
    required: bool = False
    choices: Optional[List[Any]] = None
    tunable: bool = False
    optimization_tags: List[str] = field(default_factory=list)
    order: int = 0
    conditional_defaults: List[Dict[str, Any]] = field(default_factory=list)
    default_provenance: Dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: Seed conditional defaults**

In `kg/seed.py`, update the `AlgorithmParameterSpec` for `algo.fusion.building.v1` key `match_similarity_threshold` so it includes:

```python
conditional_defaults=[
    {
        "when": {"source_combination": ["raw.google.building", "raw.osm.building"]},
        "value": 0.75,
        "provenance": {"source": "manual_seed", "reason": "Google/OSM building matches need stricter geometry confidence."},
    },
    {
        "when": {"source_combination": ["raw.microsoft.building", "raw.osm.building"]},
        "value": 0.70,
        "provenance": {"source": "static_seed", "reason": "Current Microsoft/OSM default."},
    },
    {
        "when": {"region_country_name": "Nepal"},
        "value": 0.65,
        "provenance": {"source": "operator_annotation", "reason": "Nepal training run tolerance."},
    },
    {
        "when": {"region_country_name": "Mongolia"},
        "value": 0.75,
        "provenance": {"source": "operator_annotation", "reason": "Mongolia training run precision preference."},
    },
],
default_provenance={"source": "static_seed", "reason": "Original KG seed default."},
```

Add similar `default_provenance={"source": "static_seed"}` to other active runtime specs gradually in this task. Do not invent conditional values for every algorithm.

- [ ] **Step 5: Persist fields to Neo4j**

In `kg/bootstrap.py`, add these properties in `_build_parameter_spec_section()`:

```python
"conditionalDefaults": json.dumps(spec.conditional_defaults, ensure_ascii=False),
"defaultProvenance": json.dumps(spec.default_provenance, ensure_ascii=False),
```

Use JSON strings for these nested fields to match the repo's existing `metadataJson` style.

- [ ] **Step 6: Read fields from Neo4j**

In `kg/neo4j_repository.py`, add a helper near `_parse_metadata_json()` if one does not already exist:

```python
@staticmethod
def _parse_json_property(value: object, fallback: object) -> object:
    if value in {None, ""}:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return fallback
```

Then pass these fields in `get_parameter_specs()`:

```python
conditional_defaults=list(self._parse_json_property(ps.get("conditionalDefaults"), [])),
default_provenance=dict(self._parse_json_property(ps.get("defaultProvenance"), {})),
```

- [ ] **Step 7: Add fake Neo4j mapping test**

In `tests/test_neo4j_repository.py`, extend `test_get_parameter_specs_maps_rows_from_fake_driver` or add:

```python
def test_get_parameter_specs_maps_conditional_defaults_from_fake_driver() -> None:
    repo, _driver = _repo_with_rows(
        [
            {
                "ps": {
                    "specId": "ps.test.threshold",
                    "algoId": "algo.test",
                    "key": "threshold",
                    "label": "Threshold",
                    "paramType": "float",
                    "default": 0.7,
                    "conditionalDefaults": '[{"when":{"region_country_name":"Nepal"},"value":0.65,"provenance":{"source":"operator_annotation"}}]',
                    "defaultProvenance": '{"source":"static_seed"}',
                },
                "hs": {"order": 1},
            }
        ]
    )

    specs = repo.get_parameter_specs("algo.test")

    assert specs[0].conditional_defaults[0]["value"] == 0.65
    assert specs[0].default_provenance["source"] == "static_seed"
```

Use the existing fake-driver helper names in `tests/test_neo4j_repository.py`; if the helper name differs, adapt this snippet to the local test pattern.

- [ ] **Step 8: Run tests**

Run:

```powershell
py -3.13 -m pytest tests/test_kg_parameter_specs.py tests/test_neo4j_repository.py tests/test_neo4j_bootstrap.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

Run:

```powershell
git add kg/models.py kg/seed.py kg/bootstrap.py kg/neo4j_repository.py tests/test_kg_parameter_specs.py tests/test_neo4j_repository.py
git commit -m "feat: add conditional algorithm parameter defaults"
```

---

## Task 2: Resolve Effective Parameters From KG Specs

**Files:**
- Create: `services/conditional_parameter_service.py`
- Modify: `agent/semantic_parameter_binding.py`
- Test: `tests/test_conditional_parameter_service.py`
- Test: `tests/test_semantic_parameter_binding.py`

- [ ] **Step 1: Write failing conditional-resolution tests**

Create `tests/test_conditional_parameter_service.py`:

```python
from __future__ import annotations

from kg.models import AlgorithmParameterSpec
from services.conditional_parameter_service import (
    ConditionalParameterContext,
    resolve_effective_parameters,
)


def _spec() -> AlgorithmParameterSpec:
    return AlgorithmParameterSpec(
        spec_id="ps.algo.fusion.building.v1.match_similarity_threshold",
        algo_id="algo.fusion.building.v1",
        key="match_similarity_threshold",
        label="Match Similarity Threshold",
        param_type="float",
        default=0.70,
        min_value=0.0,
        max_value=1.0,
        conditional_defaults=[
            {
                "when": {"source_combination": ["raw.google.building", "raw.osm.building"]},
                "value": 0.75,
                "provenance": {"source": "manual_seed"},
            },
            {
                "when": {"region_country_name": "Nepal"},
                "value": 0.65,
                "provenance": {"source": "operator_annotation"},
            },
        ],
        default_provenance={"source": "static_seed"},
    )


def test_source_combination_conditional_default_wins_before_region() -> None:
    context = ConditionalParameterContext(
        source_ids=["raw.osm.building", "raw.google.building", "raw.microsoft.building"],
        region_country_name="Nepal",
    )

    result = resolve_effective_parameters([_spec()], context)

    assert result.values["match_similarity_threshold"] == 0.75
    assert result.provenance["match_similarity_threshold"]["source"] == "manual_seed"


def test_region_conditional_default_applies_when_source_condition_absent() -> None:
    context = ConditionalParameterContext(
        source_ids=["raw.osm.building", "raw.microsoft.building"],
        region_country_name="Nepal",
    )

    result = resolve_effective_parameters([_spec()], context)

    assert result.values["match_similarity_threshold"] == 0.65
    assert result.provenance["match_similarity_threshold"]["source"] == "operator_annotation"


def test_static_default_has_static_provenance() -> None:
    context = ConditionalParameterContext(source_ids=["raw.osm.building"])

    result = resolve_effective_parameters([_spec()], context)

    assert result.values["match_similarity_threshold"] == 0.70
    assert result.provenance["match_similarity_threshold"]["source"] == "static_seed"
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
py -3.13 -m pytest tests/test_conditional_parameter_service.py -q
```

Expected: FAIL because `services.conditional_parameter_service` does not exist.

- [ ] **Step 3: Implement resolver**

Create `services/conditional_parameter_service.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kg.models import AlgorithmParameterSpec


@dataclass(frozen=True)
class ConditionalParameterContext:
    source_ids: list[str] = field(default_factory=list)
    region_country_name: str | None = None
    region_country_code: str | None = None
    aoi_size_bucket: str | None = None
    quality_outcome: str | None = None
    durable_learning_overrides: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EffectiveParameterResult:
    values: dict[str, Any]
    provenance: dict[str, dict[str, Any]]


def resolve_effective_parameters(
    specs: list[AlgorithmParameterSpec],
    context: ConditionalParameterContext,
) -> EffectiveParameterResult:
    values: dict[str, Any] = {}
    provenance: dict[str, dict[str, Any]] = {}
    for spec in specs:
        value = spec.default
        source = dict(spec.default_provenance or {"source": "static_seed"})
        for candidate in spec.conditional_defaults:
            when = dict(candidate.get("when") or {})
            if _matches_condition(when, context):
                value = candidate.get("value")
                source = dict(candidate.get("provenance") or {"source": "conditional_default"})
                break
        if spec.key in context.durable_learning_overrides:
            value = context.durable_learning_overrides[spec.key]
            source = {"source": "durable_learning", "reason": "runtime feedback override"}
        values[spec.key] = value
        provenance[spec.key] = source
    return EffectiveParameterResult(values=values, provenance=provenance)


def _matches_condition(condition: dict[str, Any], context: ConditionalParameterContext) -> bool:
    if "source_combination" in condition:
        required = {str(item) for item in condition["source_combination"]}
        if not required.issubset({str(item) for item in context.source_ids}):
            return False
    if "region_country_name" in condition:
        if str(condition["region_country_name"]).casefold() != str(context.region_country_name or "").casefold():
            return False
    if "region_country_code" in condition:
        if str(condition["region_country_code"]).casefold() != str(context.region_country_code or "").casefold():
            return False
    if "aoi_size_bucket" in condition:
        if str(condition["aoi_size_bucket"]) != str(context.aoi_size_bucket or ""):
            return False
    if "quality_outcome" in condition:
        if str(condition["quality_outcome"]) != str(context.quality_outcome or ""):
            return False
    return True
```

Precedence is intentionally deterministic: first matching `conditional_defaults` entry wins, then durable-learning overrides win over seeded defaults.

- [ ] **Step 4: Bind conditional defaults into semantic parameter binding**

In `agent/semantic_parameter_binding.py`, import:

```python
from services.conditional_parameter_service import ConditionalParameterContext, resolve_effective_parameters
```

Add helper:

```python
def _bind_conditional_defaults(params: dict, task, contract: SourceSemanticContract, kg_repo) -> dict:
    if kg_repo is None:
        return params
    get_parameter_specs = getattr(kg_repo, "get_parameter_specs", None)
    if not callable(get_parameter_specs):
        return params
    specs = list(get_parameter_specs(task.algorithm_id))
    if not specs:
        return params
    source_ids = list(getattr(contract, "component_source_ids", []) or [])
    result = resolve_effective_parameters(
        specs,
        ConditionalParameterContext(
            source_ids=source_ids,
            region_country_name=str(contract.metadata.get("country_name") or "") if isinstance(contract.metadata, dict) else None,
            region_country_code=str(contract.metadata.get("country_code") or "") if isinstance(contract.metadata, dict) else None,
        ),
    )
    for key, value in result.values.items():
        params.setdefault(key, value)
    params.setdefault("parameter_provenance", result.provenance)
    return params
```

Call it after existing source-semantic hints are applied:

```python
params = _bind_conditional_defaults(params, task, contract, kg_repo)
```

If `SourceSemanticContract` lacks `metadata`, use `getattr(contract, "metadata", {})` in the helper. Do not add arbitrary attributes to the contract.

- [ ] **Step 5: Add semantic binding regression**

Append to `tests/test_semantic_parameter_binding.py`:

```python
def test_semantic_parameter_binding_uses_conditional_parameter_defaults() -> None:
    plan = _plan("building", "algo.fusion.building.v1")
    contract = _contract(
        job_type="building",
        component_source_ids=["raw.google.building", "raw.osm.building"],
        metadata={"country_name": "Nepal"},
    )

    bound = bind_source_semantic_parameters(plan, contract, kg_repo=InMemoryKGRepository())

    params = bound.tasks[0].input.parameters
    assert params["match_similarity_threshold"] == 0.75
    assert params["parameter_provenance"]["match_similarity_threshold"]["source"] in {
        "manual_seed",
        "operator_annotation",
        "static_seed",
    }
```

Adapt `_contract` helper arguments to the local test helper names.

- [ ] **Step 6: Run tests**

Run:

```powershell
py -3.13 -m pytest tests/test_conditional_parameter_service.py tests/test_semantic_parameter_binding.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```powershell
git add services/conditional_parameter_service.py agent/semantic_parameter_binding.py tests/test_conditional_parameter_service.py tests/test_semantic_parameter_binding.py
git commit -m "feat: resolve conditional kg parameter defaults"
```

---

## Task 3: Strengthen Source Attempts In InputAcquisitionService

**Files:**
- Modify: `schemas/source_acquisition.py`
- Modify: `services/source_acquisition_policy.py`
- Modify: `services/input_acquisition_service.py`
- Modify: `services/source_materialization_manifest_service.py`
- Test: `tests/test_input_acquisition_service.py`
- Test: `tests/test_input_acquisition_faults.py`

- [ ] **Step 1: Write failing source attempt evidence test**

Append to `tests/test_input_acquisition_service.py`:

```python
def test_input_acquisition_writes_source_attempts_json_with_component_status(tmp_path: Path) -> None:
    registry = ArtifactRegistry(index_path=tmp_path / "registry.json")
    provider = _FakeBundleProvider(
        source_id="catalog.generic.poi",
        component_coverage={
            "raw.osm.poi": {"source_id": "raw.osm.poi", "feature_count": 8, "coverage_status": "available"},
            "raw.google.poi": {"source_id": "raw.google.poi", "feature_count": 3, "coverage_status": "available"},
            "raw.gns.poi": {"source_id": "raw.gns.poi", "feature_count": 7, "coverage_status": "available"},
        },
        provider_attempts=[
            {"source_id": "raw.osm.poi", "status": "available", "feature_count": 8},
            {"source_id": "raw.google.poi", "status": "available", "feature_count": 3},
            {"source_id": "raw.gns.poi", "status": "available", "feature_count": 7},
        ],
    )
    service = InputAcquisitionService(registry=registry, providers=[provider], cache_dir=tmp_path / "cache")

    resolved = service.resolve_task_driven_inputs(
        request=_request("poi"),
        source_id="catalog.generic.poi",
        required_output_type="dt.poi.bundle",
        input_dir=tmp_path / "run-input",
        request_bbox=(0, 0, 1, 1),
    )

    attempts_path = resolved.manifest_path.parent / "source_attempts.json"
    attempts = json.loads(attempts_path.read_text(encoding="utf-8"))
    assert [item["source_id"] for item in attempts["attempts"]] == [
        "raw.osm.poi",
        "raw.google.poi",
        "raw.gns.poi",
    ]
    assert attempts["coverage_state"] == "complete"
```

Use the existing fake provider/request helper names in the file; if they differ, adapt the constructor but preserve the assertions.

- [ ] **Step 2: Run failing test**

Run:

```powershell
py -3.13 -m pytest tests/test_input_acquisition_service.py::test_input_acquisition_writes_source_attempts_json_with_component_status -q
```

Expected: FAIL because `source_attempts.json` is not written.

- [ ] **Step 3: Extend SourceAcquisitionAttempt schema**

In `schemas/source_acquisition.py`, extend the model:

```python
class SourceAcquisitionAttempt(BaseModel):
    source_id: str
    status: str
    attempt_type: str = "provider"
    attempt_no: int = 1
    channel: str | None = None
    fault_class: str | None = None
    fault_message: str | None = None
    recoverable: bool = False
    next_retry_after_seconds: int | None = None
    coverage_status: str | None = None
    feature_count: int | None = None
    selected_for_fusion: bool = False
    external_uncontrollable: bool = False
```

- [ ] **Step 4: Add normalized source attempt builders**

In `services/source_acquisition_policy.py`, add constants:

```python
SOURCE_ATTEMPT_STATUSES = {
    "attempted",
    "available",
    "empty",
    "no_coverage",
    "network_failed",
    "provider_failed",
    "unauthorized",
    "cache_reused",
    "materialized",
}

EXTERNAL_UNCONTROLLABLE_FAULTS = {
    "SOURCE_DOWNLOAD_FAILED",
    "NETWORK_FAILED",
    "PROVIDER_UNAVAILABLE",
    "NO_OFFICIAL_COVERAGE",
    "UNAUTHORIZED",
}
```

Add:

```python
def build_source_attempt(
    *,
    source_id: str,
    status: str,
    attempt_no: int = 1,
    channel: str | None = None,
    fault_class: str | None = None,
    fault_message: str | None = None,
    coverage_status: str | None = None,
    feature_count: int | None = None,
    selected_for_fusion: bool = False,
) -> dict[str, object]:
    normalized_status = str(status or "attempted")
    external = str(fault_class or "") in EXTERNAL_UNCONTROLLABLE_FAULTS
    return SourceAcquisitionAttempt(
        source_id=source_id,
        status=normalized_status,
        attempt_no=attempt_no,
        channel=channel,
        fault_class=fault_class,
        fault_message=fault_message,
        recoverable=is_recoverable_fault(str(fault_class or "")),
        next_retry_after_seconds=retry_schedule_seconds(attempt_no=attempt_no) if fault_class and is_recoverable_fault(str(fault_class)) else None,
        coverage_status=coverage_status,
        feature_count=feature_count,
        selected_for_fusion=selected_for_fusion,
        external_uncontrollable=external,
    ).model_dump(mode="json")
```

Keep `build_failed_attempt()` and `build_success_attempt()` for backward compatibility, but make them delegate to `build_source_attempt()`.

- [ ] **Step 5: Write source_attempts.json in InputAcquisitionService**

In `services/input_acquisition_service.py`, add:

```python
def _write_source_attempts(
    *,
    path: Path,
    attempts: list[dict[str, object]],
    component_coverage: dict[str, object],
) -> Path:
    coverage = _jsonable_component_coverage(component_coverage)
    coverage_state = _coverage_state(coverage)
    payload = {
        "schema_version": 1,
        "coverage_state": coverage_state,
        "attempts": attempts,
        "component_coverage": coverage,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _coverage_state(component_coverage: dict[str, dict[str, object]]) -> str:
    if not component_coverage:
        return "missing"
    statuses = [str(item.get("coverage_status") or "") for item in component_coverage.values()]
    if statuses and all(status == "available" for status in statuses):
        return "complete"
    if any(status == "available" for status in statuses):
        return "partial"
    if any(status == "empty" for status in statuses):
        return "empty"
    return "missing"
```

Add `import json` at the top if absent.

After materialization succeeds, write:

```python
source_attempts_path = self._write_source_attempts(
    path=input_dir / "source_attempts.json",
    attempts=_provider_attempts_for_materialized(source_id, materialized),
    component_coverage=_jsonable_component_coverage(materialized.component_coverage),
)
```

Pass `source_attempts_path` into `_write_manifest()`.

- [ ] **Step 6: Extend manifest schema**

In `services/source_materialization_manifest_service.py`, add optional parameters:

```python
source_attempts_path: str | None = None,
coverage_state: str | None = None,
degradation: dict[str, object] | None = None,
```

Add these keys to the returned manifest:

```python
"source_attempts_path": source_attempts_path,
"coverage_state": coverage_state,
"degradation": dict(degradation or {}),
```

Update every `_write_manifest()` call in `InputAcquisitionService` to pass these values. Use `coverage_state=_coverage_state(component_coverage)` and `source_attempts_path=str(source_attempts_path)` when present.

- [ ] **Step 7: Run acquisition tests**

Run:

```powershell
py -3.13 -m pytest tests/test_input_acquisition_service.py tests/test_input_acquisition_faults.py tests/test_source_materialization_manifest_service.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```powershell
git add schemas/source_acquisition.py services/source_acquisition_policy.py services/input_acquisition_service.py services/source_materialization_manifest_service.py tests/test_input_acquisition_service.py tests/test_input_acquisition_faults.py
git commit -m "feat: record structured source acquisition attempts"
```

---

## Task 4: Promote Google Building Automatic Acquisition

**Files:**
- Modify: `services/source_asset_service.py`
- Modify: `kg/source_catalog.py`
- Modify: `kg/track_b_source_contract.py`
- Modify: `services/track_b_source_normalization.py`
- Test: `tests/test_source_asset_service.py`
- Test: `tests/test_track_b_source_matrix.py`
- Test: `tests/test_track_b_source_normalization.py`

- [ ] **Step 1: Add failing source-asset test using injected Google index**

Append to `tests/test_source_asset_service.py`:

```python
def test_source_asset_service_materializes_google_buildings_from_open_buildings_index(tmp_path: Path) -> None:
    google_csv = tmp_path / "google_open_buildings.csv"
    google_csv.write_text(
        "latitude,longitude,area_in_meters,confidence,geometry\n"
        "\"0.5\",\"0.5\",\"20\",\"0.9\",\"POLYGON ((0.49 0.49, 0.51 0.49, 0.51 0.51, 0.49 0.51, 0.49 0.49))\"\n",
        encoding="utf-8",
    )
    service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache",
        google_open_buildings_urls=[google_csv.as_uri()],
        prefer_local_data=False,
    )

    resolved = service.resolve_raw_source_path(
        "raw.google.building",
        request_bbox=(0, 0, 1, 1),
        aoi=_resolved_nairobi_aoi(),
    )

    assert resolved.source_id == "raw.google.building"
    assert resolved.feature_count == 1
    assert resolved.source_mode in {"asset_downloaded", "asset_cached"}
```

This test uses local file URIs so it does not require live Google network access.

- [ ] **Step 2: Run failing test**

Run:

```powershell
py -3.13 -m pytest tests/test_source_asset_service.py::test_source_asset_service_materializes_google_buildings_from_open_buildings_index -q
```

Expected: FAIL because `SourceAssetService` does not accept `google_open_buildings_urls`.

- [ ] **Step 3: Implement Google building source injection**

In `services/source_asset_service.py`:

- Add `"raw.google.building"` and `"raw.google.open_buildings.vector"` to `_REMOTELY_MATERIALIZABLE_SOURCE_IDS`.
- Add constructor argument:

```python
google_open_buildings_urls: list[str] | None = None,
```

- Store:

```python
self.google_open_buildings_urls = list(google_open_buildings_urls or [])
```

- In `resolve_raw_source_path()`, before the final `FileNotFoundError`, add:

```python
if source_id in {"raw.google.building", "raw.google.open_buildings.vector"}:
    return self._resolve_google_open_buildings(source_id=source_id, request_bbox=effective_bbox)
```

- Implement:

```python
def _resolve_google_open_buildings(
    self,
    *,
    source_id: str,
    request_bbox: Optional[BBox],
) -> SourceAssetResolution:
    if not self.google_open_buildings_urls:
        raise FileNotFoundError("Google Open Buildings URL index is not configured for automatic materialization.")
    target_dir = self.cache_dir / "google_open_buildings" / _bbox_cache_key(request_bbox)
    output_gpkg = target_dir / "google_open_buildings.gpkg"
    cache_hit = output_gpkg.exists()
    if not cache_hit:
        frames = []
        for url in self.google_open_buildings_urls:
            local_csv = self._download_cached(url, cache_subdir="google_open_buildings_parts")
            frame = self._load_google_open_buildings_csv(local_csv)
            if request_bbox is not None and not frame.empty:
                frame = clip_frame_to_request_bbox(frame, request_bbox)
            if not frame.empty:
                frames.append(frame)
        target_dir.mkdir(parents=True, exist_ok=True)
        if frames:
            merged = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs="EPSG:4326")
        else:
            merged = gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs="EPSG:4326")
        merged.to_file(output_gpkg, driver="GPKG")
    bbox, feature_count = self._inspect_vector_path(output_gpkg)
    return SourceAssetResolution(
        source_id=source_id,
        path=output_gpkg,
        source_mode="coverage_empty" if feature_count == 0 else ("asset_cached" if cache_hit else "asset_downloaded"),
        cache_hit=cache_hit,
        version_token=_path_version_token(output_gpkg),
        bbox=bbox,
        feature_count=feature_count,
    )
```

Add loader:

```python
@staticmethod
def _load_google_open_buildings_csv(path: Path) -> gpd.GeoDataFrame:
    frame = pd.read_csv(path)
    if "geometry" not in frame.columns:
        raise ValueError(f"Google Open Buildings CSV lacks geometry column: {path}")
    from shapely import wkt
    frame["geometry"] = frame["geometry"].apply(wkt.loads)
    return gpd.GeoDataFrame(frame, geometry="geometry", crs="EPSG:4326")
```

This implementation intentionally supports injected URL lists first. A later task can add official tile-index discovery when the exact source index is finalized.

- [ ] **Step 4: Promote metadata**

In `kg/track_b_source_contract.py`, change `raw.google.building`:

- `acquisition_class`: `official_remote_supported`
- `materialization_scope`: `resolved_aoi_clip`
- `license_boundary`: mention Google Open Buildings attribution and CC-BY-4.0.

In `kg/source_catalog.py`, ensure `raw.google.building` metadata says:

```python
"supports_aoi": True,
"materialization_scope": "resolved_aoi_clip",
"acquisition_class": "official_remote_supported",
"selectable_now": True,
```

Keep `raw.openbuildingmap.building` optional/supplemental. Do not promote OBM.

- [ ] **Step 5: Add normalization test for Google building**

In `tests/test_track_b_source_normalization.py`, add:

```python
def test_track_b_normalization_maps_google_building_fields() -> None:
    frame = gpd.GeoDataFrame(
        {"confidence": [0.91]},
        geometry=[Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])],
        crs="EPSG:4326",
    )

    normalized = normalize_track_b_source_frame("raw.google.building", frame, target_crs="EPSG:4326")

    assert normalized.loc[0, "source_id"] == "raw.google.building"
    assert "source_feature_id" in normalized.columns
    assert "confidence" in normalized.columns
```

- [ ] **Step 6: Run tests**

Run:

```powershell
py -3.13 -m pytest tests/test_source_asset_service.py tests/test_track_b_source_matrix.py tests/test_track_b_source_normalization.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```powershell
git add services/source_asset_service.py kg/source_catalog.py kg/track_b_source_contract.py services/track_b_source_normalization.py tests/test_source_asset_service.py tests/test_track_b_source_matrix.py tests/test_track_b_source_normalization.py
git commit -m "feat: promote google building automatic acquisition"
```

---

## Task 5: Add Authorized Google POI Automatic Acquisition

**Files:**
- Modify: `services/source_asset_service.py`
- Modify: `kg/source_catalog.py`
- Modify: `kg/track_b_source_contract.py`
- Modify: `services/track_b_source_normalization.py`
- Test: `tests/test_source_asset_service.py`
- Test: `tests/test_track_b_source_matrix.py`
- Test: `tests/test_track_b_source_normalization.py`

- [ ] **Step 1: Add failing authorization-gated POI test**

Append to `tests/test_source_asset_service.py`:

```python
def test_source_asset_service_requires_google_poi_authorization_manifest(tmp_path: Path) -> None:
    service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache",
        prefer_local_data=False,
        google_places_fetcher=lambda bbox, api_key: [],
    )

    with pytest.raises(PermissionError, match="Google POI persistence authorization"):
        service.resolve_raw_source_path(
            "raw.google.poi",
            request_bbox=(0, 0, 1, 1),
            aoi=_resolved_nairobi_aoi(),
        )


def test_source_asset_service_materializes_authorized_google_poi(tmp_path: Path) -> None:
    auth = tmp_path / "google_poi_authorization.json"
    auth.write_text(
        json.dumps(
            {
                "provider": "google_places",
                "authorization_status": "approved",
                "authorized_use": {
                    "persistent_storage": True,
                    "export_vector_files": True,
                    "fuse_with_non_google_sources": True,
                },
                "attribution_required": True,
            }
        ),
        encoding="utf-8",
    )

    def fetcher(bbox, api_key):
        return [
            {
                "place_id": "place-1",
                "name": "Hospital",
                "category": "hospital",
                "lat": 0.5,
                "lng": 0.5,
            }
        ]

    service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache",
        prefer_local_data=False,
        google_places_api_key="test-key",
        google_poi_authorization_path=auth,
        google_places_fetcher=fetcher,
    )

    resolved = service.resolve_raw_source_path(
        "raw.google.poi",
        request_bbox=(0, 0, 1, 1),
        aoi=_resolved_nairobi_aoi(),
    )

    assert resolved.source_id == "raw.google.poi"
    assert resolved.feature_count == 1
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
py -3.13 -m pytest tests/test_source_asset_service.py::test_source_asset_service_requires_google_poi_authorization_manifest tests/test_source_asset_service.py::test_source_asset_service_materializes_authorized_google_poi -q
```

Expected: FAIL because Google POI fields and provider do not exist.

- [ ] **Step 3: Add constructor configuration**

In `services/source_asset_service.py`, add constructor arguments:

```python
google_places_api_key: str | None = None,
google_poi_authorization_path: Path | None = None,
google_places_fetcher: object | None = None,
```

Store them:

```python
self.google_places_api_key = google_places_api_key
self.google_poi_authorization_path = Path(google_poi_authorization_path) if google_poi_authorization_path else None
self.google_places_fetcher = google_places_fetcher
```

Add `"raw.google.poi"` to `_REMOTELY_MATERIALIZABLE_SOURCE_IDS`.

- [ ] **Step 4: Implement authorization check**

Add:

```python
def _load_google_poi_authorization(self) -> dict[str, Any]:
    if self.google_poi_authorization_path is None or not self.google_poi_authorization_path.exists():
        raise PermissionError("Google POI persistence authorization manifest is required.")
    payload = json.loads(self.google_poi_authorization_path.read_text(encoding="utf-8"))
    authorized = payload.get("authorization_status") == "approved"
    use = dict(payload.get("authorized_use") or {})
    required = [
        use.get("persistent_storage") is True,
        use.get("export_vector_files") is True,
        use.get("fuse_with_non_google_sources") is True,
    ]
    if not authorized or not all(required):
        raise PermissionError("Google POI persistence authorization manifest does not allow this use.")
    return payload
```

- [ ] **Step 5: Implement Google POI materialization**

In `resolve_raw_source_path()`, add:

```python
if source_id == "raw.google.poi":
    return self._resolve_google_poi(request_bbox=effective_bbox)
```

Add:

```python
def _resolve_google_poi(self, *, request_bbox: Optional[BBox]) -> SourceAssetResolution:
    authorization = self._load_google_poi_authorization()
    if not self.google_places_api_key:
        raise PermissionError("GOOGLE_PLACES_API_KEY is required for Google POI acquisition.")
    if self.google_places_fetcher is None:
        raise RuntimeError("Google Places fetcher is not configured.")
    target_dir = self.cache_dir / "google_poi" / _bbox_cache_key(request_bbox)
    output_gpkg = target_dir / "google_poi.gpkg"
    auth_copy = target_dir / "google_poi_authorization.json"
    cache_hit = output_gpkg.exists()
    if not cache_hit:
        rows = list(self.google_places_fetcher(request_bbox, self.google_places_api_key))
        frame = self._google_poi_rows_to_frame(rows)
        if request_bbox is not None and not frame.empty:
            frame = clip_frame_to_request_bbox(frame, request_bbox)
        target_dir.mkdir(parents=True, exist_ok=True)
        frame.to_file(output_gpkg, driver="GPKG")
        auth_copy.write_text(json.dumps(authorization, ensure_ascii=False, indent=2), encoding="utf-8")
    bbox, feature_count = self._inspect_vector_path(output_gpkg)
    return SourceAssetResolution(
        source_id="raw.google.poi",
        path=output_gpkg,
        source_mode="coverage_empty" if feature_count == 0 else ("asset_cached" if cache_hit else "asset_downloaded"),
        cache_hit=cache_hit,
        version_token=_path_version_token(output_gpkg),
        bbox=bbox,
        feature_count=feature_count,
    )
```

Add:

```python
@staticmethod
def _google_poi_rows_to_frame(rows: list[dict[str, Any]]) -> gpd.GeoDataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs="EPSG:4326")
    frame["lat"] = pd.to_numeric(frame.get("lat"), errors="coerce")
    frame["lng"] = pd.to_numeric(frame.get("lng"), errors="coerce")
    frame = frame[frame["lat"].notna() & frame["lng"].notna()].copy()
    geometry = gpd.points_from_xy(frame["lng"], frame["lat"], crs="EPSG:4326")
    return gpd.GeoDataFrame(frame, geometry=geometry, crs="EPSG:4326")
```

This task intentionally uses an injectable fetcher. A later live integration can bind it to the chosen Google Places endpoint without making tests call the network.

- [ ] **Step 6: Add KG source metadata**

In `kg/source_catalog.py`, add `raw.google.poi` as a raw vector source with metadata:

```python
"provider_family": "google_places",
"theme": "poi",
"source_role": "core_poi_source",
"supports_aoi": True,
"materialization_scope": "resolved_aoi_clip",
"source_form": "vector",
"runtime_status": "runtime_candidate",
"selectable_now": True,
"track_b_theme": "poi",
"track_b_role": "core_remote",
"acquisition_class": "authorized_remote_supported",
"field_mapping_profile": "fields.poi.google",
"license_boundary": "Requires project authorization manifest for persistent storage and fusion with non-Google sources.",
```

In `kg/track_b_source_contract.py`, add `raw.google.poi` to POI official/authorized source list.

- [ ] **Step 7: Normalize Google POI**

In `services/track_b_source_normalization.py`, add support for `raw.google.poi` mapping:

- `source_feature_id`: `place_id`
- `name`: `name`
- `category`: `category` or `primary_type`
- `admin_country`: keep if present
- `GeoHash`: compute using existing POI geohash behavior
- `source_id`: `raw.google.poi`

Add test:

```python
def test_track_b_normalization_maps_google_poi_fields() -> None:
    frame = gpd.GeoDataFrame(
        {"place_id": ["p1"], "name": ["Clinic"], "category": ["health"]},
        geometry=[Point(0.5, 0.5)],
        crs="EPSG:4326",
    )

    normalized = normalize_track_b_source_frame("raw.google.poi", frame, target_crs="EPSG:4326")

    assert normalized.loc[0, "source_feature_id"] == "p1"
    assert normalized.loc[0, "source_id"] == "raw.google.poi"
    assert normalized.loc[0, "name"] == "Clinic"
    assert "GeoHash" in normalized.columns
```

- [ ] **Step 8: Run tests**

Run:

```powershell
py -3.13 -m pytest tests/test_source_asset_service.py tests/test_track_b_source_matrix.py tests/test_track_b_source_normalization.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

Run:

```powershell
git add services/source_asset_service.py kg/source_catalog.py kg/track_b_source_contract.py services/track_b_source_normalization.py tests/test_source_asset_service.py tests/test_track_b_source_matrix.py tests/test_track_b_source_normalization.py
git commit -m "feat: add authorized google poi acquisition"
```

---

## Task 6: Attempt All Candidate Sources Inside Existing Bundle Provider

**Files:**
- Modify: `services/local_bundle_catalog.py`
- Modify: `services/source_acquisition_policy.py`
- Test: `tests/test_local_bundle_catalog.py`
- Test: `tests/test_source_coverage_fallback.py`

- [ ] **Step 1: Add failing building all-source attempt test**

Append to `tests/test_local_bundle_catalog.py`:

```python
def test_building_bundle_attempts_google_ms_osm_and_required_road(tmp_path: Path) -> None:
    raw = _FakeRawVectorSourceService(
        feature_counts={
            "raw.google.building": 3,
            "raw.microsoft.building": 4,
            "raw.osm.building": 5,
            "raw.osm.road": 6,
            "raw.openbuildingmap.building": 0,
        }
    )
    provider = LocalBundleCatalogProvider(tmp_path, raw_source_service=raw)

    bundle = provider.materialize_with_fallback(
        source_id="catalog.flood.building",
        request_bbox=(0, 0, 1, 1),
        target_dir=tmp_path / "bundle",
        target_crs="EPSG:3857",
    )

    assert set(bundle.component_coverage) >= {
        "raw.google.building",
        "raw.microsoft.building",
        "raw.osm.building",
        "raw.osm.road",
        "raw.openbuildingmap.building",
    }
    assert bundle.component_coverage["raw.osm.road"].feature_count == 6
    assert any(attempt["source_id"] == "raw.google.building" for attempt in bundle.provider_attempts)
```

Adapt `_FakeRawVectorSourceService` to the helpers in the file.

- [ ] **Step 2: Run failing test**

Run:

```powershell
py -3.13 -m pytest tests/test_local_bundle_catalog.py::test_building_bundle_attempts_google_ms_osm_and_required_road -q
```

Expected: FAIL because building supplemental attempts do not include Google/MS/OSM/road as a complete evidence set.

- [ ] **Step 3: Add source candidate policy**

In `services/source_acquisition_policy.py`, add:

```python
def candidate_component_source_ids(source_id: str) -> list[str]:
    mapping = {
        "catalog.flood.building": [
            "raw.google.building",
            "raw.microsoft.building",
            "raw.osm.building",
            "raw.osm.road",
            "raw.openbuildingmap.building",
        ],
        "catalog.earthquake.building": [
            "raw.google.building",
            "raw.microsoft.building",
            "raw.osm.building",
            "raw.osm.road",
            "raw.openbuildingmap.building",
        ],
        "catalog.generic.poi": [
            "raw.gns.poi",
            "raw.google.poi",
            "raw.osm.poi",
        ],
        "catalog.flood.water": [
            "raw.osm.water",
            "raw.hydrolakes.water",
            "raw.osm.waterways",
            "raw.hydrorivers.water",
        ],
        "catalog.flood.waterways": [
            "raw.osm.waterways",
            "raw.hydrorivers.water",
            "raw.osm.water",
            "raw.hydrolakes.water",
        ],
        "catalog.flood.road": [
            "raw.osm.road",
            "raw.microsoft.road",
        ],
    }
    return list(mapping.get(str(source_id), []))
```

This is policy data, not a new planner module.

- [ ] **Step 4: Attempt supplemental candidates in LocalBundleCatalogProvider**

In `services/local_bundle_catalog.py`, import:

```python
from services.source_acquisition_policy import candidate_component_source_ids, build_source_attempt
```

Replace `_supplemental_component_coverage()` with logic that:

- Starts from `candidate_component_source_ids(source_id)`.
- Skips the two primary sources already represented by `osm.zip` and `ref.zip` only if their coverage already exists.
- Calls `raw_source_service.resolve(...)` for every remaining candidate into `target_dir / f"{source_id.replace('.', '_')}.zip"`.
- On success, writes `SourceCoverageStatus` and `build_source_attempt(status="available" or "empty", feature_count=...)`.
- On failure, writes a `SourceCoverageStatus` with `coverage_status="missing"` and `error=str(exc)`, plus `build_source_attempt(status="provider_failed", fault_class=classify_source_fault(...))`.

Return both supplemental coverage and attempts. If changing return type is disruptive, add a private attribute-free local list and merge into `MaterializedInputBundle.provider_attempts` before return.

- [ ] **Step 5: Enforce complete closure rules for hard targets**

In `services/source_acquisition_policy.py`, add:

```python
def required_full_closure_source_ids(source_id: str) -> list[str]:
    mapping = {
        "catalog.flood.building": [
            "raw.google.building",
            "raw.microsoft.building",
            "raw.osm.building",
            "raw.osm.road",
        ],
        "catalog.earthquake.building": [
            "raw.google.building",
            "raw.microsoft.building",
            "raw.osm.building",
            "raw.osm.road",
        ],
        "catalog.generic.poi": [
            "raw.gns.poi",
            "raw.google.poi",
            "raw.osm.poi",
        ],
    }
    return list(mapping.get(str(source_id), []))
```

Do not raise in the bundle provider solely because a hard target is absent. Record the absence in `component_coverage`; final readiness classification happens in Task 8.

- [ ] **Step 6: Run tests**

Run:

```powershell
py -3.13 -m pytest tests/test_local_bundle_catalog.py tests/test_source_coverage_fallback.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```powershell
git add services/local_bundle_catalog.py services/source_acquisition_policy.py tests/test_local_bundle_catalog.py tests/test_source_coverage_fallback.py
git commit -m "feat: attempt all configured source candidates"
```

---

## Task 7: Route Fusion Paths From Available Source Coverage

**Files:**
- Modify: `services/track_b_national_scale_service.py`
- Modify: `adapters/fusioncode_poi_adapter.py`
- Test: `tests/test_track_b_national_scale_service.py`
- Test: `tests/test_agent_run_service_multisource_building_runtime.py`
- Test: `tests/test_fusioncode_poi.py`

- [ ] **Step 1: Add failing POI named-vector order test**

Append to `tests/test_fusioncode_poi.py`:

```python
def test_poi_adapter_preserves_gng_google_osm_order(tmp_path: Path, monkeypatch) -> None:
    paths = {
        "GNG": _write_points(tmp_path / "gns.gpkg", source_id="raw.gns.poi"),
        "GOOGLE": _write_points(tmp_path / "google.gpkg", source_id="raw.google.poi"),
        "OSM": _write_points(tmp_path / "osm.gpkg", source_id="raw.osm.poi"),
    }
    captured = {}

    def fake_run(sources, params=None):
        captured["keys"] = list(sources)
        return next(iter(sources.values()))

    monkeypatch.setattr("adapters.fusioncode_poi_adapter.run_poi_geohash_priority_fusion", fake_run)

    context = _execution_context(named_vectors=paths, target_crs="EPSG:4326")
    run_poi_geohash_neighbor_match(context)

    assert captured["keys"] == ["GNG", "GOOGLE", "OSM"]
```

Adapt `_write_points` and `_execution_context` to local helpers, or create small helpers in the test.

- [ ] **Step 2: Run failing test**

Run:

```powershell
py -3.13 -m pytest tests/test_fusioncode_poi.py::test_poi_adapter_preserves_gng_google_osm_order -q
```

Expected: FAIL if dict insertion order depends on caller order.

- [ ] **Step 3: Order POI named vectors**

In `adapters/fusioncode_poi_adapter.py`, when `context.named_vectors` exists, replace direct iteration with:

```python
preferred_order = ["GNG", "GOOGLE", "OSM"]
raw_items = {str(name).upper(): path for name, path in context.named_vectors.items()}
ordered_names = [name for name in preferred_order if name in raw_items]
ordered_names.extend(sorted(name for name in raw_items if name not in preferred_order))
for name in ordered_names:
    path = raw_items[name]
    frame = gpd.read_file(path)
    if frame.crs is None:
        frame = frame.set_crs(context.target_crs)
    sources[name] = frame.to_crs(context.target_crs)
```

- [ ] **Step 4: Add national-scale full source path tests**

In `tests/test_track_b_national_scale_service.py`, add tests that seed Google building and Google POI fake local/remote outputs and assert:

```python
assert "raw.google.building" in selected_sources["component_coverage"]
assert "raw.google.poi" in selected_sources["component_coverage"]
assert inspection_summary["operator_readable_summary"]["component_coverage"]["raw.google.poi"]["coverage_status"] == "available"
```

Keep existing OSM/GNS/MS assertions.

- [ ] **Step 5: Update TrackBNationalScaleService source selection**

In `services/track_b_national_scale_service.py`:

- For building, include `raw.google.building`, `raw.microsoft.building`, `raw.osm.building`, `raw.osm.road`, and optional `raw.openbuildingmap.building` in `component_coverage`.
- Use existing `TiledBuildingRuntimeService` when at least two core building sources are available, but record whether full closure includes all four hard targets.
- For POI, build `named_vectors` with aliases:
  - `raw.gns.poi` -> `GNG`
  - `raw.google.poi` -> `GOOGLE`
  - `raw.osm.poi` -> `OSM`
- Keep GNS/OSM degraded output possible, but mark it as incomplete in readiness.

- [ ] **Step 6: Run tests**

Run:

```powershell
py -3.13 -m pytest tests/test_track_b_national_scale_service.py tests/test_agent_run_service_multisource_building_runtime.py tests/test_fusioncode_poi.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```powershell
git add services/track_b_national_scale_service.py adapters/fusioncode_poi_adapter.py tests/test_track_b_national_scale_service.py tests/test_agent_run_service_multisource_building_runtime.py tests/test_fusioncode_poi.py
git commit -m "feat: route fusion paths from source coverage"
```

---

## Task 8: Add Autonomous Fusion Readiness Classification

**Files:**
- Create: `services/autonomous_fusion_readiness_service.py`
- Modify: `services/track_b_national_scale_service.py`
- Test: `tests/test_autonomous_fusion_readiness_service.py`
- Test: `tests/test_track_b_national_scale_service.py`

- [ ] **Step 1: Write readiness tests**

Create `tests/test_autonomous_fusion_readiness_service.py`:

```python
from __future__ import annotations

from services.autonomous_fusion_readiness_service import classify_autonomous_readiness


def test_building_full_closure_requires_google_ms_osm_and_road() -> None:
    result = classify_autonomous_readiness(
        job_type="building",
        component_coverage={
            "raw.google.building": {"coverage_status": "available", "feature_count": 10},
            "raw.microsoft.building": {"coverage_status": "available", "feature_count": 11},
            "raw.osm.building": {"coverage_status": "available", "feature_count": 12},
            "raw.osm.road": {"coverage_status": "available", "feature_count": 4},
        },
        source_attempts=[],
    )

    assert result["status"] == "full_autonomous_closure"
    assert result["missing_required_source_ids"] == []


def test_poi_missing_google_is_degraded_not_full_success() -> None:
    result = classify_autonomous_readiness(
        job_type="poi",
        component_coverage={
            "raw.gns.poi": {"coverage_status": "available", "feature_count": 5},
            "raw.osm.poi": {"coverage_status": "available", "feature_count": 5},
        },
        source_attempts=[
            {
                "source_id": "raw.google.poi",
                "status": "network_failed",
                "fault_class": "NETWORK_FAILED",
                "external_uncontrollable": True,
            }
        ],
    )

    assert result["status"] == "degraded_external"
    assert result["missing_required_source_ids"] == ["raw.google.poi"]


def test_poi_missing_google_without_external_fault_is_system_failure() -> None:
    result = classify_autonomous_readiness(
        job_type="poi",
        component_coverage={
            "raw.gns.poi": {"coverage_status": "available", "feature_count": 5},
            "raw.osm.poi": {"coverage_status": "available", "feature_count": 5},
        },
        source_attempts=[],
    )

    assert result["status"] == "system_failure"
    assert result["missing_required_source_ids"] == ["raw.google.poi"]
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
py -3.13 -m pytest tests/test_autonomous_fusion_readiness_service.py -q
```

Expected: FAIL because service does not exist.

- [ ] **Step 3: Implement readiness classifier**

Create `services/autonomous_fusion_readiness_service.py`:

```python
from __future__ import annotations

from typing import Any


REQUIRED_SOURCE_IDS = {
    "building": ["raw.google.building", "raw.microsoft.building", "raw.osm.building", "raw.osm.road"],
    "poi": ["raw.gns.poi", "raw.google.poi", "raw.osm.poi"],
    "road": ["raw.osm.road", "raw.microsoft.road"],
    "water": ["raw.osm.water", "raw.hydrolakes.water"],
    "waterways": ["raw.osm.waterways", "raw.hydrorivers.water"],
}


def classify_autonomous_readiness(
    *,
    job_type: str,
    component_coverage: dict[str, Any],
    source_attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    required = REQUIRED_SOURCE_IDS.get(str(job_type), [])
    coverage = {source_id: dict(payload or {}) for source_id, payload in (component_coverage or {}).items()}
    missing = [
        source_id
        for source_id in required
        if str(coverage.get(source_id, {}).get("coverage_status") or "") != "available"
        or int(coverage.get(source_id, {}).get("feature_count") or 0) <= 0
    ]
    external_missing = [
        source_id
        for source_id in missing
        if _has_external_attempt(source_id, source_attempts)
    ]
    if not missing:
        status = "full_autonomous_closure"
    elif set(missing) == set(external_missing):
        status = "degraded_external"
    else:
        status = "system_failure"
    return {
        "status": status,
        "required_source_ids": required,
        "missing_required_source_ids": missing,
        "external_uncontrollable_source_ids": external_missing,
    }


def _has_external_attempt(source_id: str, source_attempts: list[dict[str, Any]]) -> bool:
    for attempt in source_attempts:
        if attempt.get("source_id") == source_id and attempt.get("external_uncontrollable") is True:
            return True
    return False
```

- [ ] **Step 4: Write readiness evidence from national-scale service**

In `services/track_b_national_scale_service.py`, import:

```python
from services.autonomous_fusion_readiness_service import classify_autonomous_readiness
```

Before writing `inspection_summary.json`, compute:

```python
source_attempts = list(getattr(materialized, "provider_attempts", []) or [])
autonomous_readiness = classify_autonomous_readiness(
    job_type=theme,
    component_coverage=selected_coverage,
    source_attempts=source_attempts,
)
```

Add to `inspection_summary`:

```python
"autonomous_readiness": autonomous_readiness,
```

Write `autonomous_readiness.json`:

```python
(output_root / "autonomous_readiness.json").write_text(
    json.dumps(autonomous_readiness, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
```

Add it to the `evidence` section.

- [ ] **Step 5: Run tests**

Run:

```powershell
py -3.13 -m pytest tests/test_autonomous_fusion_readiness_service.py tests/test_track_b_national_scale_service.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add services/autonomous_fusion_readiness_service.py services/track_b_national_scale_service.py tests/test_autonomous_fusion_readiness_service.py tests/test_track_b_national_scale_service.py
git commit -m "feat: classify autonomous fusion readiness"
```

---

## Task 9: Update Evidence CLI And Contract Docs

**Files:**
- Modify: `scripts/build_track_b_national_evidence.py`
- Create: `docs/superpowers/specs/2026-06-11-autonomous-source-acquisition-contract.md`
- Test: `tests/test_track_b_freeze_scripts.py`
- Test: `tests/test_track_b_source_matrix.py`

- [ ] **Step 1: Add CLI arguments**

In `scripts/build_track_b_national_evidence.py`, add arguments:

```python
parser.add_argument("--google-open-buildings-url", action="append", default=[])
parser.add_argument("--google-poi-authorization", default="")
parser.add_argument("--google-places-api-key-env", default="GOOGLE_PLACES_API_KEY")
parser.add_argument("--require-full-autonomous-closure", action="store_true")
```

Pass these into `TrackBNationalScaleService` through constructor parameters added in earlier tasks, or into its underlying `SourceAssetService` if that is the chosen integration point.

- [ ] **Step 2: Add full-closure exit rule**

After each `build_theme_evidence()` call, if `--require-full-autonomous-closure` is set, read `inspection_summary.json` and exit non-zero when:

```python
inspection_summary["autonomous_readiness"]["status"] != "full_autonomous_closure"
```

Print the missing source ids before exiting.

- [ ] **Step 3: Create contract doc**

Create `docs/superpowers/specs/2026-06-11-autonomous-source-acquisition-contract.md`:

```markdown
# Autonomous Source Acquisition Contract

## Scope

FusionAgent's engineering target is autonomous city/county-to-national fusion for building, road, POI, water polygon, and waterways. The runtime must attempt all configured sources, classify failures, choose a fusion path from available coverage, and write evidence. Network failures, upstream provider failures, authorization absence, and official no-coverage states are external-uncontrollable failures; CRS, field mapping, cache corruption, algorithm parameter mismatch, and missing evidence are system failures.

## KG Parameter Policy

No separate FusionSlotContract exists. `AlgorithmParameterSpec` is the canonical parameter and slot contract. It supports static defaults, conditional defaults by source combination and region, and provenance. Effective parameters are resolved before execution and written into task parameters with `parameter_provenance`.

## Input Acquisition Policy

No separate SourceAttemptPlanner exists. `InputAcquisitionService` writes `source_attempts.json` and `source_materialization_manifest.json`. Source attempts use normalized statuses: `available`, `empty`, `no_coverage`, `network_failed`, `provider_failed`, `unauthorized`, `cache_reused`, and `materialized`.

## Required Full-Closure Sources

| Task | Required Sources |
| --- | --- |
| building | `raw.google.building`, `raw.microsoft.building`, `raw.osm.building`, `raw.osm.road` |
| road | `raw.osm.road`, `raw.microsoft.road` |
| poi | `raw.gns.poi`, `raw.google.poi`, `raw.osm.poi` |
| water | `raw.osm.water`, `raw.hydrolakes.water` |
| waterways | `raw.osm.waterways`, `raw.hydrorivers.water` |

OBM remains optional supplemental building evidence.

## Google Sources

Google building uses Google Open Buildings automatic materialization and may be persisted with attribution under its dataset license. Google POI requires a local authorization manifest that explicitly permits persistent storage, vector export, and fusion with non-Google sources. Without that manifest, `raw.google.poi` is classified as unauthorized and full POI closure fails.

## Evidence Files

Each autonomous run must expose:

- `source_attempts.json`
- `source_materialization_manifest.json`
- `selected_sources.json`
- `source_profile_snapshot.json`
- `normalization_summary.json`
- `tile_manifest.json`
- `stitched_artifact.json`
- `quality_report.json` when available
- `autonomous_readiness.json`
```

- [ ] **Step 4: Add script tests**

In `tests/test_track_b_freeze_scripts.py`, add a test for argument parsing:

```python
def test_build_track_b_national_evidence_accepts_google_and_full_closure_args() -> None:
    args = parse_args(
        [
            "--job-type", "poi",
            "--bbox", "0,0,1,1",
            "--target-crs", "EPSG:3857",
            "--output-root", "runs/test",
            "--google-poi-authorization", "docs/private/google_poi_authorization.json",
            "--require-full-autonomous-closure",
        ]
    )

    assert args.google_poi_authorization.endswith("google_poi_authorization.json")
    assert args.require_full_autonomous_closure is True
```

- [ ] **Step 5: Run tests**

Run:

```powershell
py -3.13 -m pytest tests/test_track_b_freeze_scripts.py tests/test_track_b_source_matrix.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add scripts/build_track_b_national_evidence.py docs/superpowers/specs/2026-06-11-autonomous-source-acquisition-contract.md tests/test_track_b_freeze_scripts.py
git commit -m "docs: define autonomous source acquisition contract"
```

---

## Task 10: End-To-End Regression Matrix

**Files:**
- Create: `tests/test_autonomous_source_closure_matrix.py`
- Modify: `docs/v2-operations.md`
- Verify only after test creation.

- [ ] **Step 1: Create regression matrix test**

Create `tests/test_autonomous_source_closure_matrix.py`:

```python
from __future__ import annotations

from services.autonomous_fusion_readiness_service import classify_autonomous_readiness


def test_autonomous_closure_matrix_defines_required_sources_for_all_core_tasks() -> None:
    cases = {
        "building": ["raw.google.building", "raw.microsoft.building", "raw.osm.building", "raw.osm.road"],
        "road": ["raw.osm.road", "raw.microsoft.road"],
        "poi": ["raw.gns.poi", "raw.google.poi", "raw.osm.poi"],
        "water": ["raw.osm.water", "raw.hydrolakes.water"],
        "waterways": ["raw.osm.waterways", "raw.hydrorivers.water"],
    }

    for job_type, source_ids in cases.items():
        result = classify_autonomous_readiness(
            job_type=job_type,
            component_coverage={
                source_id: {"coverage_status": "available", "feature_count": 1}
                for source_id in source_ids
            },
            source_attempts=[],
        )
        assert result["status"] == "full_autonomous_closure", job_type
```

- [ ] **Step 2: Run regression matrix**

Run:

```powershell
py -3.13 -m pytest tests/test_autonomous_source_closure_matrix.py -q
```

Expected: PASS.

- [ ] **Step 3: Update operations doc**

In `docs/v2-operations.md`, update the Fresh-Checkout Source Asset Materialization and Track B sections:

- Add `raw.google.building`.
- Add `raw.google.poi`.
- State that Google POI requires authorization manifest.
- State OBM remains optional supplemental source.
- State full autonomous closure is stricter than historical national-scale support.

- [ ] **Step 4: Run full focused suite**

Run:

```powershell
py -3.13 -m pytest `
  tests/test_kg_parameter_specs.py `
  tests/test_conditional_parameter_service.py `
  tests/test_input_acquisition_service.py `
  tests/test_input_acquisition_faults.py `
  tests/test_source_asset_service.py `
  tests/test_local_bundle_catalog.py `
  tests/test_track_b_source_matrix.py `
  tests/test_track_b_source_normalization.py `
  tests/test_track_b_national_scale_service.py `
  tests/test_autonomous_fusion_readiness_service.py `
  tests/test_autonomous_source_closure_matrix.py `
  -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add tests/test_autonomous_source_closure_matrix.py docs/v2-operations.md
git commit -m "test: add autonomous source closure matrix"
```

---

## Task 11: Live Evidence Dry Run And Known External Boundaries

**Files:**
- Verify only, then create evidence note.
- Create: `docs/superpowers/specs/2026-06-11-autonomous-source-closure-verification.md`

- [ ] **Step 1: Run non-network dry-run suite**

Run:

```powershell
py -3.13 -m pytest `
  tests/test_source_asset_service.py `
  tests/test_track_b_national_scale_service.py `
  tests/test_autonomous_source_closure_matrix.py `
  -q
```

Expected: PASS.

- [ ] **Step 2: Run Nepal live acquisition if credentials and network are available**

Only run when `GOOGLE_PLACES_API_KEY`, Google POI authorization manifest, and Google Open Buildings URL/index configuration are present:

```powershell
py -3.13 scripts/build_track_b_national_evidence.py `
  --job-type building `
  --bbox 85.20,27.60,85.45,27.82 `
  --target-crs EPSG:32645 `
  --output-root runs/autonomous-source-closure/nepal-building `
  --country-name Nepal `
  --country-code NPL `
  --require-full-autonomous-closure

py -3.13 scripts/build_track_b_national_evidence.py `
  --job-type poi `
  --bbox 85.20,27.60,85.45,27.82 `
  --target-crs EPSG:32645 `
  --output-root runs/autonomous-source-closure/nepal-poi `
  --country-name Nepal `
  --country-code NPL `
  --google-poi-authorization docs/private/google_poi_authorization.json `
  --require-full-autonomous-closure
```

Expected: `autonomous_readiness.json` reports `full_autonomous_closure`.

- [ ] **Step 3: Run Mongolia boundary acquisition if configured**

Run building and POI against a Mongolia AOI. If Google Open Buildings has no official coverage, expected result is not a system failure when `autonomous_readiness.json` reports `degraded_external` with `raw.google.building` classified as `NO_OFFICIAL_COVERAGE`.

- [ ] **Step 4: Create verification note**

After running the commands in this task, create `docs/superpowers/specs/2026-06-11-autonomous-source-closure-verification.md` with the following sections and real command outcomes:

```markdown
# Autonomous Source Closure Verification

## Focused Test Suite

- `<exact pytest command for conditional KG parameter defaults>`: `<PASS or FAIL>`; `<short observed output summary>`.
- `<exact pytest command for structured input acquisition attempts>`: `<PASS or FAIL>`; `<short observed output summary>`.
- `<exact pytest command for Google building acquisition>`: `<PASS, FAIL, or SKIPPED>`; `<short observed output summary or skip reason>`.
- `<exact pytest command for authorized Google POI acquisition>`: `<PASS, FAIL, or SKIPPED>`; `<short observed output summary or skip reason>`.
- `<exact pytest command for autonomous readiness matrix>`: `<PASS or FAIL>`; `<short observed output summary>`.

## Live Evidence

- Nepal building: `<full_autonomous_closure, degraded_external, system_failure, or skipped>`; evidence path `<path or skip reason>`.
- Nepal POI: `<full_autonomous_closure, degraded_external, system_failure, or skipped>`; evidence path `<path or skip reason>`.
- Mongolia building/POI boundary: `<full_autonomous_closure, degraded_external, system_failure, or skipped>`; evidence path `<path or skip reason>`.

## Claim Boundary

Full autonomous closure is stricter than historical Track B national-scale support. A run is not full closure unless all required sources for the task are available with non-empty coverage or the run explicitly records an external-uncontrollable degradation.
```

Do not write synthetic pass summaries. If credentials, authorization, network, or official Google coverage are absent, record the exact skip or degradation reason.

- [ ] **Step 5: Commit verification note**

Run:

```powershell
git add docs/superpowers/specs/2026-06-11-autonomous-source-closure-verification.md
git commit -m "docs: record autonomous source closure verification"
```

---

## Self-Review Checklist

- Spec coverage:
  - No `FusionSlotContract`: satisfied by extending `AlgorithmParameterSpec`.
  - No `SourceAttemptPlanner`: satisfied by enhancing `InputAcquisitionService`, `LocalBundleCatalogProvider`, and `SourceAssetService`.
  - Conditional defaults by source combination and region: Task 1 and Task 2.
  - Provenance from static seed, durable learning, and operator annotation: Task 1 and Task 2.
  - Source attempts with granular statuses: Task 3.
  - Google building automatic acquisition: Task 4.
  - Google POI authorized automatic acquisition and persistent output: Task 5.
  - Building core sources: Tasks 6-8 require Google, MS, OSM, and OSM road.
  - POI source order `GNG`, `GOOGLE`, `OSM`: Task 7.
  - Long-running readiness foundation: source attempts and autonomous readiness are created here; checkpoint/resume expansion should be a follow-up plan after this source closure lands.
- Placeholder scan:
  - No placeholder markers from the writing-plans anti-pattern list are intentional in this plan.
  - Runtime-dependent verification values are written only after commands execute, with exact observed outcomes.
- Type consistency:
  - `AlgorithmParameterSpec.conditional_defaults` is a list of dictionaries in model, seed, bootstrap, and Neo4j mapping.
  - `SourceAcquisitionAttempt` fields are used by policy builders, input acquisition evidence, and readiness classification.
  - `autonomous_readiness.status` values are `full_autonomous_closure`, `degraded_external`, or `system_failure`.
- Scope discipline:
  - This plan does not redesign the planner.
  - This plan does not add a new source-planning module.
  - This plan does not solve full checkpoint/resume long-run operation; it creates the source-attempt and readiness evidence needed for that next plan.
