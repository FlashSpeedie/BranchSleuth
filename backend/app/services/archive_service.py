from __future__ import annotations

import os
import stat
import zipfile
from pathlib import Path

from app.config import settings


class ArchiveValidationError(ValueError):
    pass


MAX_MEMBER_COUNT = 50_000
MAX_TOTAL_RATIO = 200.0


def _safe_target(dest_root: Path, name: str) -> Path:
    if not name or name.startswith("/") or name[0] == "~":
        raise ArchiveValidationError(f"unsafe archive entry path: {name!r}")
    if ":" in name.split("/", 1)[0] and os.name == "nt" and len(name.split("/", 1)[0]) == 2:
        drive = name.split("/", 1)[0]
        if drive.rstrip(":").isalpha():
            raise ArchiveValidationError(f"absolute path in archive entry: {name!r}")
    candidate = (dest_root / name).resolve()
    root = dest_root.resolve()
    if candidate != root and root not in candidate.parents:
        raise ArchiveValidationError(f"archive entry escapes extraction directory: {name!r}")
    return candidate


def validate_zip_archive(zip_path: Path) -> int:
    size = zip_path.stat().st_size
    if size == 0:
        raise ArchiveValidationError("archive is empty")
    if size > settings.max_upload_bytes:
        raise ArchiveValidationError(f"archive exceeds size limit of {settings.max_upload_bytes} bytes")
    try:
        with zipfile.ZipFile(zip_path) as zf:
            infos = zf.infolist()
    except zipfile.BadZipFile as e:
        raise ArchiveValidationError(f"not a valid ZIP archive: {e}") from e
    if len(infos) > MAX_MEMBER_COUNT:
        raise ArchiveValidationError("archive contains too many entries")
    declared_total = 0
    top_dirs: set[str] = set()
    for info in infos:
        name = info.filename
        if info.flag_bits & 0x1:
            raise ArchiveValidationError(f"encrypted archive entry: {name!r}")
        if info.is_dir():
            continue
        parts = name.split("/")
        if not parts[0]:
            raise ArchiveValidationError(f"unsafe archive entry path: {name!r}")
        top_dirs.add(parts[0])
        declared_total += info.file_size
    if declared_total > settings.max_extracted_bytes:
        raise ArchiveValidationError(f"archive expands beyond {settings.max_extracted_bytes} bytes")
    if size > 0 and declared_total / size > MAX_TOTAL_RATIO:
        raise ArchiveValidationError("archive decompression ratio too high")
    return len(infos)


def extract_zip_safely(zip_path: Path, dest_root: Path) -> tuple[int, int]:
    validate_zip_archive(zip_path)
    dest_root.mkdir(parents=True, exist_ok=True)
    file_count = 0
    total_bytes = 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename
            target = _safe_target(dest_root, name)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if name.endswith("/"):
                continue
            file_count += 1
            if file_count > settings.max_repo_files:
                raise ArchiveValidationError(f"archive contains more than {settings.max_repo_files} files")
            total_bytes += info.file_size
            if total_bytes > settings.max_extracted_bytes:
                raise ArchiveValidationError("expanded archive exceeds size limit")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
            mode = target.stat().st_mode
            if mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
                os.chmod(target, mode & 0o777)
            if target.is_symlink():
                raise ArchiveValidationError(f"unexpected symlink: {name!r}")
    if file_count == 0:
        raise ArchiveValidationError("archive contains no files")
    return file_count, total_bytes
