# a-stock-lib

A 股投研三系统（`a-stock-tracker` 评分管道 / `a-stock-research` 新股研究 / `a-stock-monitor` 持仓监控）共享的市场数据 Provider 原语包，从 `a-stock-tracker/lib/` 剥离出来，目标是让三个系统不再各自维护一份行情/基本面抓取逻辑。

## 为什么存在

详见设计文档：[`docs/design/2026-06-22-three-system-restructure-design.md`](docs/design/2026-06-22-three-system-restructure-design.md)。核心动机：三系统重复实现行情 Provider、AKShare 行业接口长期不稳定、止损系数差异化依赖脆弱的字符串反推框架。

## 当前状态（2026-08-02）

实施计划见 [`docs/plans/2026-06-23-a-stock-lib-shared-package-plan.md`](docs/plans/2026-06-23-a-stock-lib-shared-package-plan.md)，按 strangler-fig 模式分阶段迁移：

- **Phase 1（已完成）**：包骨架 + Provider 原语层（`market_data.py`）+ Tushare/BaoStock 报价 Provider 迁移 + 新增 Tushare 基本面行业分类 Provider。`a-stock-tracker/lib/` 期间零改动。
- **Phase 2（已完成，2026-06-23）**：范围按用户决定收窄为①②——`a-stock-research/fetcher.py`接入本包的`TushareFundamentalsProvider`替换不稳定的AKShare行业字段（agy审查发现4处真实问题已修复，见`a-stock-research`仓库commit `724b858`）；全量新旧industry值diff核验已跑（25支持仓：15支占位符修复/8支分类粒度差异非bug/0支未命中）。原计划绑在Phase 2里的评分引擎试点、`validate_subjective_evidence`语法retrofit**改为独立任务**，不在此次范围内（且后者已在06-22 commit`421fe2c`里直接实现，与本包无关）。`a-stock-monitor`**没有自己的代码**（只有`SKILL.md`，所有数据操作都shell调用`a-stock-research`的`cache.py`），无法"同research模式接入"；改为核实+刷新其5支持仓的industry缓存，验证`portfolio-risk`框架推断不再出现低置信度兜底标记。
- **Phase 3（已完成）**：已按设计文档"Phase 3 硬化清单"打磨 `a-stock-lib`，并发布版本 `0.1.1`（2026-06-25）；在 2026-06-26 进一步完成了针对 BaoStock fallback 潜在挂死风险的隔离超时 Provider 加固（全量测试升至 `48 passed`），发布 `0.1.2` 版本。
- **Phase 4（已完成，2026-06-26）**：`a-stock-tracker` 完成切换，退役本地行情 Provider 副本；当前已版本化锁定 `a-stock-lib==0.2.0`，保留本地专属环境门禁与 SQLite 缓存/审计编排。
- **技术债清理（已完成，2026-06-29）**：P0（`tushare_quotes` 裸异常逃逸修复）、P1（`__init__` 返回类型注解、`_normalize_baostock_bars` 函数拆分）、Step A（新增 `fetcher_utils.py` 提取 `detect_split_ratio` 共享模块，消除 a-stock-research/a-stock-tracker 双份维护），发布 `0.1.3` 版本，全量测试 `61 passed`。
- **复合实时行情 + contracts/prompts（当前，2026-07-14）**：在既有 `0.2.0` contracts/canonical prompts 基础上新增 fail-closed 实时行情复合 Provider 与六框架主观语义映射；a-stock-research 已消费新增接口，其他消费者既有 Provider 行为不变。当前版本 `0.3.0`，全量测试 `126 passed`。
- **TuShare 生产主源 Phase 1（已完成，2026-07-21 强切 / 2026-08-02 合并回 master）**：版本升至 `0.4.1`，新增估值、财务、分红 Provider、十年估值分位计算器、统一限流/错误语义和默认凭据隔离；0.4.1 进一步修复真实 `fina_indicator` 默认响应省略 `update_flag` 的问题。a-stock-tracker 已于 2026-07-21 完成生产强切（用户已确认授权），实际消费 `0.4.1`；该功能分支此前在独立 worktree 开发，master 落后约 12 天，已于 2026-08-02 合并补齐。a-stock-research 仍为 `0.3.0`，是否升级待单独决定。
- **Phase 3b（已完成，2026-07-01同日）**：`prompts/` 渲染的 `AGENTS.md` 首次真正落地到 a-stock-research 并验证 codex 自动读取（此前只验证过 agy）；`contracts.parse_cycle_stage_tag` 接入 a-stock-research 的 `cmd_set_analysis`（覆盖 C/D/B 全部必做框架，均 fail-closed），SKILL.md 周期位置区域同步完成语法切换。这部分改动全部发生在 a-stock-research 仓库，本仓库代码未变。2026-07-02 research 已补上 `cmd_checklist` 里 C 框架的 warn-only 提前反馈 UX。详见 [`CHANGELOG.md`](CHANGELOG.md)。
- **跨项目 PM loop（已完成，2026-07-02）**：a-stock-tracker 的 Phase 6 weekly PM loop 已自动化为每周一 09:30 cron + Telegram 摘要，检查 weekly/daily/outcome 日志、`READY_CRON` 和 `accuracy-report`；tracker commit `f181010`，验证 `211 passed, 1 skipped`。Framework B 仍保持 report-only，不因自动摘要而启用生产写入。

三项目统一下一步计划见 [`docs/plans/2026-07-01-three-project-next-work-plan.md`](docs/plans/2026-07-01-three-project-next-work-plan.md)。

## 包结构

```
a_stock_lib/
  market_data.py          # MarketDataResult / CompositeMarketDataProvider / 错误码常量 / normalize_bars_result / exception_result
  valuation.py            # 十年/月末估值分位纯函数
  providers/
    tushare_quotes.py      # 行情主源（需 TUSHARE_TOKEN）
    tushare_common.py      # Token、限流、重试、错误分类和结果 metadata
    tushare_valuation.py   # daily_basic 当前/历史估值
    tushare_financials.py  # 财务指标、三大报表和分红事件
    baostock_quotes.py     # 行情 fallback
    tushare_fundamentals.py # 行业分类批量拉取 + 本地30天缓存
```

## 安装

开发模式（本仓库内迭代用）：

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

消费方安装（版本锁定，不用 `-e` 软链接——见设计文档 6.1 节）：

```bash
python3 -m build                       # 产出 dist/a_stock_lib-<version>-py3-none-any.whl
pip install /path/to/a_stock_lib-<version>-py3-none-any.whl
```

按需安装数据源依赖：`pip install -e ".[tushare]"` / `".[baostock]"`。

TuShare 生产主源 API 与字段口径见 [`docs/TUSHARE_PRIMARY_PROVIDERS.md`](docs/TUSHARE_PRIMARY_PROVIDERS.md)。

## 测试

```bash
source .venv/bin/activate
pytest tests/ -v
```

## 开发流程

本仓库按 PM/codex/agy 三方协作流水线开发，细节见 [`CLAUDE.md`](CLAUDE.md)（Claude Code 专用）/ [`AGENTS.md`](AGENTS.md)（codex/agy 等通用 agent CLI 自动读取）。
