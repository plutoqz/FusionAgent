# Superpowers Specs: Historical Evidence

Status: historical root, superseded 2026-07-10.

`docs/superpowers/specs/` contains prior-stage specs, manifests, freezes,
evidence ledgers, matrices, reviews, and staged summaries. These files are kept
for provenance and may still be referenced by legacy scripts or tests, but they
are not the current research or application entrypoint.

The current project direction is defined by:

- `docs/CURRENT.md`
- `docs/thesis/ontology_schema_v2.md`
- `docs/thesis/product_contract_spec.md`
- `docs/thesis/experiment_case_matrix.md`
- `docs/thesis/research_direction_guide_2026-07-09.md`
- `docs/research-runtime-minimum.md`

## Interpretation Rules

- Files in this directory are historical unless a current document explicitly
  reactivates one for a bounded purpose.
- Freeze reports, maturity checks, scenario evidence bundles, capability
  ledgers, paper evidence packages, and staged summaries should not be treated
  as current project goals.
- Legacy tests and scripts may still read these paths while the repository is
  being simplified. That compatibility does not make the documents
  authoritative.
- New research work should not add more long-lived freeze/maturity/ledger files
  here.

## Why This Changed

The earlier project direction accumulated too much proof machinery around
scenario harnesses, no-UI maturity checks, evidence freezes, and staged
capability ledgers. That machinery is useful as historical context, but it now
obscures the current research goal: product-contract KG design, quality gates,
evidence traces, gap declarations, and constrained LLM planning.

Future application work should start from a simple near-linear pipeline and
should not inherit this directory as a mandatory framework.

## Archive Notes

`docs/superpowers/specs/done/` remains an archive for snapshots that had already
been moved out of the former live root. The distinction between this directory
and `done/` is now historical rather than authoritative.
