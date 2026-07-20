from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from a_stock_lib.market_data import INVALID_ARGUMENT, MISSING_COLUMNS
from a_stock_lib.providers.tushare_valuation import (
    DAILY_BASIC_SOURCE,
    TushareValuationProvider,
)
from a_stock_lib.valuation import (
    FULL_10Y,
    INSUFFICIENT_HISTORY,
    SINCE_LISTING,
    compute_valuation_percentile,
)


class _FakeValuationClient:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls: list[dict[str, object]] = []

    def daily_basic(self, **kwargs: object) -> pd.DataFrame:
        self.calls.append(kwargs)
        return self.frame.copy()


def _valuation_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": ["603606.SH", "600036.SH"],
            "trade_date": ["20260717", "20260717"],
            "close": ["42.31", "44.02"],
            "pe": ["22.1", None],
            "pe_ttm": ["20.5", None],
            "pb": ["2.4", "5.1"],
            "ps": ["3.2", "4.1"],
            "ps_ttm": ["3.0", "4.0"],
            "dv_ratio": ["1.1", "2.2"],
            "dv_ttm": ["1.2", "2.3"],
            "total_mv": ["4800000", "13000000"],
            "circ_mv": ["4700000", "12000000"],
        }
    )


def test_fetch_daily_basic_by_trade_date_normalizes_official_fields() -> None:
    client = _FakeValuationClient(_valuation_frame())
    provider = TushareValuationProvider(token="fake-token", client=client)

    result = provider.fetch_daily_basic_by_trade_date("2026-07-17")

    assert result.status == "ok"
    assert result.source == DAILY_BASIC_SOURCE
    assert result.row_count == 2
    assert result.source_as_of == "2026-07-17"
    assert result.request_fingerprint
    assert result.value is not None
    assert result.value["trade_date"].tolist() == ["2026-07-17", "2026-07-17"]
    by_code = result.value.set_index("ts_code")
    assert by_code.loc["603606.SH", "close"] == pytest.approx(42.31)
    assert pd.isna(by_code.loc["600036.SH", "pe_ttm"])
    assert client.calls[0]["trade_date"] == "20260717"
    assert "pe_ttm" in str(client.calls[0]["fields"])


def test_fetch_valuation_history_uses_code_and_date_range() -> None:
    client = _FakeValuationClient(_valuation_frame().iloc[[0]])
    provider = TushareValuationProvider(token="fake-token", client=client)

    result = provider.fetch_valuation_history("603606", "2016-07-18", "2026-07-17")

    assert result.status == "ok"
    assert client.calls == [
        {
            "ts_code": "603606.SH",
            "start_date": "20160718",
            "end_date": "20260717",
            "fields": client.calls[0]["fields"],
        }
    ]


def test_fetch_daily_basic_rejects_malformed_date_without_calling_client() -> None:
    client = _FakeValuationClient(_valuation_frame())
    provider = TushareValuationProvider(token="fake-token", client=client)

    result = provider.fetch_daily_basic_by_trade_date("not-a-date")

    assert result.status == "failed"
    assert result.error_code == INVALID_ARGUMENT
    assert client.calls == []


def test_fetch_daily_basic_fails_when_official_key_column_is_missing() -> None:
    client = _FakeValuationClient(_valuation_frame().drop(columns="pb"))
    provider = TushareValuationProvider(token="fake-token", client=client)

    result = provider.fetch_daily_basic_by_trade_date("2026-07-17")

    assert result.status == "failed"
    assert result.error_code == MISSING_COLUMNS


def _monthly_frame(start_year: int, start_month: int, count: int, day: int = 20) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    year, month = start_year, start_month
    for value in range(1, count + 1):
        rows.append(
            {
                "trade_date": date(year, month, day).isoformat(),
                "pb": float(value),
                "pe_ttm": float(value * 2),
            }
        )
        month += 1
        if month == 13:
            month = 1
            year += 1
    return pd.DataFrame(rows)


def test_percentile_uses_strict_less_formula_compatible_with_tracker() -> None:
    frame = _monthly_frame(2021, 7, 60)

    result = compute_valuation_percentile(frame, field="pb", as_of_date="2026-07-20")

    assert result.coverage_status == SINCE_LISTING
    assert result.valid_months == 60
    assert result.value == 60.0
    assert result.percentile == pytest.approx(round(59 / 60 * 100, 1))


def test_percentile_marks_full_ten_year_coverage() -> None:
    frame = _monthly_frame(2016, 7, 121)

    result = compute_valuation_percentile(frame, field="pe_ttm", as_of_date="2026-07-20")

    assert result.coverage_status == FULL_10Y
    assert result.valid_months == 121
    assert result.window_start == "2016-07-20"
    assert result.window_end == "2026-07-20"


def test_full_ten_year_month_span_is_not_downgraded_by_day_of_month() -> None:
    frame = _monthly_frame(2016, 7, 121, day=25)

    result = compute_valuation_percentile(frame, "pb", "2026-07-20")

    assert result.coverage_status == FULL_10Y
    assert result.valid_months == 120
    assert result.window_start == "2016-07-25"
    assert result.window_end == "2026-06-25"


def test_percentile_rejects_non_positive_and_non_finite_values() -> None:
    frame = _monthly_frame(2025, 1, 10)
    frame.loc[0, "pb"] = 0
    frame.loc[1, "pb"] = float("inf")

    result = compute_valuation_percentile(frame, field="pb", as_of_date="2026-07-20")

    assert result.coverage_status == INSUFFICIENT_HISTORY
    assert result.valid_months == 8
    assert result.percentile is None
