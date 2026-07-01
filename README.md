# a-stock-lib

A 股投研三系统（`a-stock-tracker` 评分管道 / `a-stock-research` 新股研究 / `a-stock-monitor` 持仓监控）共享的市场数据 Provider 原语包，从 `a-stock-tracker/lib/` 剥离出来，目标是让三个系统不再各自维护一份行情/基本面抓取逻辑。

## 为什么存在

详见设计文档：[`docs/design/2026-06-22-three-system-restructure-design.md`](docs/design/2026-06-22-three-system-restructure-design.md)。核心动机：三系统重复实现行情 Provider、AKShare 行业接口长期不稳定、止损系数差异化依赖脆弱的字符串反推框架。

## 当前状态（2026-06-29）

实施计划见 [`docs/plans/2026-06-23-a-stock-lib-shared-package-plan.md`](docs/plans/2026-06-23-a-stock-lib-shared-package-plan.md)，按 strangler-fig 模式分阶段迁移：

- **Phase 1（已完成）**：包骨架 + Provider 原语层（`market_data.py`）+ Tushare/BaoStock 报价 Provider 迁移 + 新增 Tushare 基本面行业分类 Provider。`a-stock-tracker/lib/` 期间零改动。
- **Phase 2（已完成，2026-06-23）**：范围按用户决定收窄为①②——`a-stock-research/fetcher.py`接入本包的`TushareFundamentalsProvider`替换不稳定的AKShare行业字段（agy审查发现4处真实问题已修复，见`a-stock-research`仓库commit `724b858`）；全量新旧industry值diff核验已跑（25支持仓：15支占位符修复/8支分类粒度差异非bug/0支未命中）。原计划绑在Phase 2里的评分引擎试点、`validate_subjective_evidence`语法retrofit**改为独立任务**，不在此次范围内（且后者已在06-22 commit`421fe2c`里直接实现，与本包无关）。`a-stock-monitor`**没有自己的代码**（只有`SKILL.md`，所有数据操作都shell调用`a-stock-research`的`cache.py`），无法"同research模式接入"；改为核实+刷新其5支持仓的industry缓存，验证`portfolio-risk`框架推断不再出现低置信度兜底标记。
- **Phase 3（已完成）**：已按设计文档"Phase 3 硬化清单"打磨 `a-stock-lib`，并发布版本 `0.1.1`（2026-06-25）；在 2026-06-26 进一步完成了针对 BaoStock fallback 潜在挂死风险的隔离超时 Provider 加固（全量测试升至 `48 passed`），发布 `0.1.2` 版本。
- **Phase 4（已完成，2026-06-26）**：`a-stock-tracker` 完成切换，退役本地行情 Provider 副本，升级并版本化锁定 `a-stock-lib==0.1.2`，保留本地专属环境门禁与 SQLite 缓存/审计编排。
- **技术债清理（已完成，2026-06-29）**：P0（`tushare_quotes` 裸异常逃逸修复）、P1（`__init__` 返回类型注解、`_normalize_baostock_bars` 函数拆分）、Step A（新增 `fetcher_utils.py` 提取 `detect_split_ratio` 共享模块，消除 a-stock-research/a-stock-tracker 双份维护），发布 `0.1.3` 版本，全量测试 `61 passed`。详见 [`CHANGELOG.md`](CHANGELOG.md)。`contracts.py`/`prompts/` 规范化已明确拆分为独立后续任务，当前版本范围不包含。

## 包结构

```
a_stock_lib/
  market_data.py          # MarketDataResult / CompositeMarketDataProvider / 错误码常量 / normalize_bars_result / exception_result
  providers/
    tushare_quotes.py      # 行情主源（需 TUSHARE_TOKEN）
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

## 测试

```bash
source .venv/bin/activate
pytest tests/ -v
```

## 开发流程

本仓库按 PM/codex/agy 三方协作流水线开发，细节见 [`CLAUDE.md`](CLAUDE.md)（Claude Code 专用）/ [`AGENTS.md`](AGENTS.md)（codex/agy 等通用 agent CLI 自动读取）。
