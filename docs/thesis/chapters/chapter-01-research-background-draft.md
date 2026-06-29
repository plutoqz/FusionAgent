# Chapter 1 Draft: Research Background And Problem Framing

## Working Thesis Frame

Disaster-response mapping often requires fast geospatial fusion across heterogeneous vector sources, such as buildings, roads, water features, and bounded points of interest. The operational challenge is not only to run a GIS algorithm, but to choose an executable workflow, bind the correct data requirements, validate the plan, recover from bounded failures, and leave evidence that can be inspected after the run.

FusionAgent is positioned as a bounded geospatial vector-fusion runtime for this problem. The thesis studies whether KG-grounded planning, contract-bounded execution, and auditable evidence improve the reliability and inspectability of automated fusion workflows. It does not claim unrestricted geospatial autonomy, arbitrary task coverage, or a production-grade user interface.

## Research Problem

The core problem is that geospatial fusion workflows sit between two brittle extremes:

- Manual GIS workflows can be inspectable but slow to reproduce across tasks, AOIs, and source configurations.
- Unconstrained agent workflows can appear flexible but may produce invalid plans, unsupported algorithm calls, or opaque execution traces.

FusionAgent explores a middle path: an agentic runtime whose choices are constrained by a knowledge graph, runtime contracts, validation gates, and evidence artifacts. This gives the thesis a concrete object of study: executable geospatial fusion behavior under bounded task families.

## Research Questions

| RQ | Question | Primary claim |
| --- | --- | --- |
| `RQ1` | Does KG-grounded, decomposed planning improve executable-plan validity and end-to-end execution success? | `C1` |
| `RQ2` | Does bounded healing and replan improve robustness under failure while preserving runtime boundaries? | `C3` |
| `RQ3` | Does the evidence contract improve inspectability, reproducibility, and paper-evidence curation? | `C2` |

## Contributions

The current contribution set should stay deliberately narrow:

1. A KG-grounded planning and validation runtime for bounded geospatial vector-fusion tasks.
2. A contract-bounded healing and replan mechanism that keeps recovery auditable.
3. A run-level evidence contract that exposes plan, validation, audit, and artifact traces for inspection and research evidence curation.

Supporting contributions include bounded task-driven source acquisition, extension evidence across road/water/bounded POI slices, and durable learning as policy hints. These remain supporting material, not the thesis center.

## Non-Claims

The thesis should explicitly reject the following overstatements:

- FusionAgent is not a general-purpose GIS agent.
- FusionAgent does not claim unrestricted task-family coverage.
- The frontend and operator API are not the central research contribution.
- Multi-source or raster-assisted building utilities are not promoted to the shared runtime claim without new frozen evidence.
- Durable learning is not framed as open-ended autonomous self-improvement.

## Chapter To-Do

- Add a concise disaster-response scenario motivation.
- Add related-work bridge paragraphs after Chapter 2 is refreshed.
- Convert the contribution list into the final thesis introduction style.
- Keep every capability sentence traceable to the claim ledger or paper evidence freeze.
