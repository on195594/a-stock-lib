# TuShare 生产主源 Provider API

适用版本：`a-stock-lib==0.6.3`

## 安装

```bash
pip install 'a-stock-lib[tushare]==0.6.3'
```

本版本固定 `tushare==1.4.29`。Token 优先级：构造参数 → `TUSHARE_TOKEN` → 显式 `env_path` 指向的文件。禁止在代码中硬编码 Token。

## 行情与行业

`TushareMarketDataProvider` 与其他 TuShare Provider 共用 `TushareProviderBase` 的 token、client、限流、typed retry、错误分类和请求指纹。成功行情以实际最大交易日作为 `source_as_of`；标量价格完整继承 bars 的 `source_as_of`、`freshness_days`、`request_fingerprint` 和 `row_count`。

`TushareFundamentalsProvider.fetch_industry_map()` 的远端与缓存命中结果都返回缓存年龄、确定性请求指纹和映射行数。行业接口没有官方业务日期，因此 `source_as_of` 保持 `None`；抓取时点只由 `fetched_at` 表示，不伪装成财报期或交易日。

## 估值

```python
from a_stock_lib.providers import TushareValuationProvider

provider = TushareValuationProvider()
daily = provider.fetch_daily_basic_by_trade_date("2026-07-17")
history = provider.fetch_valuation_history(
    "603606",
    "2016-07-18",
    "2026-07-17",
)
```

返回 `MarketDataResult[pandas.DataFrame]`，字段包括：

```text
ts_code, trade_date, close,
pe, pe_ttm, pb, ps, ps_ttm,
dv_ratio, dv_ttm, total_mv, circ_mv
```

单位与空值遵循官方 `daily_basic`：

- `dv_ratio/dv_ttm`：百分比；
- `total_mv/circ_mv`：万元；
- 亏损公司的 `pe/pe_ttm` 为空是合法业务状态。

官方文档：[每日指标数据](https://tushare.pro/document/2?doc_id=32)。

## 估值分位

```python
from a_stock_lib.valuation import compute_valuation_percentile

result = compute_valuation_percentile(
    history.value,
    field="pb",
    as_of_date="2026-07-17",
)
```

规则：

- 截取 as-of date 向前最多十年；
- 每月使用最后一个有效交易日；
- 仅使用有限正数；
- 至少 60 个有效月；
- 使用与 tracker 兼容的严格小于公式：`count(history < current) / N * 100`；
- `coverage_status` 为 `FULL_10Y`、`SINCE_LISTING` 或 `INSUFFICIENT_HISTORY`。
- `window_start/window_end` 是实际纳入计算的首末观察日，不伪装成请求 as-of date。

## 财务

```python
from a_stock_lib.providers import TushareFinancialProvider

provider = TushareFinancialProvider()
indicator = provider.fetch_indicator_history("600036")
income = provider.fetch_income_history("600036")
balance = provider.fetch_balance_history("600036")
cashflow = provider.fetch_cashflow_history("600036")
```

四个历史方法的可选 `period` 参数遵循 TuShare 官方报告期格式 `YYYYMMDD`；`start_date/end_date` 也接受 ISO 日期并在请求前转换为 `YYYYMMDD`。

统一输出增加 `endpoint`，并提供以下可空公共键：

```text
ts_code, endpoint, ann_date, f_ann_date, end_date,
report_type, comp_type, end_type, update_flag
```

`fina_indicator` 官方不提供 `f_ann_date/report_type/comp_type/end_type`，这些字段保持 `NULL`，不得伪造。三大报表保留官方 PIT 键和更正标识。

`fina_indicator` 的选择字段包含 `or_yoy`（营业收入同比增长率）与 `dt_netprofit_yoy`（扣除非经常损益后的归母净利润同比增长率），供消费者做最新报告方向核验；它们不是自动评分或单季年化字段。

财务结果的 `source_as_of` 使用有效公告日：三大报表优先 `f_ann_date`、回退 `ann_date`；`fina_indicator` 使用 `ann_date`。

官方文档：

- [财务指标](https://tushare.pro/document/2?doc_id=79)
- [利润表](https://tushare.pro/document/2?doc_id=33)
- [资产负债表](https://tushare.pro/document/2?doc_id=36)
- [现金流量表](https://tushare.pro/document/2?doc_id=44)

## 分红

```python
from a_stock_lib.providers import TushareDividendProvider

provider = TushareDividendProvider()
result = provider.fetch_dividend_history("600036")
```

无分红记录返回 `status="ok"` 的空 DataFrame，不作为远端失败。

分红结果的 `source_as_of` 优先使用 `imp_ann_date`，缺失时回退 `ann_date`。

官方字段口径：

- `cash_div`：每股分红，税后；
- `cash_div_tax`：每股分红，税前。

官方文档：[分红送股](https://tushare.pro/document/2?doc_id=103)。

## 限流、重试和错误

- 真实 TuShare Provider 默认共享进程级 180 次/分钟限流器；
- 仅 typed timeout/connection 异常重试一次；
- 权限、积分、认证、参数、schema 和频次错误不重试；
- SDK 1.4.29 抛出 API 错误时只保留消息，无法可靠取得服务端数字 code；
- 错误消息在进入 `MarketDataResult` 前移除已知 Token。

常用错误码：

```text
AUTH_MISSING
PERMISSION_DENIED
RATE_LIMITED
TIMEOUT
REMOTE_DISCONNECTED
EMPTY_RESPONSE
MISSING_COLUMNS
SCHEMA_CHANGED
INVALID_ARGUMENT
UNKNOWN_ERROR
```

## 测试边界

默认 pytest 通过 autouse fixture 清除 TuShare、Telegram 和代理凭据。单元测试只注入 fake client，不访问网络。真实 smoke test必须单独显式运行，不属于默认测试套件。
