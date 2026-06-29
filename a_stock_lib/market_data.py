from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, Literal, Protocol, TypeVar

import pandas as pd

T = TypeVar("T")

MarketDataStatus = Literal["ok", "degraded", "failed"]

REMOTE_DISCONNECTED = "REMOTE_DISCONNECTED"
TIMEOUT = "TIMEOUT"
RATE_LIMITED = "RATE_LIMITED"
EMPTY_RESPONSE = "EMPTY_RESPONSE"
SCHEMA_CHANGED = "SCHEMA_CHANGED"
MISSING_COLUMNS = "MISSING_COLUMNS"
INSUFFICIENT_WINDOW = "INSUFFICIENT_WINDOW"
SOURCE_STALE = "SOURCE_STALE"
MIXED_SOURCE_VOLUME_UNSAFE = "MIXED_SOURCE_VOLUME_UNSAFE"
UNKNOWN_ERROR = "UNKNOWN_ERROR"
SOURCE_DISABLED = "SOURCE_DISABLED"
AUTH_MISSING = "AUTH_MISSING"
PERMISSION_DENIED = "PERMISSION_DENIED"

MarketDataErrorCode = Literal[
    "REMOTE_DISCONNECTED",
    "TIMEOUT",
    "RATE_LIMITED",
    "EMPTY_RESPONSE",
    "SCHEMA_CHANGED",
    "MISSING_COLUMNS",
    "INSUFFICIENT_WINDOW",
    "SOURCE_STALE",
    "MIXED_SOURCE_VOLUME_UNSAFE",
    "UNKNOWN_ERROR",
    "SOURCE_DISABLED",
    "AUTH_MISSING",
    "PERMISSION_DENIED",
]


@dataclass(frozen=True)
class MarketDataResult(Generic[T]):
    value: T | None
    status: MarketDataStatus
    source: str
    fetched_at: str
    fallback_source: str | None = None
    fallback_reason: str | None = None
    error_code: MarketDataErrorCode | None = None
    error_message: str | None = None
    freshness_days: int | None = None
    adjusted: str = "none"
    volume_unit: str = "unknown"


class MarketDataProvider(Protocol):
    def fetch_score_price(self, code: str, score_date: str) -> MarketDataResult[float]:
        ...

    def fetch_l3_bars(self, code: str, end_date: str, window: int) -> MarketDataResult[pd.DataFrame]:
        ...

    def fetch_daily_bars_range(self, code: str, start_date: str, end_date: str) -> MarketDataResult[pd.DataFrame]:
        ...

    def fetch_outcome_price(self, code: str, target_date: str) -> MarketDataResult[float]:
        ...

    def fetch_index_bars(self, symbol: str) -> MarketDataResult[pd.DataFrame]:
        ...


class CompositeMarketDataProvider:
    """Primary/fallback provider. Fallback results are marked degraded."""

    def __init__(self, primary: MarketDataProvider, fallback: MarketDataProvider | None = None) -> None:
        self.primary = primary
        self.fallback = fallback

    def __enter__(self) -> CompositeMarketDataProvider:
        if hasattr(self.primary, "__enter__"):
            self.primary.__enter__()
        if self.fallback and hasattr(self.fallback, "__enter__"):
            self.fallback.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            if hasattr(self.primary, "__exit__"):
                self.primary.__exit__(exc_type, exc_val, exc_tb)
        finally:
            if self.fallback and hasattr(self.fallback, "__exit__"):
                self.fallback.__exit__(exc_type, exc_val, exc_tb)

    def fetch_score_price(self, code: str, score_date: str) -> MarketDataResult[float]:
        return self._fetch("fetch_score_price", code, score_date)

    def fetch_l3_bars(self, code: str, end_date: str, window: int) -> MarketDataResult[pd.DataFrame]:
        return self._fetch("fetch_l3_bars", code, end_date, window)

    def fetch_daily_bars_range(self, code: str, start_date: str, end_date: str) -> MarketDataResult[pd.DataFrame]:
        return self._fetch("fetch_daily_bars_range", code, start_date, end_date)

    def fetch_outcome_price(self, code: str, target_date: str) -> MarketDataResult[float]:
        return self._fetch("fetch_outcome_price", code, target_date)

    def fetch_index_bars(self, symbol: str) -> MarketDataResult[pd.DataFrame]:
        return self._fetch("fetch_index_bars", symbol)

    def _fetch(self, method: str, *args: Any) -> MarketDataResult[Any]:
        primary_result = getattr(self.primary, method)(*args)
        if primary_result.status != "failed" or self.fallback is None:
            return primary_result
        fallback_result = getattr(self.fallback, method)(*args)
        if fallback_result.status == "failed":
            return MarketDataResult(
                fallback_result.value,
                "failed",
                fallback_result.source,
                fallback_result.fetched_at,
                fallback_source=primary_result.source,
                fallback_reason=primary_result.error_code or primary_result.fallback_reason or "PRIMARY_FAILED",
                error_code=fallback_result.error_code,
                error_message=_combine_failure_messages(primary_result, fallback_result),
                freshness_days=fallback_result.freshness_days,
                adjusted=fallback_result.adjusted,
                volume_unit=fallback_result.volume_unit,
            )
        return MarketDataResult(
            fallback_result.value,
            "degraded",
            fallback_result.source,
            fallback_result.fetched_at,
            fallback_source=primary_result.source,
            fallback_reason=primary_result.error_code or primary_result.fallback_reason or "PRIMARY_FAILED",
            freshness_days=fallback_result.freshness_days,
            adjusted=fallback_result.adjusted,
            volume_unit=fallback_result.volume_unit,
        )


def normalize_bars_result(df: Any, source: str, purpose: str) -> MarketDataResult[pd.DataFrame]:
    fetched_at = now()
    if df is None:
        return MarketDataResult(None, "failed", source, fetched_at, error_code=EMPTY_RESPONSE)
    if not isinstance(df, pd.DataFrame):
        return MarketDataResult(
            None,
            "failed",
            source,
            fetched_at,
            error_code=SCHEMA_CHANGED,
            error_message=f"expected pandas.DataFrame, got {type(df).__name__}",
        )
    if df.empty:
        return MarketDataResult(None, "failed", source, fetched_at, error_code=EMPTY_RESPONSE)
    rename_map = {
        "日期": "date",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
    }
    normalized = df.rename(columns=rename_map).copy()
    required = {"date", "open", "high", "low", "close"}
    if purpose == "l3_bars":
        required.add("volume")
    if not required.issubset(set(normalized.columns)):
        return MarketDataResult(
            None,
            "failed",
            source,
            fetched_at,
            error_code=MISSING_COLUMNS,
            error_message=f"missing columns: {sorted(required - set(normalized.columns))}",
        )
    keep = [col for col in ["date", "open", "high", "low", "close", "volume"] if col in normalized.columns]
    return MarketDataResult(normalized[keep], "ok", source, fetched_at, adjusted="none", volume_unit="share")


def exception_result(source: str, exc: Exception) -> MarketDataResult[pd.DataFrame]:
    message = str(exc)
    lowered = message.lower()
    if "timeout" in lowered or "timed out" in lowered or "time limit" in lowered:
        code = TIMEOUT
    elif "disconnect" in lowered or "connection" in lowered:
        code = REMOTE_DISCONNECTED
    elif "rate limit" in lowered or "rate" in lowered or "频次" in message or "限频" in message:
        code = RATE_LIMITED
    else:
        code = UNKNOWN_ERROR
    return MarketDataResult(None, "failed", source, now(), error_code=code, error_message=message)


def now() -> str:
    return datetime.now().isoformat()


def _combine_failure_messages(primary: MarketDataResult[Any], fallback: MarketDataResult[Any]) -> str:
    primary_reason = primary.error_code or primary.fallback_reason or "unknown"
    fallback_reason = fallback.error_code or fallback.fallback_reason or "unknown"
    primary_message = f": {primary.error_message}" if primary.error_message else ""
    fallback_message = f": {fallback.error_message}" if fallback.error_message else ""
    return (
        f"primary {primary.source} failed with {primary_reason}{primary_message}; "
        f"fallback {fallback.source} failed with {fallback_reason}{fallback_message}"
    )
