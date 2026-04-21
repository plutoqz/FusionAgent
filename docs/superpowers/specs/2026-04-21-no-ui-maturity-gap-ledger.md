# No-UI Maturity Gap Ledger

| README Gap | Current Status | Closure Action | Evidence Path | Required Before README Repositioning |
| --- | --- | --- | --- | --- |
| stronger robustness / learning / operator-facing claim still gated | C3/C4 are implemented, operator surface is thin | refresh evidence freeze and add operator read-model proof | `docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.md` | yes |
| search space remains bounded | building/road/water/bounded-POI are the stable claim | keep bounded wording and avoid arbitrary extensibility claims | `docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json` | yes |
| water/POI do not prove zero-cost new-topic expansion | planner/execution semantics differ by case | document partial semantics and capability tier | `docs/superpowers/specs/2026-04-21-no-ui-maturity-target.md` | yes |
| trajectory-to-road is reservation-only | no live runtime ingestion | keep as explicit boundary | README and maturity target | yes |
| durable learning is first-pass | bounded pattern-selection hint exists | freeze as bounded policy-hint evidence, not auto-tuning | paper and maturity freeze | yes |
| operator-facing productization is narrow API layer | inspection/compare/scenario APIs exist | add read models, run listing, no-UI runbook | operator tests and docs | yes |
| manual-only sources remain | some Google/reference/Excel paths remain manual | freeze supported official/local sources and document manual boundaries | source materialization tests and runbook | yes |
| AOI geocoder depends on network | Nominatim path exists with tests | add deterministic fixture/cache guidance or fallback test path | AOI tests and operations docs | yes |
