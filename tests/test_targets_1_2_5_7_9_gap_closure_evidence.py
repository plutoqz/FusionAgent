from __future__ import annotations

import json
from pathlib import Path


EVIDENCE_JSON = Path("docs/superpowers/specs/2026-05-29-targets-1-2-5-7-9-gap-closure-evidence.json")
EVIDENCE_MD = Path("docs/superpowers/specs/2026-05-29-targets-1-2-5-7-9-gap-closure-evidence.md")
RESEARCH_SUMMARY = Path("文档/研究总结0529.md")


def test_gap_closure_evidence_json_records_targets_and_boundaries() -> None:
    payload = json.loads(EVIDENCE_JSON.read_text(encoding="utf-8"))

    assert payload["date"] == "2026-05-29"
    assert payload["targets"]["1"]["claim"] == "unattended_local_operation_supported_with_scheduler_inbox_and_recovery_evidence"
    assert payload["targets"]["2"]["height_raster_evidence"] == "explicit_in_report_quality_summary"
    assert payload["targets"]["5"]["boundary"] == "bounded_aoi_poi_only"
    assert payload["targets"]["7"]["manifest"] == "source_materialization_manifest.json"
    assert payload["targets"]["8"]["reports"] == ["run_report_summary.json", "run_report.zh.md", "run_report.en.md"]
    assert payload["targets"]["9"]["operator_action"] == "included_in_recovery_hint"
    assert payload["non_claims"]["target_10"] == "bounded_policy_hints_only_no_self_mutating_model"


def test_gap_closure_docs_do_not_overclaim_self_learning_or_unbounded_poi() -> None:
    text = EVIDENCE_MD.read_text(encoding="utf-8") + "\n" + RESEARCH_SUMMARY.read_text(encoding="utf-8")

    forbidden = [
        "自动更新模型权重",
        "完全自主学习",
        "无边界POI实体对齐",
        "全球POI自动消歧已完成",
    ]
    for phrase in forbidden:
        assert phrase not in text

    assert "bounded policy hints only" in text
    assert "AOI-bounded OSM + GNS/GeoNames" in text
