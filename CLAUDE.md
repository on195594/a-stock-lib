# CLAUDE.md — a-stock-lib

## 项目简介

A 股投研三系统（`a-stock-tracker`/`a-stock-research`/`a-stock-monitor`）共享的市场数据 Provider 原语包。从 `a-stock-tracker/lib/` 剥离，目标是消灭三套重复的行情/基本面抓取实现。

**当前状态（2026-09-12）**：`0.7.0` 已发布，提供 A-F 逐项 typed owner contract 与 cache-only 行业映射读取入口。**a-stock-tracker** 与统一的 **`a-stock-agent-skills` runtime** 已通过下游 gate，并固定不可变 GitHub Release wheel 与 SHA-256 `7c4a16d452f34574584531bab6fe9d150f3cb844e5c9b2fe072295f6bb2ee385`；Agent prompt、rubric 和安装生命周期只归 `/home/lin/a-stock-agent-skills` 所有。

**文档指针**：
- 架构决策 / 为什么这么设计 → `docs/design/2026-06-22-three-system-restructure-design.md`
- 实施任务拆解 / 验收标准 → `docs/plans/2026-06-23-a-stock-lib-shared-package-plan.md`
- 跨 agent CLI 的精简仓库边界 → `AGENTS.md`；Claude 专属流程保留在本文件
- 发版全流程固定清单（build wheel → 装 tracker/agent-skills runtime → 跑消费方测试 → 同步文档） → `docs/RELEASE_CHECKLIST.md`

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
| `a_stock_lib/market_data.py` | Provider 协议原语：`MarketDataResult`、错误码常量和 `MarketDataProvider` 协议。纯类型/数据结构，不依赖具体 SDK |
| `a_stock_lib/contracts.py` | 六框架路由、周期与主观证据 typed contract |
| `a_stock_lib/framework_scoring.py` | A-F 基本面 60 分 report-only 纯函数及动态规则哈希 |
| `a_stock_lib/providers/tushare_quotes.py` | 行情主源（需 `TUSHARE_TOKEN`），已完成 Phase 3 token 来源、schema、异常分类硬化 |
| `a_stock_lib/providers/tushare_fundamentals.py` | 全市场行业分类批量拉取 + 本地 JSON 缓存（30天TTL），全新代码，替代不稳定的 AKShare `stock_individual_info_em` |
| `a_stock_lib/providers/tushare_common.py` | TuShare Token、进程级限流、typed 网络重试、错误分类、请求指纹与结果 metadata |
| `a_stock_lib/providers/tushare_valuation.py` | `daily_basic` 全市场单日与单股历史估值 Provider |
| `a_stock_lib/providers/tushare_financials.py` | 财务指标、三大报表与分红事件 Provider |
| `a_stock_lib/valuation.py` | 十年窗口、月末采样、最少 60 月的估值分位纯函数 |

---

## 安全红线

- **禁止直接修改 `~/a-stock-tracker/` 内代码** —— 虽然 tracker 已经完成切换并依赖本包，但因为 tracker 工作区当前有既有未提交改动，在没有 PM 明确授权的情况下，禁止直接修改 tracker。
- **`TUSHARE_TOKEN` 禁止硬编码** —— Provider 的 token 优先级为构造参数显式传入 > 环境变量 `TUSHARE_TOKEN` > `read_tushare_token()` 从 `~/a-stock-tracker/.env` 读取，路径可通过 `env_path` 覆盖，三个消费方共用同一份 token。`tushare_quotes.py` 已在 Phase 3 统一到这个模式。
- **测试禁止发起真实网络请求** —— `tushare` SDK 在 Provider 内部是懒加载（方法内 `import`，不是模块顶层），测试用注入 `client` 参数的方式 mock，不依赖真实 SDK 包安装
- **新增函数必须有类型注解，禁止裸 `raise Exception`** —— 失败路径统一收敛成 `MarketDataResult(status="failed", error_code=...)`，不让异常裸露给调用方

---

## 项目专属编码规范

全局通用规范（PascalCase类/snake_case函数/函数≤50行用卫语句/logger禁print/dataclass优先/自定义异常禁裸raise Exception）同样适用本项目。以下4条是这个项目特有的、通用规范没覆盖的补充（2026-06-23 agy基于现有代码模式提炼，覆盖"外部数据源接入层"特有的问题）：

1. **第三方SDK调用必须有完整异常屏障，统一转译成`MarketDataResult`**：所有触发真实网络交互的SDK调用（及紧邻的入参清洗逻辑），必须完整包在`try...except Exception`内，转译成`MarketDataResult(status="failed", error_code=...)`。不能让`ConnectionError`/`ValueError`等原生异常越过Provider边界直接抛给业务方——上层消费方不应该被迫依赖`tushare`的异常类型来写自己的`except`。
2. **本地缓存文件必须原子写入**：涉及把数据落地到本地 JSON/CSV 等缓存文件的逻辑，必须用"写临时文件完整内容→`fsync`→`Path.replace()`原子替换"的模式（参考`tushare_fundamentals.py`的`_write_cache`），不能用裸的`open("w")`覆盖写——本包会被多个进程同时导入，覆盖写期间另一个进程读到的可能是被截断的残缺文件。
3. **第三方SDK的import必须懒加载在方法内部，且保留`client`注入入口**：`tushare`不能出现在模块顶层import，必须在用到的方法内部按需`import`；构造函数必须保留`client: Any | None = None`参数用于测试注入mock，不依赖真实SDK包安装就能跑单测。
4. **单日时点查询要做向前回溯的降级语义，不能直接报失败**：查某个确切交易日的数据（如`fetch_score_price`）如果恰逢停牌/周末/节假日缺数据，不应该直接`status="failed"`，而要向前找最近一个有效交易日的数据，`status="degraded"`并带上真实的`freshness_days`，让调用方自己决定能不能接受这个陈旧度——A股节假日调休复杂、停牌情况多，这条降级逻辑应该收敛在Provider层，不要让三个消费方各自重复写日历兜底代码。

---

## 开发流程：PM / codex / agy 三方流水线

本仓库的开发不是我（Claude）独立写代码，而是按下面的角色分工协作：

- **PM（我，技术总负责人）**：理解需求、拆解任务、给 codex 写清晰可执行的任务 prompt（必须包含精确文件路径、Consumes/Produces 接口契约、验收标准）；调度 agy 做独立代码审查；对 agy 发现的问题做判断——区分"新代码引入的真实缺陷"（要求 codex 直接修）和"迁移自旧系统的预存缺陷"（记入对应阶段的硬化清单，不在搬运任务里顺手改，避免新旧包行为在迁移窗口内出现未经验证的偏差）；独立验证 codex/agy 的报告（不轻信"测试全过"的转述，自己跑一遍确认）；最终的 commit、文档更新、阶段性复盘都由我审批和执行
- **codex（主力开发者）**：实际写实现代码和测试。codex 的 sandbox 天然无法访问网络（pip install 会失败）、也无法写 `.git`（commit 会失败）——这是预期行为，不是 bug，对应的工作（装依赖、跑独立验证、git commit）由 PM 接手，不需要 codex 想办法绕过 sandbox
- **agy（代码审查与质量负责人）**：对新写的代码做对抗性审查，要求"只指出真实存在的问题，给出文件行号和具体修复建议，不要泛泛而谈"。审查范围：边界条件、异常处理是否完整、是否有静默吞错误的情况、类型设计是否合理

**流水线顺序**：codex 写代码+测试 → PM 独立验证（重新跑一遍测试，不只看 codex 的报告） → 如果是非纯迁移的新代码，派给 agy 做审查 → agy 有发现时 codex 直接修 + 补回归测试 → PM 复查决定是否需要再来一轮（**最多 2 轮**） → 仍卡住则升级给用户决策，不无限循环

**PM 的授权范围**：在本项目（`a-stock-lib`）内，PM 有 commit 的 standing authorization，不需要逐次向用户确认。但以下操作仍属于更高风险层级，动手前必须先说明并等待用户确认：force-push、`git reset --hard`、删除分支、数据库结构变更（本项目目前无数据库）、生产配置改动。这个授权范围不延伸到 `a-stock-tracker` 或其他项目。

**Commit 规范**：延续 `a-stock-tracker` 的风格，`类型: 中文描述`（`feat`/`fix`/`refactor`/`docs`/`chore`）。


<!-- ai-collab:routing -->
## AI协作模式（ai-collab）
本项目采用 ai-collab 三方协作模式（Claude=PM/架构师，codex=执行，QA工具=审查）。
新会话只要看到本项目有 `.claude/ai-collab/config.yaml`，对多步骤编码任务默认
调用 collab-pipeline skill 执行"实现→审查→提交"循环；完成一个完整plan或一批
任务后调用 collab-retro skill 复盘。配置与历史记录见 `.claude/ai-collab/`。
<!-- /ai-collab:routing -->
