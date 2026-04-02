from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Dict, List, Set


REQUIRED_SHP_PARTS = {".shp", ".shx", ".dbf"}


class ShapefileZipError(ValueError):
    pass


def _is_path_safe(base_dir: Path, target_path: Path) -> bool:
    try:
        target_path.resolve().relative_to(base_dir.resolve())
        return True
    except Exception:  # noqa: BLE001
        return False


def safe_extract_zip(zip_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            member_name = member.filename
            normalized = member_name.replace("\\", "/")
            if normalized.startswith("/") or normalized.startswith("../") or "/../" in normalized:
                raise ShapefileZipError(f"Unsafe ZIP member path: {member_name}")

            target = output_dir / normalized
            if not _is_path_safe(output_dir, target):
                raise ShapefileZipError(f"ZIP member escapes output dir: {member_name}")

            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, target.open("wb") as dst:
                dst.write(src.read())


def _collect_shapefile_parts(root: Path) -> Dict[Path, Set[str]]:
    parts: Dict[Path, Set[str]] = {}
    for item in root.rglob("*"):
        if not item.is_file():
            continue
        suffix = item.suffix.lower()
        if suffix in {".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix", ".fix"}:
            base = item.with_suffix("")
            parts.setdefault(base, set()).add(suffix)
    return parts


def find_valid_shapefile(root: Path) -> Path:
    parts = _collect_shapefile_parts(root)
    valid_bases = [base for base, exts in parts.items() if REQUIRED_SHP_PARTS.issubset(exts)]
    if not valid_bases:
        raise ShapefileZipError(
            "No valid shapefile found. ZIP must contain .shp/.shx/.dbf for at least one layer."
        )
    # Deterministic selection for now: first lexicographical valid shapefile.
    selected = sorted(valid_bases)[0]
    return selected.with_suffix(".shp")


def validate_zip_has_shapefile(zip_path: Path, extract_dir: Path) -> Path:
    safe_extract_zip(zip_path, extract_dir)
    return find_valid_shapefile(extract_dir)


def collect_bundle_files(shp_path: Path) -> List[Path]:
    base = shp_path.with_suffix("")
    parent = shp_path.parent
    candidates = []
    for file in parent.iterdir():
        if not file.is_file():
            continue
        if file.with_suffix("") == base:
            candidates.append(file)
    return sorted(candidates)


def zip_shapefile_bundle(shp_path: Path, output_zip: Path) -> Path:
    files = collect_bundle_files(shp_path)
    if not files:
        raise FileNotFoundError(f"No shapefile bundle files found near: {shp_path}")

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in files:
            zf.write(file, arcname=file.name)
    return output_zip
