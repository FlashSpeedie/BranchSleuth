from __future__ import annotations

import re
from dataclasses import dataclass, field

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
FILE_RE = re.compile(r'^diff --git (?:"?a/(.+?)"?) (?:"?b/(.+?)"?)$')


def unquote_path(path: str) -> str:
    if path.startswith('"') and path.endswith('"'):
        path = path[1:-1]
        try:
            return path.encode("latin-1", "backslashreplace").decode("unicode_escape")
        except UnicodeDecodeError:
            return path
    return path


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int

    def __post_init__(self) -> None:
        if self.old_count is None:
            self.old_count = 1
        if self.new_count is None:
            self.new_count = 1


@dataclass
class FileDiff:
    path: str
    old_path: str | None = None
    change_type: str = "modified"
    is_binary: bool = False
    hunks: list[Hunk] = field(default_factory=list)
    added_lines: dict[int, str] = field(default_factory=dict)
    removed_lines: dict[int, str] = field(default_factory=dict)
    context_lines_new: set[int] = field(default_factory=set)


def parse_unified_diff(diff_text: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    current: FileDiff | None = None
    old_lineno = 0
    new_lineno = 0
    hunk_remaining_old = 0
    hunk_remaining_new = 0
    for line in diff_text.splitlines():
        m = FILE_RE.match(line)
        if m:
            a_path = unquote_path(m.group(1))
            b_path = unquote_path(m.group(2))
            current = FileDiff(path=b_path, old_path=a_path if a_path != b_path else None)
            files.append(current)
            hunk_remaining_old = hunk_remaining_new = 0
            continue
        if current is None:
            continue
        if line.startswith("new file mode"):
            current.change_type = "added"
            current.old_path = None
            continue
        if line.startswith("deleted file mode"):
            current.change_type = "deleted"
            continue
        if line.startswith("rename from "):
            current.change_type = "renamed"
            current.old_path = unquote_path(line[len("rename from "):])
            continue
        if line.startswith("rename to "):
            current.path = unquote_path(line[len("rename to "):])
            continue
        if line.startswith("Binary files ") or line.startswith("GIT binary patch"):
            current.is_binary = True
            continue
        if line.startswith("similarity index") or line.startswith("dissimilarity index") or line.startswith("index "):
            continue
        hm = HUNK_RE.match(line)
        if hm:
            hunk = Hunk(
                old_start=int(hm.group(1)),
                old_count=int(hm.group(2) or "1"),
                new_start=int(hm.group(3)),
                new_count=int(hm.group(4) or "1"),
            )
            current.hunks.append(hunk)
            old_lineno = hunk.old_start
            new_lineno = hunk.new_start
            hunk_remaining_old = hunk.old_count
            hunk_remaining_new = hunk.new_count
            continue
        if hunk_remaining_old > 0 or hunk_remaining_new > 0:
            if line.startswith("+"):
                current.added_lines[new_lineno] = line[1:]
                new_lineno += 1
                hunk_remaining_new -= 1
            elif line.startswith("-"):
                current.removed_lines[old_lineno] = line[1:]
                old_lineno += 1
                hunk_remaining_old -= 1
            elif line.startswith(" ") or line == "":
                if hunk_remaining_old > 0:
                    old_lineno += 1
                    hunk_remaining_old -= 1
                if hunk_remaining_new > 0:
                    current.context_lines_new.add(new_lineno)
                    new_lineno += 1
                    hunk_remaining_new -= 1
            elif line.startswith("\\"):
                continue
    if current is not None and current.change_type == "renamed" and not current.hunks and not current.is_binary:
        pass
    return [f for f in files if f.change_type != "renamed" or f.hunks or f.is_binary or f.old_path != f.path]


def count_file_diff(f: FileDiff) -> int:
    return len(f.added_lines) + len(f.removed_lines)
