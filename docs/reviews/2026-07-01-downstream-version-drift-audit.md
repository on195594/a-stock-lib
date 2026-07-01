# 下游版本漂移审计

日期：2026-07-01
范围：只读审计 `a-stock-tracker` / `a-stock-research` / `a-stock-monitor` 对 `a-stock-lib` 的版本引用、实际 import 消费路径和文档状态漂移。本文不修改下游仓库，仅给出后续授权建议。

## 结论

本审计最初发现的最大漂移不是运行时 import，而是下游状态文档和安装说明滞后：

- `a-stock-tracker` 运行依赖曾锁 `a-stock-lib==0.1.3`，但多份当前状态文档仍写 `0.1.2`；现已统一升级到 `0.2.0`。
- `a-stock-research` 已真实消费 `a-stock-lib==0.2.0` 的 `contracts.py` 边界，`requirements.txt` 安装注释曾写历史 wheel `0.1.0`；现已同步到 `0.2.0`。
- `a-stock-monitor` 没有直接消费 `a-stock-lib`；它通过 `a-stock-research/cache.py` 间接使用 research 的缓存/持仓工具链。

这些漂移未构成运行阻塞，但会误导新环境部署和后续接手判断；本轮已按用户授权统一到当前最新版本 `0.2.0`。

## 当前事实

| 系统 | 当前事实 | 证据 |
|---|---|---|
| `a-stock-lib` | 最新版本 `0.2.0`，本仓库全量测试当前为 `99 passed` | `pyproject.toml` / `a_stock_lib/__init__.py`；本轮 `pytest tests/ -v` |
| `a-stock-tracker` | 依赖锁定 `a-stock-lib==0.2.0`，使用本地 wheel path | `/home/lin/a-stock-tracker/requirements.txt:4-5` |
| `a-stock-tracker` | 生产代码消费本包 Provider、协议原语和 `detect_split_ratio` | `/home/lin/a-stock-tracker/lib/market_data.py:9,121-133`；`/home/lin/a-stock-tracker/lib/fetcher.py:16` |
| `a-stock-research` | `cache.py` 直接消费 `parse_subjective_assessment_tags` / `parse_cycle_stage_tag` | `/home/lin/.claude/skills/a-stock-research/cache.py:48,529,548` |
| `a-stock-research` | `fetcher.py` 消费 `detect_split_ratio` 和 `TushareFundamentalsProvider` | `/home/lin/.claude/skills/a-stock-research/fetcher.py:17,169,460,479` |
| `a-stock-research` | `AGENTS.md` 声明由本包 canonical prompt fragments 渲染生成 | `/home/lin/.claude/skills/a-stock-research/AGENTS.md:13` |
| `a-stock-monitor` | 无直接 `a_stock_lib` import；统一调用 research `cache.py` | `/home/lin/.claude/skills/a-stock-monitor/SKILL.md:14-19` |

## 漂移清单

### P1：当前状态文档或安装说明应修

| 系统 | 漂移 | 建议动作 |
|---|---|---|
| `a-stock-research` | `requirements.txt` 注释曾建议安装 `a_stock_lib-0.1.0-py3-none-any.whl`，与当前 `0.2.0` 消费状态不一致 | 已同步到 `0.2.0` |
| `a-stock-tracker` | 当前依赖曾是 `0.1.3`，但 `README.md`、`CLAUDE.md`、`docs/runbooks/market-data-provider-recovery.md`、`docs/project-status.md`、`docs/evolution-roadmap.md` 当前状态表仍写 `0.1.2` | 已同步到 `0.2.0` |
| `a-stock-lib` | `README.md` Phase 4 行仍写 tracker 锁定 `0.1.2`，与后续升级事实不一致 | 已同步到 `0.2.0` |

### P2：历史记录保留原文

以下内容属于计划、复盘或历史审查记录，原则上不改写历史版本号：

- `a-stock-tracker/docs/evolution-roadmap.md` 的历史推进复盘和 v1.6 changelog 中的 `0.1.2`。
- `a-stock-tracker/docs/reviews/2026-06-25-phase4-a-stock-lib-transition-review.md` 中的 `0.1.1`。
- `a-stock-lib/docs/plans/*` 正文中的 `0.1.0` / `0.1.1` / `0.1.2` 历史合同示例；这类文档已在顶部补充“正文保留历史验收口径”。

### P3：无需动作

- `a-stock-monitor` 无独立 Python 代码直接消费 `a-stock-lib`，当前通过 research `cache.py` 间接消费符合项目现状。
- `a-stock-research` 的 `AGENTS.md` 已声明 canonical prompt 来源；`SKILL.md` 目前没有同样的生成来源注释，但不影响运行。是否补注释可作为低优先级清理项。

## 后续建议

1. 后续发布本包新版本时，同步更新 tracker `requirements.txt` 与当前状态文档。
2. 继续保留历史计划/复盘中的当时版本号，不做追溯改写。
3. 若后续要让 research 的安装说明避免再次漂移，可把精确 wheel 文件名改为 `<version>` 模板。

## Subagent 核查记录

本审计使用两个只读 explorer subagent 并行核查：

- tracker explorer：确认升级前 `/home/lin/a-stock-tracker/requirements.txt:5` 锁 `a-stock-lib==0.1.3`，并列出当前状态文档中的 `0.1.2` 漂移。
- research/monitor explorer：确认 research `cache.py` / `fetcher.py` 的 `a_stock_lib` 消费点、升级前 `requirements.txt` 的 `0.1.0` 注释漂移，以及 monitor 仅通过 research `cache.py` 间接消费。
