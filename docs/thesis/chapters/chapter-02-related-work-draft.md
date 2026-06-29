# Chapter 2 Draft: Related Work And Gap Framing

This draft frames the related-work chapter without locking final citations. Specific papers should be refreshed before final writing, but the comparison axes are already clear from the thesis scope.

## Related-Work Axes

The thesis should compare FusionAgent against four neighboring lines of work:

1. geospatial data fusion and conflation systems
2. GIS agents and natural-language GIS workflow assistants
3. knowledge-graph or ontology-grounded planning systems
4. workflow validation, provenance, and reproducible geospatial pipelines

The chapter should avoid presenting FusionAgent as better than all prior systems in a broad sense. The narrower argument is that FusionAgent combines bounded KG-grounded planning, fail-closed runtime validation, recovery governance, and run-level evidence in one executable geospatial fusion runtime.

## Geospatial Fusion And Conflation

Traditional geospatial fusion and conflation work focuses on matching, aligning, deduplicating, and reconciling features across sources. This literature is important because FusionAgent depends on deterministic GIS fusion algorithms rather than replacing them with agent reasoning.

Thesis positioning:

- FusionAgent does not claim novelty in low-level geometry matching alone.
- The contribution is the runtime that selects, validates, executes, and audits bounded fusion workflows.
- Fusion quality metrics must be reported separately from agentic planning metrics.

## GIS Agents And Workflow Assistants

GIS agents and natural-language workflow systems address the usability gap between user intent and spatial analysis workflows. They are relevant because FusionAgent also accepts task-oriented or scenario-oriented requests.

Thesis positioning:

- FusionAgent is narrower than a general GIS assistant.
- It emphasizes executable vector-fusion workflows rather than broad interactive GIS help.
- Its task boundary is explicit: building, road, water, and bounded POI runtime slices.
- Unsupported tasks should fail closed rather than producing plausible but unsupported workflow text.

## KG And Ontology Grounding

Knowledge graphs and ontologies are often used to organize geospatial concepts, data sources, task types, or tool capabilities. For this thesis, the important comparison point is not only semantic retrieval, but whether grounding constrains executable planning.

Thesis positioning:

- KG context is used to constrain task, source, algorithm, and parameter choices.
- Decomposed algorithm primitives make plan validation more inspectable.
- KG fallback should be reported as a runtime governance event rather than hidden as ordinary success.

## Validation, Provenance, And Reproducibility

Reproducible geospatial pipelines commonly emphasize scripted workflows, provenance, source tracking, and artifact management. FusionAgent overlaps with this area through its evidence contract.

Thesis positioning:

- The evidence contract is not just logging; it is a paper-facing and operator-facing trace of plan, validation, execution, audit, and artifacts.
- Result-only output is insufficient for the thesis because it cannot explain whether a run followed the bounded contract.
- Reproducibility claims should remain tied to frozen source IDs, manifests, and checked-in evidence paths.

## Gap Statement

The target gap is a bounded but practical one:

Existing systems often emphasize either GIS algorithm quality, natural-language workflow convenience, semantic organization, or reproducible pipelines. FusionAgent studies the intersection where an agentic runtime must produce executable geospatial fusion workflows, reject unsupported plans, recover from bounded failures, and emit audit-ready evidence.

This gap supports the three research questions:

- `RQ1`: whether KG-grounded decomposition improves executable planning.
- `RQ2`: whether bounded healing and replan improve robustness.
- `RQ3`: whether evidence contracts improve inspection and paper-evidence curation.

## Chapter To-Do

- Refresh final citations before manuscript integration.
- Convert each related-work axis into 2-3 citation-backed paragraphs.
- Add a comparison table with columns for task boundary, grounding, validation, recovery, and evidence contract.
- Keep the comparison focused on research positioning rather than product feature coverage.
