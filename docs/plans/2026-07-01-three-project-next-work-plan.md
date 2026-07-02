# 三项目下一步工作计划

日期：2026-07-01
Owner：Hermes PM
状态：active cross-project plan

## 当前统一基线

| 项目 | 当前状态 | 证据 |
|---|---|---|
| `a-stock-lib` | 共享 Provider、contracts、prompts canonical 源；版本 `0.2.0` | 本仓库全量测试 `99 passed`；`README.md` / `CHANGELOG.md` / `AGENTS.md` 已同步 |
| `a-stock-tracker` | 已锁定 `a-stock-lib==0.2.0`；继续 Phase 6 report-only | `requirements.txt` 版本锁定；tracker 测试 `205 passed`；`docs/project-status.md` 已同步 |
| `a-stock-research` | 已消费 `a-stock-lib==0.2.0` 的行业 Provider、拆股工具、主观标签 parser、周期标签 parser | `fetcher.py` / `cache.py` 已接入；`docs/project-status.md` 已新增 |
| `a-stock-monitor` | 无独立代码仓；通过 research/cache 和 skill 流程间接消费数据 | 暂不单独规划代码任务，随 research 流程约束同步 |

## PM 原则

- 三项目继续保持横向解耦：`a-stock-lib` 只放共享原语，tracker/research 只保留各自业务编排。
- 版本变更必须同步更新消费方文档和安装状态，不再让 tracker/research 停留在旧版本口径。
- Framework B 仍不得生产写入；Phase 6 只做 report-only 观察和样本复核。
- 涉及真实生产 `cache.db`、cron、Telegram 推送、watchlist、权重或 schema 的变更，必须单独确认任务边界。

## 下一步任务队列

| 优先级 | 任务 | 所属项目 | 说明 | Exit criteria |
|---|---|---|---|---|
| P0 | 状态文档同步机制 | 三项目 | 每次共享包 release 后同步 lib/tracker/research 的状态页、依赖版本、测试基线 | 三个项目文档版本一致，无旧 `0.1.x` 当前口径残留 |
| P1 | Phase 6 weekly PM loop | `a-stock-tracker` | 持续任务；2026-07-02 已完成一轮并修复 cache/timeout 问题，后续继续复核 weekly/daily/outcome、`READY_CRON`、`accuracy-report` | 日志正常则维持 report-only；异常则先修行情/cron |
| P1 | Framework B label review 准备 | `a-stock-tracker` | 阻塞于自然结案；2026-07-26 后检查 B label 30d 已结案样本、overdue、行业覆盖、B-A delta | 满足门槛后写 review 文档；仍不直接上线 B 生产写入 |
| P1 | C 框架 checklist 提前反馈 | `a-stock-research` | 2026-07-02 已实施：`cmd_checklist` 对 C 框架缺失周期标签做 warn-only 提示；B/D 仍由 `cmd_set_analysis` fail-closed | 用户在 checklist 阶段可提前看到 C 框架周期标签缺失提示 |
| P1 | parser 容错策略 spec | `a-stock-lib` → `a-stock-research` | 2026-07-02 已定 strict-v1：不支持空格、全角括号/引号等变体；research 不补临时正则 | spec 已落地，后续若放宽必须先改 `a-stock-lib/contracts.py` 与对抗测试 |
| P1 | `watchlist-refresh` 超时保护 | `a-stock-research` | 2026-07-02 已实施：cache 命令外层 timeout、单股 Claude `timeout -k` 强杀兜底、bash 测试覆盖 | 脚本有外层 timeout/退出码测试，真实 cron 风险被隔离 |
| P2 | 数据库路径防呆 | `a-stock-research` | CLI smoke test 曾误写生产库；需要减少 agent/PM 手工操作误用默认 `cache.db` 的概率 | 非 pytest CLI 操作前能明确显示或覆盖数据库路径 |
| P2 | release checklist 固化 | `a-stock-lib` | 把 build wheel、安装 tracker venv、安装 research Python、运行消费方测试、更新文档整理为固定清单 | 下次 `0.2.x` 发布可按清单执行，减少 downstream drift |

## 暂不推进

- 不调整 tracker `weights.json`。
- 不恢复 Framework B 生产 predictions。
- 不做 `a-stock-monitor` 独立代码化，除非它出现独立仓库或独立运行入口。
- 不把 parser 容错临时写在 research；共享契约问题必须先回到 `a-stock-lib`。
