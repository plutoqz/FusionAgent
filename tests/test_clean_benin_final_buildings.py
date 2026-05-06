from __future__ import annotations

from pathlib import Path

from docx import Document

from scripts.clean_benin_final_buildings import (
    build_clean_final_height_series,
    build_final_height_value,
    extract_keep_fields_from_docx,
    shp_source_columns_for_keep_fields,
    should_drop_non_building_record,
)


def test_extract_keep_fields_from_docx_reads_list_in_order(tmp_path: Path) -> None:
    docx_path = tmp_path / "keep_fields.docx"
    doc = Document()
    doc.add_paragraph("01. detail_side")
    doc.add_paragraph("02. source_layer")
    doc.add_paragraph("03. group_score")
    doc.add_paragraph("04. src_flag")
    doc.add_paragraph("05. name_fused")
    doc.add_paragraph("06. name_candidates")
    doc.add_paragraph("07. fusion_lineage")
    doc.add_paragraph("08. height_final")
    doc.add_paragraph("09. height_final_source")
    doc.add_paragraph("10. fusion_source")
    doc.add_paragraph("11. final_height")
    doc.save(docx_path)

    assert extract_keep_fields_from_docx(docx_path) == [
        "detail_side",
        "source_layer",
        "group_score",
        "src_flag",
        "name_fused",
        "name_candidates",
        "fusion_lineage",
        "height_final",
        "height_final_source",
        "fusion_source",
        "final_height",
    ]


def test_non_building_record_rule_matches_clear_false_positives() -> None:
    assert should_drop_non_building_record("Clôture du cimetière", 1.5)
    assert should_drop_non_building_record("Parking Moto", 2.0)
    assert should_drop_non_building_record("Site Pompe", 0.5)
    assert should_drop_non_building_record("Funerarium Les anges", 0.5)
    assert should_drop_non_building_record("Place vodùn Yedomin", 1.0)
    assert not should_drop_non_building_record("Mairie de Ouidah", 1.5)
    assert not should_drop_non_building_record("Basilique de l'Immaculée Conception", 1.5)
    assert not should_drop_non_building_record("Guérite", 1.0)
    assert not should_drop_non_building_record("Scierie", 1.5)
    assert not should_drop_non_building_record("Dortoir", 1.5)
    assert not should_drop_non_building_record("Marché Arzeke de Parakou", 1.5)


def test_final_height_rule_distinguishes_floor_and_exact_three() -> None:
    assert build_final_height_value(2.4) == 3.0
    assert build_final_height_value(3.0) == 3.01
    assert build_final_height_value(8.234) == 8.23


def test_clean_final_height_series_falls_back_to_existing_final_height() -> None:
    result = build_clean_final_height_series(
        source_values=[None, 2.5, 3.0, 7.126],
        existing_final_values=[3.0, 3.0, 3.0, 9.0],
    )
    assert result.tolist() == [3.01, 3.0, 3.01, 7.13]


def test_clean_final_height_series_floors_fallback_values_too() -> None:
    result = build_clean_final_height_series(
        source_values=[None, None, None],
        existing_final_values=[2.2, 3.0, 6.666],
    )
    assert result.tolist() == [3.0, 3.01, 6.67]


def test_shp_source_columns_for_keep_fields_maps_truncated_names() -> None:
    columns = [
        "detail_sid",
        "source_lay",
        "group_scor",
        "src_flag",
        "name_fused",
        "name_candi",
        "fusion_lin",
        "height_fin",
        "height_f_1",
        "fusion_sou",
        "final_heig",
    ]
    assert shp_source_columns_for_keep_fields(columns) == {
        "detail_side": "detail_sid",
        "source_layer": "source_lay",
        "group_score": "group_scor",
        "src_flag": "src_flag",
        "name_fused": "name_fused",
        "name_candidates": "name_candi",
        "fusion_lineage": "fusion_lin",
        "height_final": "height_fin",
        "height_final_source": "height_f_1",
        "fusion_source": "fusion_sou",
        "final_height": "final_heig",
    }
