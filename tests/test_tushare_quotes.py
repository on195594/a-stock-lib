from __future__ import annotations

import pandas as pd
import pytest

from a_stock_lib.market_data import (
    INVALID_ARGUMENT,
    MISSING_COLUMNS,
    RATE_LIMITED,
    SCHEMA_CHANGED,
    SOURCE_STALE,
    TIMEOUT,
)
from a_stock_lib.providers.tushare_quotes import (
    DAILY_SOURCE,
    TRADE_CAL_SOURCE,
    TushareMarketDataProvider,
    _normalize_tushare_bars,
)


class _TradeCalendarClient:
    def __init__(self, value) -> None:
        self._value = value

    def trade_cal(self, **kwargs):
        return self._value


class _DailyClient:
    def __init__(self, value: pd.DataFrame) -> None:
        self._value = value

    def daily(self, **kwargs):
        return self._value


def test_tushare_provider_constructs_without_token(tmp_path, monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    provider = TushareMarketDataProvider(token=None, env_path=tmp_path / "missing.env")
    assert provider.token is None


def test_tushare_provider_reads_token_from_env(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "fake-token-123")
    provider = TushareMarketDataProvider()
    assert provider.token == "fake-token-123"


def test_tushare_provider_reads_token_from_env_file_when_env_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("TUSHARE_TOKEN=file-token-456\n")

    provider = TushareMarketDataProvider(env_path=env_path)

    assert provider.token == "file-token-456"


def test_tushare_stock_code_supports_beijing_exchange() -> None:
    from a_stock_lib.providers.tushare_quotes import to_tushare_stock_code

    assert to_tushare_stock_code("920000") == "920000.BJ"
    assert to_tushare_stock_code("430047.BJ") == "430047.BJ"


def test_tushare_normalizer_requires_dataframe():
    result = _normalize_tushare_bars(
        [{"trade_date": "20260623", "close": "10.5"}],
        DAILY_SOURCE,
        "score_price",
    )

    assert result.status == "failed"
    assert result.error_code == SCHEMA_CHANGED


def test_tushare_normalizer_requires_ohlc_for_score_price():
    result = _normalize_tushare_bars(
        pd.DataFrame({"trade_date": ["20260623"], "close": [10.5]}),
        DAILY_SOURCE,
        "score_price",
    )

    assert result.status == "failed"
    assert result.error_code == MISSING_COLUMNS


@pytest.mark.parametrize("bad_close", [float("nan"), float("inf"), 0.0, -1.0])
def test_tushare_normalizer_rejects_invalid_prices(bad_close: float):
    result = _normalize_tushare_bars(
        pd.DataFrame(
            {
                "trade_date": ["20260623"],
                "open": [10.0],
                "high": [11.0],
                "low": [9.0],
                "close": [bad_close],
            }
        ),
        DAILY_SOURCE,
        "score_price",
    )

    assert result.status == "failed"
    assert result.error_code == SCHEMA_CHANGED


def test_fetch_score_price_rejects_future_observation():
    provider = TushareMarketDataProvider(
        token="fake-token",
        client=_DailyClient(
            pd.DataFrame(
                {
                    "trade_date": ["20260624"],
                    "open": [10.0],
                    "high": [11.0],
                    "low": [9.0],
                    "close": [10.5],
                    "vol": [100.0],
                }
            )
        ),
    )

    result = provider.fetch_score_price("600036", "2026-06-23")

    assert result.status == "failed"
    assert result.error_code == SOURCE_STALE
    assert result.value is None


def test_fetch_daily_bars_range_rejects_observation_after_end_date():
    provider = TushareMarketDataProvider(
        token="fake-token",
        client=_DailyClient(
            pd.DataFrame(
                {
                    "trade_date": ["20260624"],
                    "open": [10.0],
                    "high": [11.0],
                    "low": [9.0],
                    "close": [10.5],
                    "vol": [100.0],
                }
            )
        ),
    )

    result = provider.fetch_daily_bars_range("600036", "2026-06-01", "2026-06-23")

    assert result.status == "failed"
    assert result.error_code == SOURCE_STALE


def test_tushare_normalizer_rejects_inconsistent_ohlc():
    result = _normalize_tushare_bars(
        pd.DataFrame(
            {
                "trade_date": ["20260623"],
                "open": [10.0],
                "high": [9.0],
                "low": [8.0],
                "close": [10.5],
            }
        ),
        DAILY_SOURCE,
        "score_price",
    )

    assert result.status == "failed"
    assert result.error_code == SCHEMA_CHANGED


def test_fetch_score_price_rejects_malformed_source_date():
    provider = TushareMarketDataProvider(
        token="fake-token",
        client=_DailyClient(
            pd.DataFrame(
                {
                    "trade_date": ["2026-06-1a"],
                    "open": [10.0],
                    "high": [11.0],
                    "low": [9.0],
                    "close": [10.5],
                    "vol": [100.0],
                }
            )
        ),
    )

    result = provider.fetch_score_price("600036", "2026-06-23")

    assert result.status == "failed"
    assert result.error_code == SCHEMA_CHANGED


def test_fetch_l3_bars_rejects_malformed_source_date():
    provider = TushareMarketDataProvider(
        token="fake-token",
        client=_DailyClient(
            pd.DataFrame(
                {
                    "trade_date": ["2026-06-0x"],
                    "open": [10.0],
                    "high": [11.0],
                    "low": [9.0],
                    "close": [10.5],
                    "vol": [100.0],
                }
            )
        ),
    )

    result = provider.fetch_l3_bars("600036", "2026-06-23", 1)

    assert result.status == "failed"
    assert result.error_code == SCHEMA_CHANGED


@pytest.mark.parametrize(
    ("start_date", "end_date"),
    [("not-a-date", "2026-06-23"), ("2026-06-24", "2026-06-23")],
)
def test_fetch_daily_bars_range_rejects_invalid_range(start_date: str, end_date: str):
    provider = TushareMarketDataProvider(token="fake-token")

    result = provider.fetch_daily_bars_range("600036", start_date, end_date)

    assert result.status == "failed"
    assert result.error_code == INVALID_ARGUMENT


def test_tushare_retry_call_does_not_retry_permission_limit_errors():
    provider = TushareMarketDataProvider(token="fake-token")
    calls = 0

    def fail_permission():
        nonlocal calls
        calls += 1
        raise RuntimeError("You do not have permission. Limit level: 3")

    with pytest.raises(RuntimeError, match="Limit level"):
        provider._retry_call(fail_permission)

    assert calls == 1


def test_tushare_trade_calendar_non_dataframe_fails_schema_changed():
    provider = TushareMarketDataProvider(token="fake-token", client=_TradeCalendarClient({"cal_date": []}))

    result = provider.fetch_trade_calendar("2026-06-01", "2026-06-23")

    assert result.status == "failed"
    assert result.source == TRADE_CAL_SOURCE
    assert result.error_code == SCHEMA_CHANGED


def test_fetch_score_price_rejects_malformed_date():
    provider = TushareMarketDataProvider(token="fake-token")
    result = provider.fetch_score_price("600036", "not-a-date")
    assert result.status == "failed"
    assert result.error_code == INVALID_ARGUMENT
    assert result.value is None
    assert result.error_message is not None


def test_fetch_l3_bars_rejects_malformed_date():
    provider = TushareMarketDataProvider(token="fake-token")
    result = provider.fetch_l3_bars("600036", "not-a-date", 60)
    assert result.status == "failed"
    assert result.error_code == INVALID_ARGUMENT
    assert result.value is None
    assert result.error_message is not None


def test_fetch_outcome_price_rejects_malformed_date():
    provider = TushareMarketDataProvider(token="fake-token")
    result = provider.fetch_outcome_price("600036", "not-a-date")
    assert result.status == "failed"
    assert result.error_code == INVALID_ARGUMENT
    assert result.value is None
    assert result.error_message is not None


def test_fetch_score_price_preserves_complete_request_metadata():
    provider = TushareMarketDataProvider(
        token="fake-token",
        client=_DailyClient(
            pd.DataFrame(
                {
                    "trade_date": ["20260623"],
                    "open": [10.0],
                    "high": [11.0],
                    "low": [9.0],
                    "close": [10.5],
                    "vol": [100.0],
                }
            )
        ),
    )

    result = provider.fetch_score_price("600036", "2026-06-23")

    assert result.status == "ok"
    assert result.value == 10.5
    assert result.freshness_days == 0
    assert result.source_as_of == "2026-06-23"
    assert result.request_fingerprint
    assert result.row_count == 1
