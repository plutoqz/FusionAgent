from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from pathlib import Path
import sys
from types import ModuleType


DEFAULT_FUSIONCODE_ROOT = Path("E:/vscode/fusioncode")


@dataclass(frozen=True)
class FusionCodeModules:
    root: Path
    matching_engine: ModuleType
    temporal_validator: ModuleType
    spatial_optimizer: ModuleType
    post_conflict_shrink_refiner: ModuleType | None = None
    obm_enricher: ModuleType | None = None
    quality_assessor: ModuleType | None = None


def fusioncode_root() -> Path:
    return Path(os.getenv("FUSIONCODE_ROOT", str(DEFAULT_FUSIONCODE_ROOT))).resolve()


def _ensure_paths(root: Path) -> None:
    paths = [
        root,
        root / "algorithm_core",
        root / "algorithm_core" / "models",
        root / "MapTileTool",
        root / "MapTileTool" / "FusionTool",
    ]
    for path in paths:
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)


def load_module(module_name: str) -> ModuleType:
    root = fusioncode_root()
    _ensure_paths(root)
    return importlib.import_module(module_name)


def load_optional_module(module_name: str) -> ModuleType | None:
    try:
        return load_module(module_name)
    except Exception:  # noqa: BLE001
        return None


def load_fusioncode_modules() -> FusionCodeModules:
    root = fusioncode_root()
    _ensure_paths(root)
    return FusionCodeModules(
        root=root,
        matching_engine=importlib.import_module("matching_engine"),
        temporal_validator=importlib.import_module("temporal_validator"),
        spatial_optimizer=importlib.import_module("spatial_optimizer"),
        post_conflict_shrink_refiner=load_optional_module("post_conflict_shrink_refiner"),
        obm_enricher=load_optional_module("obm_enricher"),
        quality_assessor=load_optional_module("quality_assessor"),
    )
