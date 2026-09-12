from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Generic, Literal, Protocol, TypeVar

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
UNKNOWN_ERROR = "UNKNOWN_ERROR"
SOURCE_DISABLED = "SOURCE_DISABLED"
AUTH_MISSING = "AUTH_MISSING"
PERMISSION_DENIED = "PERMISSION_DENIED"
INVALID_ARGUMENT = "INVALID_ARGUMENT"
CACHE_MISSING = "CACHE_MISSING"
CACHE_STALE = "CACHE_STALE"
CACHE_CORRUPT = "CACHE_CORRUPT"
CACHE_MALFORMED = "CACHE_MALFORMED"
CACHE_FUTURE_TIMESTAMP = "CACHE_FUTURE_TIMESTAMP"
CACHE_READ_FAILED = "CACHE_READ_FAILED"

MarketDataErrorCode = Literal[
    "REMOTE_DISCONNECTED",
    "TIMEOUT",
    "RATE_LIMITED",
    "EMPTY_RESPONSE",
    "SCHEMA_CHANGED",
    "MISSING_COLUMNS",
    "INSUFFICIENT_WINDOW",
    "SOURCE_STALE",
    "UNKNOWN_ERROR",
    "SOURCE_DISABLED",
    "AUTH_MISSING",
    "PERMISSION_DENIED",
    "INVALID_ARGUMENT",
    "CACHE_MISSING",
    "CACHE_STALE",
    "CACHE_CORRUPT",
    "CACHE_MALFORMED",
    "CACHE_FUTURE_TIMESTAMP",
    "CACHE_READ_FAILED",
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
    source_as_of: str | None = None
    request_fingerprint: str | None = None
    row_count: int | None = None


class MarketDataProvider(Protocol):
    def fetch_score_price(
        self, code: str, score_date: str
    ) -> MarketDataResult[float]: ...

    def fetch_l3_bars(
        self, code: str, end_date: str, window: int
    ) -> MarketDataResult[pd.DataFrame]: ...

    def fetch_daily_bars_range(
        self, code: str, start_date: str, end_date: str
    ) -> MarketDataResult[pd.DataFrame]: ...

    def fetch_outcome_price(
        self, code: str, target_date: str
    ) -> MarketDataResult[float]: ...

    def fetch_index_bars(self, symbol: str) -> MarketDataResult[pd.DataFrame]: ...


def now() -> str:
    return datetime.now().isoformat()
