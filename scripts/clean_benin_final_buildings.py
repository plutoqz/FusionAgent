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
DEFAULT_OUTPUT_GPKG = "final_buildings.gpkg"
DEFAULT_OUTPUT_SHP = "final_buildings.shp"
DEFAULT_REPORT_TXT = "final_buildings_report.txt"
DEFAULT_NAME_REVIEW_CSV = "benin_name_nonbuilding_candidates_v2.csv"

HEIGHT_FLOOR_SOURCE_COLUMN = "height_conflict_3d_final"
HEIGHT_GPKG_SOURCE_FALLBACK = "height_raster_centroid"
HEIGHT_GPKG_TARGET_COLUMN = "final_height"
HEIGHT_SHP_SOURCE_FALLBACK = "height_r_2"
HEIGHT_SHP_TARGET_COLUMN = "final_heig"
HEIGHT_FLOOR_THRESHOLD = 2.5
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
    r"\bbuanderie\b",
    r"\blocal cuisson\b",
    r"\bs[ée]choir\b",
    r"\babris famille\b",
    r"\bpaillote\b",
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
    "fusion_source",
    "final_height",
]

LOW_HEIGHT_DELETE_NAMES = {
    "clôture du cimetière",
    "séchoir à riz de sinsinkou-tora",
}


@dataclass(frozen=True)
class CandidateNameRule:
    name: str
    name_zh: str
    suggested_action: str
    risk_category: str
    suggested_non_building_category: str
    reason: str


@dataclass(frozen=True)
class CandidateScoreResult:
    should_drop: bool
    delete_threshold: int
    total_points: int
    name_points: int
    height_points: int
    area_points: int
    shape_points: int
    area_penalty_points: int
    matched_rule_kind: str
    matched_name_signal: str


@dataclass(frozen=True)
class CandidateFeatureDecision:
    source_fid: int
    resolved_name: str
    raw_height: float | None
    area_m2: float | None
    aspect_ratio: float | None
    score: CandidateScoreResult


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


def _normalize_ascii_text(value: object) -> str:
    text = _normalize_text(value)
    return (
        text.replace("ô", "o")
        .replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("à", "a")
        .replace("ù", "u")
        .replace("û", "u")
        .replace("ï", "i")
        .replace("î", "i")
        .replace("ç", "c")
    )


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


def _classify_candidate_name_signal(name: str, rule: CandidateNameRule) -> tuple[int, str, str]:
    normalized = _normalize_ascii_text(name or rule.name)
    combined = " ".join(
        part
        for part in [
            normalized,
            _normalize_ascii_text(rule.risk_category),
            _normalize_ascii_text(rule.suggested_non_building_category),
            _normalize_ascii_text(rule.reason),
        ]
        if part
    )

    explicit_patterns = [
        r"\bcloture\b",
        r"\bcimeti",
        r"\bparking\b",
        r"\bsite pompe\b",
        r"\bpompe\b",
        r"\breservoir\b",
        r"\btank\b",
        r"\bforage\b",
        r"\bwell\b",
    ]
    open_shelter_patterns = [
        r"\bauvent\b",
        r"\babri",
        r"\bpaillot",
        r"\bapatam\b",
    ]
    service_patterns = [
        r"\bbuanderie\b",
        r"\blocal cuisson\b",
        r"\bsechoir\b",
        r"\bdouche",
        r"\btoilet",
        r"\blatrine",
    ]
    ambiguous_site_patterns = [
        r"\bplace\b",
        r"\bvodun\b",
        r"\bsite\b",
        r"\bexperimentation\b",
    ]

    if any(re.search(pattern, combined, flags=re.IGNORECASE) for pattern in explicit_patterns):
        return 6, "explicit_non_building", "明确非建筑名称"
    if any(re.search(pattern, combined, flags=re.IGNORECASE) for pattern in open_shelter_patterns):
        return 5, "open_shelter", "棚亭/开放式构筑物名称"
    if any(re.search(pattern, combined, flags=re.IGNORECASE) for pattern in service_patterns):
        return 3, "service_accessory", "附属服务设施名称"
    if any(re.search(pattern, combined, flags=re.IGNORECASE) for pattern in ambiguous_site_patterns):
        return 3, "ambiguous_site", "场地/地点名称"
    if rule.suggested_action == "建议删除":
        return 4, "explicit_non_building", "候选表已标注建议删除"
    if rule.suggested_action == "建议人工复核":
        return 3, "service_accessory", "候选表已标注建议人工复核"
    return 2, "candidate", "候选表待复核名称"


def score_candidate_non_building(
    *,
    name: str,
    rule: CandidateNameRule,
    raw_height: float | None,
    area_m2: float | None,
    aspect_ratio: float | None,
) -> CandidateScoreResult:
    name_points, rule_kind, signal = _classify_candidate_name_signal(name, rule)

    height_points = 0
    if raw_height is not None:
        if raw_height < 2.5:
            height_points = 3
        elif raw_height < 3.5:
            height_points = 2
        elif raw_height < 5.0:
            height_points = 1

    area_points = 0
    area_penalty_points = 0
    if area_m2 is not None:
        if area_m2 < 25:
            area_points = 3
        elif area_m2 < 80:
            area_points = 2
        elif area_m2 < 250:
            area_points = 1

        if rule_kind == "explicit_non_building" and area_m2 > 1000:
            area_penalty_points = 2
        elif rule_kind == "ambiguous_site" and area_m2 > 500:
            area_penalty_points = 1

    shape_points = 0
    if aspect_ratio is not None:
        if aspect_ratio > 5:
            shape_points = 2
        elif aspect_ratio > 3:
            shape_points = 1

    total_points = name_points + height_points + area_points + shape_points + area_penalty_points
    delete_threshold = 7
    return CandidateScoreResult(
        should_drop=total_points >= delete_threshold,
        delete_threshold=delete_threshold,
        total_points=total_points,
        name_points=name_points,
        height_points=height_points,
        area_points=area_points,
        shape_points=shape_points,
        area_penalty_points=area_penalty_points,
        matched_rule_kind=rule_kind,
        matched_name_signal=signal,
    )


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
    if numeric < HEIGHT_FLOOR_THRESHOLD:
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
        "buanderie",
        "local cuisson",
        "séchoir",
        "sechoir",
        "abris famille",
        "paillote",
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
        f"WHEN {resolved} < {HEIGHT_FLOOR_THRESHOLD} THEN {HEIGHT_EQUAL_VALUE} "
        f"ELSE ROUND({resolved}, 2) END"
    )


def _build_gpkg_sql(drop_fids: Iterable[int]) -> tuple[str, str]:
    keep_columns = [
        '"detail_side"',
        '"source_layer"',
        f"{_sqlite_round_expr('group_score')} AS \"group_score\"",
        '"src_flag"',
        '"name_fused"',
        '"name_candidates"',
        '"fusion_lineage"',
        '"fusion_source"',
        f"{_build_final_height_expr('height_conflict_3d_final', 'height_final')} AS \"final_height\"",
        '"geom"',
    ]
    drop_list = sorted(set(int(fid) for fid in drop_fids))
    if drop_list:
        fid_filter = ", ".join(str(fid) for fid in drop_list)
        where_clause = f"fid NOT IN ({fid_filter})"
    else:
        where_clause = "1=1"
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


def load_candidate_name_rules(path: Path) -> dict[str, CandidateNameRule]:
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path, encoding="utf-8-sig")
    rules: dict[str, CandidateNameRule] = {}
    for _, row in frame.iterrows():
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        normalized = _normalize_text(name)
        suggested_action = str(row.get("suggested_action") or "").strip()
        if normalized in LOW_HEIGHT_DELETE_NAMES:
            suggested_action = "建议删除"
        else:
            suggested_action = "恢复保留"
        rules[normalized] = CandidateNameRule(
            name=name,
            name_zh=str(row.get("name_zh") or "").strip(),
            suggested_action=suggested_action,
            risk_category=str(row.get("risk_category") or "").strip(),
            suggested_non_building_category=str(row.get("suggested_non_building_category_v2") or "").strip(),
            reason=str(row.get("reason") or "").strip(),
        )
    if not rules:
        raise ValueError(f"No candidate name rules found in {path}")
    return rules


def _sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _resolve_candidate_name(name_fused: object, name_candidates: object) -> str:
    primary = str(name_fused or "").strip()
    if primary:
        return primary
    return str(name_candidates or "").strip()


def _compute_aspect_ratio(minx: float, miny: float, maxx: float, maxy: float) -> float | None:
    width = maxx - minx
    height = maxy - miny
    min_side = min(width, height)
    max_side = max(width, height)
    if min_side <= 0:
        return None
    return max_side / min_side


def score_candidate_features_from_gpkg(
    input_path: Path,
    candidate_rules: dict[str, CandidateNameRule],
) -> list[CandidateFeatureDecision]:
    normalized_names = sorted(candidate_rules.keys())
    quoted_names = ", ".join(_sql_quote(name) for name in normalized_names)
    where = f"LOWER(TRIM(COALESCE(NULLIF(name_fused, ''), NULLIF(name_candidates, '')))) IN ({quoted_names})"
    frame = gpd.read_file(input_path, layer="fused_buildings", where=where, fid_as_index=True)
    decisions: list[CandidateFeatureDecision] = []
    for _, row in frame.iterrows():
        resolved_name = _resolve_candidate_name(row.get("name_fused"), row.get("name_candidates"))
        normalized = _normalize_text(resolved_name)
        rule = candidate_rules.get(normalized)
        if rule is None:
            continue
        raw_height = _safe_float(row.get("height_conflict_3d_final"))
        if rule.suggested_action != "建议删除":
            continue
        geometry = row.geometry
        area_m2 = _safe_float(getattr(geometry, "area", None))
        minx, miny, maxx, maxy = geometry.bounds
        aspect_ratio = _compute_aspect_ratio(minx, miny, maxx, maxy)
        score = score_candidate_non_building(
            name=resolved_name,
            rule=rule,
            raw_height=raw_height,
            area_m2=area_m2,
            aspect_ratio=aspect_ratio,
        )
        if raw_height is None or raw_height >= 2.5:
            score = CandidateScoreResult(
                should_drop=False,
                delete_threshold=score.delete_threshold,
                total_points=score.total_points,
                name_points=score.name_points,
                height_points=score.height_points,
                area_points=score.area_points,
                shape_points=score.shape_points,
                area_penalty_points=score.area_penalty_points,
                matched_rule_kind=score.matched_rule_kind,
                matched_name_signal=score.matched_name_signal,
            )
        decisions.append(
            CandidateFeatureDecision(
                source_fid=int(row.name),
                resolved_name=resolved_name,
                raw_height=raw_height,
                area_m2=area_m2,
                aspect_ratio=aspect_ratio,
                score=score,
            )
        )
    return decisions


def _candidate_decision_summary(
    decisions: Iterable[CandidateFeatureDecision],
    candidate_rules: dict[str, CandidateNameRule],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for decision in decisions:
        rule = candidate_rules.get(_normalize_text(decision.resolved_name))
        rows.append(
            {
                "name": decision.resolved_name,
                "name_zh": rule.name_zh if rule else "",
                "source_fid": decision.source_fid,
                "raw_height": decision.raw_height,
                "area_m2": decision.area_m2,
                "aspect_ratio": decision.aspect_ratio,
                "score": decision.score.total_points,
                "delete_threshold": decision.score.delete_threshold,
                "should_drop": decision.score.should_drop,
                "risk_category": rule.risk_category if rule else "",
                "non_building_category_zh": rule.suggested_non_building_category if rule else "",
                "rule_kind": decision.score.matched_rule_kind,
                "signal": decision.score.matched_name_signal,
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "name",
                "source_fid",
                "name_zh",
                "raw_height",
                "area_m2",
                "aspect_ratio",
                "score",
                "delete_threshold",
                "should_drop",
                "risk_category",
                "non_building_category_zh",
                "rule_kind",
                "signal",
            ]
        )
    return pd.DataFrame(rows)


def _apply_shp_cleaning(frame: gpd.GeoDataFrame, drop_fids: set[int]) -> tuple[gpd.GeoDataFrame, dict[str, int]]:
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

    fid_column = "fid" if "fid" in frame.columns else None
    drop_mask = pd.Series(False, index=frame.index)
    if fid_column is not None and drop_fids:
        drop_mask = pd.to_numeric(frame[fid_column], errors="coerce").isin(drop_fids)

    resolved_height = source_height.where(source_height.notna(), fallback_height)
    stats = {
        "input_count": int(len(frame)),
        "dropped_non_building": int(drop_mask.sum()),
        "floor_to_3": int(((resolved_height.notna()) & (resolved_height < HEIGHT_FLOOR_THRESHOLD) & (~drop_mask)).sum()),
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


def clean_gpkg(
    input_path: Path,
    output_path: Path,
    keep_fields: list[str],
    report: dict[str, object],
    drop_fids: set[int],
) -> Path:
    ogr2ogr = _find_ogr2ogr()
    if output_path.exists():
        output_path.unlink()

    sql, layer_name = _build_gpkg_sql(drop_fids)
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
            "gpkg_dropped_non_building": len(drop_fids),
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


def clean_shp(
    input_path: Path,
    output_path: Path,
    keep_fields: list[str],
    report: dict[str, object],
    drop_fids: set[int],
) -> Path:
    frame = gpd.read_file(input_path)
    if frame.crs is None:
        frame = frame.set_crs("EPSG:32631")

    frame, stats = _apply_shp_cleaning(frame, drop_fids)
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
        f"- 以 {HEIGHT_FLOOR_SOURCE_COLUMN} 作为最终高度来源；若该字段缺失，SHP 使用其自身的高度冲突字段回退。",
        f"- 仅小于 2.50m 的记录置为 3.00m。",
        f"- 原先被统一赋值 3.00m 的 2.50m 至 3.00m 建筑高度现恢复原值。",
        f"- 恰好等于 3.00m 的记录改为 3.01m，以区分原始 3m 与 floor 后 3m。",
        f"- 其余值保留并四舍五入到 2 位小数。",
        "",
        "名称清理：",
        f"- 仅对候选表 {report['name_review_csv']} 中的可疑名称对象做对象级复核打分。",
        "- 当前仅删除两类同时满足“名称为指定非建筑物且原始高度 < 2.5m”的对象：Clôture du cimetière、Séchoir à riz de Sinsinkou-Tora。",
        "- 其余此前疑似非建筑名称对象全部恢复保留。",
        "",
        "打分方法：",
        "- 本版结果不再按总分批量删除候选对象；下面的分值说明仅保留为候选名称复核背景。",
        "- 名称分：明确非建筑/设备/场地类记 6 分；棚亭/开放式构筑物类记 5 分；附属服务设施类记 3 分；模糊场地/地点类记 3 分；其余候选名记 2 分。",
        "- 原始高度分：height_conflict_3d_final < 2.5m 记 3 分；2.5m-3.5m 记 2 分；3.5m-5.0m 记 1 分；>= 5.0m 记 0 分。",
        "- 面积分：面积 < 25m² 记 3 分；25-80m² 记 2 分；80-250m² 记 1 分；>= 250m² 记 0 分。",
        "- 形态分：包围盒长宽比 > 5 记 2 分；> 3 记 1 分；其余记 0 分。",
        "- 大面积惩罚修正：明确非建筑类且面积 > 1000m² 加 2 分；模糊场地/地点类且面积 > 500m² 加 1 分。",
        "",
        "删除指标：",
        "- 本版仅删除 Clôture du cimetière 与 Séchoir à riz de Sinsinkou-Tora 两类对象中原始高度 < 2.5m 的记录。",
        "- 不再按总分 >= 7 的规则批量删除其他疑似非建筑名称对象。",
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
    candidate_summary = report.get("candidate_summary")
    if isinstance(candidate_summary, pd.DataFrame) and not candidate_summary.empty:
        lines.extend(
            [
                "",
                "候选名称删除明细：",
                f"- 候选对象总数: {len(candidate_summary)}",
                f"- 达到删除阈值对象数: {int(candidate_summary['should_drop'].sum())}",
            ]
        )
        grouped = (
            candidate_summary.groupby("name", dropna=False)
            .agg(
                name_zh=("name_zh", "first"),
                risk_category=("risk_category", "first"),
                non_building_category_zh=("non_building_category_zh", "first"),
                total=("name", "size"),
                dropped=("should_drop", "sum"),
                min_score=("score", "min"),
                max_score=("score", "max"),
            )
            .reset_index()
            .sort_values(["dropped", "name"], ascending=[False, True], kind="mergesort")
        )
        for _, row in grouped.iterrows():
            display_name = row["name"]
            if row["name_zh"]:
                display_name = f"{display_name}（{row['name_zh']}）"
            lines.append(
                f"- {display_name}: 类别={row['risk_category'] or '未分类'}；中文删除类别={row['non_building_category_zh'] or '未标注'}；"
                f"删除 {int(row['dropped'])}/{int(row['total'])} 条；分数范围 {int(row['min_score'])}-{int(row['max_score'])}。"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Path]:
    if not args.input_gpkg.exists():
        raise FileNotFoundError(args.input_gpkg)
    if not args.input_shp.exists():
        raise FileNotFoundError(args.input_shp)
    if not args.keep_docx.exists():
        raise FileNotFoundError(args.keep_docx)

    keep_fields = [field for field in extract_keep_fields_from_docx(args.keep_docx) if field in KEEP_FIELDS]
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    output_gpkg = output_dir / args.output_gpkg
    output_shp = output_dir / args.output_shp
    report_txt = output_dir / args.report_txt
    candidate_rules = load_candidate_name_rules(args.name_review_csv)
    candidate_decisions = score_candidate_features_from_gpkg(args.input_gpkg, candidate_rules)
    drop_fids = {decision.source_fid for decision in candidate_decisions if decision.score.should_drop}

    report: dict[str, object] = {
        "gpkg_input_path": str(args.input_gpkg),
        "gpkg_output_path": str(output_gpkg),
        "shp_input_path": str(args.input_shp),
        "shp_output_path": str(output_shp),
        "docx_path": str(args.keep_docx),
        "keep_fields": keep_fields,
        "name_review_csv": str(args.name_review_csv),
        "candidate_summary": _candidate_decision_summary(candidate_decisions, candidate_rules),
    }

    clean_gpkg(args.input_gpkg, output_gpkg, keep_fields, report, drop_fids)
    clean_shp(args.input_shp, output_shp, keep_fields, report, drop_fids)
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
    parser.add_argument("--name-review-csv", type=Path, default=DEFAULT_OUTPUT_DIR / DEFAULT_NAME_REVIEW_CSV)
    return parser.parse_args()


def main() -> None:
    run(_parse_args())


if __name__ == "__main__":
    main()
