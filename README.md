# a-stock-lib

A 股共享的确定性计算与数据 Provider。只维护有真实消费者的公共语义，不承载产品流程或 Agent 调度。

## 项目分工

- **a-stock-lib**：行情/财务 Provider、来源与时效、A—F typed contract、基本面评分、估值与送转计算。
- **a-stock-agent-skills**：首次研究、持仓监控、文本 QA；持仓、风险与写入授权归其 runtime。
- **a-share-research**：引用核验型财报研究应用、历史报告与价格参考；直接消费本包的财务和估值 Provider，不承担持仓或账户写入。

保留独立包和版本锁定；当前直接消费者是上述两个应用。各自独立存储与发布，公共接口变更按实际影响验证两方。Research 优先复用现有 Provider，缺少的接口按其项目约束直接调用 TuShare；出现真实复用需求后再评估公共能力，不为共享搬迁应用代码。

三项目的[项目契约](https://github.com/on195594/a-share-research/blob/main/docs/project-contract.md)、[路线图](https://github.com/on195594/a-share-research/blob/main/docs/roadmap.md)和[实施计划](https://github.com/on195594/a-share-research/blob/main/docs/implementation-plan.md)统一维护在 `a-share-research/docs/`。报告只读复用仍为规划项，Lib 不承载其接口、研究流程或 Agent 调度。

`a-stock-tracker` 已停止，其未来消费和 MCP 接入计划已取消，只保留历史参考。历史 Tracker Framework A 已结案；本包现有 A—F 计算合同继续维护。

## 公共表面

| 模块 | 职责 |
|---|---|
| `market_data.py` | `MarketDataResult`、Provider 协议、错误码 |
| `contracts.py` | 框架、周期、主观证据 typed contract |
| `framework_scoring.py` | A—F 基本面 60 分 report-only 纯函数、规则哈希 |
| `valuation.py` / `fetcher_utils.py` | 估值分位、送转复权 |
| `providers/` | TuShare adapters、行业缓存、实时行情时效校验 |

来源、时间、缺失、降级和 fallback 必须可追溯；Provider 错误结构化，缓存原子写入，SDK 懒加载且可注入。评分不完整或被阻断时不得用于投资动作；本包不做择时、仓位、状态写入或收益承诺。

## 开发与发布

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest tests -q
git diff --check
```

TuShare 为可选依赖：`pip install -e '.[tushare]'`。消费者使用版本化 wheel，不使用源码软链接。源码版本以 `pyproject.toml` 和 `a_stock_lib/__init__.py` 为准；部署版本以各消费者的锁文件和部署记录为准，不能由源码版本推断。

- [开发约束](AGENTS.md)
- [Provider 字段与数据语义](docs/TUSHARE_PRIMARY_PROVIDERS.md)
- [发版与消费方验证](docs/RELEASE_CHECKLIST.md)
- [变更历史](CHANGELOG.md)；`docs/specs/` 保留合同依据，`docs/reviews/` 保留审查证据。

## 历史恢复

已完成的 2026-06/07 迁移设计、四份计划和 `HANDOFF.md` 不再作为开发入口，内容由 Git 历史保存。清理前快照：`6dc856ea1183fe6f6c8ff9f5201b0c920b5008ec`；例如 `git show 6dc856ea:HANDOFF.md`。历史日志中的旧路径按同样方式恢复，不重新执行旧安装、cron 或多 Agent 流程。

旧 `.claude/ai-collab/` 配置/流水线状态和已退休文本 parser 的容错 Spec 也移出活动树；删除前快照为 `d2f62b554fdcceda0f15eee89df3f2e66ce8198a`。当前只保留 typed contract，不恢复旧标签 parser 或客户端专属治理入口。
