from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from benchmark_platform.canonical import canonical_sha256
from benchmark_platform.crosswalk import CrosswalkReport, validate_crosswalk
from benchmark_platform.design_loader import FrozenDesignBundle
from benchmark_platform.models import BenchmarkPlatformValidationError, FailureClass, FailureRecord


CONTEXT_CONTRACT_ID = "fusionagent.benchmark-platform.canonical-context.v1"


class CanonicalContextError(BenchmarkPlatformValidationError):
    """Raised when a canonical context cannot be closed against the frozen KG."""


class DecisionStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: str = Field(pattern=r"^(selected|resolved|executed|evaluated)$")
    value: str = Field(min_length=1)
    source: str = Field(min_length=1)


class CanonicalContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_id: str
    design_id: str
    kg_release_id: str
    kg_semantic_hash: str
    template_family_id: str
    scenario_id: str
    task_ids: tuple[str, ...]
    contract_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    algorithm_ids: tuple[str, ...]
    policy_ids: tuple[str, ...]
    observation_hash: str
    semantic_hash: str
    crosswalk: CrosswalkReport
    decisions: tuple[DecisionStatus, ...]
    payload: dict[str, Any]


def _fail(code: str, message: str, path: tuple[str | int, ...] = ()) -> None:
    raise CanonicalContextError([
        FailureRecord(
            failure_class=FailureClass.RUNTIME_INVALID_STATE,
            message=message,
            path=path,
            validator="canonical_context",
            details={"code": code},
        )
    ])


def _ids(report: CrosswalkReport, kind: str) -> tuple[str, ...]:
    return tuple(sorted(item.reference_id for item in report.bindings if item.reference_type == kind))


def build_canonical_context(
    bundle: FrozenDesignBundle,
    template: Mapping[str, Any],
    observation: Mapping[str, Any],
    *,
    scenario_id: str | None = None,
    decisions: Mapping[str, tuple[str, str]] | None = None,
) -> CanonicalContext:
    if bundle.design_id != "fusionagent.benchmark-design.v1" or not bundle.kg_release_id:
        _fail("missing_identity", "frozen design bundle has no valid design or KG identity")
    if not isinstance(observation, Mapping):
        _fail("invalid_observation", "observation must be a mapping")
    report = validate_crosswalk(bundle, template)
    task_state = template.get("task_state")
    if not isinstance(task_state, Mapping):
        _fail("missing_task_state", "template task_state is required", ("task_state",))
    tasks = task_state.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        _fail("missing_task_state", "template must contain at least one task", ("task_state", "tasks"))
    task_ids = tuple(sorted(str(item["task_id"]) for item in tasks if isinstance(item, Mapping) and item.get("task_id")))
    if not task_ids:
        _fail("missing_task_id", "template tasks must contain task_id")
    resolved_scenario = scenario_id or str(task_state.get("scenario_id") or task_state.get("scenario_profile_id") or "")
    if not resolved_scenario:
        _fail("missing_scenario", "scenario_id must be explicit; aliases or defaults are forbidden", ("task_state",))
    scenario_ids = _ids(report, "scenario")
    if resolved_scenario not in scenario_ids:
        _fail("scenario_mismatch", "scenario_id is not closed by the crosswalk", ("scenario_id",))
    payload = {
        "contract_id": CONTEXT_CONTRACT_ID,
        "design_id": bundle.design_id,
        "kg_release_id": bundle.kg_release_id,
        "kg_semantic_hash": bundle.kg_semantic_hash,
        "template_family_id": template.get("template_family_id"),
        "scenario_id": resolved_scenario,
        "task_state": task_state,
        "observation": observation,
        "crosswalk": report.model_dump(mode="json"),
    }
    decision_items = decisions or {}
    statuses = tuple(
        DecisionStatus(state=state, value=value, source=source)
        for state, (value, source) in sorted(decision_items.items())
    )
    return CanonicalContext(
        contract_id=CONTEXT_CONTRACT_ID,
        design_id=bundle.design_id,
        kg_release_id=bundle.kg_release_id,
        kg_semantic_hash=bundle.kg_semantic_hash,
        template_family_id=str(template["template_family_id"]),
        scenario_id=resolved_scenario,
        task_ids=task_ids,
        contract_ids=_ids(report, "contract"),
        source_ids=_ids(report, "source"),
        algorithm_ids=_ids(report, "algorithm"),
        policy_ids=tuple(sorted(_ids(report, "quality_policy") + _ids(report, "intent_policy"))),
        observation_hash=canonical_sha256(observation),
        semantic_hash=canonical_sha256(payload),
        crosswalk=report,
        decisions=statuses,
        payload=payload,
    )
