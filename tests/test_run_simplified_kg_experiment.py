from __future__ import annotations

import json
from types import SimpleNamespace

from scripts import run_simplified_kg_experiment as experiment
from scripts.run_simplified_kg_experiment import (
    ABLATIONS,
    ADVERSARIAL_PROFILE,
    COMPLEX_PROFILE,
    HELDOUT_CONFIRMATORY_PROFILE,
    OBSERVABLE_INVARIANT_PROFILE,
    OBSERVABLE_INVARIANT_V3_PROFILE,
    PRIMARY_METHODS,
    generate_cases,
    run_experiment,
)
from scripts.build_heldout_confirmatory_cases import build_cases as build_heldout_cases
from schemas.research_llm_pilot import ResearchPlanningDecision


def test_generate_cases_has_24_paired_members_across_12_families() -> None:
    cases = generate_cases()

    assert len(cases) == 48
    assert len({case["pair_id"] for case in cases}) == 24
    assert {case["variant"] for case in cases} == {"base", "fault"}
    assert {case["product"] for case in cases} == {"building", "road", "water_polygon", "waterways", "poi"}


def test_local_harness_writes_requested_traces_and_tables(tmp_path) -> None:
    output = tmp_path / "simplified"

    summary = run_experiment(output, mode="local", case_limit=4)

    assert summary["claim_eligible"] is False
    assert summary["row_count"] == 4 * (len(PRIMARY_METHODS) + len(ABLATIONS))
    assert (output / "main_comparison.md").exists()
    assert (output / "kg_ablation.md").exists()
    assert (output / "success_trace.json").exists()
    assert (output / "failure_trace.json").exists()
    rows = json.loads((output / "rows.json").read_text(encoding="utf-8"))
    assert all({"raw_request", "kg_provided", "plan", "tool_call_sequence", "stage_status", "oracle", "vetoes"} <= set(row) for row in rows)
    assert any(row["method"] == "llm_full_contract_kg" for row in rows)
    assert any(row["method"] == "without_contract_quality_delivery_policy" for row in rows)


def test_ablation_summary_reports_drop_against_full_kg(tmp_path) -> None:
    summary = run_experiment(tmp_path / "simplified", mode="local", case_limit=2)

    assert set(summary["ablation_drops_vs_full_contract_kg"]) == set(ABLATIONS)
    assert "deterministic local harness" in (tmp_path / "simplified" / "conclusion.md").read_text(encoding="utf-8")


def test_observable_profile_hides_fault_labels_and_keeps_raw_signals() -> None:
    cases = generate_cases(profile=OBSERVABLE_INVARIANT_PROFILE)

    assert all("fault_signal" not in case["observations"] for case in cases)
    aoi_fault = next(case for case in cases if case["family"] == "aoi_determination" and case["is_fault"])
    validator_fault = next(case for case in cases if case["family"] == "validator_veto" and case["is_fault"])
    assert aoi_fault["observations"]["aoi_resolved"] is False
    assert validator_fault["observations"]["validator_veto"] == "contract_conflict"
    assert aoi_fault["oracle"]["acceptance"]["allowed_decisions"] == ["reject"]


def test_observable_invariant_accepts_safe_alternative_for_missing_source() -> None:
    case = next(
        case
        for case in generate_cases(profile=OBSERVABLE_INVARIANT_PROFILE)
        if case["family"] == "source_availability" and case["is_fault"]
    )
    plan = ResearchPlanningDecision.model_validate(
        {"decision": "reject", "tasks": [], "uncertainties": [], "evidence": ["no source available"]}
    )

    evaluation = experiment._evaluate(case, plan, method="test", error=None)

    assert evaluation["stage_status"]["delivery"] is True
    assert evaluation["oracle_pass"] is True


def test_corrected_profile_can_run_only_reference_baselines(tmp_path) -> None:
    output = tmp_path / "corrected-baselines"

    summary = run_experiment(
        output,
        mode="local",
        profile=OBSERVABLE_INVARIANT_PROFILE,
        selected_methods=("rules_only", "fixed_workflow"),
    )

    assert summary["row_count"] == 96
    assert {item["method"] for item in summary["methods"]} == {"rules_only", "fixed_workflow"}
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["fault_labels_exposed_to_methods"] is False
    assert manifest["selected_methods"] == ["rules_only", "fixed_workflow"]
    assert manifest["primary_methods"] == ["rules_only", "fixed_workflow"]
    assert manifest["ablations"] == []


def test_v3_pairs_have_observable_differences_and_balanced_products() -> None:
    cases = generate_cases(profile=OBSERVABLE_INVARIANT_V3_PROFILE)

    for pair_id in {case["pair_id"] for case in cases}:
        base = next(case for case in cases if case["pair_id"] == pair_id and case["variant"] == "base")
        fault = next(case for case in cases if case["pair_id"] == pair_id and case["variant"] == "fault")
        comparable_base_request = {key: value for key, value in base["request"].items() if key != "request_id"}
        comparable_fault_request = {key: value for key, value in fault["request"].items() if key != "request_id"}
        assert comparable_base_request != comparable_fault_request or base["observations"] != fault["observations"]
    product_counts = {
        product: sum(case["product"] == product for case in cases)
        for product in experiment.PRODUCTS
    }
    assert sorted(product_counts.values()) == [8, 10, 10, 10, 10]
    assert all("fault_signal" not in case["observations"] for case in cases)
    assert all("crosswalk_status" not in case["observations"] for case in cases)


def test_complex_profile_has_six_paired_high_difficulty_scenarios() -> None:
    cases = generate_cases(profile=COMPLEX_PROFILE)

    assert len(cases) == 12
    assert len({case["pair_id"] for case in cases}) == 6
    assert {case["variant"] for case in cases} == {"base", "fault"}
    faults = [case for case in cases if case["is_fault"]]
    assert all("multi_constraint_fault" in case["perturbation_tags"] for case in faults)
    assert all(len(case["task_kinds"]) >= 2 for case in cases)
    assert len({case["request"]["request_id"] for case in cases}) == 12
    assert all(case["evaluation_profile"] == COMPLEX_PROFILE for case in cases)


def test_complex_faults_are_observable_and_grounded() -> None:
    cases = generate_cases(profile=COMPLEX_PROFILE)
    by_pair = {case["pair_id"]: case for case in cases if case["is_fault"]}

    assert by_pair["complex.multi_source_quality.s1"]["observations"]["quality_measurements"]["water_polygon"]["geometry_valid"] is False
    assert by_pair["complex.multi_source_quality.s1"]["observations"]["source_checks"]["water_polygon"][0]["acquisition_status"] == "timeout"
    assert by_pair["complex.alias_precedence.s2"]["request"]["products"][0] == "poi"
    assert "roads" in by_pair["complex.alias_precedence.s2"]["request"]["products"]
    contract_case = by_pair["complex.contract_evidence.s3"]
    assert contract_case["observations"]["proposed_output_fields"]["building"] != contract_case["oracle"]["ground_truth"]["products"]["building"]["required_fields"]
    assert contract_case["observations"]["available_evidence"]["building"] != contract_case["oracle"]["ground_truth"]["products"]["building"]["evidence_requirements"]
    assert by_pair["complex.algorithm_acquisition.s4"]["observations"]["required_algorithm_override"] == "algo.external.unregistered.v1"
    assert by_pair["complex.veto_delivery.s5"]["observations"]["validator_results"][0]["status"] == "fail"
    assert by_pair["complex.aoi_source.s6"]["observations"]["selected_aoi_id"] is None


def test_adversarial_profile_has_repeated_broad_baseline_stress_cases() -> None:
    cases = generate_cases(profile=ADVERSARIAL_PROFILE)

    assert len(cases) == 120
    assert len({case["pair_id"] for case in cases}) == 60
    assert len({case["family"] for case in cases}) == 12
    assert all(
        sum(case["pair_id"] == pair_id for case in cases) == 2
        for pair_id in {case["pair_id"] for case in cases}
    )
    assert all(
        case["oracle"]["decision"] == "plan"
        and case["oracle"]["hard_veto"] is None
        for case in cases
        if case["variant"] == "base"
    )
    assert all("fault_signal" not in case["observations"] for case in cases)
    aliases = next(
        case for case in cases
        if case["family"] == "mixed_alias_crosswalk" and case["is_fault"]
    )
    assert any(token in set(experiment.V3_CROSSWALK_ALIASES.values()) for token in aliases["request"]["products"])
    hidden_veto = next(
        case for case in cases
        if case["family"] == "nonexplicit_veto" and case["is_fault"]
    )
    assert hidden_veto["observations"]["validator_results"][0]["status"] == "blocked"
    assert hidden_veto["oracle"]["hard_veto"] == "nonexplicit_contract_veto"


def test_adversarial_ontology_exposes_precedence_only_to_full_kg() -> None:
    case = next(
        case for case in generate_cases(profile=ADVERSARIAL_PROFILE)
        if case["family"] == "priority_conflict" and case["is_fault"]
    )
    repo = experiment.InMemoryKGRepository(experience_policy="pinned_snapshot")
    full, _ = experiment._build_context(case, "llm_full_contract_kg", repo)
    no_ontology, _ = experiment._build_context(
        case, "without_ontology_identity_crosswalk", repo
    )
    assert full["ontology_identity_crosswalk"]["canonical_precedence"]
    assert "ontology_identity_crosswalk" not in no_ontology


def test_complex_profile_local_matrix_writes_all_methods(tmp_path) -> None:
    output = tmp_path / "complex"
    summary = run_experiment(output, mode="local", profile=COMPLEX_PROFILE)

    assert summary["row_count"] == 12 * (len(PRIMARY_METHODS) + len(ABLATIONS))
    assert summary["evaluation_profile"] == COMPLEX_PROFILE
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["case_count"] == 12
    assert manifest["method_count"] == 8
    assert manifest["claim_boundary"].startswith("deterministic local harness")


def test_adversarial_local_matrix_supports_deterministic_parallel_collection(tmp_path) -> None:
    output = tmp_path / "adversarial-parallel"
    summary = run_experiment(
        output,
        mode="local",
        profile=ADVERSARIAL_PROFILE,
        case_limit=4,
        max_workers=3,
    )

    assert summary["row_count"] == 4 * (len(PRIMARY_METHODS) + len(ABLATIONS))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["runtime"]["max_workers"] == 3
    rows = json.loads((output / "rows.json").read_text(encoding="utf-8"))
    assert [row["execution_index"] for row in rows] == list(range(len(rows)))


def test_heldout_fixture_is_balanced_independent_and_compound() -> None:
    cases = build_heldout_cases()
    faults = [case for case in cases if case["is_fault"]]

    assert len(cases) == 240
    assert len({case["pair_id"] for case in cases}) == 120
    assert {case["evaluation_profile"] for case in cases} == {HELDOUT_CONFIRMATORY_PROFILE}
    assert {
        count: sum(case["design_metadata"]["constraint_count"] == count for case in faults)
        for count in (1, 2, 3)
    } == {1: 40, 2: 40, 3: 40}
    assert not any(
        {"source_permission_denied", "timeout_exhausted"}
        <= set(case["design_metadata"]["fault_signals"])
        for case in faults
    )
    assert all(
        sum(
            case["family"] == family
            and case["product"] == product
            and case["is_fault"]
            for case in cases
        ) == 2
        for family in {case["family"] for case in cases}
        for product in experiment.PRODUCTS
    )


def test_heldout_runner_uses_exact_llm_replicates_and_case_level_majority(tmp_path) -> None:
    case_file = experiment.REPO_ROOT / "experiments" / "heldout_confirmatory_v1" / "cases.json"
    output = tmp_path / "heldout"
    summary = run_experiment(
        output,
        mode="local",
        profile=HELDOUT_CONFIRMATORY_PROFILE,
        case_file=case_file,
        case_limit=4,
        selected_methods=PRIMARY_METHODS,
        llm_replicates=3,
        max_workers=3,
    )

    assert summary["row_count"] == 4 * (3 * 3 + 2)
    by_method = {item["method"]: item for item in summary["methods"]}
    assert all(item["case_count"] == 4 for item in by_method.values())
    assert by_method["llm_full_contract_kg"]["execution_count"] == 12
    assert by_method["rules_only"]["execution_count"] == 4
    rows = json.loads((output / "rows.json").read_text(encoding="utf-8"))
    assert {row["replicate_id"] for row in rows if row["method"] == "llm_only"} == {1, 2, 3}
    assert len(list((output / "traces").rglob("trace.json"))) == len(rows)
    assert (output / "confirmatory_statistics.md").exists()
    stats = summary["confirmatory_statistics"]
    assert stats["analysis_unit"].startswith("case-level majority")
    assert stats["llm_replicates"] == 3
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    selected_cases = json.loads((output / "cases.json").read_text(encoding="utf-8"))
    assert set(manifest["families"]) == {case["family"] for case in selected_cases}
    assert manifest["scenarios"] == manifest["families"]
    assert manifest["repetitions_per_scenario"] == 2


def test_heldout_labels_and_oracle_are_excluded_from_every_planning_input() -> None:
    cases = {
        case["family"]: case
        for case in build_heldout_cases()
        if case["is_fault"]
    }
    repo = experiment.InMemoryKGRepository(experience_policy="pinned_snapshot")

    for case in cases.values():
        for method in PRIMARY_METHODS:
            context, _trace = experiment._build_context(case, method, repo)
            serialized = json.dumps(context, ensure_ascii=False)
            assert {"oracle", "design_metadata", "perturbation_tags", "is_fault", "variant"}.isdisjoint(context)
            assert "fault_signals" not in serialized
            assert "oracle_kind" not in serialized


def test_heldout_profile_requires_frozen_case_file(tmp_path) -> None:
    try:
        run_experiment(tmp_path / "missing-heldout", mode="local", profile=HELDOUT_CONFIRMATORY_PROFILE)
    except ValueError as exc:
        assert "requires case_file" in str(exc)
    else:
        raise AssertionError("heldout profile accepted a generated in-run case set")


def test_heldout_frozen_truth_matches_full_kg_projection() -> None:
    cases = [case for case in build_heldout_cases() if not case["is_fault"]]
    repo = experiment.InMemoryKGRepository(experience_policy="pinned_snapshot")
    checked: set[tuple[str, str]] = set()

    for case in cases:
        context, _trace = experiment._build_context(case, "llm_full_contract_kg", repo)
        capabilities = {
            item["task_kind"]: item
            for item in context["capability_algorithm_grounding"]["tasks"]
        }
        contracts = {
            item["task_kind"]: item
            for item in context["contract_quality_delivery_policy"]["products"]
        }
        for task in case["task_kinds"]:
            key = (case["request"]["disaster_type"], task)
            if key in checked:
                continue
            truth = case["oracle"]["ground_truth"]["products"][task]
            assert {item["id"] for item in capabilities[task]["algorithms"]} == set(truth["algorithm_ids"])
            assert {item["id"] for item in capabilities[task]["sources"]} == set(truth["source_ids"])
            assert contracts[task]["contract"]["id"] == truth["contract_id"]
            assert contracts[task]["output_requirement"]["required_fields"] == truth["required_fields"]
            assert contracts[task]["contract"]["evidence_requirements"] == truth["evidence_requirements"]
            checked.add(key)

    assert checked == {(disaster, task) for disaster in {"earthquake", "flood"} for task in experiment.PRODUCTS}


def test_outcome_metrics_separate_denominators_and_mark_unexecuted_e2e(tmp_path) -> None:
    summary = run_experiment(tmp_path / "complex-metrics", mode="local", profile=COMPLEX_PROFILE)
    by_method = {item["method"]: item for item in summary["methods"]}
    rules = by_method["rules_only"]["outcome_metrics"]

    assert rules["base_normal_planning_denominator"] == 6
    assert rules["fault_handling_denominator"] == 6
    assert rules["hard_veto_correct_trigger_denominator"] == 2
    assert rules["constrained_delivery_correct_denominator"] == 3
    assert rules["actual_e2e_completion_rate"] is None
    assert rules["actual_e2e_completion_denominator"] == 0
    report = (tmp_path / "complex-metrics" / "outcome_metrics.md").read_text(encoding="utf-8")
    assert "n/a (0/0)" in report
    main = (tmp_path / "complex-metrics" / "main_comparison.md").read_text(encoding="utf-8")
    assert "Base normal" in main
    assert "Fault-only" in main
    assert "Oracle pass (secondary)" in main
    conclusion = (tmp_path / "complex-metrics" / "conclusion.md").read_text(encoding="utf-8")
    assert "fault-only metric" in conclusion
    plan = (tmp_path / "complex-metrics" / "experiment_plan.md").read_text(encoding="utf-8")
    assert "mixed clean base members with fault members" in plan


def test_v3_model_inputs_do_not_expose_experiment_labels() -> None:
    cases = generate_cases(profile=OBSERVABLE_INVARIANT_V3_PROFILE)
    repo = experiment.InMemoryKGRepository(experience_policy="pinned_snapshot")
    request_ids = [case["request"]["request_id"] for case in cases]

    assert len(set(request_ids)) == len(cases)
    assert all(request_id.startswith("REQ-") and len(request_id) == 20 for request_id in request_ids)
    assert all(set(request_id[4:]) <= set("0123456789abcdef") for request_id in request_ids)
    for case in cases:
        request_id = case["request"]["request_id"].casefold()
        assert case["family"].casefold() not in request_id
        assert case["variant"].casefold() not in request_id
        if "operator_note_present" in case["perturbation_tags"]:
            assert case["request"]["operator_note"] == "Archive the coordination ticket after review."
        else:
            assert "operator_note" not in case["request"]
        for method in experiment.ALL_METHODS:
            context, _trace = experiment._build_context(case, method, repo)
            assert {"oracle", "is_fault", "family", "variant"}.isdisjoint(context)


def test_v3_projection_uses_only_matching_kg_entities_and_relations() -> None:
    cases = generate_cases(profile=OBSERVABLE_INVARIANT_V3_PROFILE)
    repo = experiment.InMemoryKGRepository(experience_policy="pinned_snapshot")
    case = next(case for case in cases if case["family"] == "kg_crosswalk" and case["is_fault"])

    full_context, full_trace = experiment._build_context(case, "llm_full_contract_kg", repo)
    llm_only_context, llm_only_trace = experiment._build_context(case, "llm_only", repo)
    no_ontology_context, no_ontology_trace = experiment._build_context(
        case,
        "without_ontology_identity_crosswalk",
        repo,
    )

    assert full_context["ontology_identity_crosswalk"]["mappings"][0]["status"] == "resolved"
    assert llm_only_context["tool_catalog"]["algorithms"]
    assert "capability_algorithm_grounding" not in llm_only_context
    assert llm_only_trace["entities"] == []
    assert full_context["contract_quality_delivery_policy"]["products"][0]["task_kind"] == case["product"]
    governed_by = [item for item in full_trace["relationships"] if item["relation"] == "governed_by"]
    assert governed_by == [
        {
            "source": case["oracle"]["ground_truth"]["products"][case["product"]]["task_id"],
            "relation": "governed_by",
            "target": case["oracle"]["ground_truth"]["products"][case["product"]]["contract_id"],
        }
    ]
    assert no_ontology_context["capability_algorithm_grounding"]["tasks"] == []
    assert no_ontology_context["contract_quality_delivery_policy"]["products"] == []
    assert no_ontology_trace["entities"] == []


def test_v3_canonical_ablation_contexts_remove_only_declared_module() -> None:
    case = next(
        case
        for case in generate_cases(profile=OBSERVABLE_INVARIANT_V3_PROFILE)
        if case["variant"] == "base"
    )
    repo = experiment.InMemoryKGRepository(experience_policy="pinned_snapshot")
    removed_by_method = {
        "without_ontology_identity_crosswalk": "ontology_identity_crosswalk",
        "without_capability_algorithm_grounding": "capability_algorithm_grounding",
        "without_contract_quality_delivery_policy": "contract_quality_delivery_policy",
    }
    contexts = {
        method: experiment._build_context(case, method, repo)[0]
        for method in (
            "llm_only",
            "llm_full_contract_kg",
            *removed_by_method,
        )
    }
    modules = {
        "ontology_identity_crosswalk",
        "capability_algorithm_grounding",
        "contract_quality_delivery_policy",
    }

    assert modules <= set(contexts["llm_full_contract_kg"])
    for method, removed_module in removed_by_method.items():
        assert removed_module not in contexts[method]
        assert modules - {removed_module} <= set(contexts[method])
    catalogs = [context["tool_catalog"] for context in contexts.values()]
    assert all(catalog == catalogs[0] for catalog in catalogs[1:])


def test_v3_oracle_rejects_invented_algorithm_and_missing_evidence() -> None:
    cases = generate_cases(profile=OBSERVABLE_INVARIANT_V3_PROFILE)

    algorithm_case = next(case for case in cases if case["family"] == "algorithm_capability" and case["is_fault"])
    algorithm_plan = _v3_plan(
        algorithm_case,
        decision="gap",
        state="gap",
        algorithm_id="algo.completely_invented.v999",
        evidence=["algo.external.unregistered.v1"],
    )
    assert experiment._evaluate(algorithm_case, algorithm_plan, method="audit", error=None)["oracle_pass"] is False

    for family, decision, state in (
        ("contract_requiredness", "gap", "gap"),
        ("quality_gate", "degraded", "provisional"),
        ("evidence_completeness", "manual_intervention", "pending"),
    ):
        case = next(case for case in cases if case["family"] == family and case["is_fault"])
        plan = _v3_plan(case, decision=decision, state=state, algorithm_id=None, evidence=[])
        assert experiment._evaluate(case, plan, method="audit", error=None)["oracle_pass"] is False


def test_v3_crosswalk_scores_canonical_result_not_explanation_wording() -> None:
    case = next(
        case
        for case in generate_cases(profile=OBSERVABLE_INVARIANT_V3_PROFILE)
        if case["family"] == "kg_crosswalk" and case["is_fault"]
    )
    algorithm_id = case["oracle"]["ground_truth"]["products"][case["product"]]["algorithm_ids"][0]
    plan = _v3_plan(
        case,
        decision="plan",
        state="planned",
        algorithm_id=algorithm_id,
        evidence=["source_provenance"],
    )

    assert experiment._evaluate(case, plan, method="audit", error=None)["oracle_pass"] is True


def test_v3_baseline_run_records_controlled_boundary_and_reproducibility(tmp_path) -> None:
    output = tmp_path / "v3-baselines"

    summary = run_experiment(
        output,
        mode="local",
        profile=OBSERVABLE_INVARIANT_V3_PROFILE,
        selected_methods=("rules_only", "fixed_workflow"),
        invocation=["python", "runner.py", "--profile", OBSERVABLE_INVARIANT_V3_PROFILE],
    )

    by_method = {item["method"]: item for item in summary["methods"]}
    assert by_method["rules_only"]["oracle_pass_rate"] == 32 / 48
    assert by_method["fixed_workflow"]["oracle_pass_rate"] == 26 / 48
    assert sum(by_method["rules_only"]["paired_outcomes"].values()) == 24
    assert "Controlled completion" in (output / "main_comparison.md").read_text(encoding="utf-8")
    rows = json.loads((output / "rows.json").read_text(encoding="utf-8"))
    assert all(row["tool_execution_mode"] == "not_executed_controlled_evaluation" for row in rows)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["case_set_hash"]
    assert manifest["prompt"]["semantic_hash"]
    assert manifest["source_state"]["git_commit"]
    assert manifest["source_state"]["source_file_hashes"]
    assert manifest["runtime"]["invocation"][0] == "python"


def test_v3_pair_selection_keeps_complete_pair(tmp_path) -> None:
    output = tmp_path / "selected-pair"

    summary = run_experiment(
        output,
        mode="local",
        profile=OBSERVABLE_INVARIANT_V3_PROFILE,
        selected_methods=("rules_only", "fixed_workflow"),
        selected_pair_ids=("kg_crosswalk.poi.s2",),
    )

    assert summary["row_count"] == 4
    cases = json.loads((output / "cases.json").read_text(encoding="utf-8"))
    assert {case["variant"] for case in cases} == {"base", "fault"}
    assert {case["pair_id"] for case in cases} == {"kg_crosswalk.poi.s2"}


def _v3_plan(
    case: dict,
    *,
    decision: str,
    state: str,
    algorithm_id: str | None,
    evidence: list[str],
) -> ResearchPlanningDecision:
    tasks = []
    for index, task in enumerate(case["oracle"]["ground_truth"]["canonical_order"], start=1):
        token = experiment._presented_token_for_task(case, task)
        sources = [
            item["source_id"]
            for item in case["observations"]["source_checks"].get(token, [])
            if item.get("catalog_status") == "available" and item.get("acquisition_status") == "ready"
        ]
        task_algorithm = algorithm_id if task == case["product"] else case["oracle"]["ground_truth"]["products"][task]["algorithm_ids"][0]
        tasks.append(
            {
                "order": index,
                "task_kind": task,
                "source_ids": sources,
                "algorithm_id": task_algorithm,
                "delivery_state": state if task == case["product"] else "planned",
                "rationale": "test plan",
            }
        )
    return ResearchPlanningDecision.model_validate(
        {"decision": decision, "tasks": tasks, "uncertainties": [], "evidence": evidence}
    )


def test_resume_retries_only_failed_llm_rows_and_preserves_failure(tmp_path, monkeypatch) -> None:
    output = tmp_path / "simplified"
    run_experiment(output, mode="local", case_limit=2)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    manifest["mode"] = "live"
    (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    rows = json.loads((output / "rows.json").read_text(encoding="utf-8"))
    failed = next(row for row in rows if row["method"] == "llm_only")
    failed["provider_attempt"] = {"success": False, "failure_class": "transport_error"}
    for row in rows:
        if row is not failed and (row["method"].startswith("llm_") or row["method"].startswith("without_")):
            row["provider_attempt"] = _complete_attempt()
    (output / "rows.json").write_text(json.dumps(rows), encoding="utf-8")

    class Provider:
        model = "test-model"
        base_url = "https://example.test/v1"

    monkeypatch.setattr(experiment, "_live_provider", lambda: Provider())
    monkeypatch.setattr(
        experiment,
        "_run_one",
        lambda case, method, **_kwargs: {
            **failed,
            "case_id": case["case_id"],
            "method": method,
            "provider_attempt": _complete_attempt(),
            "error": None,
        },
    )

    summary = experiment.resume_failed_calls(output)

    assert summary["claim_eligible"] is True
    assert summary["resume"]["retried_call_count"] == 1
    assert summary["total_retry_count"] == 1
    failed_traces = list((output / "failed_attempts").rglob("trace-*.json"))
    assert len(failed_traces) == 1
    resumed_rows = json.loads((output / "rows.json").read_text(encoding="utf-8"))
    resumed = next(row for row in resumed_rows if row["case_id"] == failed["case_id"] and row["method"] == "llm_only")
    assert resumed["retry_count"] == 1
    assert resumed["retry_history"] == [
        {
            "failure_class": "transport_error",
            "error": failed["error"],
            "preserved_trace": str(failed_traces[0].resolve()),
        }
    ]


def test_transport_only_resume_preserves_schema_failures_as_method_outcomes(tmp_path, monkeypatch) -> None:
    output = tmp_path / "transport-only"
    run_experiment(
        output,
        mode="local",
        case_limit=2,
        selected_methods=("llm_only", "llm_full_contract_kg"),
    )
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    manifest["mode"] = "live"
    (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    rows = json.loads((output / "rows.json").read_text(encoding="utf-8"))
    transport_row, schema_row, *remaining = rows
    transport_row["provider_attempt"] = {
        **_complete_attempt(),
        "success": False,
        "http_status": 500,
        "failure_class": "http_error",
    }
    transport_row["plan"] = None
    transport_row["error"] = "HTTP 500"
    schema_row["provider_attempt"] = _complete_attempt()
    schema_row["plan"] = None
    schema_row["error"] = "schema validation failed"
    for row in remaining:
        row["provider_attempt"] = _complete_attempt()
    (output / "rows.json").write_text(json.dumps(rows), encoding="utf-8")

    class Provider:
        model = "test-model"
        base_url = "https://example.test/v1"

    monkeypatch.setattr(experiment, "_live_provider", lambda: Provider())
    monkeypatch.setattr(
        experiment,
        "_run_one",
        lambda case, method, **_kwargs: {
            **transport_row,
            "case_id": case["case_id"],
            "method": method,
            "provider_attempt": _complete_attempt(),
            "plan": rows[-1]["plan"],
            "error": None,
        },
    )

    summary = experiment.resume_failed_calls(output, transport_only=True)

    assert summary["resume"]["retried_call_count"] == 1
    resumed = json.loads((output / "rows.json").read_text(encoding="utf-8"))
    preserved = next(
        row for row in resumed
        if row["case_id"] == schema_row["case_id"] and row["method"] == schema_row["method"]
    )
    assert preserved["error"] == "schema validation failed"
    assert preserved["plan"] is None


def test_claim_gate_rejects_strict_json_that_fails_plan_schema(tmp_path) -> None:
    output = tmp_path / "schema-invalid"
    run_experiment(output, mode="local", case_limit=2, selected_methods=("llm_full_contract_kg",))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    manifest["mode"] = "live"
    rows = json.loads((output / "rows.json").read_text(encoding="utf-8"))
    for row in rows:
        row["provider_attempt"] = _complete_attempt()
    rows[0]["plan"] = None
    rows[0]["error"] = "schema validation failed"

    summary = experiment._finalize_outputs(
        output,
        manifest=manifest,
        rows=rows,
        provider=SimpleNamespace(model="test-model", base_url="https://example.test/v1"),
    )

    assert summary["claim_eligible"] is False
    assert summary["provider"]["provider_response_count"] == 2
    assert summary["provider"]["schema_valid_plan_count"] == 1
    assert summary["provider"]["complete_llm_call_count"] == 1
    assert "schema_validation_error" in summary["provider"]["failure_classes"]


def test_resume_retries_schema_invalid_provider_success(tmp_path, monkeypatch) -> None:
    output = tmp_path / "schema-retry"
    run_experiment(output, mode="local", case_limit=2, selected_methods=("llm_full_contract_kg",))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    manifest["mode"] = "live"
    (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    rows = json.loads((output / "rows.json").read_text(encoding="utf-8"))
    failed = rows[0]
    failed["provider_attempt"] = {
        **_complete_attempt(),
        "response_model": "test-model",
    }
    failed["plan"] = None
    failed["error"] = "schema validation failed"
    for row in rows[1:]:
        row["provider_attempt"] = _complete_attempt()
    (output / "rows.json").write_text(json.dumps(rows), encoding="utf-8")

    class Provider:
        model = "test-model"
        base_url = "https://example.test/v1"

    monkeypatch.setattr(experiment, "_live_provider", lambda: Provider())
    monkeypatch.setattr(
        experiment,
        "_run_one",
        lambda case, method, **_kwargs: {
            **failed,
            "case_id": case["case_id"],
            "method": method,
            "plan": {"decision": "plan"},
            "provider_attempt": _complete_attempt(),
            "error": None,
        },
    )

    summary = experiment.resume_failed_calls(output)

    assert summary["resume"]["retried_call_count"] == 1
    assert summary["claim_eligible"] is True
    assert len(list((output / "failed_attempts").rglob("trace-*.json"))) == 1


def _complete_attempt() -> dict:
    return {
        "success": True,
        "failure_class": None,
        "parse_mode": "strict_json",
        "requested_model": "test-model",
        "response_model": "test-model",
        "usage": {"total_tokens": 10},
    }
