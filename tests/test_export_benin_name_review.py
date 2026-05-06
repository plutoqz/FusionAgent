from __future__ import annotations

import pandas as pd

from scripts.export_benin_name_review import classify_name_risk, summarize_name_records


def test_classify_name_risk_marks_clear_non_building_names() -> None:
    category, action, reason = classify_name_risk("Clôture du cimetière")
    assert category == "围栏/边界"
    assert action == "建议删除"
    assert "非建筑" in reason


def test_classify_name_risk_keeps_clear_religious_building_names() -> None:
    category, action, reason = classify_name_risk("Basilique de l'Immaculée Conception")
    assert category == "主体建筑"
    assert action == "建议保留"
    assert "宗教建筑" in reason


def test_classify_name_risk_deletes_parking_and_keeps_guardhouse() -> None:
    category, action, _ = classify_name_risk("Parking Moto")
    assert category == "停车/车库"
    assert action == "建议删除"

    category, action, _ = classify_name_risk("Guérite")
    assert category == "主体建筑"
    assert action == "建议保留"


def test_summarize_name_records_aggregates_counts_and_height_range() -> None:
    frame = pd.DataFrame(
        [
            {"name": "Guérite", "source_layer": "OBM", "height_conflict_3d_final": 1.0, "final_height": 3.0},
            {"name": "Guérite", "source_layer": "GG", "height_conflict_3d_final": 4.5, "final_height": 4.5},
        ]
    )

    summary = summarize_name_records(frame)

    assert len(summary) == 1
    row = summary.iloc[0]
    assert row["name"] == "Guérite"
    assert row["record_count"] == 2
    assert row["source_layers"] == "GG,OBM"
    assert row["min_height_conflict_3d_final"] == 1.0
    assert row["max_height_conflict_3d_final"] == 4.5
