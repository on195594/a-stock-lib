"""Fail-closed realtime quote composition for A-share consumers.

The primary source is accepted on its own only after schema and freshness
validation.  If it fails, both independent fallback sources must agree on
trade date, freshness and price before the first fallback quote is returned.
"""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import Callable, Protocol, Sequence

from a_stock_lib.market_data import (
    SCHEMA_CHANGED,
    SOURCE_STALE,
    UNKNOWN_ERROR,
    MarketDataErrorCode,
    MarketDataResult,
)

PRICE_DISAGREEMENT = "PRICE_DISAGREEMENT"
TRADE_DATE_MISMATCH = "TRADE_DATE_MISMATCH"


@dataclass(frozen=True)
class QuoteObservation:
    """Normalized price observation returned by one realtime source."""

    price: float
    quote_date: str
    quote_time: str
    source: str
    instrument_name: str | None = None

    @property
    def as_of(self) -> str:
        return f"{self.quote_date}T{self.quote_time}"


@dataclass(frozen=True)
class ValidatedRealtimeQuote:
    """Chosen quote plus every observation used to validate it."""

    price: float
    quote_date: str
    quote_time: str
    source: str
    degraded: bool
    verification: dict[str, QuoteObservation]
    instrument_name: str | None = None

    @property
    def as_of(self) -> str:
        return f"{self.quote_date}T{self.quote_time}"

    def verification_dict(self) -> dict[str, dict[str, object]]:
        """Return JSON-serializable verification details."""
        return {name: asdict(observation) for name, observation in self.verification.items()}


class QuoteSource(Protocol):
    """Minimal injectable source protocol used by the composite provider."""

    def fetch_quote(self, code: str) -> MarketDataResult[QuoteObservation]:
        ...


class MarketSession(str, Enum):
    PRE_OPEN = "pre_open"
    INTRADAY = "intraday"
    NON_TRADING = "non_trading"


class ValidatedRealtimeQuoteProvider:
    """Sina-primary quote provider with Eastmoney/Tencent dual fallback."""

    def __init__(
        self,
        primary: QuoteSource,
        eastmoney: QuoteSource,
        tencent: QuoteSource,
        trading_dates: Sequence[date] | Callable[[], Sequence[date]],
        *,
        clock: Callable[[], datetime] | None = None,
        max_intraday_age_seconds: int = 120,
        max_relative_difference: float = 0.003,
    ) -> None:
        if (
            isinstance(max_intraday_age_seconds, bool)
            or not isinstance(max_intraday_age_seconds, int)
            or max_intraday_age_seconds < 0
        ):
            raise ValueError("max_intraday_age_seconds must be non-negative")
        if (
            isinstance(max_relative_difference, bool)
            or not isinstance(max_relative_difference, (int, float))
            or not math.isfinite(max_relative_difference)
            or not 0 <= max_relative_difference < 1
        ):
            raise ValueError("max_relative_difference must be in [0, 1)")
        self.primary = primary
        self.eastmoney = eastmoney
        self.tencent = tencent
        self._trading_dates = trading_dates
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.max_intraday_age_seconds = max_intraday_age_seconds
        self.max_relative_difference = max_relative_difference

    def fetch_quote(self, code: str) -> MarketDataResult[ValidatedRealtimeQuote]:
        """Fetch a validated quote; fail unless the fallback pair agrees."""
        try:
            now = _ensure_aware_utc(self.clock())
            raw_dates = (
                self._trading_dates()
                if callable(self._trading_dates)
                else self._trading_dates
            )
            dates = sorted(set(raw_dates))
        except Exception as exc:
            return _failed(
                "validated_quote",
                datetime.now(timezone.utc),
                SCHEMA_CHANGED,
                f"invalid clock or trading calendar: {exc}",
            )
        if not dates:
            return _failed("validated_quote", now, SCHEMA_CHANGED, "trading calendar is empty")

        primary_result = self._fetch_source(self.primary, code, now, dates)
        if primary_result.status == "ok" and primary_result.value is not None:
            observation = primary_result.value
            value = ValidatedRealtimeQuote(
                price=observation.price,
                quote_date=observation.quote_date,
                quote_time=observation.quote_time,
                source=observation.source,
                degraded=False,
                verification={observation.source: observation},
                instrument_name=observation.instrument_name,
            )
            return MarketDataResult(value, "ok", observation.source, now.isoformat())

        with ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="quote-fallback",
        ) as executor:
            east_future = executor.submit(
                self._fetch_source, self.eastmoney, code, now, dates
            )
            tencent_future = executor.submit(
                self._fetch_source, self.tencent, code, now, dates
            )
            east = east_future.result()
            tencent = tencent_future.result()
        if (
            east.status != "ok"
            or east.value is None
            or tencent.status != "ok"
            or tencent.value is None
        ):
            details = "; ".join(
                f"{item.source}: {item.error_code or item.error_message or item.status}"
                for item in (east, tencent)
            )
            return _failed("validated_quote", now, east.error_code or tencent.error_code or UNKNOWN_ERROR, details)

        if east.value.source == tencent.value.source:
            return _failed(
                "validated_quote",
                now,
                SCHEMA_CHANGED,
                "fallback observations do not identify independent sources",
            )
        if east.value.quote_date != tencent.value.quote_date:
            return _failed("validated_quote", now, SCHEMA_CHANGED, TRADE_DATE_MISMATCH)
        relative_difference = abs(east.value.price - tencent.value.price) / east.value.price
        if relative_difference > self.max_relative_difference:
            return _failed(
                "validated_quote",
                now,
                SCHEMA_CHANGED,
                f"{PRICE_DISAGREEMENT}: {relative_difference:.6f}",
            )

        chosen = east.value
        value = ValidatedRealtimeQuote(
            price=chosen.price,
            quote_date=chosen.quote_date,
            quote_time=chosen.quote_time,
            source=chosen.source,
            degraded=True,
            verification={chosen.source: chosen, tencent.value.source: tencent.value},
            instrument_name=chosen.instrument_name or tencent.value.instrument_name,
        )
        return MarketDataResult(
            value,
            "degraded",
            chosen.source,
            now.isoformat(),
            fallback_source=primary_result.source,
            fallback_reason=primary_result.error_code or "PRIMARY_FAILED",
        )

    def _fetch_source(
        self,
        source: QuoteSource,
        code: str,
        now: datetime,
        trading_dates: Sequence[date],
    ) -> MarketDataResult[QuoteObservation]:
        try:
            result = source.fetch_quote(code)
        except Exception as exc:  # provider boundary must not leak raw exceptions
            return _failed(type(source).__name__, now, UNKNOWN_ERROR, str(exc))
        if not isinstance(result, MarketDataResult):
            return _failed(
                type(source).__name__,
                now,
                SCHEMA_CHANGED,
                f"expected MarketDataResult, got {type(result).__name__}",
            )
        if result.status not in {"ok", "degraded", "failed"}:
            return _failed(
                result.source,
                now,
                SCHEMA_CHANGED,
                f"invalid provider status: {result.status!r}",
            )
        if result.status == "failed" or result.value is None:
            return result
        if not isinstance(result.value, QuoteObservation):
            return _failed(
                result.source,
                now,
                SCHEMA_CHANGED,
                f"expected QuoteObservation, got {type(result.value).__name__}",
            )
        try:
            error = validate_quote_observation(
                result.value,
                now,
                trading_dates,
                max_intraday_age_seconds=self.max_intraday_age_seconds,
            )
        except (TypeError, ValueError) as exc:
            return _failed(result.source, now, SCHEMA_CHANGED, str(exc))
        if error is None:
            return result
        return _failed(result.source, now, SOURCE_STALE if "stale" in error else SCHEMA_CHANGED, error)


def validate_quote_observation(
    observation: QuoteObservation,
    now: datetime,
    trading_dates: Sequence[date],
    *,
    max_intraday_age_seconds: int = 120,
) -> str | None:
    """Validate price fields and session-aware freshness for one source."""
    if (
        isinstance(observation.price, bool)
        or not isinstance(observation.price, (int, float))
        or not math.isfinite(float(observation.price))
        or observation.price <= 0
    ):
        return "invalid price"
    if not isinstance(observation.source, str) or not observation.source.strip():
        return "invalid source"
    if (
        observation.instrument_name is not None
        and (
            not isinstance(observation.instrument_name, str)
            or not observation.instrument_name.strip()
        )
    ):
        return "invalid instrument name"
    try:
        quote_date = date.fromisoformat(observation.quote_date)
        quote_time = time.fromisoformat(observation.quote_time)
    except (TypeError, ValueError):
        return "invalid quote date/time"

    now_shanghai = _ensure_aware_utc(now).astimezone(timezone(timedelta(hours=8)))
    session, expected_date = market_session(now_shanghai, trading_dates)
    if quote_date != expected_date:
        return f"stale trade date: expected {expected_date.isoformat()}, got {quote_date.isoformat()}"
    if session is not MarketSession.INTRADAY:
        return None

    quote_dt = datetime.combine(quote_date, quote_time, tzinfo=now_shanghai.tzinfo)
    age = (now_shanghai - quote_dt).total_seconds()
    if age < -30 or age > max_intraday_age_seconds:
        return f"stale intraday quote: age={age:.0f}s"
    return None


def market_session(now_shanghai: datetime, trading_dates: Sequence[date]) -> tuple[MarketSession, date]:
    """Return session and the trade date a valid observation must represent."""
    available = sorted(item for item in set(trading_dates) if item <= now_shanghai.date())
    if not available:
        raise ValueError("trading calendar has no date before current time")
    today_is_trading = now_shanghai.date() in available
    current_time = now_shanghai.time().replace(tzinfo=None)
    intraday = (
        time(9, 30) <= current_time <= time(11, 30)
        or time(13, 0) <= current_time <= time(15, 0)
    )
    if today_is_trading and intraday:
        return MarketSession.INTRADAY, now_shanghai.date()
    if today_is_trading and current_time < time(9, 30):
        previous = [item for item in available if item < now_shanghai.date()]
        if not previous:
            raise ValueError("trading calendar has no previous trade date")
        return MarketSession.PRE_OPEN, previous[-1]
    return MarketSession.NON_TRADING, available[-1]


def _ensure_aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("clock must return datetime")
    if value.tzinfo is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _failed(
    source: str,
    now: datetime,
    error_code: MarketDataErrorCode,
    message: str,
) -> MarketDataResult:
    return MarketDataResult(
        None,
        "failed",
        source,
        now.isoformat(),
        error_code=error_code,
        error_message=message,
    )
