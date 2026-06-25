from __future__ import annotations

import pandas as pd
import pytest

from a_stock_lib.market_data import (
    EMPTY_RESPONSE,
    MISSING_COLUMNS,
    SCHEMA_CHANGED,
    TIMEOUT,
    CompositeMarketDataProvider,
    MarketDataResult,
    exception_result,
    normalize_bars_result,
)


def test_market_data_result_defaults():
    result = MarketDataResult(1.23, "ok", "test.source", "2026-06-23T10:00:00")
    assert result.value == 1.23
    assert result.status == "ok"
    assert result.adjusted == "none"
    assert result.volume_unit == "unknown"
    assert result.error_code is None


class _FakeProvider:
    def __init__(self, result: MarketDataResult):
        self._result = result

    def fetch_score_price(self, code, score_date):
        return self._result

    def fetch_l3_bars(self, code, end_date, window):
        return self._result

    def fetch_daily_bars_range(self, code, start_date, end_date):
        return self._result

    def fetch_outcome_price(self, code, target_date):
        return self._result

    def fetch_index_bars(self, symbol):
        return self._result


def test_composite_provider_uses_primary_when_ok():
    primary = _FakeProvider(MarketDataResult(1.0, "ok", "primary.src", "t"))
    fallback = _FakeProvider(MarketDataResult(2.0, "ok", "fallback.src", "t"))
    composite = CompositeMarketDataProvider(primary, fallback)
    result = composite.fetch_score_price("600036", "2026-06-23")
    assert result.value == 1.0
    assert result.source == "primary.src"


def test_composite_provider_falls_back_and_marks_degraded():
    primary = _FakeProvider(
        MarketDataResult(None, "failed", "primary.src", "t", error_code=TIMEOUT)
    )
    fallback = _FakeProvider(MarketDataResult(2.0, "ok", "fallback.src", "t"))
    composite = CompositeMarketDataProvider(primary, fallback)
    result = composite.fetch_score_price("600036", "2026-06-23")
    assert result.value == 2.0
    assert result.status == "degraded"
    assert result.fallback_source == "primary.src"
    assert result.fallback_reason == TIMEOUT


def test_composite_provider_no_fallback_returns_primary_failure():
    primary = _FakeProvider(
        MarketDataResult(None, "failed", "primary.src", "t", error_code=TIMEOUT)
    )
    composite = CompositeMarketDataProvider(primary, fallback=None)
    result = composite.fetch_score_price("600036", "2026-06-23")
    assert result.status == "failed"
    assert result.error_code == TIMEOUT


def test_composite_provider_exit_always_closes_fallback_when_primary_exit_raises():
    class _ExitRaisesProvider(_FakeProvider):
        def __exit__(self, exc_type, exc_val, exc_tb):
            raise RuntimeError("primary close failed")

    class _ExitRecordsProvider(_FakeProvider):
        def __init__(self, result: MarketDataResult):
            super().__init__(result)
            self.closed = False

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.closed = True

    primary = _ExitRaisesProvider(MarketDataResult(1.0, "ok", "primary.src", "t"))
    fallback = _ExitRecordsProvider(MarketDataResult(2.0, "ok", "fallback.src", "t"))
    composite = CompositeMarketDataProvider(primary, fallback)

    with pytest.raises(RuntimeError, match="primary close failed"):
        composite.__exit__(None, None, None)

    assert fallback.closed is True


def test_composite_provider_preserves_primary_reason_when_fallback_also_fails():
    primary = _FakeProvider(
        MarketDataResult(None, "failed", "primary.src", "t", error_code=TIMEOUT)
    )
    fallback = _FakeProvider(
        MarketDataResult(None, "failed", "fallback.src", "t", error_code=EMPTY_RESPONSE)
    )
    composite = CompositeMarketDataProvider(primary, fallback)

    result = composite.fetch_score_price("600036", "2026-06-23")

    assert result.status == "failed"
    assert result.source == "fallback.src"
    assert result.error_code == EMPTY_RESPONSE
    assert result.fallback_source == "primary.src"
    assert result.fallback_reason == TIMEOUT
    assert "primary.src" in (result.error_message or "")
    assert "fallback.src" in (result.error_message or "")


def test_normalize_bars_result_renames_chinese_columns():
    df = pd.DataFrame(
        {"日期": ["2026-06-23"], "开盘": [10.0], "最高": [11.0], "最低": [9.5], "收盘": [10.5], "成交量": [1000]}
    )
    result = normalize_bars_result(df, "test.source", "l3_bars")
    assert result.status == "ok"
    assert list(result.value.columns) == ["date", "open", "high", "low", "close", "volume"]


def test_normalize_bars_result_empty_df_fails():
    result = normalize_bars_result(pd.DataFrame(), "test.source", "l3_bars")
    assert result.status == "failed"
    assert result.error_code == EMPTY_RESPONSE


def test_normalize_bars_result_missing_columns_fails():
    df = pd.DataFrame({"日期": ["2026-06-23"], "收盘": [10.5]})
    result = normalize_bars_result(df, "test.source", "l3_bars")
    assert result.status == "failed"
    assert result.error_code == MISSING_COLUMNS


def test_normalize_bars_result_requires_ohlc_for_non_l3_bars():
    df = pd.DataFrame({"日期": ["2026-06-23"], "收盘": [10.5]})
    result = normalize_bars_result(df, "test.source", "score_price")
    assert result.status == "failed"
    assert result.error_code == MISSING_COLUMNS


def test_normalize_bars_result_non_dataframe_fails():
    result = normalize_bars_result([{"date": "2026-06-23", "close": 10.5}], "test.source", "l3_bars")
    assert result.status == "failed"
    assert result.error_code == SCHEMA_CHANGED


def test_exception_result_classifies_timeout():
    result = exception_result("test.source", Exception("Connection timeout after 30s"))
    assert result.error_code == TIMEOUT


def test_exception_result_classifies_time_limit_as_timeout():
    result = exception_result("test.source", Exception("time limit exceeded"))
    assert result.error_code == TIMEOUT
