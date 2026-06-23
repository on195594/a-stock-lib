# a-stock-lib

A 股投研三系统（`a-stock-tracker` 评分管道 / `a-stock-research` 新股研究 / `a-stock-monitor` 持仓监控）共享的市场数据 Provider 原语包，从 `a-stock-tracker/lib/` 剥离出来，目标是让三个系统不再各自维护一份行情/基本面抓取逻辑。

## 为什么存在

详见设计文档：[`docs/design/2026-06-22-three-system-restructure-design.md`](docs/design/2026-06-22-three-system-restructure-design.md)。核心动机：三系统重复实现行情 Provider、AKShare 行业接口长期不稳定、止损系数差异化依赖脆弱的字符串反推框架。

## 当前状态（2026-06-23）

实施计划见 [`docs/plans/2026-06-23-a-stock-lib-shared-package-plan.md`](docs/plans/2026-06-23-a-stock-lib-shared-package-plan.md)，按 strangler-fig 模式分阶段迁移：

- **Phase 1（已完成）**：包骨架 + Provider 原语层（`market_data.py`）+ Tushare/BaoStock 报价 Provider 迁移 + 新增 Tushare 基本面行业分类 Provider。`a-stock-tracker/lib/` 期间零改动。
- **Phase 2（未开始）**：`a-stock-research`/`a-stock-monitor` 先接入本包，作为低风险验证场。
- **Phase 3（未开始）**：根据 Phase 2 暴露的问题打磨本包。已知待修问题见设计文档"Phase 3 硬化清单"一节。
- **Phase 4（未开始）**：`a-stock-tracker` 最后切换，退役本地 `lib/` 副本。**目前 tracker 仍在用自己本地的 `lib/`，未依赖本包。**

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
