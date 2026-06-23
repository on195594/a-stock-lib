# AGENTS.md — a-stock-lib

跨 agent CLI（codex / agy / 其他）在本仓库工作时的约束。与 `CLAUDE.md` 内容实质相同，去掉了 Claude 专属表述。

## 项目是什么

A 股投研三系统（`a-stock-tracker`/`a-stock-research`/`a-stock-monitor`）共享的市场数据 Provider 原语包，从 `a-stock-tracker/lib/` 剥离。

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

- **不要修改 `~/a-stock-tracker/lib/`** —— 本包目前处于"从 tracker 复制+新增"阶段，tracker 还没有切换到依赖本包，必须保持零风险敞口
- **不要硬编码 `TUSHARE_TOKEN`** —— 运行时通过 `read_tushare_token()` 从 `~/a-stock-tracker/.env` 读取
- **不要在测试里发起真实网络请求** —— 第三方 SDK（`tushare`/`baostock`）的 import 必须留在方法内部（懒加载），测试通过给 Provider 构造函数传入 mock `client` 参数来隔离
- **所有新函数要有类型注解，不要裸 `raise Exception`** —— 失败路径统一返回 `MarketDataResult(status="failed", error_code=...)`
- **新增依赖前先确认必要性**，不要静默引入 `pyproject.toml` 之外的包

## 角色分工与流水线

本仓库由三方协作开发，不是单一 agent 独立完成：

- **PM（人类用户的委托方，负责任务下发与最终把关）**：拆解任务、下发带精确文件路径和接口契约的任务说明；调度审查；对发现的问题做判断——区分"新代码的真实缺陷"（要求直接修）与"迁移自旧系统的预存缺陷"（记入硬化清单，不在搬运任务里顺手改）；独立验证后才 commit；最终的文档更新和复盘由 PM 执行
- **codex（主力开发者）**：写实现代码和测试。如果 sandbox 限制了网络访问或 `.git` 写入，这是预期边界，不需要绕过——把环境相关的步骤（装依赖、commit）明确报告给 PM，由 PM 接手
- **agy（代码审查/质量负责人）**：做对抗性审查，只指出真实存在的问题，给出文件行号和具体修复建议；审查重点是边界条件、异常处理完整性、是否静默吞错误、类型设计合理性

**流水线**：写代码 → 独立验证 → （新代码）审查 → 有问题直接修+补回归测试 → 复查决定是否需要再来一轮（最多 2 轮）→ 仍卡住升级给用户。

## Commit 规范

`类型: 中文描述`（`feat`/`fix`/`refactor`/`docs`/`chore`），与 `a-stock-tracker` 保持一致。commit 本身由 PM 执行。
