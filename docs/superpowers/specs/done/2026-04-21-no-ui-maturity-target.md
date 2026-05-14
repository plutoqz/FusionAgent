# No-UI Maturity Target

## Target Statement

FusionAgent is considered a mature no-UI vector data fusion agent when it can accept natural-language and local scenario-triggered requests, select sources and workflows under KG/runtime constraints, execute or partially execute bounded building/road/water/POI tasks with explicit evidence semantics, recover through documented repair/replan paths, consume durable learning as bounded policy hints, produce auditable artifacts, and expose operator-grade read APIs and runbooks without requiring a final frontend.

## In Scope

- Natural-language task-driven requests.
- Local file-inbox scenario-triggered requests.
- KG-constrained planning and validation.
- Task-driven source acquisition for bounded official/local sources.
- Building, road, water, and bounded POI evidence with explicit execution-level versus planner-level status.
- Reactive healing, full replan V1 evidence, and bounded durable-learning policy hints.
- Machine-readable and human-readable evidence freeze artifacts.
- No-UI operator read APIs, CLI scripts, and runbooks.

## Out Of Scope

- Final visual frontend.
- Multi-user authentication.
- Production cloud deployment guarantees.
- External live event-feed provider integrations.
- Full policy auto-tuning.
- Arbitrary task-family extensibility.
- Live trajectory-to-road ingestion.

## Rename Gate

README wording may change from "prototype" to "mature no-UI vector data fusion agent" only after the maturity gates in `docs/superpowers/plans/2026-04-21-no-ui-mature-agent-plan.md` pass and the final evidence freeze is committed.
