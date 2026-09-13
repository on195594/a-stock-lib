from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "published_identity", ROOT / "scripts/check_published_version_identity.py"
)
assert SPEC and SPEC.loader
published_identity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(published_identity)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)


def _repo(tmp_path: Path, *, tagged: bool = True) -> Path:
    _git(tmp_path, "init", "-q", "-b", "master")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "user.email", "test@example.com")
    (tmp_path / "a_stock_lib").mkdir()
    (tmp_path / "a_stock_lib/__init__.py").write_text("__version__ = '1.0.0'\n")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "1.0.0"\n'
    )
    _commit(tmp_path, "initial")
    if tagged:
        _git(tmp_path, "tag", "-a", "v1.0.0", "-m", "release")
    return tmp_path


def test_no_matching_tag_passes(tmp_path: Path) -> None:
    assert published_identity.check_repository(_repo(tmp_path, tagged=False)) == []


def test_head_at_annotated_tag_passes(tmp_path: Path) -> None:
    assert published_identity.check_repository(_repo(tmp_path)) == []


def test_docs_only_after_tag_passes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "README.md").write_text("docs only\n")
    _commit(repo, "docs")
    assert published_identity.check_repository(repo) == []


@pytest.mark.parametrize("path", ["a_stock_lib/value.py", "pyproject.toml"])
def test_committed_artifact_change_fails(tmp_path: Path, path: str) -> None:
    repo = _repo(tmp_path)
    (repo / path).write_text(
        'value = 1\n'
        if path.startswith("a_stock_lib/")
        else '[project]\nname = "changed"\nversion = "1.0.0"\n'
    )
    _commit(repo, "change")
    assert "published package version reused" in published_identity.check_repository(
        repo
    )[0]


@pytest.mark.parametrize("state", ["unstaged", "staged", "untracked"])
def test_uncommitted_artifact_change_fails(tmp_path: Path, state: str) -> None:
    repo = _repo(tmp_path)
    path = repo / (
        "a_stock_lib/new.py" if state == "untracked" else "a_stock_lib/__init__.py"
    )
    path.write_text("changed = True\n")
    if state == "staged":
        _git(repo, "add", str(path.relative_to(repo)))
    assert "published package version reused" in published_identity.check_repository(
        repo
    )[0]


def test_current_repository_has_clean_published_identity() -> None:
    assert published_identity.check_repository(ROOT) == []
