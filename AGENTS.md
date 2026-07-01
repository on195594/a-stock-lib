# AGENTS.md — a-stock-lib

跨 agent CLI（codex / agy / 其他）在本仓库工作时的约束。与 `CLAUDE.md` 内容实质相同，去掉了 Claude 专属表述。

## 项目是什么

A 股投研三系统（`a-stock-tracker`/`a-stock-research`/`a-stock-monitor`）共享的市场数据 Provider 原语包，从 `a-stock-tracker/lib/` 剥离。

当前状态（2026-07-01）：本仓库版本为 `0.2.0`。Phase 1-4（核心包/research行业Provider接入/本包硬化/tracker切换）均已完成并提交，含 BaoStock fallback 进程挂死风险隔离超时加固。2026-06-29 完成三轮技术债清理（P0/P1/Step A，详见 CHANGELOG）。2026-07-01 完成 `contracts.py`（LLM输出→代码消费边界类型+标签解析）与 `prompts/` canonical 源+渲染脚本，发布 `0.2.0`；a-stock-research `cache.py` 已硬切换主观分项证据校验到新解析器（旧 `validate_subjective_evidence` 已删除）。a-stock-tracker 与 a-stock-research 均已升级并消费 `a-stock-lib==0.2.0`。全量测试 `99 passed`。

Phase 3b（周期位置判断结构化校验接线，2026-07-01同日完成）：`prompts/` 渲染的 `AGENTS.md` 首次真正落地到 a-stock-research 并验证 codex 会自动读取（此前只验证过 agy）；`contracts.parse_cycle_stage_tag` 已接入 a-stock-research 的 `cmd_set_analysis`（不是 `cmd_checklist`——`cmd_checklist` 只对 A/C/F 框架生效，而周期位置判断必做的是 C/D/B，二者交集仅 C 一个框架，接 checklist 无法形成对 B/D 的真正约束），C/D/B 框架均为 fail-closed。这部分代码改动全部发生在 a-stock-research 仓库，本仓库自身代码未变。`cmd_checklist` 里 C 框架的 warn-only 提前反馈 UX 仍标记为 stretch，未实施。

权威文档：
- 架构决策 → `docs/design/2026-06-22-three-system-restructure-design.md`
- 任务拆解/验收标准 → `docs/plans/2026-06-23-a-stock-lib-shared-package-plan.md`

## 运行与测试

```bash
cd ~/a-stock-lib && source .venv/bin/activate
pytest tests/ -v
```

修改代码后必须保证全量测试通过，再交回给 PM。

## 全局约束

- **不要直接修改 `~/a-stock-tracker/` 内代码** —— 虽然 tracker 已经完成切换并依赖本包，但因为 tracker 工作区当前有既有未提交改动，在没有 PM 明确授权的情况下，禁止直接修改 tracker。
- **不要硬编码 `TUSHARE_TOKEN`** —— Provider 的 token 优先级为构造参数显式传入 > 环境变量 `TUSHARE_TOKEN` > `read_tushare_token()` 从 `~/a-stock-tracker/.env` 读取（路径可通过 `env_path` 覆盖）。`tushare_quotes.py` 已在 Phase 3 统一到这个模式。
- **不要在测试里发起真实网络请求** —— 第三方 SDK（`tushare`/`baostock`）的 import 必须留在方法内部（懒加载），测试通过给 Provider 构造函数传入 mock `client` 参数来隔离
- **所有新函数要有类型注解，不要裸 `raise Exception`** —— 失败路径统一返回 `MarketDataResult(status="failed", error_code=...)`
- **新增依赖前先确认必要性**，不要静默引入 `pyproject.toml` 之外的包

## 项目专属编码规范（2026-06-23 agy基于现有代码模式提炼）

1. **第三方SDK调用必须有完整异常屏障**：触发真实网络交互的SDK调用必须完整包在`try...except Exception`内，统一转译成`MarketDataResult(status="failed", error_code=...)`，不让原生异常越过Provider边界
2. **本地缓存文件必须原子写入**：用"写临时文件→`fsync`→`Path.replace()`"模式（参考`tushare_fundamentals.py`的`_write_cache`），不用裸`open("w")`覆盖写——本包会被多进程同时导入，覆盖写期间另一进程可能读到截断的残缺文件
3. **第三方SDK的import必须懒加载在方法内部**，且构造函数保留`client: Any | None = None`注入入口
4. **单日时点查询要做向前回溯的降级语义**：停牌/节假日缺数据时不直接`failed`，向前找最近有效交易日，`status="degraded"`+真实`freshness_days`，让调用方自行决定能否接受

## 角色分工与流水线

本仓库由三方协作开发，不是单一 agent 独立完成：

- **PM（人类用户的委托方，负责任务下发与最终把关）**：拆解任务、下发带精确文件路径和接口契约的任务说明；调度审查；对发现的问题做判断——区分"新代码的真实缺陷"（要求直接修）与"迁移自旧系统的预存缺陷"（记入硬化清单，不在搬运任务里顺手改）；独立验证后才 commit；最终的文档更新和复盘由 PM 执行
- **codex（主力开发者）**：写实现代码和测试。如果 sandbox 限制了网络访问或 `.git` 写入，这是预期边界，不需要绕过——把环境相关的步骤（装依赖、commit）明确报告给 PM，由 PM 接手
- **agy（代码审查/质量负责人）**：做对抗性审查，只指出真实存在的问题，给出文件行号和具体修复建议；审查重点是边界条件、异常处理完整性、是否静默吞错误、类型设计合理性

**流水线**：写代码 → 独立验证 → （新代码）审查 → 有问题直接修+补回归测试 → 复查决定是否需要再来一轮（最多 2 轮）→ 仍卡住升级给用户。

## Commit 规范

`类型: 中文描述`（`feat`/`fix`/`refactor`/`docs`/`chore`），与 `a-stock-tracker` 保持一致。commit 本身由 PM 执行。
