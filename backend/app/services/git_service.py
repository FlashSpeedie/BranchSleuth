from __future__ import annotations

import subprocess
import tarfile
import tempfile
from pathlib import Path

from app.config import settings

MAX_OUTPUT_BYTES = 32 * 1024 * 1024


class GitError(RuntimeError):
    pass


def run_git(args: list[str], cwd: str | Path | None = None, timeout: int = 120) -> str:
    cmd = ["git", "-c", "protocol.version=2", "-c", "core.askPass=true", *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise GitError(f"git {' '.join(args[:2])} timed out after {timeout}s") from e
    except FileNotFoundError as e:
        raise GitError("git executable not found") from e
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:2000]
        if "Authentication failed" in err or "could not read Username" in err:
            raise GitError("repository not found or requires authentication")
        raise GitError(f"git {' '.join(args[:2])} failed: {err}")
    if len(proc.stdout) > MAX_OUTPUT_BYTES:
        raise GitError("git output exceeds size limit")
    return proc.stdout


def clone(url: str, dest: Path, timeout: int = 600) -> None:
    run_git(["clone", "--no-hardlinks", "--single-branch", url, str(dest)], timeout=timeout)


def ls_remote(repo: str, is_local: bool, timeout: int = 60) -> list[tuple[str, str]]:
    args = ["ls-remote", "--heads", "--tags"] + (["--symref", "HEAD", repo] if not is_local else [])
    out = run_git(args if is_local else ["ls-remote", repo], cwd=repo if is_local else None, timeout=timeout)
    refs: list[tuple[str, str]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or "symref" in line:
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        sha, ref = parts
        if len(sha) == 40 or len(sha) == 64:
            refs.append((ref, sha))
    return refs


def detect_default_branch(repo: str, is_local: bool) -> str | None:
    if is_local:
        out = run_git(["symbolic-ref", "--short", "HEAD"], cwd=repo)
        return out.strip() or None
    try:
        out = run_git(["ls-remote", "--symref", "HEAD", repo], timeout=60)
        for line in out.splitlines():
            if "ref: refs/heads/" in line and "HEAD" in line:
                return line.split("refs/heads/")[-1].split()[0].strip()
    except GitError:
        return None
    return None


def resolve_ref(repo: str, ref: str) -> str:
    out = run_git(["rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=repo)
    return out.strip()


def extract_snapshot(repo: str, ref: str, dest: Path, timeout: int = 300) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as tf:
        tar_path = Path(tf.name)
    try:
        run_git(["archive", "--format=tar", ref, "-o", str(tar_path)], cwd=repo, timeout=timeout)
        if tar_path.stat().st_size > settings.max_extracted_bytes:
            raise GitError("snapshot archive exceeds size limit")
        with tarfile.open(tar_path, "r:") as tgz:
            def is_within_dir(base: Path, target: Path) -> bool:
                return base.resolve() in target.resolve().parents or base.resolve() == target.resolve()
            count = 0
            members = tgz.getmembers()
            if len(members) > settings.max_repo_files:
                raise GitError("snapshot contains too many files")
            for member in members:
                target = dest / member.name
                if member.name.startswith("/") or ".." in member.name.split("/"):
                    raise GitError(f"unsafe path in snapshot: {member.name}")
                if not is_within_dir(dest, target if member.isdir() else target.parent):
                    raise GitError(f"snapshot entry escapes directory: {member.name}")
                if member.issym() or member.islnk():
                    continue
                count += 1
            tgz.extractall(dest, filter="data")
            return count
    finally:
        try:
            tar_path.unlink(missing_ok=True)
        except OSError:
            pass


def diff_revisions(repo: str, sha_a: str, sha_b: str, timeout: int = 120) -> str:
    out = run_git(["diff", "--no-color", "--no-ext-diff", "-M", sha_a, sha_b], cwd=repo, timeout=timeout)
    if len(out) > MAX_OUTPUT_BYTES:
        out = out[:MAX_OUTPUT_BYTES] + "\n\n[diff truncated by BranchSleuth size limit]"
    return out
