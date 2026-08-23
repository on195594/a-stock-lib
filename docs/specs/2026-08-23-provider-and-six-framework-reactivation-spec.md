# Provider 统一与六框架评分路线重启规范

**日期：** 2026-08-23
**状态：** 已授权实施（仓库内，不含生产切换）

## 目标

1. 让 `TushareMarketDataProvider` 复用现有 `TushareProviderBase`，删除 token、client、限流、重试和异常分类的重复实现。
2. 补齐行情与行业 `MarketDataResult` 已有但此前未完整填充的 metadata。
3. 在 `a-stock-lib` 恢复 A/B/C/D/E/F 六框架的确定性基本面评分代码路径，作为纯函数、report-only 能力。

## 非目标

- 不修改 tracker 的生产 `weights.json`、Framework A daily、数据库、cron、Telegram、watchlist 或现有预注册裁决。
- 不部署新 wheel，不切换 tracker 或 agent runtime。
- 不回填或重算历史分析/预测。
- 不自动验证 LLM/人工证据的真实性；只接受调用方已经结构化的主观评级或数值输入。
- 不实现择时 20 分、仓位矩阵或自动交易动作。

## Provider 合同

- 行情 Provider 必须继承 `TushareProviderBase`，通过 `_request_frame()` 发起 TuShare 请求。
- 所有成功的行情/行业结果必须填充：`source`、`source_as_of`、`fetched_at`、`freshness_days`（有明确目标日或缓存年龄时）、`request_fingerprint`、`row_count`。
- 行情 `source_as_of` 为实际返回的最大交易日；标量结果继承上游 metadata。
- 行业远端结果以抓取日作为来源观察日；缓存结果继承抓取日、缓存年龄、确定性请求指纹和映射行数。
- 现有错误码、最近可用价格语义、OHLC/日期 fail-closed 行为保持不变。

## 六框架评分合同

### 公共输出

每次评分返回：

- framework key；
- 每个维度的输入来源、得分、满分与理由；
- 基本面小计（满分 60）；
- `complete` 与缺失维度；
- 红线触发列表。

任一必填维度缺失时 `complete=false`，不得把结果标记为可用于投资决策；仍可展示已计算维度以便补数。红线触发时 `blocked=true`，但保留机械分用于审计。

### 输入边界

- 数值输入只接受有限数；`NaN/Inf` 按缺失处理。
- 主观维度只接受现有 `SubjectiveAssessment`/`RatingTier`；优档满分、格档半分，缺失不猜测。
- C/D/B 周期或趋势折扣按当前 framework 文档执行；调用方负责提供已核验的周期、趋势、压力测试和同行分位输入。
- 每个框架严格保持当前基本面 60 分结构，不修改阈值和权重。

### 框架范围

- A：ROE、净利增长、负债、毛利率稳定性、护城河、行业地位；保留资本密集制造债务例外的结构化输入。
- B：仅商业银行；ROE、NIM 绝对值/趋势、不良率、拨备、护城河、行业地位；三项核心银行数据全缺时不完整。
- C：成熟/成长资源分支、周期折扣、压力后股息率、产量/储量兑现、储量竞争力、行业地位及红线。
- D：行业 ROE 分位、业务量增长、负债、压力后股息率、特许经营、行业地位及政策/周期折扣。
- E：ROE、净利增长、毛利率、存货周转、品牌渠道、行业地位及红线。
- F：收入增长、毛利率趋势、研发强度、订单月数/NRR、现金流质量、行业地位及红线。

## 验收

1. Provider 聚焦测试覆盖成功 metadata、缓存命中 metadata、无效参数和异常边界。
2. 六框架各至少一个满分/格档或折扣用例；另有缺失输入、边界阈值和红线用例。
3. `a-stock-lib` 全量 pytest、Ruff/format（若仓库配置）、build 与 `git diff --check` 通过。
4. tracker 与 agent-skills 不发生生产或运行时变更；如只读兼容测试可运行，则现有消费者测试保持通过。
5. 最终 diff 不包含既有 `AGENTS.md`、`CLAUDE.md` 用户修改。

## 停止条件

- 当前 A—F 文档存在无法唯一解释的阈值/权重冲突；
- 实现需要改变真实策略权重、数据库 schema 或生产路径；
- 无法用当前结构化输入表达某维度而必须从自然语言正则猜测。

遇到停止条件时保留 Provider/metadata 修复，只报告具体评分 blocker，不伪造实现。
