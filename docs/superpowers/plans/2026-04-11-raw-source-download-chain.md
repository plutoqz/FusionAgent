# Raw Source Download Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans together with superpowers:test-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the missing `raw source -> acquisition/cache/clip -> bundle assembly` runtime path so `task-driven` requests can expand into concrete data acquisition, version checks, and clipped reuse instead of depending on bundle-level hardcoded local shapefile reads.

**Architecture:** Keep the current `planner -> validator -> executor -> healing -> writeback` loop unchanged. Introduce a raw-vector acquisition service backed by shared source-catalog specs, let the local bundle provider assemble `osm.zip` and `ref.zip` from cached raw sources, and make clipping CRS-safe even when cached artifacts are stored in a projected CRS.

**Tech Stack:** Python, dataclasses, GeoPandas, existing artifact registry JSON index, pytest

---

## File Structure

### Existing files to modify

- Modify: `E:\vscode\fusionAgent\kg\source_catalog.py`
- Modify: `E:\vscode\fusionAgent\services\input_acquisition_service.py`
- Modify: `E:\vscode\fusionAgent\services\local_bundle_catalog.py`
- Modify: `E:\vscode\fusionAgent\services\agent_run_service.py`
- Modify: `E:\vscode\fusionAgent\tests\test_input_acquisition_service.py`
- Modify: `E:\vscode\fusionAgent\tests\test_local_bundle_catalog.py`
- Modify: `E:\vscode\fusionAgent\tests\test_agent_run_service_enhancements.py`
- Modify: `E:\vscode\fusionAgent\README.md`

### New files to create

- Create: `E:\vscode\fusionAgent\services\raw_vector_source_service.py`
- Create: `E:\vscode\fusionAgent\utils\vector_clip.py`
- Create: `E:\vscode\fusionAgent\tests\test_raw_vector_source_service.py`

---

### Task 1: Define Raw Source Materialization Specs

**Files:**
- Modify: `E:\vscode\fusionAgent\kg\source_catalog.py`
- Modify: `E:\vscode\fusionAgent\tests\test_local_bundle_catalog.py`

- [x] **Step 1: Add failing coverage for raw-source locator strategies and bundle assembly metadata**
- [x] **Step 2: Extend the source catalog with explicit raw source specs instead of loose `path_hint` strings**
- [x] **Step 3: Expose helpers for resolving bundle `component_source_ids` into concrete raw source specs**

### Task 2: Implement Raw Source Cache, Version Check, And CRS-Safe Clip Reuse

**Files:**
- Create: `E:\vscode\fusionAgent\services\raw_vector_source_service.py`
- Create: `E:\vscode\fusionAgent\utils\vector_clip.py`
- Modify: `E:\vscode\fusionAgent\services\input_acquisition_service.py`
- Create: `E:\vscode\fusionAgent\tests\test_raw_vector_source_service.py`
- Modify: `E:\vscode\fusionAgent\tests\test_input_acquisition_service.py`

- [x] **Step 1: Write failing tests for raw source download/cache reuse and non-`EPSG:4326` clip correctness**
- [x] **Step 2: Introduce shared clipping helpers that transform the request bbox into the dataset CRS before clipping**
- [x] **Step 3: Implement a raw source acquisition service with registry-backed version-aware reuse**
- [x] **Step 4: Re-run focused tests until the raw source and clip-reuse layer is green**

### Task 3: Assemble Bundle Inputs From Raw Sources At Runtime

**Files:**
- Modify: `E:\vscode\fusionAgent\services\local_bundle_catalog.py`
- Modify: `E:\vscode\fusionAgent\services\agent_run_service.py`
- Modify: `E:\vscode\fusionAgent\tests\test_local_bundle_catalog.py`
- Modify: `E:\vscode\fusionAgent\tests\test_agent_run_service_enhancements.py`

- [x] **Step 1: Write failing tests showing bundle providers assemble OSM/ref zips via raw source acquisition**
- [x] **Step 2: Refactor `LocalBundleCatalogProvider` to materialize bundles from `component_source_ids`**
- [x] **Step 3: Wire `AgentRunService` to construct the bundle provider with a shared raw source cache service**
- [x] **Step 4: Re-run runtime tests until task-driven auto input preparation passes through the raw-source layer**

### Task 4: Update Documentation And Close The Stage

**Files:**
- Modify: `E:\vscode\fusionAgent\README.md`
- Modify: `E:\vscode\fusionAgent\docs\superpowers\plans\2026-04-11-raw-source-download-chain.md`

- [x] **Step 1: Update README to describe raw-source acquisition, cache reuse, and bundle assembly behavior**
- [x] **Step 2: Mark this plan document with the executed checkpoints**
- [x] **Step 3: Run focused verification for the new download chain**
- [x] **Step 4: Commit, push branch, merge to `main`, and push `main`**

## Execution Status

- Status: completed
- Runtime outcome: task-driven runs now follow `raw source -> acquisition/cache/version check -> clip reuse -> bundle assembly` instead of depending on final bundle shapefiles only.
- Evidence in code: `services/raw_vector_source_service.py`, `utils/vector_clip.py`, `services/local_bundle_catalog.py`, `services/agent_run_service.py`
