# a-stock-lib

A 股投研三系统（`a-stock-tracker` 评分管道 / `a-stock-research` 新股研究 / `a-stock-monitor` 持仓监控）共享的市场数据 Provider 原语包，从 `a-stock-tracker/lib/` 剥离出来，目标是让三个系统不再各自维护一份行情/基本面抓取逻辑。

## 为什么存在

详见设计文档：[`docs/design/2026-06-22-three-system-restructure-design.md`](docs/design/2026-06-22-three-system-restructure-design.md)。核心动机：三系统重复实现行情 Provider、AKShare 行业接口长期不稳定、止损系数差异化依赖脆弱的字符串反推框架。

## 当前状态（2026-08-23）

当前版本 `0.5.2`。在 `0.5.1` 基线上收紧行情非法值、OHLC 一致性与日期范围边界，行业缓存写失败改为结构化降级，并修复包版本身份不一致。`a-stock-tracker` 与 `a-stock-agent-skills` runtime 均已完成 `0.5.2` 切换和回读。

下游为 `a-stock-tracker` 与 `/home/lin/a-stock-agent-skills`；后者是 research/monitor/QA 与 runtime 的唯一 canonical carrier。

## 包结构

```
a_stock_lib/
  market_data.py          # MarketDataResult / MarketDataProvider / 错误码常量
  valuation.py            # 十年/月末估值分位纯函数
  providers/
    tushare_quotes.py      # 行情主源（需 TUSHARE_TOKEN）
    tushare_common.py      # Token、限流、重试、错误分类和结果 metadata
    tushare_valuation.py   # daily_basic 当前/历史估值
    tushare_financials.py  # 财务指标、三大报表和分红事件
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

按需安装 TuShare 依赖：`pip install -e ".[tushare]"`。

TuShare 生产主源 API 与字段口径见 [`docs/TUSHARE_PRIMARY_PROVIDERS.md`](docs/TUSHARE_PRIMARY_PROVIDERS.md)。

## 测试

```bash
source .venv/bin/activate
pytest tests/ -v
```

## 开发流程

本仓库按 PM/codex/agy 三方协作流水线开发，细节见 [`CLAUDE.md`](CLAUDE.md)（Claude Code 专用）/ [`AGENTS.md`](AGENTS.md)（codex/agy 等通用 agent CLI 自动读取）。
