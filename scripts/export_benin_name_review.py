from __future__ import annotations

import argparse
import re
import sqlite3
import time
from pathlib import Path

import pandas as pd


DEFAULT_INPUT_GPKG = Path(
    r"E:\fyx\data\Benin\final_shp\fusionbuildings\conflictresolution\final\fused_buildings_final_height.gpkg"
)
DEFAULT_OUTPUT_DIR = Path(r"E:\fyx\data\Benin\final_shp\fusionbuildings\conflictresolution\final")
DEFAULT_OUTPUT_CSV = "benin_building_name_review.csv"
DEFAULT_OUTPUT_TXT = "benin_building_name_review.txt"

NON_BUILDING_RULES: list[tuple[str, list[str], str, str]] = [
    ("围栏/边界", [r"cl[oô]ture", r"cemet", r"cimeti", r"fence", r"wall", r"gate", r"boundary"], "建议删除", "明显属于围栏、边界或门卫类非建筑对象"),
    ("卫生设施", [r"toilet", r"latrine", r"douche", r"bath"], "建议人工复核", "属于卫生附属设施，可能不是主体建筑"),
    ("停车/车库", [r"parking"], "建议删除", "明显属于停车场或停车区域，不应视作建筑物"),
    ("车库/附属用房", [r"garage"], "建议人工复核", "可能是附属用房，也可能是实际建筑，需要人工确认"),
    ("棚亭/附属小构筑物", [r"hangar", r"paillote", r"abris", r"abri", r"kiosk", r"shed", r"canopy"], "建议人工复核", "更像临时棚或附属小构筑物"),
    ("泵/井/罐设施", [r"pompe", r"well", r"tank", r"forage"], "建议删除", "更像点式设施或设备，不像建筑主体"),
    ("加工/附属设施", [r"s[ée]choir", r"local cuisson", r"scierie", r"buanderie", r"fabrication"], "建议人工复核", "更像生产附属设施，需结合几何和用途判断"),
]

BUILDING_KEEP_RULES: list[tuple[str, list[str], str]] = [
    ("门卫亭/岗亭", [r"guérite", r"guard house", r"gatehouse"], "可视作小型建筑物或附属建筑，按建筑保留"),
    ("宗教建筑", [r"\bbasilic", r"\bbasilique\b", r"\bchurch\b", r"\bmosqu", r"\bchapel", r"\btemple\b", r"église", r"eglise"], "明显是宗教建筑"),
    ("公共建筑", [r"\bmairie\b", r"h[ôo]tel de ville", r"\btribunal\b", r"\bambassade\b"], "明显是公共建筑"),
    ("教育建筑", [r"\bschool\b", r"\bcollege\b", r"\buniversity\b", r"\bamphi", r"amphith"], "明显是教育建筑"),
    ("医疗建筑", [r"\bclinique\b", r"h[ôo]pital", r"\blaboratoire\b"], "明显是医疗或科研建筑"),
]

MANUAL_TRANSLATIONS = {
    "clôture du cimetière": "墓地围栏",
    "abris famille, pédiatrie": "家属候棚（儿科）",
    "abris famille, réanimation": "家属候棚（重症监护）",
    "buanderie": "洗衣房",
    "douches et toilettes": "淋浴和厕所",
    "les latrines": "厕所",
    "guérite": "门卫亭",
    "hangar": "棚屋/简易棚",
    "local cuisson": "烹饪间",
    "paillote": "茅草棚",
    "parking moto": "摩托车停车场",
    "site pompe": "泵站点",
    "séchoir à riz de sina bouya": "Sina Bouya 稻谷晾晒场",
    "séchoir à riz de sinsinkou-tora": "Sinsinkou-Tora 稻谷晾晒场",
    "direction du garage central adminitratif du ministère des finances et de l'économie": "财政与经济部行政中央车库管理处",
    "fabrication de gari": "加里粉制作点",
    "scierie": "锯木厂/锯木作坊",
    "marché sèhi de bohicon": "博希孔塞伊市场",
    "dortoir": "宿舍",
    "dortoirs": "宿舍楼",
    "aluminum roof building": "铝皮屋顶建筑",
    "building near boboessa": "Boboessa 附近建筑",
    "marché arzeke de parakou": "帕拉库 Arzeke 市场",
    "centre yeteen": "Yeteen 中心",
    "aluminum roof building on dirt road": "土路旁铝皮屋顶建筑",
    "pédiatrie-néonatalogie": "儿科-新生儿科",
    "résidence e": "E 住宅",
    "hadj ali": "Hadj Ali",
    "iut lokossa": "洛科萨理工学院",
    "magasin": "商铺/仓库",
    "otammari lodge": "Otammari 旅馆",
    "quénum": "Quenum",
    "résidence b2": "B2 住宅",
    "hôtel bénin horizon": "贝宁地平线酒店",
    "place vodùn yedomin": "Yedomin 伏都场地",
    "sbee - société béninoise d'énergie électrique": "贝宁电力公司",
    "administration cous": "COUS 行政楼",
    "dortoir administration": "宿舍行政楼",
    "ecole le petit poucet - site 1": "小拇指学校 - 1号地块",
    "ecole le petit poucet - site 3": "小拇指学校 - 3号地块",
    "long wearhouse": "长条仓库",
    "résidence c2": "C2 住宅",
    "résidence e2": "E2 住宅",
    "terminal": "终端楼/候车楼",
    "warehouse": "仓库",
    "general building": "普通建筑",
    "hotel plm aledjo": "PLM Aledjo 酒店",
    "musée kaba": "Kaba 博物馆",
    "paillotte": "茅草棚",
    "résidence d": "D 住宅",
    "résidence d2": "D2 住宅",
    "résidence f2": "F2 住宅",
    "sanctuaire marial notre dame d'arigbo": "Arigbo 圣母朝圣地",
    "université nationale des sciences, technologies, ingénierie et mathématiques (unstim)": "贝宁国立科技工程与数学大学",
    "école primaire privée le flambeau de la réussite": "成功火炬私立小学",
    "akpaki": "Akpaki",
    "administration fsa": "FSA 行政楼",
    "building at agbantokpa": "Agbantokpa 建筑",
    "bâtiment a fsa": "FSA A楼",
    "bâtiment d epac": "EPAC D楼",
    "centre de formation p. bioret": "P. Bioret 培训中心",
    "centre de traitement anti lèpre": "麻风病治疗中心",
    "collège privé d'enseignement technique et professionel espoir plus": "希望加私立职业技术学院",
    "complexe scolaire womey enawa": "Womey Enawa 学校综合体",
    "cour d'appel": "上诉法院",
    "hospitalisation": "住院楼",
    "hélios": "Hélios",
    "maison johnson": "Johnson 住宅",
    "maison des jeunes": "青年之家",
    "odjoube j.": "Odjoube J.",
    "paroisse jésus eucharistie": "圣体耶稣堂区",
    "paroisse st. pierre et paul agla": "Agla 圣彼得圣保罗堂区",
    "programme national de lutte contre le sida (pnls)": "国家艾滋病防治项目楼",
}


def _log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def translate_name_to_chinese(name: str) -> str:
    normalized = _normalize_text(name)
    if normalized in MANUAL_TRANSLATIONS:
        return MANUAL_TRANSLATIONS[normalized]
    return ""


def classify_name_risk(name: str) -> tuple[str, str, str]:
    normalized = _normalize_text(name)
    for category, patterns, reason in BUILDING_KEEP_RULES:
        if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in patterns):
            return "主体建筑", "建议保留", reason
    for category, patterns, action, reason in NON_BUILDING_RULES:
        if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in patterns):
            return category, action, reason
    return "未分类", "待人工判断", "名称本身不足以判断，建议结合高度、面积和几何形态复核"


def load_named_records(input_gpkg: Path) -> pd.DataFrame:
    connection = sqlite3.connect(input_gpkg)
    try:
        query = """
        SELECT
            COALESCE(NULLIF(TRIM(name_fused),''), NULLIF(TRIM(name_candidates),'')) AS name,
            source_layer,
            height_conflict_3d_final,
            final_height
        FROM fused_buildings
        WHERE COALESCE(TRIM(name_fused),'')<>'' OR COALESCE(TRIM(name_candidates),'')<>''
        """
        frame = pd.read_sql_query(query, connection)
    finally:
        connection.close()
    return frame


def summarize_name_records(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for name, group in frame.groupby("name", dropna=True):
        category, action, reason = classify_name_risk(str(name))
        heights = pd.to_numeric(group["height_conflict_3d_final"], errors="coerce")
        finals = pd.to_numeric(group["final_height"], errors="coerce")
        rows.append(
            {
                "name": name,
                "name_zh": translate_name_to_chinese(str(name)),
                "record_count": int(len(group)),
                "source_layers": ",".join(sorted({str(value) for value in group["source_layer"].dropna() if str(value)})),
                "min_height_conflict_3d_final": None if heights.dropna().empty else round(float(heights.min()), 2),
                "max_height_conflict_3d_final": None if heights.dropna().empty else round(float(heights.max()), 2),
                "min_final_height": None if finals.dropna().empty else round(float(finals.min()), 2),
                "max_final_height": None if finals.dropna().empty else round(float(finals.max()), 2),
                "risk_category": category,
                "suggested_action": action,
                "reason": reason,
            }
        )
    output = pd.DataFrame(rows)
    sort_key = {"建议删除": 0, "建议人工复核": 1, "待人工判断": 2, "建议保留": 3}
    output["_sort"] = output["suggested_action"].map(sort_key).fillna(9)
    output = output.sort_values(
        ["_sort", "risk_category", "record_count", "name"],
        ascending=[True, True, False, True],
        kind="mergesort",
    ).drop(columns=["_sort"])
    return output.reset_index(drop=True)


def write_txt_summary(path: Path, summary: pd.DataFrame) -> None:
    lines = [
        "贝宁建筑名称人工审查清单",
        "=" * 72,
        "",
        f"唯一名称数量：{len(summary)}",
        f"建议删除数量：{int((summary['suggested_action'] == '建议删除').sum())}",
        f"建议人工复核数量：{int((summary['suggested_action'] == '建议人工复核').sum())}",
        f"待人工判断数量：{int((summary['suggested_action'] == '待人工判断').sum())}",
        f"建议保留数量：{int((summary['suggested_action'] == '建议保留').sum())}",
        "",
        "重点可疑名称：",
    ]
    suspicious = summary[summary["suggested_action"].isin(["建议删除", "建议人工复核"])].copy()
    for _, row in suspicious.iterrows():
        lines.append(
            f"- {row['name']} | 中文: {row['name_zh'] or '待补'} | 类别: {row['risk_category']} | 动作: {row['suggested_action']} | "
            f"数量: {row['record_count']} | 高度范围: {row['min_height_conflict_3d_final']} - {row['max_height_conflict_3d_final']} | 理由: {row['reason']}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Path]:
    named = load_named_records(args.input_gpkg)
    summary = summarize_name_records(named)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / args.output_csv
    txt_path = args.output_dir / args.output_txt
    summary.to_csv(csv_path, index=False, encoding="utf-8-sig")
    write_txt_summary(txt_path, summary)
    return {"csv": csv_path, "txt": txt_path}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Benin building name review sheets.")
    parser.add_argument("--input-gpkg", type=Path, default=DEFAULT_INPUT_GPKG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output-csv", default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--output-txt", default=DEFAULT_OUTPUT_TXT)
    return parser.parse_args()


def main() -> None:
    run(_parse_args())


if __name__ == "__main__":
    main()
