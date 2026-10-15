from __future__ import annotations

import zipfile
from pathlib import Path


BASELINE_PRICING = '''"""Pricing rules for TinyShop."""


def apply_discount(subtotal: float) -> float:
    """Apply the volume discount: orders strictly above $100 get 10% off."""
    if subtotal > 100:
        return subtotal * 0.9
    return subtotal
'''

MODIFIED_PRICING = '''"""Pricing rules for TinyShop."""


def apply_discount(subtotal: float) -> float:
    """Apply the volume discount: orders strictly above $100 get 10% off."""
    if subtotal >= 100:
        return subtotal * 0.9
    return subtotal
'''

TESTS_PRICING = '''import math

from tinyshop.pricing import apply_discount


def test_no_discount_at_zero():
    assert apply_discount(0) == 0


def test_no_discount_below_threshold():
    assert apply_discount(99.5) == 99.5


def test_discount_above_threshold():
    assert math.isclose(apply_discount(150), 135.0)
'''

PYPROJECT = '''[project]
name = "tinyshop"
version = "0.1.0"
requires-python = ">=3.12"
'''

PYTEST_INI = """[pytest]
pythonpath = .
"""


def write_repo_files(root: Path, modified: bool = False) -> None:
    (root / "tinyshop").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "tinyshop" / "__init__.py").write_text("")
    (root / "tinyshop" / "pricing.py").write_text(MODIFIED_PRICING if modified else BASELINE_PRICING)
    (root / "tests" / "test_pricing.py").write_text(TESTS_PRICING)
    (root / "pyproject.toml").write_text(PYPROJECT)
    (root / "pytest.ini").write_text(PYTEST_INI)


def build_fixture_git_repo(root: Path) -> tuple[str, str]:
    """Create a real git repository with baseline and modified commits.

    Returns (repo_path, modified_sha)."""
    import subprocess

    def git(*args: str) -> str:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if proc.returncode != 0:
            raise RuntimeError(f"git {args} failed: {proc.stderr}")
        return proc.stdout.strip()

    root.mkdir(parents=True, exist_ok=True)
    git("init", "-b", "main")
    git("config", "user.email", "fixture@branchsleuth.test")
    git("config", "user.name", "BranchSleuth Fixture")
    write_repo_files(root, modified=False)
    git("add", "-A")
    git("commit", "-m", "baseline: pricing with strict > 100 discount rule")
    write_repo_files(root, modified=True)
    git("add", "-A")
    git("commit", "-m", "modify: adjust discount comparison (introduces boundary defect)")
    sha = git("rev-parse", "HEAD")
    return str(root), sha


def build_snapshot_pair(root: Path) -> tuple[Path, Path]:
    baseline = root / "baseline"
    modified = root / "modified"
    write_repo_files(baseline, modified=False)
    write_repo_files(modified, modified=True)
    return baseline, modified


def zip_dir(source: Path, zip_path: Path, arc_root: str = "tinyshop-src") -> None:
    with zipfile.ZipFile(zip_path, "w") as zf:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                zf.write(path, f"{arc_root}/{path.relative_to(source).as_posix()}")
