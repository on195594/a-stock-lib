# a-stock-lib

A 股共享的确定性计算与数据 Provider。只维护有真实消费者的公共语义，不承载产品流程或 Agent 调度。

## 项目分工

- **a-stock-lib**：行情/财务 Provider、来源与时效、A—F typed contract、基本面评分、历史估值数据与送转计算。
- **a-stock-agent-skills**：首次研究、持仓监控、文本 QA；持仓、风险与写入授权归其 runtime。
- **a-share-research**：引用核验型财报研究应用、历史报告与价格参考；直接消费本包的财务和估值 Provider，不承担持仓或账户写入。

保留独立包和版本锁定；当前直接消费者是上述两个应用。各自独立存储与发布，公共接口变更按实际影响验证两方。Research 优先复用现有 Provider，缺少的接口按其项目约束直接调用 TuShare；出现真实复用需求后再评估公共能力，不为共享搬迁应用代码。

三项目的[项目契约](https://github.com/on195594/a-share-research/blob/main/docs/project-contract.md)、[路线图](https://github.com/on195594/a-share-research/blob/main/docs/roadmap.md)和[实施计划](https://github.com/on195594/a-share-research/blob/main/docs/implementation-plan.md)统一维护在 `a-share-research/docs/`。报告只读复用仍为规划项，Lib 不承载其接口、研究流程或 Agent 调度。

`a-stock-tracker` 已停止，其未来消费和 MCP 接入计划已取消，只保留历史参考。历史 Tracker Framework A 已结案；本包现有 A—F 计算合同继续维护。

## 公共表面

| 模块 | 职责 |
|---|---|
| `market_data.py` | `MarketDataResult`、状态与错误码 |
| `contracts.py` | 框架、周期、主观证据 typed contract |
| `framework_scoring.py` | A—F 基本面 60 分 report-only 纯函数；规则哈希为 `RULE_VERSION` + 阈值表的规范化 JSON 摘要，固定规则哈希与显式边界、分支断言守护规则行为 |
| `fetcher_utils.py` | 送转复权（显式 `as_of`，兼容 TuShare/AKShare 字段） |
| `providers/` | TuShare adapters、行业缓存、实时行情时效校验；稳定导出见 `providers.__all__` |

来源、时间、缺失、降级和 fallback 必须可追溯；Provider 错误结构化，缓存原子写入，SDK 懒加载且可注入。评分不完整或被阻断时不得用于投资动作；本包不做择时、仓位、状态写入或收益承诺。

## 开发与验证

```bash
# 开发环境与依赖同步
uv sync --extra dev

# 运行全量测试
nice -n 15 uv run pytest -x

# 检查代码格式与发版一致性
python3 scripts/check_published_version_identity.py
git diff --check
```

TuShare 为可选依赖：`uv pip install -e '.[tushare]'`（或 `pip install -e '.[tushare]'`）。消费者使用版本化 wheel，不使用源码软链接。源码版本以 `pyproject.toml` 和 `a_stock_lib/__init__.py` 为准；部署版本以各消费者的锁文件和部署记录为准，不能由源码版本推断。

- [开发约束](AGENTS.md)
- [Provider 字段与数据语义](docs/TUSHARE_PRIMARY_PROVIDERS.md)
- [发版与消费方验证](docs/RELEASE_CHECKLIST.md)
- [变更历史](CHANGELOG.md)；`docs/specs/` 是历史合同依据，与当前源码或上述文档冲突时以后者为准。

## 历史快照

已完成的 2026-06/07 迁移设计、四份计划、`HANDOFF.md`、旧 AI 流水线配置和已退休文本 parser / 审查记录已移出活动树，由 Git 历史和归档 tag 保存。历史快照参考：`6dc856ea`（迁移设计）、`d2f62b55`（旧流水线）、`acabb35`（Tracker 审查记录）。当前分支只维护当前有效公共 typed contract 与 provider 契约。
