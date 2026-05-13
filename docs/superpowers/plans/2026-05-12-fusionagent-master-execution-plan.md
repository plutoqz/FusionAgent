# FusionAgent Master Execution Plan

**Completion Status:** Active on 2026-05-12. This document is the single execution sequence for the repo's currently active planning work. Phase 1 closed on 2026-05-12 with fresh verification; Phase 2 is now the next active implementation phase. It consolidates older plan files into one ordered backlog, but keeps those files as detailed task references rather than deleting them.

**Goal:** 在不扩大系统主张边界的前提下，把 FusionAgent 收敛为一个可复现、可校验、可支撑论文实验与本地操作的 `KG-grounded geospatial fusion agent runtime`，并把剩余工作统一到一条可执行主线上。

**Primary Runtime Claim:** 当前稳定主张仍然限定在 `building`、`road`、`water` 与 bounded `poi`，共享运行骨架仍然是 `planner -> validator -> executor -> healing/replan -> writeback`，共享证据契约仍然是 `run.json`、`plan.json`、`validation.json`、`audit.jsonl` 与 artifact bundle。

**Non-Goals For This Master Plan:**

- 不在近期执行中引入新的主题切片
- 不把 `trajectory-to-road` 从 metadata seam 提升成可执行能力
- 不把 Benin research utilities 直接包装成新的主运行时主张
- 不把前端工作台包装成系统核心能力闭环
- 不在论文主线闭合前启动大规模 backend 迁移或 `fusioncode` 全量接管

## Phase 0: Documentation Discovery And Plan Normalization

This phase is closed by the creation of this document. Later execution phases must still reread the listed references before implementation instead of assuming APIs or scope from memory.

### Allowed Stable Interfaces

- Runtime backbone: `planner -> validator -> executor -> healing/replan -> writeback`
- Stable themes: `building`, `road`, `water`, bounded `poi`
- Stable evidence surfaces: `run.json`, `plan.json`, `validation.json`, `audit.jsonl`, artifact bundle
- Existing operator and inspection entry points:
  - `GET /api/v2/runs/{run_id}/inspection`
  - `GET /api/v2/runs/{left_run_id}/compare/{right_run_id}`
  - `GET /api/v2/runtime`
  - existing scenario run APIs under `api/routers/scenario_runs.py`
- Local startup baseline: `python scripts/start_local.py --port 8000`

### Current Baseline Already Closed

- Scenario reporting and scenario harness foundations are already documented as completed in:
  - `docs/superpowers/plans/2026-04-21-scenario-evidence-and-reporting-upgrade.md`
  - `docs/superpowers/plans/2026-04-21-scenario-harness-plan.md`
- Capability boundary and wording anchors already exist in:
  - `docs/superpowers/specs/2026-05-06-capability-consolidation-review.md`
  - `docs/superpowers/specs/2026-05-06-redundancy-and-drift-ledger.md`
  - `docs/superpowers/specs/2026-05-06-consolidation-backlog.md`
  - `docs/superpowers/specs/2026-05-06-next-execution-sequence.md`
- KG baseline moved from "live drift" to usable default runtime evidence in:
  - `docs/superpowers/specs/2026-05-10-kg-gates-evidence-summary.md`

### Old Plan Mapping

| Old plan | Decision in this master plan | Notes |
| --- | --- | --- |
| `2026-04-21-scenario-evidence-and-reporting-upgrade.md` | historical complete | checklist stale, but file header says completed |
| `2026-04-21-scenario-harness-plan.md` | historical complete | checklist stale, but file header says completed |
| `2026-04-21-scenario-regression-set-plan.md` | keep as Phase 3 support plan | scenario capability regression and freeze refresh |
| `2026-04-21-no-ui-mature-agent-plan.md` | partially superseded | keep only operator, evidence, maturity-check, and runbook closures |
| `2026-04-23-system-next-improvements.md` | keep as Phase 2 primary detail | core-next runtime hardening source |
| `2026-04-27-benin-building-runtime-preparation.md` | keep as Phase 5 primary detail | bounded Benin scale-preparation track |
| `2026-04-29-fusioncode-algorithm-library-kg-integration.md` | defer to Conditional Phase 6 | too large for current thesis-critical path |
| `2026-05-06-fusionagent-agent-capability-update-roadmap.md` | keep as Phase 2 and Phase 3 primary detail | thesis-serving capability hardening source |
| `2026-05-06-fusionagent-thesis-research-design-roadmap.md` | keep as Phase 4 primary detail | thesis packaging source |
| `2026-05-09-kg-closure-and-graph-backend-roadmap.md` | keep as Phase 1 primary detail | immediate baseline stabilization source |

### Verification Checklist

- Confirm this file references every previously active plan under `docs/superpowers/plans/`
- Confirm the repo now has a single ordering document for active work
- Confirm completed plans are treated as historical baseline, not reopened blindly

### Anti-Pattern Guards

- Do not reopen already completed scenario foundation work unless a current failing test or drift proves regression.
- Do not create a second "master roadmap" with different wording.
- Do not promote deferred scope simply because an older plan still contains unchecked boxes.

## Phase 1: KG Closure And Runtime Contract Stabilization

This phase is closed on 2026-05-12. It was the immediate gate for all later thesis experiments and capability claims, and its latest closure evidence is recorded in `docs/superpowers/specs/2026-05-09-kg-closure-gates.md`.

### What To Implement

Use `docs/superpowers/plans/2026-05-09-kg-closure-and-graph-backend-roadmap.md` as the detailed task source, but normalize current sequencing as follows:

1. Treat Task 1 and Task 2 as already evidenced by `docs/superpowers/specs/2026-05-10-kg-gates-evidence-summary.md`.
2. Continue with the remaining high-value closures:
   - promote `ScenarioProfile` and `OutputSchemaPolicy` from passive metadata to active runtime constraints
   - ensure `ParameterSpec` and decomposed workflow candidates remain reachable under the default `Neo4j` backend
   - fix project isolation through configurable namespace and guarded reads or writes
   - freeze paper-ready KG gates before any new ablation or thesis comparison run
3. If runtime drift is rediscovered, reopen Task 1 or Task 2 only with fresh evidence.

### Documentation References

- `docs/superpowers/plans/2026-05-09-kg-closure-and-graph-backend-roadmap.md`
- `docs/superpowers/specs/2026-05-09-kg-closure-gates.md`
- `docs/superpowers/specs/2026-05-10-kg-gates-evidence-summary.md`
- `docs/superpowers/specs/2026-05-06-capability-consolidation-review.md`

### Verification Checklist

- `python scripts/start_local.py --port 8000` reports `KG contract: PASS`
- Focused KG and repository tests for profile activation, schema enforcement, repository reachability, and namespace isolation pass
- A bounded default-backend smoke subset for `building / road / water / poi` still passes
- A refreshed gate summary is written when behavior or evidence changes materially

### Anti-Pattern Guards

- Do not start backend migration experiments before the default `Neo4j` path is stable.
- Do not widen theme scope during KG cleanup.
- Do not claim paper-ready KG semantics until tests, runtime behavior, and smoke evidence all align.

## Phase 2: Core-Next Runtime Hardening

This phase merges the unfinished core from `system-next improvements` and the thesis-critical P0 chain from the `agent capability update roadmap`.

### What To Implement

Execute the following chain in order:

1. Finish the tool-contract path:
   - keep `ToolSpec` registry and handler contract enforcement as the canonical execution gate
   - ensure unknown algorithms, invalid parameters, and type mismatches fail closed
2. Add step-level KG grounding proof:
   - plan grounding report
   - grounding summaries in artifacts and inspection
3. Add explicit unsupported-intent rejection:
   - reject or clarify off-domain and unsupported requests deterministically
4. Add failure and operations trustworthiness:
   - stable failure taxonomy
   - token and latency telemetry
   - checkpoint or stale-run recovery inspection

Within this phase, use the existing evidence rule from `docs/superpowers/specs/2026-05-06-consolidation-backlog.md`: a capability is not considered closed until tests, runtime artifact, inspection surface, and operations wording all exist.

### Documentation References

- `docs/superpowers/plans/2026-04-23-system-next-improvements.md`
- `docs/superpowers/plans/2026-05-06-fusionagent-agent-capability-update-roadmap.md`
- `docs/superpowers/specs/2026-05-06-consolidation-backlog.md`
- `docs/superpowers/specs/2026-05-06-next-execution-sequence.md`
- `docs/superpowers/specs/2026-04-23-system-next-improvement-review.md`
- `docs/superpowers/specs/2026-04-23-complexity-boundary-ledger.md`

### Verification Checklist

- Focused tests for tool contract, grounding report, unsupported-intent guard, failure taxonomy, telemetry, and recovery scanner pass
- `plan.json` and `audit.jsonl` expose new grounding or failure metadata in machine-readable form
- inspection endpoints expose contract failures and recovery or operator guidance without reading raw logs
- `README.md`, `README.en.md`, and `docs/v2-operations.md` are updated only for closed items

### Anti-Pattern Guards

- Do not treat partial artifact changes as phase closure without inspection and operations wording.
- Do not add free-form tool calling or undocumented dispatch paths.
- Do not add production HA or self-evolving-agent wording while only implementing local trustworthiness controls.

## Phase 3: Operator Surface, Scenario Boundedness, And Regression Closure

This phase closes the gap between "evidence-rich artifacts" and "operator-usable runtime", while locking scenario claims to bounded proof.

### What To Implement

1. Finish the remaining P1 or operator-facing closures from `2026-05-06-fusionagent-agent-capability-update-roadmap.md`:
   - input acquisition fault taxonomy and fallback policy normalization
   - decision-friendly inspection digest
   - explicit scenario scope guards
   - planner retrieval prioritization only after the P0 chain from Phase 2 is closed
2. Absorb the still-relevant operator and evidence items from `2026-04-21-no-ui-mature-agent-plan.md`:
   - run registry and operator read models
   - artifact preview or evidence products
   - no-UI operations runbook
   - maturity check and maturity evidence freeze
3. Execute the still-active scenario regression tightening from `2026-04-21-scenario-regression-set-plan.md`:
   - typed `capability_checks`
   - harness-side capability validation
   - refreshed checked-in scenario manifest
   - refreshed scenario evidence freeze when behavior changes

### Documentation References

- `docs/superpowers/plans/2026-05-06-fusionagent-agent-capability-update-roadmap.md`
- `docs/superpowers/plans/2026-04-21-no-ui-mature-agent-plan.md`
- `docs/superpowers/plans/2026-04-21-scenario-regression-set-plan.md`
- `docs/no-ui-agent-operations.md` when it exists
- `docs/superpowers/specs/2026-04-21-operator-read-model-contract.md` when it exists

### Verification Checklist

- Focused tests for input-fault taxonomy, inspection digest, scenario scope guards, run registry, operator summaries, artifact preview, and maturity checks pass
- scenario harness validates capability evidence instead of phase-only success
- operator can list, inspect, compare, and summarize without manually reading run directories
- no-UI evidence freeze and runbook are refreshed if new read surfaces materially change the operator contract

### Anti-Pattern Guards

- Do not reopen broad no-UI maturity marketing language before the actual gates pass.
- Do not allow scenario partial success to hide missing capability evidence.
- Do not make front-end polish the substitute for no-UI inspection completeness.

## Phase 4: Thesis Research Asset Closure

This phase converts the stabilized runtime and evidence surfaces into thesis-ready research assets. It should start only after Phase 1 and the P0 part of Phase 2 are closed.

### What To Implement

Use `docs/superpowers/plans/2026-05-06-fusionagent-thesis-research-design-roadmap.md` as the detailed source and close it in this order:

1. write the thesis research specification and claim ledger
2. define mandatory baselines, ablations, and metrics
3. turn Benin workflow into bounded scale-validation evidence
4. build the related-work comparison matrix
5. produce the thesis outline and staged execution timeline
6. write the handshake between thesis plan and capability plan so paper claims never outrun runtime evidence

### Documentation References

- `docs/superpowers/plans/2026-05-06-fusionagent-thesis-research-design-roadmap.md`
- `docs/superpowers/specs/2026-05-06-capability-inventory.md`
- `docs/superpowers/specs/2026-05-10-kg-gates-evidence-summary.md`
- evidence freeze and manifest files already referenced by the thesis roadmap

### Verification Checklist

- thesis-spec, experiment-matrix, related-work, outline or timeline, and handshake tests or guard checks pass where defined
- paper-facing docs use the same bounded vocabulary as the capability consolidation review
- every promoted thesis claim maps to current runtime evidence, not planned future work

### Anti-Pattern Guards

- Do not use planned-but-unimplemented runtime capability as thesis evidence.
- Do not let the thesis narrative force new runtime scope into the repo.
- Do not start large Benin or `fusioncode` expansion just to make the outline look stronger.

## Phase 5: Benin Scale Preparation Under Current Runtime Boundary

This is the bounded scale-up phase. It should only start after the baseline runtime and operator surfaces are credible enough to support larger AOIs.

### What To Implement

Use `docs/superpowers/plans/2026-04-27-benin-building-runtime-preparation.md` as the detailed task source, but keep the execution boundary explicit:

1. canonical Benin source profiles
2. KG metadata expansion that distinguishes `runtime_candidate` from `reservation_only`
3. planner and runtime guards for reserved capabilities
4. deterministic tile partitioning and tile manifests
5. tile-aware clip cache reuse
6. tiled parallel building runtime for the already supported executable building flow
7. Benin benchmarks, operator evidence, and documentation

This phase is for bounded scale validation of the current building path, not for silently upgrading the repo to full multi-source or raster-height semantics.

### Documentation References

- `docs/superpowers/plans/2026-04-27-benin-building-runtime-preparation.md`
- `docs/superpowers/specs/2026-05-06-capability-consolidation-review.md`
- `docs/superpowers/specs/2026-05-10-kg-gates-evidence-summary.md`

### Verification Checklist

- focused tests for source profiling, tile partitioning, tile runtime, and raster inspection seams pass
- benchmarks and operator evidence are written for bounded Benin cases
- documentation clearly separates executable-now building flow from reservation-only future semantics

### Anti-Pattern Guards

- Do not market research utilities as stable runtime features.
- Do not promote raster-height or multi-source building fusion unless they share the same runtime evidence contract as current stable flows.
- Do not bypass earlier KG or operator guardrails just because the AOI is larger.

## Conditional Phase 6: Deferred Expansion Tracks

These tracks remain explicitly deferred until Phases 1 through 5 close or the thesis schedule no longer depends on restraint.

### Deferred Track A: Full `fusioncode` Algorithm Library Integration

The plan file `docs/superpowers/plans/2026-04-29-fusioncode-algorithm-library-kg-integration.md` stays as a detailed future design, but it is not on the current critical path because it combines:

- new algorithm primitive layer
- new adapters across multiple themes
- major KG and validator expansion
- larger runtime surface than the current thesis-critical baseline requires

Only reopen it when:

- KG closure is stable
- thesis-critical runtime hardening is closed
- bounded Benin evidence no longer satisfies the research need

### Deferred Track B: Backend Migration Spikes

Keep `NebulaGraph`, `Alibaba Cloud GDB`, and `PolarDB Graph / Apache AGE` only as conditional migration spikes after the default backend is closed and only if a concrete performance or isolation blocker remains.

### Deferred Track C: Front-End Evidence Surface Growth

Front-end evidence views remain optional operator support work. They must not replace no-UI evidence, inspection, and runbook completeness in the core claim.

## Final Phase: Repository-Wide Verification And Plan Hygiene

After every active phase above is closed, run a final verification and cleanup pass.

### What To Implement

1. run focused and full verification required by the closed phases
2. refresh evidence freeze files that materially changed
3. update old plan headers or archive notes so "completed", "active", and "deferred" are no longer ambiguous
4. ensure README and thesis-facing wording match the actual achieved boundary

### Documentation References

- this master plan
- every phase source plan that was actually executed
- active evidence freeze, manifest, and operations docs

### Verification Checklist

- no remaining active phase claims rely on unchecked evidence
- completed plan files either say completed or are explicitly marked as superseded by this master plan
- `README.md`, `README.en.md`, and operations docs share one stable boundary vocabulary

### Anti-Pattern Guards

- Do not leave historical plans with stale status in a way that reintroduces ambiguity.
- Do not update positioning text ahead of verification output.
- Do not treat "document merged" as equivalent to "runtime claim closed".

## Stop Conditions

Stop and re-review before continuing if any of the following becomes true:

- a task introduces new domain scope not covered by the bounded runtime claim
- a task promotes a claim without matching evidence
- a task duplicates an existing runtime interface with a one-off script
- a task turns reservation-only metadata into executable wording without tests and operations proof
- a task lets thesis or demo language outrun the default runtime baseline

## Expected Outcome

If executed in order, this master plan should leave the repo in a state where:

- default KG runtime is stable and reproducible
- core runtime trustworthiness gaps are closed with testable evidence
- operators can inspect and reason about runs without raw-directory spelunking
- thesis assets are derived from actual runtime evidence rather than roadmap intent
- Benin work stays bounded to defensible scale-validation value
- larger expansions remain consciously deferred instead of accidentally leaking into the main claim
