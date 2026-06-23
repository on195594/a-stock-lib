# CLAUDE.md — a-stock-lib

## 项目简介

A 股投研三系统（`a-stock-tracker`/`a-stock-research`/`a-stock-monitor`）共享的市场数据 Provider 原语包。从 `a-stock-tracker/lib/` 剥离，目标是消灭三套重复的行情/基本面抓取实现。

**文档指针**：
- 架构决策 / 为什么这么设计 → `docs/design/2026-06-22-three-system-restructure-design.md`
- 实施任务拆解 / 验收标准 → `docs/plans/2026-06-23-a-stock-lib-shared-package-plan.md`
- 跨 agent CLI（codex/agy）的等价约束 → `AGENTS.md`（内容与本文件实质重叠，去掉 Claude 专属表述）

---

## 路径与运行

```bash
cd ~/a-stock-lib
source .venv/bin/activate

pytest tests/ -v           # 改动前必须全通过
python3 -m build           # 产出版本化 wheel（消费方安装这个，不用 -e 软链接）
```

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `a_stock_lib/market_data.py` | Provider 协议原语：`MarketDataResult`/错误码常量/`CompositeMarketDataProvider`/`normalize_bars_result`/`exception_result`。纯函数+无 IO 副作用，不依赖任何具体数据源 SDK |
| `a_stock_lib/providers/tushare_quotes.py` | 行情主源（需 `TUSHARE_TOKEN`），从 tracker 原样迁移 |
| `a_stock_lib/providers/baostock_quotes.py` | 行情 degraded fallback，从 tracker 原样迁移 |
| `a_stock_lib/providers/tushare_fundamentals.py` | 全市场行业分类批量拉取 + 本地 JSON 缓存（30天TTL），全新代码，替代不稳定的 AKShare `stock_individual_info_em` |

---

## 安全红线

- **禁止修改 `~/a-stock-tracker/lib/`** —— 在 Phase 4（tracker 切换）之前，tracker 必须保持零风险敞口，继续用自己本地的 `lib/` 跑生产；本包只做"复制+新增"，不做"挪走"
- **`TUSHARE_TOKEN` 禁止硬编码** —— 运行时从 `~/a-stock-tracker/.env` 读取（`read_tushare_token()`），路径可通过构造参数覆盖，三个消费方共用同一份 token
- **测试禁止发起真实网络请求** —— `tushare`/`baostock` SDK 在 Provider 内部是懒加载（方法内 `import`，不是模块顶层），测试用注入 `client` 参数的方式 mock，不依赖真实 SDK 包安装
- **新增函数必须有类型注解，禁止裸 `raise Exception`** —— 失败路径统一收敛成 `MarketDataResult(status="failed", error_code=...)`，不让异常裸露给调用方

---

## 开发流程：PM / codex / agy 三方流水线

本仓库的开发不是我（Claude）独立写代码，而是按下面的角色分工协作：

- **PM（我，技术总负责人）**：理解需求、拆解任务、给 codex 写清晰可执行的任务 prompt（必须包含精确文件路径、Consumes/Produces 接口契约、验收标准）；调度 agy 做独立代码审查；对 agy 发现的问题做判断——区分"新代码引入的真实缺陷"（要求 codex 直接修）和"迁移自旧系统的预存缺陷"（记入对应阶段的硬化清单，不在搬运任务里顺手改，避免新旧包行为在迁移窗口内出现未经验证的偏差）；独立验证 codex/agy 的报告（不轻信"测试全过"的转述，自己跑一遍确认）；最终的 commit、文档更新、阶段性复盘都由我审批和执行
- **codex（主力开发者）**：实际写实现代码和测试。codex 的 sandbox 天然无法访问网络（pip install 会失败）、也无法写 `.git`（commit 会失败）——这是预期行为，不是 bug，对应的工作（装依赖、跑独立验证、git commit）由 PM 接手，不需要 codex 想办法绕过 sandbox
- **agy（代码审查与质量负责人）**：对新写的代码做对抗性审查，要求"只指出真实存在的问题，给出文件行号和具体修复建议，不要泛泛而谈"。审查范围：边界条件、异常处理是否完整、是否有静默吞错误的情况、类型设计是否合理

**流水线顺序**：codex 写代码+测试 → PM 独立验证（重新跑一遍测试，不只看 codex 的报告） → 如果是非纯迁移的新代码，派给 agy 做审查 → agy 有发现时 codex 直接修 + 补回归测试 → PM 复查决定是否需要再来一轮（**最多 2 轮**） → 仍卡住则升级给用户决策，不无限循环

**PM 的授权范围**：在本项目（`a-stock-lib`）内，PM 有 commit 的 standing authorization，不需要逐次向用户确认。但以下操作仍属于更高风险层级，动手前必须先说明并等待用户确认：force-push、`git reset --hard`、删除分支、数据库结构变更（本项目目前无数据库）、生产配置改动。这个授权范围不延伸到 `a-stock-tracker` 或其他项目。

**Commit 规范**：延续 `a-stock-tracker` 的风格，`类型: 中文描述`（`feat`/`fix`/`refactor`/`docs`/`chore`）。
