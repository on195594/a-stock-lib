from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from a_stock_lib import prompts


REPO_ROOT = Path(__file__).resolve().parents[1]
RENDER_PROMPTS_PATH = REPO_ROOT / "scripts" / "render_prompts.py"
FRAGMENTS_DIR = REPO_ROOT / "a_stock_lib" / "prompts" / "fragments"


def load_render_prompts_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("render_prompts_for_tests", RENDER_PROMPTS_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_skill_text(include_frontmatter: bool = False) -> str:
    frontmatter = "---\nname: fixture\n---\n" if include_frontmatter else ""
    return (
        frontmatter
        + "# Synthetic skill\n\n"
        "PRESERVE_BEFORE\n\n"
        "## 第一步：行业识别\n"
        "OLD_INDUSTRY_CONTENT\n"
        "## 第1.5步：周期位置判断（C/D/B框架必做，其余框架可选）\n"
        "OLD_CYCLE_CONTENT\n"
        "## 第二步：基本面评分（60分）\n"
        "PRESERVE_AFTER_SCORE\n\n"
        "> **⚠️ 主观分项证据门槛**（适用所有框架的护城河/行业地位/特许经营稀缺性/品牌渠道类条目）："
        "OLD_SUBJECTIVE_CONTENT"
        "\n\n> **⚠️ 客观分项核验门槛**\n"
        "PRESERVE_OBJECTIVE_CONTENT\n\n"
        "## 第四步：双轨评级与仓位建议\n"
        "OLD_DUAL_TRACK_CONTENT\n"
        "## 第五步：防韭菜检查（买入前必做）\n"
        "PRESERVE_AFTER_ALL\n"
        "Claude should read docs. Read ~/.claude/skills/a-stock-research/frameworks/a.md\n"
        "Run python3 ~/.claude/skills/a-stock-research/cache.py\n"
    )


def fragment_text(filename: str) -> str:
    return (FRAGMENTS_DIR / filename).read_text(encoding="utf-8")


def test_compute_fragment_hashes_returns_sha256_for_each_fragment(tmp_path: Path) -> None:
    for index, filename in enumerate(prompts.FRAGMENT_FILENAMES):
        content = f"fixture-{filename}-{index}\n".encode("utf-8")
        (tmp_path / filename).write_bytes(content)

    hashes = prompts.compute_fragment_hashes(tmp_path)

    assert hashes == {
        filename: hashlib.sha256((tmp_path / filename).read_bytes()).hexdigest()
        for filename in prompts.FRAGMENT_FILENAMES
    }


def test_manifest_hashes_match_real_fragment_files() -> None:
    from a_stock_lib.prompts.manifest import FRAGMENT_HASHES

    assert prompts.compute_fragment_hashes(FRAGMENTS_DIR) == FRAGMENT_HASHES


def test_render_skill_md_splices_four_canonical_fragments_and_preserves_unrelated_text(tmp_path: Path) -> None:
    render_prompts = load_render_prompts_module()
    source = tmp_path / "SKILL.md"
    source.write_text(synthetic_skill_text(), encoding="utf-8")

    rendered = render_prompts.render_skill_md(source)

    expected_fragments = [
        fragment_text("industry_routing.md"),
        fragment_text("cycle_stage.md"),
        fragment_text("subjective_evidence.md").rstrip("\n"),
        fragment_text("dual_track_rating.md"),
    ]
    for expected in expected_fragments:
        assert expected in rendered

    assert rendered.index(expected_fragments[0]) < rendered.index(expected_fragments[1])
    assert rendered.index(expected_fragments[1]) < rendered.index("## 第二步：基本面评分（60分）")
    assert rendered.index(expected_fragments[2]) < rendered.index("> **⚠️ 客观分项核验门槛**")
    assert rendered.index(expected_fragments[3]) < rendered.index("## 第五步：防韭菜检查（买入前必做）")
    assert "PRESERVE_BEFORE" in rendered
    assert "PRESERVE_AFTER_SCORE" in rendered
    assert "PRESERVE_OBJECTIVE_CONTENT" in rendered
    assert "PRESERVE_AFTER_ALL" in rendered
    assert "OLD_INDUSTRY_CONTENT" not in rendered
    assert "OLD_CYCLE_CONTENT" not in rendered
    assert "OLD_SUBJECTIVE_CONTENT" not in rendered
    assert "OLD_DUAL_TRACK_CONTENT" not in rendered


def test_replace_region_splices_between_markers() -> None:
    render_prompts = load_render_prompts_module()

    rendered = render_prompts.replace_region(
        "before <start> old body <end> after",
        "<start>",
        "<end>",
        "<start> new body ",
    )

    assert rendered == "before <start> new body <end> after"


@pytest.mark.parametrize(
    ("content", "match"),
    [
        ("before old body <end> after", "start marker not found: '<start>'"),
        ("before <start> old body after", "end marker not found after '<start>': '<end>'"),
    ],
)
def test_replace_region_raises_value_error_when_marker_missing(content: str, match: str) -> None:
    render_prompts = load_render_prompts_module()

    with pytest.raises(ValueError, match=match):
        render_prompts.replace_region(content, "<start>", "<end>", "replacement")


@pytest.mark.parametrize(
    ("content", "match"),
    [
        ("before <start> old body <end> after <start>", "start marker is not unique: '<start>'"),
        (
            "before <start> old body <end> after <end>",
            "end marker is not unique after '<start>': '<end>'",
        ),
    ],
)
def test_replace_region_raises_value_error_when_marker_is_not_unique(content: str, match: str) -> None:
    render_prompts = load_render_prompts_module()

    with pytest.raises(ValueError, match=match):
        render_prompts.replace_region(content, "<start>", "<end>", "replacement")


def test_write_text_atomic_creates_and_overwrites_leaving_no_temp_file(tmp_path: Path) -> None:
    """End-state check only: content is correct and no dangling temp file remains.

    Does not mock ``os.fsync``/``Path.replace`` to prove the write path is
    internally atomic — that would require intercepting those calls directly,
    which this test does not attempt.
    """
    render_prompts = load_render_prompts_module()
    target = tmp_path / "rendered.md"

    render_prompts.write_text_atomic(target, "first content\n")

    assert target.read_text(encoding="utf-8") == "first content\n"

    render_prompts.write_text_atomic(target, "second content\n")

    assert target.read_text(encoding="utf-8") == "second content\n"
    assert list(tmp_path.glob(f".{target.name}.tmp.*")) == []


def test_render_agents_md_strips_frontmatter_rewrites_claude_and_prepends_header(tmp_path: Path) -> None:
    render_prompts = load_render_prompts_module()
    source = tmp_path / "SKILL.md"
    source.write_text(synthetic_skill_text(include_frontmatter=True), encoding="utf-8")

    rendered = render_prompts.render_agents_md(source)
    rendered_body = rendered.split("---\n\n", 1)[1]

    assert rendered.startswith("# AGENTS.md — a-stock-research\n\n")
    assert "name: fixture" not in rendered
    assert "Claude" not in rendered_body
    assert "codex/agy should read docs." in rendered_body
    assert "Read /home/lin/.claude/skills/a-stock-research/frameworks/a.md" in rendered_body
    assert "python3 /home/lin/.claude/skills/a-stock-research/cache.py" in rendered_body


def test_warn_if_manifest_stale_prints_no_warning_when_hashes_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    render_prompts = load_render_prompts_module()
    for filename in prompts.FRAGMENT_FILENAMES:
        (tmp_path / filename).write_text(f"content for {filename}\n", encoding="utf-8")
    hashes = prompts.compute_fragment_hashes(tmp_path)
    monkeypatch.setattr(render_prompts, "FRAGMENTS_DIR", tmp_path)
    monkeypatch.setattr(render_prompts, "FRAGMENT_HASHES", hashes)

    render_prompts.warn_if_manifest_stale()

    captured = capsys.readouterr()
    assert "WARNING" not in captured.out
    assert "WARNING" not in captured.err


def test_warn_if_manifest_stale_prints_warning_on_hash_mismatch_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    render_prompts = load_render_prompts_module()
    for filename in prompts.FRAGMENT_FILENAMES:
        (tmp_path / filename).write_text(f"content for {filename}\n", encoding="utf-8")
    hashes = prompts.compute_fragment_hashes(tmp_path)
    mismatched = dict(hashes)
    mismatched[prompts.FRAGMENT_FILENAMES[0]] = "0" * 64
    monkeypatch.setattr(render_prompts, "FRAGMENTS_DIR", tmp_path)
    monkeypatch.setattr(render_prompts, "FRAGMENT_HASHES", mismatched)

    render_prompts.warn_if_manifest_stale()

    captured = capsys.readouterr()
    assert "WARNING: prompt fragment hash mismatch" in captured.err
    assert prompts.FRAGMENT_FILENAMES[0] in captured.err
    assert captured.out == ""
