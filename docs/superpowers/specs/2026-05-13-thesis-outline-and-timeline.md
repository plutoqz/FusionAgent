# Thesis Outline And Timeline

## Chapter 1 Introduction

- bounded disaster-response geospatial fusion problem
- why executable runtime evidence matters beyond GeoQA or metadata discovery
- research questions `RQ1`, `RQ2`, and `RQ3`
- thesis contributions and explicit non-claims

## Chapter 2 Related Work

- geospatial agents and GIS interaction systems
- KG or ontology grounding for reasoning control
- verification-oriented graph or query systems
- bounded scenario reasoning and hazard-domain references

## Chapter 3 Method

- `planner -> validator -> executor -> healing/replan -> writeback`
- KG-decomposed algorithm primitives
- contract-bounded planning and execution with healing
- auditable evidence contract and operator inspection surfaces

## Chapter 4 Experiments

- `RQ1` baseline and ablation matrix
- `RQ2` healing and replan robustness slice
- `RQ3` inspection and evidence-contract slice
- bounded scale-validation appendix or subsection for the large-AOI building utility

## Chapter 5 Results And Discussion

- main quantitative findings by `RQ1`, `RQ2`, `RQ3`
- bounded extensibility discussion for `road`, `water`, and bounded `poi`
- failure analysis, drift risks, and validity threats

## Chapter 6 Conclusion

- final claim summary
- limitations that remain outside the runtime boundary
- next-step work that is explicitly not claimed in the thesis

## Stage 1: Freeze Claims And Writing Inputs

- finalize `2026-05-13-thesis-research-spec.md`
- finalize `2026-05-13-thesis-claims-ledger.md`
- update the canonical paper matrix metadata
- lock related-work comparison wording

## Stage 2: Freeze Baselines And Ablations

- keep `2026-04-21-paper-experiment-matrix.json` as the canonical experiment source
- verify `RQ1`, `RQ2`, and `RQ3` baseline semantics remain aligned with the live runtime boundary
- mark exploratory comparisons separately from frozen thesis comparisons

## Stage 3: Refresh Evidence And Scale-Validation Notes

- rerun `python scripts/freeze_paper_evidence.py --spec docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json --output-json docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json --output-markdown docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md`
- keep no-UI maturity, scenario, and KG gate evidence synchronized with the same runtime boundary
- keep the Benin-labeled workflow framed as scale-validation evidence, not a country-specific thesis chapter

## Stage 4: Draft The Thesis

- draft Chapters 1-3 from the frozen claim and related-work docs
- draft Chapter 4 from the canonical matrix and frozen paper evidence
- draft Chapters 5-6 only after the evidence summary is refreshed

## Stage 5: Final Consistency Pass

- check that thesis wording matches `README.md`, `docs/v2-operations.md`, and `docs/superpowers/specs/2026-05-06-capability-inventory.md`
- reject any sentence that outruns the current live evidence or promotes deferred seams
