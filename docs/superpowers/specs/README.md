# Superpowers Specs: Live vs Archive

`docs/superpowers/specs/` is the live root for documents that are consumed by the
current execution chain. Scripts, tests, README text, runbooks, and paper-freeze
pipelines must read active specs from this directory.

`docs/superpowers/specs/done/` is the archive for historical snapshots. Archived
files may preserve audit history, but they are not allowed to become the current
runtime or thesis entrypoint again.

## Live rules

- Keep every currently consumed manifest, freeze, contract, and capability file
  in `docs/superpowers/specs/`.
- Do not repoint scripts or tests to `done/` just because a live file was moved.
- When a historical file becomes active again, restore or rewrite it in the live
  root and leave the archive copy as history.
- Do not maintain two different files that both claim to be the current version
  of the same spec.

## Archive rules

- `done/` keeps snapshots that are useful for traceability or historical review.
- Archived files can describe past plans, closed evidence packages, or retired
  drafts, but they should not be the target of active automation.
- If a live file is superseded, move the old snapshot to `done/` only after the
  replacement exists in the live root.

## Current active index

The following files are the current live specs that participate in the active
execution chain defined by
`docs/superpowers/plans/2026-05-13-fusionagent-master-execution-plan.md`.

### Phase A / Phase B live evidence

- `2026-04-08-benchmark-followup-summary.md`
- `2026-04-08-building-real-benchmark-result.json`
- `2026-04-08-building-micro-benchmark-result.json`
- `2026-04-07-real-data-eval-manifest.json`
- `2026-04-07-fusion-agent-v2-design.md`
- `2026-04-10-thesis-aligned-agent-design.md`
- `2026-04-16-building-micro-msft-fresh-checkout-result.json`
- `2026-04-16-building-micro-alignment-result.json`
- `2026-04-17-agentic-any-region-fusion-design.md`
- `2026-04-20-evaluation-contract-claim-lock.md`
- `2026-04-20-evidence-ledger.md`
- `2026-04-21-no-ui-maturity-target.md`
- `2026-04-21-no-ui-maturity-gap-ledger.md`
- `2026-04-21-no-ui-maturity-evidence-freeze.json`
- `2026-04-21-no-ui-maturity-evidence-freeze.md`
- `2026-04-21-operator-read-model-contract.md`
- `2026-04-21-paper-experiment-matrix.json`
- `2026-04-21-paper-evidence-freeze.json`
- `2026-04-21-paper-evidence-freeze.md`
- `2026-04-21-scenario-eval-manifest.json`
- `2026-04-21-scenario-regression-set-design.md`
- `2026-04-21-scenario-trigger-proof.md`
- `2026-04-21-scenario-evidence-freeze.json`
- `2026-04-21-scenario-evidence-freeze.md`

### Phase C / Phase D / Phase E baseline docs

- `2026-05-06-capability-consolidation-review.md`
- `2026-05-06-capability-inventory.md`
- `2026-05-06-capability-matrix.json`
- `2026-05-06-consolidation-backlog.md`
- `2026-05-06-next-execution-sequence.md`
- `2026-05-06-redundancy-and-drift-ledger.md`
- `2026-04-23-system-next-improvement-review.md`
- `2026-05-06-related-work-gap-matrix.json`
- `2026-05-06-related-work-gap-matrix.md`
- `2026-05-09-kg-closure-gates.md`
- `2026-05-10-kg-gates-evidence-summary.md`
- `2026-05-12-building-gitega-micro-msft-neo4j-baseline-8012.json`
- `2026-05-13-thesis-research-spec.md`
- `2026-05-13-thesis-claims-ledger.md`
- `2026-05-13-thesis-related-work-matrix.json`
- `2026-05-13-thesis-related-work-matrix.md`
- `2026-05-13-thesis-outline-and-timeline.md`
- `2026-05-13-thesis-capability-handshake.md`

### Consolidation design context

- `2026-05-13-single-plan-consolidation-design.md`

If a future Phase B-E task introduces a new active spec, add it to this index in
the same change that starts consuming it.
