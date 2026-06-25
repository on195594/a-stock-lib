from __future__ import annotations

import pandas as pd

from a_stock_lib.market_data import MISSING_COLUMNS, REMOTE_DISCONNECTED, SCHEMA_CHANGED, TIMEOUT, UNKNOWN_ERROR
from a_stock_lib.providers.baostock_quotes import (
    BaoStockMarketDataProvider,
    _exception_result,
    _normalize_baostock_bars,
    to_baostock_index_code,
    to_baostock_stock_code,
)


def test_baostock_provider_constructs():
    provider = BaoStockMarketDataProvider()
    assert provider is not None


class _LoginResult:
    error_code = "0"
    error_msg = ""


class _LoginRaisesClient:
    def login(self):
        raise RuntimeError("login socket closed")

    def logout(self):
        pass


class _QueryResult:
    def __init__(self, fields: list[str], rows: list[list[str]]) -> None:
        self.error_code = "0"
        self.error_msg = ""
        self.fields = fields
        self._rows = rows
        self._index = -1

    def next(self) -> bool:
        self._index += 1
        return self._index < len(self._rows)

    def get_row_data(self) -> list[str]:
        return self._rows[self._index]


class _QueryClient:
    def __init__(self, result: _QueryResult) -> None:
        self._result = result
        self.logged_out = False

    def login(self):
        return _LoginResult()

    def query_history_k_data_plus(self, *args, **kwargs):
        return self._result

    def logout(self) -> None:
        self.logged_out = True


class _QueryRaisesClient:
    def __init__(self) -> None:
        self.login_count = 0

    def login(self):
        self.login_count += 1
        return _LoginResult()

    def query_history_k_data_plus(self, *args, **kwargs):
        raise RuntimeError("connection reset by peer")

    def logout(self) -> None:
        pass


def test_baostock_login_exception_returns_failed_result():
    provider = BaoStockMarketDataProvider(client=_LoginRaisesClient())

    result = provider.fetch_daily_bars_range("600036", "2026-06-01", "2026-06-23")

    assert result.status == "failed"
    assert result.error_code == UNKNOWN_ERROR
    assert "login socket closed" in (result.error_message or "")


def test_baostock_exception_result_classifies_timeout_and_connection():
    timeout_result = _exception_result(Exception("request timed out"))
    connection_result = _exception_result(Exception("connection reset by peer"))

    assert timeout_result.error_code == TIMEOUT
    assert connection_result.error_code == REMOTE_DISCONNECTED


def test_baostock_fetch_index_bars_invalid_symbol_returns_failed_result():
    provider = BaoStockMarketDataProvider(client=_QueryClient(_QueryResult([], [])))

    result = provider.fetch_index_bars("not-an-index")

    assert result.status == "failed"
    assert result.error_code == UNKNOWN_ERROR
    assert "unsupported stock code" in (result.error_message or "")


def test_baostock_normalizer_requires_ohlc_columns_for_score_price():
    result = _normalize_baostock_bars(
        pd.DataFrame([{"date": "2026-06-23", "close": "10.5"}]),
        "score_price",
    )

    assert result.status == "failed"
    assert result.error_code == MISSING_COLUMNS


def test_baostock_normalizer_requires_dataframe():
    result = _normalize_baostock_bars(
        [{"date": "2026-06-23", "close": "10.5"}],
        "score_price",
    )

    assert result.status == "failed"
    assert result.error_code == SCHEMA_CHANGED


def test_baostock_query_missing_ohlc_returns_missing_columns():
    provider = BaoStockMarketDataProvider(
        client=_QueryClient(
            _QueryResult(
                ["date", "close", "volume"],
                [["2026-06-23", "10.5", "1000"]],
            )
        )
    )

    result = provider.fetch_daily_bars_range("600036", "2026-06-01", "2026-06-23")

    assert result.status == "failed"
    assert result.error_code == MISSING_COLUMNS


def test_baostock_code_normalization_supports_common_formats_and_bj():
    assert to_baostock_stock_code("600036.SH") == "sh.600036"
    assert to_baostock_stock_code("sh600036") == "sh.600036"
    assert to_baostock_stock_code("830838") == "bj.830838"
    assert to_baostock_stock_code("bj.830838") == "bj.830838"


def test_baostock_index_code_maps_000001_to_shanghai_index():
    assert to_baostock_index_code("000001") == "sh.000001"
    assert to_baostock_index_code("sh000001") == "sh.000001"


def test_baostock_context_query_exception_resets_login_state():
    client = _QueryRaisesClient()
    provider = BaoStockMarketDataProvider(client=client)

    with provider:
        result = provider.fetch_daily_bars_range("600036", "2026-06-01", "2026-06-23")
        assert result.status == "failed"
        assert result.error_code == REMOTE_DISCONNECTED
        assert provider._is_logged_in is False

        provider.fetch_daily_bars_range("600036", "2026-06-01", "2026-06-23")

    assert client.login_count == 2
