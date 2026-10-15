from __future__ import annotations

import difflib
from pathlib import Path

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".hypothesis", ".pytest_cache"}


def _walk_files(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        rel = path.relative_to(root).as_posix()
        files[rel] = path.read_bytes()
    return files


def _is_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def snapshot_unified_diff(baseline_dir: Path, modified_dir: Path) -> str:
    old_files = _walk_files(baseline_dir)
    new_files = _walk_files(modified_dir)
    all_paths = sorted(set(old_files) | set(new_files))
    chunks: list[str] = []
    for rel in all_paths:
        old_data = old_files.get(rel)
        new_data = new_files.get(rel)
        if old_data == new_data:
            continue
        if old_data is not None and _is_binary(old_data):
            chunks.append(f"diff --git a/{rel} b/{rel}\nBinary files differ\n")
            continue
        if new_data is not None and _is_binary(new_data):
            chunks.append(f"diff --git a/{rel} b/{rel}\nBinary files differ\n")
            continue
        old_text = old_data.decode("utf-8", "replace") if old_data is not None else ""
        new_text = new_data.decode("utf-8", "replace") if new_data is not None else ""
        if old_data is None:
            chunks.append(f"diff --git a/{rel} b/{rel}\nnew file mode 100644\n")
        elif new_data is None:
            chunks.append(f"diff --git a/{rel} b/{rel}\ndeleted file mode 100644\n")
        else:
            chunks.append(f"diff --git a/{rel} b/{rel}\n")
        diff = difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
        chunks.append("".join(diff))
    return "\n".join(chunks)
