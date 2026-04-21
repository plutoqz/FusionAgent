from services.scenario_report_service import render_scenario_reports


def test_render_scenario_reports_writes_chinese_and_english_markdown(tmp_path):
    summary = _make_scenario_summary_with_kg_trace_workflow_trace_and_metrics()

    output = render_scenario_reports(summary=summary, documents_dir=tmp_path)

    zh = (tmp_path / "scenario_report.zh.md").read_text(encoding="utf-8")
    en = (tmp_path / "scenario_report.en.md").read_text(encoding="utf-8")
    assert output["zh"].endswith("scenario_report.zh.md")
    assert output["en"].endswith("scenario_report.en.md")
    assert "知识图谱关系链" in zh
    assert "KG Relationship Chain" in en
    assert "智能体评价指标" in zh
    assert "Agentic Evaluation Metrics" in en
    assert "自进化证据" in zh
    assert "Self-Evolution Evidence" in en


def _make_scenario_summary_with_kg_trace_workflow_trace_and_metrics():
    return {
        "scenario_name": "Parakou earthquake",
        "kg_path_traces": [{"chains": [{"nodes": [], "edges": []}]}],
        "workflow_traces": [{"steps": [{"step_name": "aoi_resolved", "status": "succeeded"}]}],
        "source_coverage": [],
        "evaluation": {
            "data_fusion_metrics": [],
            "agentic_metrics": {"manual_intervention_count": 0},
            "self_evolution": {"hint_available": False},
        },
        "final_outputs": [],
    }
