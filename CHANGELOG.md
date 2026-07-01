# Changelog

## [0.2.0] — 2026-07-01

### Added
- `a_stock_lib/contracts.py`：新增 `FrameworkKey`/`FrameworkDecision`/`CycleStage`/`CycleStageAssessment`/`SubjectiveCategory`/`RatingTier`/`EvidenceConfidence`/`SubjectiveAssessment` 类型，正式收编"LLM 主观判断→代码消费"边界；`parse_cycle_stage_tag`/`parse_subjective_assessment_tags` 提供内嵌结构化标记语法解析，替代 a-stock-research 现有的自由文本填空/正则扫描方案。`FrameworkDecision.confident`/`SubjectiveAssessment.confidence` 目前只解析存储，无下游消费方。
- `a_stock_lib/prompts/`：canonical prompt 片段（`fragments/*.md`）+ sha256 漂移检测（`manifest.py`）+ `scripts/render_prompts.py` 渲染脚本，产出 Claude 用 `SKILL.md` 等价文本与新 `AGENTS.md`（供 codex/agy 未来跑同一套研究流程）。
- `tests/test_contracts.py`（18 个）、`tests/test_render_prompts.py`（12 个）。

### Changed
- `a_stock_lib/__init__.py`、`pyproject.toml`：版本从 `0.1.3` 升至 `0.2.0`（新增公开 API 面，非补丁号）。

### 技术债/加固（collab-pipeline 两轮审查发现并修复）
- `contracts.py` 正则解析 3 处边界问题：分类名贪婪匹配吞掉前置中文散文导致合法标签被静默丢弃、标签体在引号内 `]` 处误截断、引号内容不支持嵌入换行。
- `render_prompts.py` 的 `replace_region` 补齐标记唯一性校验（原先只查"是否存在"不查"是否唯一"，标记重复会静默拼接到错误位置）；`write_text_atomic` 与 `manifest.py` 记录的 hash 值补齐回归测试。

全量测试 `92 passed`。

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
