from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from types import ModuleType


@lru_cache(maxsize=16)
def load_legacy_module(module_name: str, file_path: str) -> ModuleType:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Legacy algorithm file not found: {file_path}")

    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module spec from {file_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

