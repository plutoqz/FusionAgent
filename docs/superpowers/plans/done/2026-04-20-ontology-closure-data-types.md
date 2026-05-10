# Ontology Closure Data Types Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the smallest useful executable/research ontology gap by exposing seeded `DataTypeNode` records through KG context and validating data-type reference closure.

**Architecture:** Add `list_data_types()` to the KG repository interface and both repository implementations. Carry data types into `KGContext`, serialize them into planner retrieval context, and add a focused ontology-closure test proving seed references resolve to declared data types.

**Tech Stack:** Python dataclasses, in-memory KG repository, Neo4j repository, pytest

**Completion Status:** Completed on 2026-04-20 in branch `codex/ontology-closure-data-types`. Focused verification passed with `30 passed`; final verification used `python -m pytest -q` and passed with `164 passed, 1 skipped, 6 warnings`.

---

## File Map

- Modify: `kg/models.py`
  Responsibility: add `data_types` to `KGContext`.
- Modify: `kg/repository.py`
  Responsibility: add `list_data_types()` to the repository contract.
- Modify: `kg/inmemory_repository.py`
  Responsibility: expose seeded `DATA_TYPES` and include them in built context.
- Modify: `kg/neo4j_repository.py`
  Responsibility: query managed `DataType` nodes and include them in built context.
- Modify: `agent/retriever.py`
  Responsibility: serialize data types into planner retrieval context.
- Create: `tests/test_ontology_closure.py`
  Responsibility: prove data types are exposed and seed references are closed.
- Modify: `tests/test_planner_context.py`
  Responsibility: prove planner context exposes data types.
- Modify: `docs/superpowers/specs/2026-04-20-evidence-ledger.md`
  Responsibility: record Phase E evidence.

---

## Task 1: Add Data Type Exposure Tests

**Files:**
- Create: `tests/test_ontology_closure.py`
- Modify: `tests/test_planner_context.py`

- [x] **Step 1: Write failing KG context test**

Add `test_kg_context_exposes_seeded_data_types`.

Expected red result:

```text
AttributeError: 'KGContext' object has no attribute 'data_types'
```

- [x] **Step 2: Write seed closure test**

Add `test_seed_ontology_data_type_references_are_closed`, covering:

```text
Algorithm input/output types
DataSource supported types
WorkflowPattern step input/output types
OutputSchemaPolicy output types
CAN_TRANSFORM_TO source/target types
```

- [x] **Step 3: Write failing planner context test**

Add `test_planner_context_exposes_data_types`.

Expected red result:

```text
KeyError: 'data_types'
```

## Task 2: Implement Data Type Context

**Files:**
- Modify: `kg/models.py`
- Modify: `kg/repository.py`
- Modify: `kg/inmemory_repository.py`
- Modify: `kg/neo4j_repository.py`
- Modify: `agent/retriever.py`

- [x] **Step 1: Extend repository contract**

Add:

```python
def list_data_types(self) -> List[DataTypeNode]:
    ...
```

- [x] **Step 2: Implement in-memory list**

Return sorted seeded `DATA_TYPES`.

- [x] **Step 3: Implement Neo4j list**

Query managed `DataType` nodes ordered by `typeId`.

- [x] **Step 4: Include data types in KGContext and planner retrieval**

Add `data_types` to `KGContext` and serialize each item with:

```text
type_id
theme
geometry_type
description
```

## Task 3: Verify

**Files:**
- Modify: `docs/superpowers/plans/done/2026-04-20-ontology-closure-data-types.md`

- [x] **Step 1: Run red checks**

Executed before implementation:

```powershell
python -m pytest -q tests/test_ontology_closure.py tests/test_planner_context.py::test_planner_context_exposes_data_types
```

Result:

```text
2 failed, 1 passed
```

- [x] **Step 2: Run focused green checks**

Executed after implementation:

```powershell
python -m pytest -q tests/test_ontology_closure.py tests/test_planner_context.py::test_planner_context_exposes_data_types
```

Result:

```text
3 passed
```

- [x] **Step 3: Run KG/planner regression subset**

Executed:

```powershell
python -m pytest -q tests/test_ontology_closure.py tests/test_planner_context.py tests/test_kg_repository_enhancements.py tests/test_neo4j_repository.py tests/test_neo4j_bootstrap.py
```

Result:

```text
30 passed
```

- [x] **Step 4: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected:

```text
164 passed, 1 skipped, 6 warnings
```

## Self-Review

- Scope control: This phase does not attempt full OWL/SHACL closure.
- Evidence: Runtime planner context now carries explicit data-type nodes, and seed references are tested for closure.
- Compatibility: Existing planner context keys remain additive; no existing retrieval fields were renamed.
