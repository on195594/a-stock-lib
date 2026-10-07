# a-stock-lib

A 股共享的确定性计算与数据 Provider。只维护有真实消费者的公共语义，不承载产品流程或 Agent 调度。

## 项目分工

- **a-stock-lib**：行情/财务 Provider、来源与时效、A—F typed contract、基本面评分、估值与送转计算。
- **a-stock-agent-skills**：首次研究、持仓监控、文本 QA；持仓、风险与写入授权归其 runtime。
- **a-stock-tracker**：同业发现、个人研究记录、事实变化与隔离的机器研究；已合并原 screen，当前不直接依赖本包，不承担持仓或交易。Framework A 已结案，不恢复评分实验。

保留独立包和版本锁定；当前直接消费者是 agent-skills runtime。按真实调用维护公共语义，不为“共享”向 Tracker 重新添加依赖，也不合并数据库、发布或产品边界。

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
