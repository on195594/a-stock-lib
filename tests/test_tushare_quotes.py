from __future__ import annotations

import pandas as pd
import pytest

from a_stock_lib.market_data import MISSING_COLUMNS, RATE_LIMITED, SCHEMA_CHANGED, TIMEOUT
from a_stock_lib.providers.tushare_quotes import (
    DAILY_SOURCE,
    TRADE_CAL_SOURCE,
    TushareMarketDataProvider,
    _exception_result,
    _normalize_tushare_bars,
)


class _TradeCalendarClient:
    def __init__(self, value) -> None:
        self._value = value

    def trade_cal(self, **kwargs):
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


def test_tushare_exception_result_classifies_time_limit_as_timeout():
    result = _exception_result(DAILY_SOURCE, Exception("time limit exceeded"))
    assert result.error_code == TIMEOUT


def test_tushare_exception_result_classifies_rate_limit_without_plain_limit():
    result = _exception_result(DAILY_SOURCE, Exception("request rate limit exceeded"))
    assert result.error_code == RATE_LIMITED


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
