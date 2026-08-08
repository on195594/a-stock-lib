#!/usr/bin/env python3
"""Render backend prompt files from canonical a-stock-lib fragments.

The ``skill_md`` target reads the explicitly supplied canonical Skill source
at render time, then
replaces only the four canonical LLM-instruction regions with files from
``a_stock_lib/prompts/fragments``. This keeps the generated Claude
``SKILL.md`` anchored to the real current hand-authored source, including YAML
frontmatter and tool/shell instructions, instead of relying on a manually
copied template that can silently drift.

The ``agents_md`` target uses the same rendered body, strips client YAML
frontmatter, and adds plain-markdown codex/agy framing.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from a_stock_lib.prompts import FRAGMENT_FILENAMES, compute_fragment_hashes  # noqa: E402
from a_stock_lib.prompts.manifest import FRAGMENT_HASHES  # noqa: E402


FRAGMENTS_DIR = REPO_ROOT / "a_stock_lib" / "prompts" / "fragments"
MANIFEST_PATH = REPO_ROOT / "a_stock_lib" / "prompts" / "manifest.py"


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a-stock prompt targets.")
    parser.add_argument("target", nargs="?", choices=("skill_md", "agents_md"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--update-manifest",
        action="store_true",
        help="Recompute and rewrite a_stock_lib/prompts/manifest.py instead of rendering.",
    )
    parser.add_argument("--skill-source", type=Path, required=False, help="Explicit canonical Skill.md source")
    args = parser.parse_args()

    if args.update_manifest:
        update_manifest()
        return 0

    if args.target is None or args.output_dir is None or args.skill_source is None:
        parser.error("target, --output-dir, and --skill-source are required unless --update-manifest is used")
    if not args.skill_source.is_file():
        parser.error(f"skill source is not a regular file: {args.skill_source}")

    warn_if_manifest_stale()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.target == "skill_md":
        output_path = args.output_dir / "SKILL.md"
        write_text_atomic(output_path, render_skill_md(args.skill_source))
    else:
        output_path = args.output_dir / "AGENTS.md"
        write_text_atomic(output_path, render_agents_md(args.skill_source))

    print(f"wrote {output_path}")
    return 0


def update_manifest() -> None:
    hashes = compute_fragment_hashes(FRAGMENTS_DIR)
    lines = [
        '"""Recorded prompt fragment hashes.',
        "",
        "Run `python3 scripts/render_prompts.py --update-manifest` after intentional",
        "canonical fragment edits to refresh these values.",
        '"""',
        "from __future__ import annotations",
        "",
        "FRAGMENT_HASHES: dict[str, str] = {",
    ]
    for filename in FRAGMENT_FILENAMES:
        lines.append(f'    "{filename}": "{hashes[filename]}",')
    lines.extend(["}", ""])
    write_text_atomic(MANIFEST_PATH, "\n".join(lines))
    print(f"updated {MANIFEST_PATH}")


def warn_if_manifest_stale() -> None:
    current = compute_fragment_hashes(FRAGMENTS_DIR)
    for filename in FRAGMENT_FILENAMES:
        recorded = FRAGMENT_HASHES.get(filename)
        actual = current[filename]
        if recorded != actual:
            print(
                "WARNING: prompt fragment hash mismatch for "
                f"{filename}: manifest={recorded} current={actual}; "
                "canonical source changed since last render, please re-render.",
                file=sys.stderr,
            )


def render_skill_md(skill_source: Path) -> str:
    rendered = skill_source.read_text(encoding="utf-8")
    replacements = (
        (
            "## 第一步：行业识别\n",
            "## 第1.5步：周期位置判断（C/D/B框架必做，其余框架可选）\n",
            fragment_text("industry_routing.md"),
        ),
        (
            "## 第1.5步：周期位置判断（C/D/B框架必做，其余框架可选）\n",
            "## 第二步：基本面评分（60分）\n",
            fragment_text("cycle_stage.md"),
        ),
        (
            "> **⚠️ 主观分项证据门槛**（适用所有框架的护城河/行业地位/特许经营稀缺性/品牌渠道类条目）：",
            "\n\n> **⚠️ 客观分项核验门槛**",
            fragment_text("subjective_evidence.md").rstrip("\n"),
        ),
        (
            "## 第四步：双轨评级与仓位建议\n",
            "## 第五步：防韭菜检查（买入前必做）\n",
            fragment_text("dual_track_rating.md"),
        ),
    )
    for start_marker, end_marker, replacement in replacements:
        rendered = replace_region(rendered, start_marker, end_marker, replacement)
    return rendered


def replace_region(content: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = content.find(start_marker)
    if start == -1:
        raise ValueError(f"start marker not found: {start_marker!r}")
    if content.find(start_marker, start + 1) != -1:
        raise ValueError(f"start marker is not unique: {start_marker!r}")
    end = content.find(end_marker, start + len(start_marker))
    if end == -1:
        raise ValueError(f"end marker not found after {start_marker!r}: {end_marker!r}")
    if content.find(end_marker, end + 1) != -1:
        raise ValueError(f"end marker is not unique after {start_marker!r}: {end_marker!r}")
    return content[:start] + replacement + content[end:]


def render_agents_md(skill_source: Path) -> str:
    skill_body = strip_yaml_frontmatter(render_skill_md(skill_source))
    skill_body = skill_body.replace("Claude", "codex/agy")

    header = """# AGENTS.md — a-stock-research

跨 agent CLI（codex / agy / 其他）在 a-stock-research skill 目录工作时的投研执行约束。与 `SKILL.md` 的业务流程实质相同，去掉 Claude Code 专属 YAML frontmatter，保留 Bash/Read 可执行指令。

## 项目是什么

A 股首次投研分析助手：基本面60分 + 择时20分 = 总分80分，用于新股票研究、首次买入决策、优质公司筛选和多股横向比较。持仓监控、止损触发、卖出信号应使用 `/a-stock-monitor`。

## 运行边界

- 先执行缓存/fetcher 流程，再进入行业识别、框架评分和输出格式。
- cache.py / fetcher.py / frameworks/*.md 仍位于 a-stock-research skill 目录；codex/agy 可按下方 Bash/Read 指令直接调用或读取。
- 本文件由 `a-stock-lib` 的 canonical prompt fragments 渲染生成；纯 LLM 判断 prose 以 `a_stock_lib/prompts/fragments/` 为来源。

---

"""
    return header + skill_body


def strip_yaml_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    if end == -1:
        return text
    return text[end + len("\n---\n") :]


def fragment_text(filename: str) -> str:
    if filename not in FRAGMENT_FILENAMES:
        raise ValueError(f"unknown fragment: {filename}")
    return (FRAGMENTS_DIR / filename).read_text(encoding="utf-8")


def write_text_atomic(path: Path, text: str) -> None:
    tmp_path = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp_path.write_text(text, encoding="utf-8")
    with tmp_path.open("rb") as handle:
        os.fsync(handle.fileno())
    tmp_path.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
