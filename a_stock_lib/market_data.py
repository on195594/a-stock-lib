from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Generic, Literal, TypeVar

T = TypeVar("T")

MarketDataStatus = Literal["ok", "degraded", "failed"]

REMOTE_DISCONNECTED = "REMOTE_DISCONNECTED"
TIMEOUT = "TIMEOUT"
RATE_LIMITED = "RATE_LIMITED"
EMPTY_RESPONSE = "EMPTY_RESPONSE"
SCHEMA_CHANGED = "SCHEMA_CHANGED"
MISSING_COLUMNS = "MISSING_COLUMNS"
SOURCE_STALE = "SOURCE_STALE"
UNKNOWN_ERROR = "UNKNOWN_ERROR"
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
    "SOURCE_STALE",
    "UNKNOWN_ERROR",
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


def now() -> str:
    return datetime.now().isoformat()
