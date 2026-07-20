from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Literal

import pandas as pd

FULL_10Y = "FULL_10Y"
SINCE_LISTING = "SINCE_LISTING"
INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
ValuationCoverageStatus = Literal["FULL_10Y", "SINCE_LISTING", "INSUFFICIENT_HISTORY"]


@dataclass(frozen=True)
class ValuationPercentile:
    value: float | None
    percentile: float | None
    window_start: str | None
    window_end: str | None
    valid_months: int
    coverage_status: ValuationCoverageStatus


def _ten_year_start(as_of: date) -> date:
    try:
        return as_of.replace(year=as_of.year - 10)
    except ValueError:
        return as_of.replace(year=as_of.year - 10, day=28)


def _monthly_valid_values(
    frame: pd.DataFrame,
    field: str,
    as_of: date,
) -> pd.DataFrame:
    working = frame[["trade_date", field]].copy()
    working["trade_date"] = pd.to_datetime(working["trade_date"], errors="coerce")
    working[field] = pd.to_numeric(working[field], errors="coerce")
    start = pd.Timestamp(_ten_year_start(as_of))
    end = pd.Timestamp(as_of)
    working = working[(working["trade_date"] >= start) & (working["trade_date"] <= end)]
    working = working[working[field].map(lambda value: pd.notna(value) and math.isfinite(value) and value > 0)]
    working = working.sort_values("trade_date")
    working["month"] = working["trade_date"].dt.to_period("M")
    return working.groupby("month", as_index=False).tail(1).reset_index(drop=True)


def compute_valuation_percentile(
    frame: pd.DataFrame,
    field: str,
    as_of_date: str,
    minimum_months: int = 60,
) -> ValuationPercentile:
    """Compute a month-end valuation percentile using tracker-compatible strict-less rank."""
    if field not in {"pb", "pe_ttm"}:
        raise ValueError(f"unsupported valuation field: {field}")
    if "trade_date" not in frame.columns or field not in frame.columns:
        raise ValueError(f"missing required columns: trade_date, {field}")
    if minimum_months <= 0:
        raise ValueError("minimum_months must be positive")
    as_of = date.fromisoformat(as_of_date[:10])
    monthly = _monthly_valid_values(frame, field, as_of)
    valid_months = len(monthly)
    window_start = monthly["trade_date"].iloc[0].date().isoformat() if valid_months else None
    window_end = monthly["trade_date"].iloc[-1].date().isoformat() if valid_months else None
    if valid_months < minimum_months:
        value = float(monthly[field].iloc[-1]) if valid_months else None
        return ValuationPercentile(value, None, window_start, window_end, valid_months, INSUFFICIENT_HISTORY)
    current = float(monthly[field].iloc[-1])
    percentile = round(float((monthly[field] < current).sum() / valid_months * 100), 1)
    first_month = monthly["trade_date"].iloc[0].to_period("M").ordinal
    as_of_month = pd.Period(as_of, freq="M").ordinal
    coverage = FULL_10Y if as_of_month - first_month >= 120 else SINCE_LISTING
    return ValuationPercentile(current, percentile, window_start, window_end, valid_months, coverage)
