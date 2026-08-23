# a-stock-lib

A 股投研三系统（`a-stock-tracker` 评分管道 / `a-stock-research` 新股研究 / `a-stock-monitor` 持仓监控）共享的市场数据 Provider 原语包，从 `a-stock-tracker/lib/` 剥离出来，目标是让三个系统不再各自维护一份行情/基本面抓取逻辑。

## 为什么存在

详见设计文档：[`docs/design/2026-06-22-three-system-restructure-design.md`](docs/design/2026-06-22-three-system-restructure-design.md)。核心动机：三系统重复实现行情 Provider、AKShare 行业接口长期不稳定、止损系数差异化依赖脆弱的字符串反推框架。

## 当前状态（2026-08-23）

当前仓库版本 `0.6.0`：TuShare 行情统一复用 Provider base，行情/行业 metadata 完整化，并恢复 A—F 六框架的 report-only 基本面评分纯函数。生产消费者仍运行已验证的 `0.5.3`；`0.6.0` 尚未部署。

下游为 `a-stock-tracker` 与 `/home/lin/a-stock-agent-skills`；后者是 research/monitor/QA 与 runtime 的唯一 canonical carrier。

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
