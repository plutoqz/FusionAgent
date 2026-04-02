from pathlib import Path
import zipfile

import pytest

from utils.shp_zip import ShapefileZipError, validate_zip_has_shapefile


def test_validate_zip_rejects_path_traversal(tmp_path: Path) -> None:
    zip_path = tmp_path / "bad_traversal.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("../evil.shp", b"dummy")
        zf.writestr("../evil.shx", b"dummy")
        zf.writestr("../evil.dbf", b"dummy")

    with pytest.raises(ShapefileZipError):
        validate_zip_has_shapefile(zip_path, tmp_path / "extract")

