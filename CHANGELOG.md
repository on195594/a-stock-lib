# Changelog

## [0.2.0] — 2026-07-01

### Added
- `a_stock_lib/contracts.py`：新增 `FrameworkKey`/`FrameworkDecision`/`CycleStage`/`CycleStageAssessment`/`SubjectiveCategory`/`RatingTier`/`EvidenceConfidence`/`SubjectiveAssessment` 类型，正式收编"LLM 主观判断→代码消费"边界；`parse_cycle_stage_tag`/`parse_subjective_assessment_tags` 提供内嵌结构化标记语法解析，替代 a-stock-research 现有的自由文本填空/正则扫描方案。`SubjectiveAssessment.confidence` 目前只解析/验证，无下游消费方；`FrameworkDecision` 目前仅为类型占位，尚未实现对应解析器。
- `a_stock_lib/prompts/`：canonical prompt 片段（`fragments/*.md`）+ sha256 漂移检测（`manifest.py`）+ `scripts/render_prompts.py` 渲染脚本，产出 Claude 用 `SKILL.md` 等价文本与新 `AGENTS.md`（供 codex/agy 未来跑同一套研究流程）。
- `tests/test_contracts.py`（18 个）、`tests/test_render_prompts.py`（12 个）。

### Changed
- `a_stock_lib/__init__.py`、`pyproject.toml`：版本从 `0.1.3` 升至 `0.2.0`（新增公开 API 面，非补丁号）。

### 技术债/加固（collab-pipeline 两轮审查发现并修复）
- `contracts.py` 正则解析 3 处边界问题：分类名贪婪匹配吞掉前置中文散文导致合法标签被静默丢弃、标签体在引号内 `]` 处误截断、引号内容不支持嵌入换行。
- `render_prompts.py` 的 `replace_region` 补齐标记唯一性校验（原先只查"是否存在"不查"是否唯一"，标记重复会静默拼接到错误位置）；`write_text_atomic` 与 `manifest.py` 记录的 hash 值补齐回归测试。

全量测试 `92 passed`。

### collab-pipeline 执行复盘（Phase 1/2/3a，2026-07-01）
- **agy 审查质量**：本轮2次独立审查，共10条发现，9条有效/1条不确定（判定"unreliable"未出现）——延续项目历史高可信度记录。Phase 1 复查阶段agy自己提出的第4个发现（未闭合引号跨标签吞噬）经PM实测复现不成立（返回安全空列表），未追加第3轮修复；Phase 3a 审查提出的2条"Critical"经PM核实均非真实阻塞（a-stock-lib安装状态已提前验证；"格"档要求填证据字段不构成矛盾），但审查本身仍揭示了真实的文档滞后问题（a-stock-lib CLAUDE.md/AGENTS.md/README.md 停留在0.1.3表述）。
- **执行偏差（重复出现）**：`codex:codex-rescue` 子agent本轮7次调度中每次都默认把 `codex exec` 丢进后台就返回，且被追问进度时明确拒绝轮询（"polling...is out of scope for this subagent"）。每次都靠PM追发一条"请同步执行"消息补救，本轮已作为skill-patch提案修复。
- **真实生产风险的发现方式**：Phase 3a 原计划里"切换后跑 `cache.py clear` 清理"这一步，在真正执行前被PM直接读源码发现远比预期破坏性大（清空整个基本面缓存或某股票全部历史，而非只清当天记录）——不是靠agy审查发现，而是PM在派发任务前的例行代码核对环节主动挖出来的。已改为精确SQL按code+当天日期删除，只影响2条记录。
- **跨仓库改动的审查覆盖**：Phase 3a 是本轮唯一实际改动生产代码（a-stock-research）的部分，虽然该仓库没有自己的ai-collab配置，仍额外派了一轮agy审查（未走标准record-run/record-review记账，因为项目边界不在a-stock-lib内）。

### Phase 3b 执行复盘（周期位置判断结构化校验接线，2026-07-01）
- **首次真实下游消费**：`prompts/` 的 `AGENTS.md` 渲染目标此前只在 scratch 环境验证过等价性，本轮首次真正落地到 a-stock-research 仓库并提交；同时验证了 codex（不只是 agy）会自动发现并遵循 AGENTS.md——此前设计文档只对 agy 做过实测。
- **落地前发现的跨阶段缺口**：AGENTS.md 落地审查时发现渲染结果会把 canonical fragment 里已经写好的周期位置结构化标签语法带出来，但生产 SKILL.md 和 cache.py 都还没有对应的解析/校验实现（Phase 3b 此前一直被列为"暂不包含"）——是逐区域 diff 出来的，不是先假设没问题就直接提交。
- **两轮 collab-adversarial-decision 收敛**：`cmd_checklist` vs `cmd_set_analysis` 接入点选择、fail-closed vs warn-only 分级策略，均经 codex+agy 独立视角一致收敛，决策记录见 `decisions.jsonl`。分级策略原定 C 直接 fail-closed / B-D 先观察后切换，用户随后明确要求跳过观察期直接对 B/D 同步 fail-closed。
- **跨仓库实现边界**：本轮实际代码改动（SKILL.md 语法切换、cmd_set_analysis 校验、AGENTS.md 落地）全部发生在 a-stock-research 仓库（该仓库无自己的 ai-collab 配置），PM 直接实现+自测，未走 collab-pipeline 的 codex 派发循环。

## [0.1.3] — 2026-06-29

### Added
- `a_stock_lib/fetcher_utils.py`：新增 `detect_split_ratio` 共享实现，统一送转复权检测逻辑，消除 a-stock-research 与 a-stock-tracker 双份独立维护（历史第 4 次重复修复触发本次提取）。使用 `getattr` 防御性写法，行为优于原版本（非 DataFrame 输入静默返回 `(0.0, None)`）。
- `tests/test_fetcher_utils.py`：10 个单元测试，覆盖 None/空 DataFrame/未来除权日/年报前除权日/方案进度过滤/累计送转等边界条件。

### Changed
- `a_stock_lib/__init__.py`、`pyproject.toml`：版本从 `0.1.2` 升至 `0.1.3`。
- `providers/baostock_quotes.py`：拆分 `_normalize_baostock_bars`，将校验逻辑提取为独立辅助函数 `_check_baostock_df`（P1 技术债）。
- `market_data.py`：为 `CompositeMarketDataProvider.__init__` 补充 `-> None` 返回类型注解（P1 技术债）。

### Fixed
- `providers/tushare_quotes.py`：修复 `fetch_score_price`、`fetch_l3_bars`、`fetch_outcome_price` 三个方法中 `_parse_date` 调用裸异常逃逸问题（P0）；无效日期格式现返回 `MarketDataResult(status="failed", error_code=UNKNOWN_ERROR)`。
- `a-stock-tracker/lib/fetcher.py`（消费方）：
  - `timed_call_with_retry`：`max_retries=0` 时 `for` 循环不执行导致 `result` 未绑定的 `UnboundLocalError`，在循环前初始化哨兵 `("ERROR", "no attempts made")`。
  - `avg_of`：补充 `if series is None: return None` 守卫，与 a-stock-research 版本行为对齐。

### Infrastructure
- a-stock-research `fetcher.py`、a-stock-tracker `lib/fetcher.py`：各自删除约 40 行本地 `_detect_split_ratio` 实现，改为 `from a_stock_lib.fetcher_utils import detect_split_ratio as _detect_split_ratio`，调用点不变。
- Tracker venv 与系统 Python（user site-packages）均已安装 `a-stock-lib==0.1.3`。
- ai-collab state 补录：runs.jsonl（2 条）、qa-reliability.jsonl（1 条，agy verdict=reliable）。

### collab-pipeline 执行复盘
- **执行偏差**：codex 沙箱跨仓库路径写入被策略拒绝（a-stock-tracker 不在 project_root 内），Step C 改由 PM 直接执行。
- **agy 审查质量（Step C）**：3 条发现全部有效（0 幻觉），I-1 采纳（测试断言从类型检查升级为哨兵等值验证），m-1 采纳（注释说明 fn 在 max_retries=0 时不被调用），m-2 注记（负值 max_retries 隐式修复，不加测试）。
- **Step A**：PM 独立执行（改动等价于已审查的计划文档，未额外派 agy），10 个测试通过后直接提交。

## [0.1.2] — 2026-06-23

Phase 1-4 完成：Provider 层迁移、Provider 硬化（BaoStock 进程挂死隔离超时）、Tracker 切换消费 a-stock-lib。详见 `docs/plans/2026-06-23-a-stock-lib-shared-package-plan.md`。
