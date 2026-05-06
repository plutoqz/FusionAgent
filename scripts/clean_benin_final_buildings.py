from __future__ import annotations

import argparse
import math
import re
import shutil
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import numpy as np
import pandas as pd
from docx import Document
from pyogrio import read_info


DEFAULT_INPUT_GPKG = Path(
    r"E:\fyx\data\Benin\final_shp\fusionbuildings\conflictresolution\final\fused_buildings_final_height.gpkg"
)
DEFAULT_INPUT_SHP = Path(r"E:\fyx\data\Benin\final_shp\fusionbuildings\conflictresolution\final\cut.shp")
DEFAULT_KEEP_DOCX = Path(r"E:\fyx\data\Benin\拟保留 数据列 及问题.docx")
DEFAULT_OUTPUT_DIR = Path(r"E:\fyx\data\Benin\final_shp\fusionbuildings\conflictresolution\final")
DEFAULT_OUTPUT_GPKG = "fused_buildings_final_height_cleaned.gpkg"
DEFAULT_OUTPUT_SHP = "cut_cleaned.shp"
DEFAULT_REPORT_TXT = "final_fields_cleaning_report.txt"

HEIGHT_FLOOR_SOURCE_COLUMN = "height_conflict_3d_final"
HEIGHT_GPKG_SOURCE_FALLBACK = "height_raster_centroid"
HEIGHT_GPKG_TARGET_COLUMN = "final_height"
HEIGHT_SHP_SOURCE_FALLBACK = "height_r_2"
HEIGHT_SHP_TARGET_COLUMN = "final_heig"
HEIGHT_EQUAL_VALUE = 3.0
HEIGHT_EXACT_THREE_REMAP = 3.01
NUMERIC_ROUND_COLUMNS = {
    "group_score",
    "wzp_score",
    "avg_prob",
    "core_score",
    "core_avg_prob",
    "core_p90_prob",
    "core_max_prob",
    "core_px_count",
    "core_support_ratio",
    "raster_cell_m",
    "height_ms",
    "height_obm",
    "height_google",
    "height_osm",
    "height_vector_fused",
    "height_final",
    "height_raster_max",
    "height_raster_min",
    "height_raster_centroid",
    "height_raster_dominant",
    "conflict_area_removed",
    "conflict_shift_m",
    "height_conflict_final",
    "confidence",
    "height_3d_globfp",
    "height_3d_match_distance_m",
    "height_conflict_3d_final",
    "final_height",
}

NON_BUILDING_PATTERNS = [
    r"\bcl[oô]ture\b",
    r"\bcimeti[èe]re\b",
    r"\bcemetery\b",
    r"\bgraveyard\b",
    r"\bfunerarium\b",
    r"\bfence\b",
    r"\bwall\b",
    r"\bparking\b",
    r"\bsite pompe\b",
    r"\bpompe\b",
    r"\bplace\b",
    r"\bvod[ùu]n\b",
    r"\bwell\b",
    r"\btank\b",
    r"\bforage\b",
]

ALLOWED_HUMAN_PLACE_PATTERNS = [
    r"\bchurch\b",
    r"\bmosqu[éee]\b",
    r"\bcathedral\b",
    r"\bchapel\b",
    r"\bbasilic",
    r"\btemple\b",
    r"\bmairie\b",
    r"\bh[ôo]tel de ville\b",
    r"\bclinic\b",
    r"\bhopital\b",
    r"\bh[ôo]pital\b",
    r"\bschool\b",
    r"\bcollege\b",
    r"\buniversity\b",
    r"\btribunal\b",
    r"\bmarket\b",
]

KEEP_FIELDS = [
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


def _log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def _find_ogr2ogr() -> str:
    candidates = [
        shutil.which("ogr2ogr"),
        r"D:\Softwares\Anaconda3\Library\bin\ogr2ogr.exe",
        r"C:\Program Files\QGIS 3.40.11\bin\ogr2ogr.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise FileNotFoundError("Cannot find ogr2ogr executable.")


def _find_ogrinfo() -> str:
    candidates = [
        shutil.which("ogrinfo"),
        r"D:\Softwares\Anaconda3\Library\bin\ogrinfo.exe",
        r"C:\Program Files\QGIS 3.40.11\bin\ogrinfo.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise FileNotFoundError("Cannot find ogrinfo executable.")


def _quote_sql(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _safe_float(value: object) -> float | None:
    try:
        numeric = float(value)
    except Exception:  # noqa: BLE001
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def extract_keep_fields_from_docx(path: Path) -> list[str]:
    document = Document(path)
    ordered: list[str] = []
    seen: set[str] = set()
    pattern = re.compile(r"^\s*\d+\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*$")
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        match = pattern.match(text)
        if not match:
            continue
        field = match.group(1)
        if field not in seen and field in KEEP_FIELDS:
            ordered.append(field)
            seen.add(field)
    if not ordered:
        raise ValueError(f"No keep fields found in docx: {path}")
    return ordered


def _text_is_non_building(name: str) -> bool:
    if not name:
        return False
    lowered = _normalize_text(name)
    if not lowered:
        return False
    if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in ALLOWED_HUMAN_PLACE_PATTERNS):
        return False
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in NON_BUILDING_PATTERNS)


def should_drop_non_building_record(name: str | None, source_height: float | None) -> bool:
    if not name:
        return False
    if source_height is None or source_height >= 2.5:
        return False
    return _text_is_non_building(name)


def build_final_height_value(value: object) -> float | None:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    if abs(numeric - HEIGHT_EQUAL_VALUE) < 1e-9:
        return HEIGHT_EXACT_THREE_REMAP
    if numeric < HEIGHT_EQUAL_VALUE:
        return HEIGHT_EQUAL_VALUE
    return round(numeric, 2)


def build_clean_final_height_series(
    *,
    source_values: Iterable[object],
    existing_final_values: Iterable[object],
) -> pd.Series:
    source = pd.to_numeric(pd.Series(list(source_values)), errors="coerce")
    existing = pd.to_numeric(pd.Series(list(existing_final_values)), errors="coerce")
    resolved = source.where(source.notna(), existing)
    return resolved.apply(build_final_height_value)


def _column_exists(connection: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info('{table_name}')").fetchall()
    return any(row[1] == column_name for row in rows)


def _count_rows(connection: sqlite3.Connection, table_name: str, where_sql: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM '{table_name}' WHERE {where_sql}").fetchone()[0])


def _build_drop_sql_expression(columns: Iterable[str]) -> str:
    clauses = [f'LOWER(COALESCE("{column}", \'\'))' for column in columns]
    return " || ' ' || ".join(clauses)


def _non_building_name_patterns() -> list[str]:
    return [
        "cloture",
        "clôture",
        "cimetiere",
        "cimetière",
        "cemetery",
        "graveyard",
        "funerarium",
        "parking",
        "site pompe",
        "pompe",
        "place",
        "vodùn",
        "vodun",
        "well",
        "tank",
        "forage",
    ]


def _build_non_building_filter_sql(name_columns: Iterable[str], height_column: str, *, threshold: float = 2.5) -> str:
    name_expr = _build_drop_sql_expression(name_columns)
    patterns = _non_building_name_patterns()
    conditions = " OR ".join([f"{name_expr} LIKE '%{pattern}%'" for pattern in patterns])
    return f"({height_column} IS NOT NULL AND {height_column} < {threshold} AND ({conditions}))"


def _sqlite_round_expr(column: str, places: int = 2) -> str:
    return f"ROUND({column}, {places})"


def _build_final_height_expr(source_column: str, fallback_column: str) -> str:
    resolved = f"COALESCE({source_column}, {fallback_column})"
    return (
        f"CASE WHEN {resolved} IS NULL THEN NULL "
        f"WHEN ABS({resolved} - {HEIGHT_EQUAL_VALUE}) < 1e-9 THEN {HEIGHT_EXACT_THREE_REMAP} "
        f"WHEN {resolved} < {HEIGHT_EQUAL_VALUE} THEN {HEIGHT_EQUAL_VALUE} "
        f"ELSE ROUND({resolved}, 2) END"
    )


def _build_gpkg_sql() -> tuple[str, str]:
    keep_columns = [
        '"detail_side"',
        '"source_layer"',
        f"{_sqlite_round_expr('group_score')} AS \"group_score\"",
        '"src_flag"',
        '"name_fused"',
        '"name_candidates"',
        '"fusion_lineage"',
        f"{_sqlite_round_expr('height_final')} AS \"height_final\"",
        '"height_final_source"',
        '"fusion_source"',
        f"{_build_final_height_expr('height_conflict_3d_final', 'height_final')} AS \"final_height\"",
        '"geom"',
    ]
    where_clause = f"NOT {_build_non_building_filter_sql(['name_fused', 'name_candidates'], 'height_conflict_3d_final')}"
    sql = f"SELECT {', '.join(keep_columns)} FROM fused_buildings WHERE {where_clause}"
    return sql, "fused_buildings"


def _gpkg_counts(path: Path, layer_name: str, where_sql: str) -> int:
    ogrinfo = _find_ogrinfo()
    result = subprocess.run(
        [ogrinfo, str(path), "-ro", "-q", "-dialect", "SQLite", "-sql", f"SELECT COUNT(*) AS c FROM {layer_name} WHERE {where_sql}"],
        check=True,
        capture_output=True,
        text=True,
    )
    match = re.search(r"c \(Integer\) = (\d+)", result.stdout)
    if not match:
        raise ValueError(f"Unable to parse count from ogrinfo output: {result.stdout}")
    return int(match.group(1))


def _shp_output_fields() -> dict[str, str]:
    return {
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


def shp_source_columns_for_keep_fields(columns: Iterable[str]) -> dict[str, str]:
    source_columns = list(columns)
    lookup = {column.lower(): column for column in source_columns}
    alias_map = {
        "detail_side": ["detail_side", "detail_sid"],
        "source_layer": ["source_layer", "source_lay"],
        "group_score": ["group_score", "group_scor"],
        "src_flag": ["src_flag"],
        "name_fused": ["name_fused"],
        "name_candidates": ["name_candidates", "name_candi"],
        "fusion_lineage": ["fusion_lineage", "fusion_lin"],
        "height_final": ["height_final", "height_fin"],
        "height_final_source": ["height_final_source", "height_f_1"],
        "fusion_source": ["fusion_source", "fusion_sou"],
        "final_height": ["final_height", "final_heig"],
    }
    mapping: dict[str, str] = {}
    for canonical, aliases in alias_map.items():
        for alias in aliases:
            if alias.lower() in lookup:
                mapping[canonical] = lookup[alias.lower()]
                break
    return mapping


def _detect_shp_source_columns(columns: Iterable[str]) -> tuple[str, str]:
    column_set = set(columns)
    source_height = "height_c_1" if "height_c_1" in column_set else next(
        (col for col in columns if col.lower().startswith("height_c")),
        None,
    )
    if source_height is None:
        raise ValueError("Cannot detect height_conflict_3d_final column in cut.shp")
    return source_height, "name_fused" if "name_fused" in column_set else "name_candi"


def _apply_shp_cleaning(frame: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict[str, int]]:
    source_height_column, name_primary_column = _detect_shp_source_columns(frame.columns)
    fallback_height_column = "height_fin" if "height_fin" in frame.columns else None
    if fallback_height_column is None:
        fallback_height_column = next((col for col in frame.columns if col.startswith("height_") and col != "final_heig"), None)
    if fallback_height_column is None:
        raise ValueError("Cannot detect fallback height column in cut.shp")

    source_height = pd.to_numeric(frame[source_height_column], errors="coerce")
    fallback_height = pd.to_numeric(frame[fallback_height_column], errors="coerce")
    final_height = build_clean_final_height_series(
        source_values=source_height,
        existing_final_values=fallback_height,
    )
    frame = frame.copy()
    frame["final_heig"] = final_height
    frame["height_fin"] = pd.to_numeric(frame["height_fin"], errors="coerce").round(2)
    if "height_f_1" in frame.columns:
        frame["height_f_1"] = frame["height_f_1"]
    if "group_scor" in frame.columns:
        frame["group_scor"] = pd.to_numeric(frame["group_scor"], errors="coerce").round(2)

    drop_mask = pd.Series(False, index=frame.index)
    for idx in frame.index:
        name = str(frame.at[idx, name_primary_column] or "")
        if not name and "name_candi" in frame.columns:
            name = str(frame.at[idx, "name_candi"] or "")
        if should_drop_non_building_record(name, _safe_float(source_height.loc[idx])):
            drop_mask.at[idx] = True

    resolved_height = source_height.where(source_height.notna(), fallback_height)
    stats = {
        "input_count": int(len(frame)),
        "dropped_non_building": int(drop_mask.sum()),
        "floor_to_3": int(((resolved_height.notna()) & (resolved_height < HEIGHT_EQUAL_VALUE) & (~drop_mask)).sum()),
        "exact_three_to_3_01": int(((resolved_height.notna()) & (abs(resolved_height - HEIGHT_EQUAL_VALUE) < 1e-9) & (~drop_mask)).sum()),
    }
    if stats["dropped_non_building"]:
        frame = frame.loc[~drop_mask].copy()

    source_map = shp_source_columns_for_keep_fields(frame.columns)
    keep_columns = [source_map[key] for key in KEEP_FIELDS if key in source_map]
    if "geometry" not in frame.columns:
        raise ValueError("Missing geometry in cut.shp")
    reverse_rename = {source_map[key]: _shp_output_fields()[key] for key in KEEP_FIELDS if key in source_map}
    frame = frame[keep_columns + ["geometry"]].rename(columns=reverse_rename)
    frame = _round_numeric_columns(frame)
    return frame, stats


def _round_numeric_columns(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    output = frame.copy()
    for column in NUMERIC_ROUND_COLUMNS:
        if column in output.columns:
            output[column] = pd.to_numeric(output[column], errors="coerce").round(2)
    return output


def _retain_columns(frame: gpd.GeoDataFrame, keep_fields: list[str]) -> gpd.GeoDataFrame:
    columns = [column for column in keep_fields if column in frame.columns]
    if "geometry" not in frame.columns:
        raise ValueError("Geometry column missing")
    columns.append("geometry")
    return frame[columns].copy()


def _update_final_height(frame: gpd.GeoDataFrame, source_column: str, target_column: str) -> tuple[gpd.GeoDataFrame, int, int]:
    output = frame.copy()
    source = pd.to_numeric(output[source_column], errors="coerce")
    target = pd.to_numeric(output[target_column], errors="coerce")
    fill_mask = target.isna() & source.notna()
    source_values = source.where(fill_mask)
    final_values = source_values.apply(build_final_height_value)
    output.loc[fill_mask, target_column] = final_values[fill_mask]
    output[target_column] = pd.to_numeric(output[target_column], errors="coerce")
    exact_three_to_3_01 = int((fill_mask & (source == HEIGHT_EQUAL_VALUE)).sum())
    floor_to_3 = int((fill_mask & source.notna() & (source < HEIGHT_EQUAL_VALUE)).sum())
    return output, floor_to_3, exact_three_to_3_01


def clean_gpkg(input_path: Path, output_path: Path, keep_fields: list[str], report: dict[str, object]) -> Path:
    ogr2ogr = _find_ogr2ogr()
    if output_path.exists():
        output_path.unlink()

    sql, layer_name = _build_gpkg_sql()
    _log("writing cleaned GPKG with ogr2ogr")
    subprocess.run(
        [
            ogr2ogr,
            "-f",
            "GPKG",
            str(output_path),
            str(input_path),
            layer_name,
            "-nln",
            "fused_buildings",
            "-dialect",
            "SQLite",
            "-sql",
            sql,
        ],
        check=True,
    )

    report.update(
        {
            "gpkg_input_count": read_info(input_path, layer="fused_buildings")["features"],
            "gpkg_output_count": read_info(output_path, layer="fused_buildings")["features"],
            "gpkg_dropped_non_building": _gpkg_counts(
                input_path,
                "fused_buildings",
                _build_non_building_filter_sql(["name_fused", "name_candidates"], "height_conflict_3d_final"),
            ),
            "gpkg_floor_to_3": _gpkg_counts(
                output_path,
                "fused_buildings",
                f"ABS(final_height - {HEIGHT_EQUAL_VALUE}) < 1e-9",
            ),
            "gpkg_exact_three_to_3_01": _gpkg_counts(
                output_path,
                "fused_buildings",
                f"ABS(final_height - {HEIGHT_EXACT_THREE_REMAP}) < 1e-9",
            ),
        }
    )
    return output_path


def clean_shp(input_path: Path, output_path: Path, keep_fields: list[str], report: dict[str, object]) -> Path:
    frame = gpd.read_file(input_path)
    if frame.crs is None:
        frame = frame.set_crs("EPSG:32631")

    frame, stats = _apply_shp_cleaning(frame)
    if output_path.exists():
        for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg", ".qpj", ".shp.xml"):
            candidate = output_path.with_suffix(suffix)
            candidate.unlink(missing_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(output_path, driver="ESRI Shapefile")
    report.update(
        {
            "shp_input_count": stats["input_count"],
            "shp_output_count": len(frame),
            "shp_dropped_non_building": stats["dropped_non_building"],
            "shp_floor_to_3": stats["floor_to_3"],
            "shp_exact_three_to_3_01": stats["exact_three_to_3_01"],
        }
    )
    return output_path


def write_report(path: Path, report: dict[str, object]) -> None:
    lines = [
        "贝宁最终字段精简与高度语义修订报告",
        "=" * 72,
        "",
        "处理范围：",
        f"- GPKG: {report['gpkg_input_path']} -> {report['gpkg_output_path']}",
        f"- SHP: {report['shp_input_path']} -> {report['shp_output_path']}",
        f"- 字段保留依据: {report['docx_path']}",
        "",
        "保留字段：",
        "- " + ", ".join(report["keep_fields"]),
        "",
        "高度规则：",
        f"- 以 {HEIGHT_FLOOR_SOURCE_COLUMN} 作为 3m 语义修订来源；若该字段缺失，SHP 使用其自身的高度冲突字段回退。",
        f"- 小于 3.00m 置为 3.00m。",
        f"- 恰好等于 3.00m 的记录改为 3.01m，以区分原始 3m 与 floor 后 3m。",
        f"- 其余值保留并四舍五入到 2 位小数。",
        "",
        "名称清理：",
        "- 基于非建筑词典和模式识别清理 OSM/名称字段中的非建筑对象。",
        "- 命中且原高度 < 2.5m 的记录已删除。",
        "",
        "统计：",
        f"- GPKG 输入: {report.get('gpkg_input_count', 0)}",
        f"- GPKG 输出: {report.get('gpkg_output_count', 0)}",
        f"- GPKG 删除非建筑名: {report.get('gpkg_dropped_non_building', 0)}",
        f"- GPKG floor 到 3.00m: {report.get('gpkg_floor_to_3', 0)}",
        f"- GPKG 原始 3.00m -> 3.01m: {report.get('gpkg_exact_three_to_3_01', 0)}",
        f"- SHP 输入: {report.get('shp_input_count', 0)}",
        f"- SHP 输出: {report.get('shp_output_count', 0)}",
        f"- SHP 删除非建筑名: {report.get('shp_dropped_non_building', 0)}",
        f"- SHP floor 到 3.00m: {report.get('shp_floor_to_3', 0)}",
        f"- SHP 原始 3.00m -> 3.01m: {report.get('shp_exact_three_to_3_01', 0)}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Path]:
    if not args.input_gpkg.exists():
        raise FileNotFoundError(args.input_gpkg)
    if not args.input_shp.exists():
        raise FileNotFoundError(args.input_shp)
    if not args.keep_docx.exists():
        raise FileNotFoundError(args.keep_docx)

    keep_fields = extract_keep_fields_from_docx(args.keep_docx)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    output_gpkg = output_dir / args.output_gpkg
    output_shp = output_dir / args.output_shp
    report_txt = output_dir / args.report_txt

    report: dict[str, object] = {
        "gpkg_input_path": str(args.input_gpkg),
        "gpkg_output_path": str(output_gpkg),
        "shp_input_path": str(args.input_shp),
        "shp_output_path": str(output_shp),
        "docx_path": str(args.keep_docx),
        "keep_fields": keep_fields,
    }

    clean_gpkg(args.input_gpkg, output_gpkg, keep_fields, report)
    clean_shp(args.input_shp, output_shp, keep_fields, report)
    write_report(report_txt, report)
    return {"gpkg": output_gpkg, "shp": output_shp, "report": report_txt}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean Benin final building outputs.")
    parser.add_argument("--input-gpkg", type=Path, default=DEFAULT_INPUT_GPKG)
    parser.add_argument("--input-shp", type=Path, default=DEFAULT_INPUT_SHP)
    parser.add_argument("--keep-docx", type=Path, default=DEFAULT_KEEP_DOCX)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output-gpkg", default=DEFAULT_OUTPUT_GPKG)
    parser.add_argument("--output-shp", default=DEFAULT_OUTPUT_SHP)
    parser.add_argument("--report-txt", default=DEFAULT_REPORT_TXT)
    return parser.parse_args()


def main() -> None:
    run(_parse_args())


if __name__ == "__main__":
    main()
