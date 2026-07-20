# TuShare 生产主源共享数据合同

创建时间：2026-07-20  
状态：accepted for Phase 1 implementation  
目标版本：`a-stock-lib==0.4.0`

## 1. 决策

`a-stock-lib` 是 `a-stock-tracker`、`a-stock-research`、`a-stock-monitor` 与独立监控器共享的 Provider、错误语义和确定性派生计算载体。

本包不建立跨项目共享可写数据库，不拥有评分、持仓、告警或 cron。各消费方保存自己的业务缓存，通过本合同保持来源、口径和失败语义一致。

## 2. 已验证基线

| 运行环境 | a-stock-lib | tushare |
| --- | --- | --- |
| a-stock-tracker | 0.2.0 | 1.4.29 |
| a-stock-research | 0.3.0 | 1.4.29 |
| a-stock-lib 源码 | 0.3.0 | optional dependency 未锁版本 |

Phase 1 从源码 `0.3.0` 开发 `0.4.0`。不要求 tracker 先单独升级到 0.3.0；tracker 与 research 必须分别在隔离环境直接验证 0.4.0，随后再进入生产切换讨论。

购买 2000 积分后已真实验证以下接口可用：

- `daily_basic`
- `fina_indicator`
- `income`
- `balancesheet`
- `cashflow`
- `dividend`

TuShare 盘中实时行情、公告正文和新闻属于独立权限，不属于本合同。

## 3. Provider 边界

### 3.1 `TushareValuationProvider`

职责：

- 按 `trade_date` 获取全市场 `daily_basic`；
- 按 `ts_code + start_date + end_date` 获取单股历史估值；
- 校验 `ts_code`、交易日、数值范围和必需列；
- 返回原始日度估值观察，不负责写业务数据库。

最小字段：

```text
ts_code, trade_date, close,
pe, pe_ttm, pb, ps, ps_ttm,
dv_ratio, dv_ttm,
total_mv, circ_mv
```

`pe`/`pe_ttm` 对亏损公司为空是合法业务状态，不得转换为 0，也不得把整条记录判为抓取失败。

### 3.2 `TushareFinancialProvider`

职责：统一封装四个共享财务接口，但保留 endpoint 身份，不把不同报表拼成一条无来源宽表。

公开能力：

```text
fetch_indicator_history
fetch_income_history
fetch_balance_history
fetch_cashflow_history
```

统一输出必须包含以下可空公共键：

```text
ts_code, endpoint, ann_date, f_ann_date, end_date,
report_type, comp_type, end_type, update_flag
```

`income`、`balancesheet`、`cashflow` 官方输出提供全部上述报告键；`fina_indicator` 官方输出仅提供 `ts_code/ann_date/end_date/update_flag`，因此其 `f_ann_date/report_type/comp_type/end_type` 必须保持 `NULL`。接口缺少字段时记录字段级缺失，不得用其他报告期、其他 endpoint 或旧缓存静默补值。

### 3.3 `TushareDividendProvider`

职责：获取分红方案及实施事件，保留方案状态和关键日期。分红原始记录与 `daily_basic.dv_ttm` 不互相覆盖：前者是事件事实，后者是 TuShare 当日估值快照字段。

### 3.4 确定性估值派生

PE/PB 分位计算属于共享、纯函数、无 I/O 的确定性逻辑，应在本包实现，避免 tracker/research/monitor 各自维护算法。

输入：日度估值观察和 as-of date。  
输出至少包含：

```text
value
percentile
window_start
window_end
valid_months
coverage_status
```

算法合同：

1. 使用 as-of date 向前最多十年的数据；
2. 每月选择最后一个有效交易日；
3. PE_TTM 仅接受有限且大于 0 的值；
4. PB 仅接受有限且大于 0 的值；
5. 当前值与历史样本采用同一字段口径；
6. 少于 60 个有效月度样本时返回 `INSUFFICIENT_HISTORY`，不得输出可用于评分的分位；
7. 上市不足十年但达到 60 个样本时为 `SINCE_LISTING`；
8. 覆盖十年且样本合格时为 `FULL_10Y`；
9. 分位沿用 tracker 兼容口径：`count(history < current) / N * 100`，严格小于，不把等值样本计入；
10. 不得把 12 个月样本标为“十年分位”。

## 4. 统一结果合同

新 Provider 复用 `MarketDataResult`，不创建第二套结果抽象。metadata 至少包含：

```text
source
source_as_of
fetched_at
freshness_days
request_fingerprint
row_count
```

`source_as_of` 必须表示来源观察的实际可见日期，而不是财务报告期：估值使用 `trade_date`；三大报表使用非空 `f_ann_date` 优先、否则 `ann_date`；`fina_indicator` 使用 `ann_date`；分红使用 `imp_ann_date` 优先、否则 `ann_date`。估值派生的 `window_start/window_end` 也必须返回实际纳入计算的首末观察日。

失败结果至少包含：

```text
status=failed|degraded
error_code
sanitized error_message
source
fetched_at
```

建议新增或复用的错误类别：

```text
AUTH_MISSING
PERMISSION_DENIED
RATE_LIMITED
TIMEOUT
REMOTE_DISCONNECTED
EMPTY_RESPONSE
MISSING_COLUMNS
SCHEMA_CHANGED
SOURCE_STALE
INVALID_ARGUMENT
UNKNOWN_ERROR
```

任何错误信息不得包含 Token、完整请求头、`.env` 内容或代理凭据。

## 5. SDK、限流和重试

- `pyproject.toml` 的 tushare optional dependency 固定为 `tushare==1.4.29`；不新增第三方依赖。
- Provider 构造函数继续支持显式 `client` 注入，SDK import 保持懒加载。
- TuShare 1.4.29 在 API 失败时仅抛出 `Exception(result["msg"])`，服务端数字 code 已被 SDK 丢弃。因此不得声称可以可靠读取 40203 等原始 code。
- 客户端主动节流到不高于 180 次/分钟，并允许测试注入 clock/sleep；不得依赖触发服务端限流来调速。
- `requests.Timeout`、`ConnectionError` 等网络瞬态错误最多一次有界重试。
- 权限、积分、认证、参数和 schema 错误不重试。
- 对 SDK 泛型异常仅做经过测试的已知消息分类，同时保留脱敏后的原始消息；未知消息为 `UNKNOWN_ERROR`。
- 不复制 TuShare 私有 HTTP Client，不绕过 SDK 自建含 Token 的请求。

## 6. Point-in-time 合同

Provider 返回 TuShare 当前可见的历史记录，但不声称历史回填具备严格 PIT 语义。

消费方必须区分：

```text
backfilled_latest       # 今天回填得到的历史数据，可能包含后来更正
prospective_observed    # 正式采集日起真实观察并不可变保存的数据
```

规则：

- 回填记录不得用于覆盖历史预测或伪造历史时点可见数据；
- 三大报表的有效公告日为非空 `f_ann_date` 优先，否则 `ann_date`；`fina_indicator` 只能使用 `ann_date`；空字符串必须先规范为 `NULL`；
- 给定 score date，只能选择有效公告日不晚于 score date 的记录；
- 后续更正必须形成新的 observation，不覆盖旧 observation；
- `update_flag` 是来源字段，不足以单独证明完整的更正历史。

## 7. 缓存与持久化边界

- 本包不持有共享 SQLite；
- 新估值/财务/分红 Provider 不写 tracker 或 research 数据库；
- 现有行业 JSON 缓存可以保留，不扩展为跨项目综合数据库；
- 原始响应归档、checkpoint、幂等写入和 schema migration 由消费方负责；
- Provider 必须返回足够 metadata，使消费方能够构造 deterministic record key 和审计记录；
- deterministic record key 基于 endpoint、来源自然键和 canonical payload，不包含 run id 或 observed-at；消费方应把不可变数据记录与每次 observation event 分开保存。

## 8. 测试隔离

`tests/conftest.py` 应提供 autouse fixture，默认清除：

```text
TUSHARE_TOKEN
TG_TOKEN
TG_CHAT_ID
HTTPS_PROXY
HTTP_PROXY
ALL_PROXY
```

单元测试：

- 只使用 fake client；
- 不读取真实 `.env`；
- 不访问网络；
- 不写消费方数据库；
- time/sleep 必须可注入；
- 覆盖合法 PE 空值、停牌空日、字段缺失、限流、权限、网络错误和未知错误。

真实 Token smoke test 必须是显式命令，不属于默认 pytest，且只请求最小数据、不得打印凭据。

## 9. 版本与发布 Gate

发布 0.4.0 前必须满足：

1. a-stock-lib 全量单测通过；
2. 新增接口文档和 CHANGELOG；
3. wheel 构建成功；
4. tracker 隔离环境安装 0.4.0 并跑全量门禁；
5. research 隔离环境安装 0.4.0 并跑全量测试；
6. tracker/research 的实际 import 版本均打印为 0.4.0；
7. 不将 0.4.0 安装到生产环境，直到各自 shadow 通过并取得 cutover 确认。

## 10. 非目标

Phase 1 不做：

- 盘中实时行情替换；
- 新闻、公告正文或银行专属 NIM/NPL/拨备采集；
- 跨项目共享数据库；
- 评分权重修改；
- cron 修改；
- 历史预测重算；
- 生产 Token 或数据库写入。

## 11. Phase 1 验收命令

```bash
python -m pytest tests/ -q
python -m build
python -m compileall -q a_stock_lib
```

静态检查以本仓库已配置的门禁为准；不得以本轮迁移为由全仓格式化或修复无关既存类型债务。
