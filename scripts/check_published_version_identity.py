#!/usr/bin/env python3
"""Reject reuse of a published version after wheel-relevant changes."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tomllib


ARTIFACT_FILES = {"pyproject.toml", "MANIFEST.in", "setup.py", "setup.cfg"}
ARTIFACT_PREFIX = "a_stock_lib/"


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
    )


def _artifact_relevant(path: str) -> bool:
    return path in ARTIFACT_FILES or path.startswith(ARTIFACT_PREFIX)


def _changed_paths(repo: Path, tag_commit: str) -> set[str]:
    paths: set[str] = set()
    for args in (
        ("diff", "--name-only", f"{tag_commit}..HEAD"),
        ("diff", "--name-only", "HEAD"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        paths.update(_git(repo, *args).stdout.splitlines())
    return {path for path in paths if _artifact_relevant(path)}


def check_repository(repo: Path) -> list[str]:
    """Return identity errors for one git checkout."""
    try:
        version = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))[
            "project"
        ]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        return [f"cannot read project.version: {exc}"]

    tag = f"v{version}"
    if _git(repo, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}", check=False).returncode:
        return []
    tag_commit = _git(repo, "rev-list", "-n", "1", tag).stdout.strip()
    if _git(repo, "merge-base", "--is-ancestor", tag_commit, "HEAD", check=False).returncode:
        return [f"published tag {tag} is not an ancestor of HEAD"]
    changed = sorted(_changed_paths(repo, tag_commit))
    if not changed:
        return []
    return [
        "published package version reused after artifact-relevant source changed: "
        + ", ".join(changed)
    ]


def main() -> int:
    errors = check_repository(Path(__file__).resolve().parents[1])
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("published package identity: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
