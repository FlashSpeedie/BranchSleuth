import io
import zipfile
from pathlib import Path

import pytest

from app.services.archive_service import ArchiveValidationError, extract_zip_safely, validate_zip_archive


def make_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def write_zip(tmp_path: Path, entries: dict[str, bytes]) -> Path:
    p = tmp_path / "upload.zip"
    p.write_bytes(make_zip(entries))
    return p


def test_valid_zip_extracts(tmp_path):
    z = write_zip(tmp_path, {"pkg/__init__.py": "", "pkg/mod.py": "x = 1\n"})
    dest = tmp_path / "out"
    file_count, total = extract_zip_safely(z, dest)
    assert file_count == 2
    assert total == 6
    assert (dest / "pkg" / "mod.py").read_text() == "x = 1\n"


def test_path_traversal_rejected(tmp_path):
    z = write_zip(tmp_path, {"good.txt": b"ok", "../evil.txt": b"boom"})
    dest = tmp_path / "out"
    with pytest.raises(ArchiveValidationError, match="escapes|unsafe"):
        extract_zip_safely(z, dest)
    assert not (tmp_path / "evil.txt").exists()


def test_absolute_path_rejected(tmp_path):
    z = write_zip(tmp_path, {"/etc/evil.txt": b"boom"})
    with pytest.raises(ArchiveValidationError):
        extract_zip_safely(z, tmp_path / "out")


def test_zip_bomb_ratio_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.max_extracted_bytes", 10_000_000)
    big = b"A" * 5_000_000
    zip_path = tmp_path / "bomb.zip"
    zip_path.write_bytes(make_zip({f"f{i}.bin": big for i in range(4)}))
    with pytest.raises(ArchiveValidationError, match="expands beyond|ratio"):
        validate_zip_archive(zip_path)


def test_declared_size_limit_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.max_extracted_bytes", 1000)
    z = write_zip(tmp_path, {"big.bin": b"x" * 100_000})
    with pytest.raises(ArchiveValidationError):
        validate_zip_archive(z)


def test_empty_archive_rejected(tmp_path):
    z = write_zip(tmp_path, {})
    with pytest.raises(ArchiveValidationError):
        extract_zip_safely(z, tmp_path / "out")


def test_not_a_zip_rejected(tmp_path):
    p = tmp_path / "fake.zip"
    p.write_bytes(b"this is not a zip file")
    with pytest.raises(ArchiveValidationError, match="not a valid ZIP"):
        validate_zip_archive(p)


def test_too_many_files_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.max_repo_files", 3)
    z = write_zip(tmp_path, {f"f{i}.txt": b"x" for i in range(5)})
    with pytest.raises(ArchiveValidationError, match="files"):
        extract_zip_safely(z, tmp_path / "out")


def test_archive_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.max_upload_bytes", 100)
    z = write_zip(tmp_path, {"f.bin": b"x" * 1000})
    with pytest.raises(ArchiveValidationError, match="size limit"):
        validate_zip_archive(z)
