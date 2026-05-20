# Thesis And Capability Handshake

## Role Split

- research plan answers why and how to prove the thesis contribution
- capability plan answers what to freeze and what to harden so the thesis stays inside a defensible runtime boundary

## Current Owners

- thesis-facing owner docs:
  - `docs/superpowers/specs/2026-05-13-thesis-research-spec.md`
  - `docs/superpowers/specs/2026-05-13-thesis-claims-ledger.md`
  - `docs/superpowers/specs/2026-05-13-thesis-related-work-matrix.md`
  - `docs/superpowers/specs/2026-05-13-thesis-outline-and-timeline.md`
- capability-facing owner docs:
  - `docs/superpowers/specs/2026-05-06-capability-inventory.md`
  - `docs/v2-operations.md`
  - `docs/superpowers/specs/2026-05-18-track-b-national-scale-evidence-freeze.json`

## Handshake Rules

1. The thesis plan may promote only claims that already map to live evidence, checked-in tests, frozen summaries, or explicit run artifacts.
2. The capability plan may continue hardening runtime features only insofar as that work supports the thesis experiment chain or closes a currently documented boundary.
3. If a runtime capability is still `research_utility`, `reservation_only`, `deferred`, or otherwise outside the stable contract, the thesis must describe it as bounded support or future work rather than as a promoted contribution.
4. Benin-labeled validation scripts remain scale-validation evidence only; they do not redefine the thesis scope as a country-specific system.

## Immediate Application

- `Phase A-D` decides what the runtime can already claim.
- `Phase E` packages only those claims into thesis-facing assets.
- Any wording conflict is resolved in favor of the narrower runtime-evidence interpretation.

## Non-Negotiable Boundary

The thesis narrative must not outrun Phase A-D. In practice that means no final-product UI claim, no live `trajectory-to-road` claim, no autonomous-learning claim, and no promotion of multi-source building validation utilities into the shared runtime story without new frozen evidence.
