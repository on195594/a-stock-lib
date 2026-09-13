# a-stock-lib

A 股消费者共享的确定性领域与市场数据包。`a-stock-lib` 是跨 consumer 的 shared deterministic logic owner，避免评分、分类、估值和 Provider 语义出现多套实现。

## 为什么存在

详见设计文档：[`docs/design/2026-06-22-three-system-restructure-design.md`](docs/design/2026-06-22-three-system-restructure-design.md)。核心动机：三系统重复实现行情 Provider、AKShare 行业接口长期不稳定、止损系数差异化依赖脆弱的字符串反推框架。

## 当前状态（2026-09-13）

当前已发布版本为 `0.8.0`：保留 A-F typed threshold/classification 与 cache-only 行业映射公共合同，并删除已无生产调用方的 legacy report parser。GitHub Release wheel 的 SHA-256 为 `a811945b23d97eb121ff82d54bc0ba0810000a5379a9e9786fdcdc9220b30310`。

下游为 `a-stock-tracker` 与 `/home/lin/a-stock-agent-skills`；后者是 research/monitor/QA 与 runtime 的唯一 canonical carrier。

## 职责边界

### Domain

- `FrameworkKey`、`CycleStage`、`SubjectiveAssessment`；
- A—F threshold / classification 与 framework scoring；
- 估值纯函数。

### Data

- `MarketDataResult` 与 Provider contracts；
- TuShare adapters；
- provenance、freshness 与 cache failure semantics。

本仓库不拥有 holdings、L3、Tier、W1、Skill routing、Agent orchestration 或 SQLite portfolio state；这些 application policy 留在 consumer。

## 包结构

```
a_stock_lib/
  market_data.py          # MarketDataResult / MarketDataProvider / 错误码常量
  contracts.py            # 六框架路由、周期与主观证据 typed contract
  framework_scoring.py    # A-F 基本面60分 report-only 纯函数
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

## 六框架评分（report-only）

`a_stock_lib.framework_scoring.score_fundamentals()` 接受已结构化的客观指标、`SubjectiveAssessment` 和可选周期阶段，返回每个维度得分、60 分机械小计、缺失输入和红线。`complete=false` 或 `blocked=true` 的结果不得用于投资动作；本模块不写数据库、不计算择时/仓位，也未接入生产 tracker。

## 测试

```bash
source .venv/bin/activate
pytest tests/ -v
```

## 开发流程

本仓库按 PM/codex/agy 三方协作流水线开发，细节见 [`CLAUDE.md`](CLAUDE.md)（Claude Code 专用）/ [`AGENTS.md`](AGENTS.md)（codex/agy 等通用 agent CLI 自动读取）。
