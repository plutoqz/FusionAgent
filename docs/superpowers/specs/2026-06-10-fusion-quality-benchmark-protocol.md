# Fusion Quality Benchmark Protocol

## Claim Boundary

Fusion quality claims require real or semi-real AOI cases, frozen source versions, fixed baselines, and task-specific metrics. Synthetic cases are smoke-only unless their generation mechanism is independent of the tested algorithm.

## Data Tiers

| Tier | Thesis Use | Required Label |
| --- | --- | --- |
| real | quality claim | real_source |
| semi_real | robustness or quality claim | perturbation_independent |
| synthetic | smoke by default | algorithm_independent_synthetic only if used for quality |

## Task Metrics

Building, road, waterways, water polygon, and POI metrics are evaluated through `services.artifact_evaluation_service` and interpreted by `services.fusion_quality_benchmark_service`.

## Freeze B Rule

Changing AOIs, source versions, baselines, metric definitions, or independence labels after Freeze B creates a new manifest id.
