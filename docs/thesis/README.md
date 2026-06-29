# FusionAgent Thesis Workspace

This directory is the paper-facing workspace for the FusionAgent thesis. It should contain draft chapters, experiment plans, and thesis-facing evidence indexes. Historical roadmaps and machine-generated evidence remain in `docs/superpowers/specs` so existing tests and scripts keep a single evidence source.

## Current Thesis Position

FusionAgent is framed as a bounded, KG-grounded geospatial vector-fusion runtime for disaster-response workflows. The thesis claim is not a general-purpose agent claim, not a frontend-product claim, and not an unrestricted GIS automation claim.

## Directory Layout

| Path | Purpose |
| --- | --- |
| `chapters/` | Chapter working drafts that can later be merged into the thesis manuscript. |
| `experiments/` | Experiment design, ablation plan, metric plan, and run priorities. |
| `evidence/` | Paper-facing indexes that point back to frozen evidence sources. |
| `experiment-results-draft.md` | Results-and-discussion working draft for currently frozen evidence and pending metrics. |

## Chapter Drafts

| File | Chapter role |
| --- | --- |
| `chapters/chapter-01-research-background-draft.md` | Background, problem framing, RQs, contributions, and non-claims. |
| `chapters/chapter-02-related-work-draft.md` | Related-work axes and gap framing before final citation refresh. |
| `chapters/chapter-03-technical-route-draft.md` | Runtime architecture and technical route. |
| `chapters/chapter-04-experiment-design-draft.md` | Experiment protocol, metrics, baselines, and reporting rules. |
| `chapters/chapter-05-results-analysis-draft.md` | Formal Chapter 5 results-and-analysis draft. |
| `experiment-results-draft.md` | Working bridge between frozen evidence and Chapter 5 material. |

## Canonical Evidence Sources

Use these files as source-of-truth references instead of creating duplicate evidence tables by hand:

| Evidence source | Role |
| --- | --- |
| `docs/superpowers/specs/2026-05-13-thesis-research-spec.md` | Thesis scope, research questions, primary lines, and non-claims. |
| `docs/superpowers/specs/2026-05-13-thesis-claims-ledger.md` | Claim-to-evidence mapping and overstatement boundaries. |
| `docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json` | Canonical row-level experiment matrix for paper evidence. |
| `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json` | Machine-readable paper evidence freeze. |
| `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md` | Human-readable paper evidence freeze. |
| `docs/superpowers/specs/2026-06-10-freeze-c-experiment-matrix.json` | Next Freeze C experiment matrix. |
| `docs/superpowers/specs/2026-06-10-thesis-evidence-tables.md` | Rendered thesis evidence table from Freeze C manifests. |
| `docs/superpowers/specs/2026-06-10-freeze-c-ablation-a0-a2-manifest.json` | Frozen controlled A0/A1/A2a/A2b/A2c ablation evidence. |
| `docs/superpowers/specs/2026-06-10-freeze-c-quality-controlled-supplement-manifest.json` | Frozen controlled semi-real quality supplement evidence. |

## Immediate Work Order

1. Keep `C1`, `C2`, and `C3` as the primary thesis claims.
2. Refresh generated evidence only through scripts, not manual table editing.
3. Use `exp-ablation-a0-a2-controlled-comparison` for controlled ablation comparisons, while preserving its counterfactual scope label.
4. Draft Chapters 1-3 now, because their claims already have stable boundaries.
5. Draft Chapter 5 with frozen controlled ablation and controlled quality supplement evidence; keep original Freeze B real-world quality claims provisional.

## Guardrails

- Do not promote `trajectory-to-road` into the executable runtime claim.
- Do not present frontend or no-UI operator surfaces as the core thesis contribution.
- Do not treat Benin scale-validation scripts as the shared runtime proof without a new freeze.
- Do not claim autonomous self-evolution from bounded durable learning hints.
