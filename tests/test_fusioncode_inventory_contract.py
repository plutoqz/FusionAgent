from __future__ import annotations

from pathlib import Path


FUSIONCODE_ROOT = Path("E:/vscode/fusioncode")


def test_fusioncode_core_files_exist() -> None:
    expected = [
        "algorithm_adapter.py",
        "algorithm_core/main.py",
        "algorithm_core/models/matching_engine.py",
        "algorithm_core/models/temporal_validator.py",
        "algorithm_core/models/spatial_optimizer.py",
        "algorithm_core/models/post_conflict_shrink_refiner.py",
        "algorithm_core/models/obm_enricher.py",
        "algorithm_core/models/quality_assessor.py",
        "MapTileTool/FusionTool/road.py",
        "MapTileTool/FusionTool/river.py",
        "MapTileTool/FusionTool/lake.py",
        "MapTileTool/FusionTool/conflict.py",
        "MapTileTool/FusionPOI.py",
    ]
    missing = [rel for rel in expected if not (FUSIONCODE_ROOT / rel).exists()]
    assert missing == []


def test_fusioncode_entry_points_are_still_present() -> None:
    files_and_symbols = {
        "algorithm_adapter.py": ["def _parse_geometry_source_paths", "def run_full_pipeline"],
        "algorithm_core/models/matching_engine.py": [
            "class MatchConfig",
            "def generate_candidate_edges_v8",
            "def process_worker_v8",
            "def build_fusion_rows",
            "def execute_v8_fusion",
        ],
        "algorithm_core/models/temporal_validator.py": [
            "def validate_existence_parallel",
            "def extract_height_parallel",
        ],
        "algorithm_core/models/spatial_optimizer.py": [
            "class OptConfig",
            "def optimize_road_topology",
            "def build_constraint_graph",
            "def run_graph_optimization_v5",
            "def calculate_metrics",
        ],
        "MapTileTool/FusionTool/road.py": ["def process_road_fusion"],
        "MapTileTool/FusionTool/river.py": ["def perform_river_fusion"],
        "MapTileTool/FusionTool/lake.py": ["def process_lake_fusion"],
        "MapTileTool/FusionTool/conflict.py": ["def detect_conflicts"],
        "MapTileTool/FusionPOI.py": ["def PiPei"],
    }
    for rel, symbols in files_and_symbols.items():
        text = (FUSIONCODE_ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        for symbol in symbols:
            assert symbol in text, f"{symbol} missing from {rel}"
