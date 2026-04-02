from pathlib import Path
import zipfile

import pytest

from utils.shp_zip import ShapefileZipError, validate_zip_has_shapefile


def _make_zip(zip_path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)


def test_validate_zip_has_valid_shapefile(tmp_path: Path) -> None:
    zip_path = tmp_path / "ok.zip"
    _make_zip(
        zip_path,
        {
            "sample.shp": b"dummy-shp",
            "sample.shx": b"dummy-shx",
            "sample.dbf": b"dummy-dbf",
            "sample.prj": b"dummy-prj",
        },
    )

    shp_path = validate_zip_has_shapefile(zip_path, tmp_path / "extract")
    assert shp_path.name == "sample.shp"
    assert shp_path.exists()


def test_validate_zip_missing_parts(tmp_path: Path) -> None:
    zip_path = tmp_path / "bad.zip"
    _make_zip(
        zip_path,
        {
            "sample.shp": b"dummy-shp",
            "sample.dbf": b"dummy-dbf",
        },
    )

    with pytest.raises(ShapefileZipError):
        validate_zip_has_shapefile(zip_path, tmp_path / "extract_bad")

