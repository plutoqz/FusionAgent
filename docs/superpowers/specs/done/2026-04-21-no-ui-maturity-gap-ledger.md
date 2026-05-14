# No-UI Maturity Gap Ledger

| README Gap | Current Status | Closure Action | Evidence Path | README Repositioning Status |
| --- | --- | --- | --- | --- |
| stronger robustness / learning / operator-facing claim still gated | C3/C4 are implemented, operator surface is thin | freeze as mature no-UI evidence, not production-ready or frontend-complete evidence | `docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.md` | closed in maturity freeze |
| search space remains bounded | building/road/water/bounded-POI are the stable claim | keep bounded wording and avoid arbitrary extensibility claims | `docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json` | documented boundary |
| water/POI do not prove zero-cost new-topic expansion | planner/execution semantics differ by case | document partial semantics and capability tier | `docs/superpowers/specs/2026-04-21-no-ui-maturity-target.md` | documented boundary |
| trajectory-to-road is reservation-only | no live runtime ingestion | keep as explicit boundary | README and maturity target | documented boundary |
| durable learning is first-pass | bounded pattern-selection hint exists | freeze as bounded policy-hint evidence, not auto-tuning | paper and maturity freeze | closed as bounded evidence |
| operator-facing productization is narrow API layer | inspection/compare/scenario APIs exist | keep as no-UI read-API/runbook evidence, with independent frontend still out of achieved state | operator tests and docs | closed as no-UI boundary |
| manual-only sources remain | some Google/reference/Excel paths remain manual | freeze supported official/local sources and document manual boundaries | source materialization tests and runbook | documented boundary |
| AOI geocoder depends on network | Nominatim path exists with tests | keep deterministic fixture/cache guidance and fallback expectations explicit | AOI tests and operations docs | documented boundary |
