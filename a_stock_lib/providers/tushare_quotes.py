from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from a_stock_lib.market_data import (
    EMPTY_RESPONSE,
    INVALID_ARGUMENT,
    INSUFFICIENT_WINDOW,
    MISSING_COLUMNS,
    SCHEMA_CHANGED,
    SOURCE_STALE,
    MarketDataResult,
)
from a_stock_lib.providers.tushare_common import (
    DEFAULT_ENV_PATH,
    TushareRateLimiter,
    TushareProviderBase,
    classify_tushare_exception,
    replace_frame_result,
)

DAILY_SOURCE = "tushare.daily"
INDEX_DAILY_SOURCE = "tushare.index_daily"
TRADE_CAL_SOURCE = "tushare.trade_cal"
TUSHARE_VOLUME_UNIT = "hand"


class TushareMarketDataProvider(TushareProviderBase):
    """Tushare Pro implementation of the market-data provider boundary."""

    def __init__(
        self,
        token: str | None = None,
        client: Any | None = None,
        client_factory: Callable[[str], Any] | None = None,
        env_path: Path = DEFAULT_ENV_PATH,
        rate_limiter: TushareRateLimiter | None = None,
    ) -> None:
        super().__init__(
            token=token,
            client=client,
            client_factory=client_factory,
            env_path=env_path,
            rate_limiter=rate_limiter,
        )

    def fetch_score_price(self, code: str, score_date: str) -> MarketDataResult[float]:
        try:
            _score_dt = _parse_date(score_date)
        except ValueError as exc:
            return _invalid_argument(DAILY_SOURCE, exc)
        start_date = _compact(_score_dt - timedelta(days=10))
        result = self._fetch_daily(code, start_date, _compact(_score_dt), "score_price")
        if result.value is None or result.value.empty:
            return _scalar_failure(result, DAILY_SOURCE)
        return _scalar_price_result(result, _score_dt)

    def fetch_l3_bars(self, code: str, end_date: str, window: int) -> MarketDataResult[pd.DataFrame]:
        try:
            _end_dt = _parse_date(end_date)
        except ValueError as exc:
            return _invalid_argument(DAILY_SOURCE, exc)
        lookback_days = max(365, window * 3)
        start_date = _compact(_end_dt - timedelta(days=lookback_days))
        result = self._fetch_daily(code, start_date, _compact(_end_dt), "l3_bars")
        if result.value is None:
            return result
        if len(result.value) < window:
            return MarketDataResult(
                None,
                "failed",
                result.source,
                result.fetched_at,
                error_code=INSUFFICIENT_WINDOW,
                error_message=f"expected at least {window} rows, got {len(result.value)}",
                adjusted=result.adjusted,
                volume_unit=result.volume_unit,
                source_as_of=result.source_as_of,
                request_fingerprint=result.request_fingerprint,
                row_count=result.row_count,
            )
        return result

    def fetch_daily_bars_range(self, code: str, start_date: str, end_date: str) -> MarketDataResult[pd.DataFrame]:
        try:
            start = _parse_date(start_date)
            end = _parse_date(end_date)
            if start > end:
                raise ValueError("start_date must not be after end_date")
        except ValueError as exc:
            return _invalid_argument(DAILY_SOURCE, exc)
        return self._fetch_daily(code, _compact(start), _compact(end), "l3_bars")

    def fetch_outcome_price(self, code: str, target_date: str) -> MarketDataResult[float]:
        try:
            _target_dt = _parse_date(target_date)
        except ValueError as exc:
            return _invalid_argument(DAILY_SOURCE, exc)
        start_date = _compact(_target_dt - timedelta(days=10))
        result = self._fetch_daily(code, start_date, _compact(_target_dt), "outcome_price")
        if result.value is None or result.value.empty:
            return _scalar_failure(result, DAILY_SOURCE)
        return _scalar_price_result(result, _target_dt)

    def fetch_index_bars(self, symbol: str) -> MarketDataResult[pd.DataFrame]:
        try:
            ts_code = to_tushare_index_code(symbol)
        except ValueError as exc:
            return _invalid_argument(INDEX_DAILY_SOURCE, exc)
        result = self._request_frame(
            INDEX_DAILY_SOURCE,
            "index_daily",
            {"ts_code": ts_code},
            {"trade_date", "open", "high", "low", "close"},
        )
        return _normalize_requested_bars(
            result, "index_bars", date.fromisoformat(result.fetched_at[:10])
        )

    def fetch_trade_calendar(self, start_date: str, end_date: str) -> MarketDataResult[pd.DataFrame]:
        try:
            start = _parse_date(start_date)
            end = _parse_date(end_date)
            if start > end:
                raise ValueError("start_date must not be after end_date")
        except ValueError as exc:
            return _invalid_argument(TRADE_CAL_SOURCE, exc)
        result = self._request_frame(
            TRADE_CAL_SOURCE,
            "trade_cal",
            {
                "exchange": "SSE",
                "is_open": "1",
                "start_date": _compact(start),
                "end_date": _compact(end),
                "fields": "cal_date",
            },
            {"cal_date"},
        )
        if result.value is None:
            return result
        try:
            normalized = result.value[["cal_date"]].rename(columns={"cal_date": "date"}).copy()
            normalized["date"] = normalized["date"].map(_format_tushare_date)
            normalized = normalized.sort_values("date").reset_index(drop=True)
        except Exception as exc:
            return _schema_failure(result, exc)
        normalized_result = replace_frame_result(result, normalized, normalized["date"].max())
        freshness = max(
            0,
            (
                date.fromisoformat(result.fetched_at[:10])
                - date.fromisoformat(str(normalized_result.source_as_of))
            ).days,
        )
        return replace(normalized_result, freshness_days=freshness)

    def _fetch_daily(self, code: str, start_date: str, end_date: str, purpose: str) -> MarketDataResult[pd.DataFrame]:
        try:
            ts_code = to_tushare_stock_code(code)
        except ValueError as exc:
            return _invalid_argument(DAILY_SOURCE, exc)
        raw = self._request_frame(
            DAILY_SOURCE,
            "daily",
            {
                "ts_code": ts_code,
                "start_date": start_date,
                "end_date": end_date,
                "fields": "ts_code,trade_date,open,high,low,close,vol,amount",
            },
            {"trade_date", "open", "high", "low", "close"},
        )
        result = _normalize_requested_bars(raw, purpose, _parse_date(end_date))
        if result.value is None:
            return result
        lower = _format_tushare_date(start_date)
        upper = _format_tushare_date(end_date)
        if result.value["date"].min() < lower or result.value["date"].max() > upper:
            return MarketDataResult(
                None,
                "failed",
                result.source,
                result.fetched_at,
                error_code=SOURCE_STALE,
                error_message="source observation is outside requested date range",
                adjusted=result.adjusted,
                volume_unit=result.volume_unit,
                source_as_of=result.source_as_of,
                request_fingerprint=result.request_fingerprint,
                row_count=result.row_count,
            )
        return result


def to_tushare_stock_code(code: str) -> str:
    normalized = code.strip().upper()
    if normalized.endswith((".SH", ".SZ", ".BJ")):
        return normalized
    if len(normalized) != 6 or not normalized.isdigit():
        raise ValueError(f"unsupported stock code: {code}")
    if normalized.startswith("6"):
        return f"{normalized}.SH"
    if normalized.startswith(("0", "3")):
        return f"{normalized}.SZ"
    if normalized.startswith(("4", "8", "92")):
        return f"{normalized}.BJ"
    raise ValueError(f"unsupported stock code: {code}")


def to_tushare_index_code(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if normalized.endswith((".SH", ".SZ")):
        return normalized
    if normalized in {"000300", "SH000300"}:
        return "000300.SH"
    if len(normalized) == 6 and normalized.isdigit():
        suffix = "SH" if normalized.startswith("0") else "SZ"
        return f"{normalized}.{suffix}"
    raise ValueError(f"unsupported index symbol: {symbol}")


def _normalize_tushare_bars(df: Any, source: str, purpose: str) -> MarketDataResult[pd.DataFrame]:
    fetched_at = _now()
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
    normalized = df.rename(columns={"trade_date": "date", "vol": "volume"}).copy()
    required = {"date", "open", "high", "low", "close"}
    if purpose == "l3_bars":
        required.add("volume")
    missing = required - set(normalized.columns)
    if missing:
        return MarketDataResult(
            None,
            "failed",
            source,
            fetched_at,
            error_code=MISSING_COLUMNS,
            error_message=f"missing columns: {sorted(missing)}",
        )
    keep = [col for col in ["date", "open", "high", "low", "close", "volume"] if col in normalized.columns]
    try:
        normalized["date"] = normalized["date"].map(_format_tushare_date)
        for col in [c for c in ["open", "high", "low", "close", "volume"] if c in normalized.columns]:
            normalized[col] = pd.to_numeric(normalized[col], errors="raise")
            invalid = normalized[col].map(
                lambda value: not math.isfinite(float(value)) or value < 0 or (col != "volume" and value == 0)
            )
            if invalid.any():
                raise ValueError(f"invalid {col} value")
        inconsistent = (
            (normalized["low"] > normalized["high"])
            | ~normalized["open"].between(normalized["low"], normalized["high"])
            | ~normalized["close"].between(normalized["low"], normalized["high"])
        )
        if inconsistent.any():
            raise ValueError("inconsistent OHLC values")
    except Exception as exc:
        return MarketDataResult(None, "failed", source, fetched_at, error_code=SCHEMA_CHANGED, error_message=str(exc))
    return MarketDataResult(
        normalized[keep].sort_values("date").reset_index(drop=True),
        "ok",
        source,
        fetched_at,
        adjusted="none",
        volume_unit=TUSHARE_VOLUME_UNIT,
    )


def _normalize_requested_bars(
    raw: MarketDataResult[pd.DataFrame],
    purpose: str,
    reference_date: date,
) -> MarketDataResult[pd.DataFrame]:
    if raw.value is None:
        return raw
    normalized = _normalize_tushare_bars(raw.value, raw.source, purpose)
    if normalized.value is None:
        return MarketDataResult(
            None,
            "failed",
            raw.source,
            raw.fetched_at,
            error_code=normalized.error_code,
            error_message=normalized.error_message,
            request_fingerprint=raw.request_fingerprint,
            row_count=raw.row_count,
        )
    source_as_of = str(normalized.value["date"].max())
    return MarketDataResult(
        normalized.value,
        raw.status,
        raw.source,
        raw.fetched_at,
        adjusted=normalized.adjusted,
        volume_unit=normalized.volume_unit,
        freshness_days=max(0, (reference_date - date.fromisoformat(source_as_of)).days),
        source_as_of=source_as_of,
        request_fingerprint=raw.request_fingerprint,
        row_count=len(normalized.value),
    )


def _schema_failure(
    result: MarketDataResult[pd.DataFrame], exc: Exception
) -> MarketDataResult[pd.DataFrame]:
    return MarketDataResult(
        None,
        "failed",
        result.source,
        result.fetched_at,
        error_code=SCHEMA_CHANGED,
        error_message=str(exc),
        request_fingerprint=result.request_fingerprint,
        row_count=result.row_count,
    )


def _scalar_failure(result: MarketDataResult[pd.DataFrame], source: str) -> MarketDataResult[float]:
    return MarketDataResult(
        None,
        "failed",
        result.source or source,
        result.fetched_at,
        error_code=result.error_code,
        error_message=result.error_message,
        adjusted=result.adjusted,
        volume_unit=result.volume_unit,
        source_as_of=result.source_as_of,
        request_fingerprint=result.request_fingerprint,
        row_count=result.row_count,
    )


def _invalid_argument(source: str, exc: ValueError) -> MarketDataResult[Any]:
    return MarketDataResult(
        None,
        "failed",
        source,
        _now(),
        error_code=INVALID_ARGUMENT,
        error_message=str(exc),
    )


def _scalar_price_result(
    result: MarketDataResult[pd.DataFrame], requested_date: date
) -> MarketDataResult[float]:
    assert result.value is not None and not result.value.empty
    row = result.value.iloc[-1]
    freshness = (requested_date - _parse_date(str(row["date"]))).days
    if freshness < 0:
        return MarketDataResult(
            None,
            "failed",
            result.source,
            result.fetched_at,
            error_code=SOURCE_STALE,
            error_message="source observation is after requested date",
            adjusted=result.adjusted,
            volume_unit=result.volume_unit,
            source_as_of=result.source_as_of,
            request_fingerprint=result.request_fingerprint,
            row_count=result.row_count,
        )
    return MarketDataResult(
        float(row["close"]),
        "ok" if freshness == 0 else "degraded",
        result.source,
        result.fetched_at,
        fallback_reason=None if freshness == 0 else "NEAREST_AVAILABLE_PRICE",
        freshness_days=freshness,
        adjusted=result.adjusted,
        volume_unit=result.volume_unit,
        source_as_of=result.source_as_of,
        request_fingerprint=result.request_fingerprint,
        row_count=result.row_count,
    )


def _exception_result(
    source: str,
    exc: Exception,
    token: str | None = None,
) -> MarketDataResult[pd.DataFrame]:
    code, message = classify_tushare_exception(exc, token)
    return MarketDataResult(None, "failed", source, _now(), error_code=code, error_message=message)


def _compact(value: str | date) -> str:
    return _parse_date(value).strftime("%Y%m%d")


def _format_tushare_date(value: Any) -> str:
    return _parse_date(str(value)).isoformat()


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    if "-" in raw[:10]:
        return date.fromisoformat(raw[:10])
    return datetime.strptime(raw[:8], "%Y%m%d").date()


def _now() -> str:
    return datetime.now().isoformat()
