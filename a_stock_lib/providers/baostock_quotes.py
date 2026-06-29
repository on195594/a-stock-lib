from __future__ import annotations

from datetime import date, datetime, timedelta
import multiprocessing
import os
import pickle
import tempfile
import traceback
from typing import Any

import pandas as pd

from a_stock_lib.market_data import (
    EMPTY_RESPONSE,
    MISSING_COLUMNS,
    RATE_LIMITED,
    REMOTE_DISCONNECTED,
    SCHEMA_CHANGED,
    INSUFFICIENT_WINDOW,
    TIMEOUT,
    UNKNOWN_ERROR,
    MarketDataResult,
)

BAOSTOCK_SOURCE = "baostock.query_history_k_data_plus"
BAOSTOCK_VOLUME_UNIT = "share"
DEFAULT_BAOSTOCK_TIMEOUT_SECONDS = 10.0


class BaoStockMarketDataProvider:
    """BaoStock daily-bar provider for fallback/backfill use."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self._is_logged_in = False
        self._in_context = False

    def __enter__(self) -> BaoStockMarketDataProvider:
        self._in_context = True
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._in_context = False
        self.close()

    def close(self) -> None:
        if self._is_logged_in and self._client is not None:
            try:
                self._client.logout()
            except Exception:
                pass
            self._is_logged_in = False

    def fetch_score_price(self, code: str, score_date: str) -> MarketDataResult[float]:
        start_date = (_parse_date(score_date) - timedelta(days=10)).isoformat()
        result = self._fetch_bars(code, start_date, score_date, "score_price")
        if result.value is None or result.value.empty:
            return _scalar_failure(result)
        row = result.value.iloc[-1]
        freshness = (_parse_date(score_date) - _parse_date(str(row["date"]))).days
        return MarketDataResult(
            float(row["close"]),
            "ok" if freshness == 0 else "degraded",
            result.source,
            result.fetched_at,
            fallback_reason=None if freshness == 0 else "NEAREST_AVAILABLE_PRICE",
            freshness_days=freshness,
            adjusted=result.adjusted,
            volume_unit=result.volume_unit,
        )

    def fetch_l3_bars(self, code: str, end_date: str, window: int) -> MarketDataResult[pd.DataFrame]:
        start_date = (_parse_date(end_date) - timedelta(days=max(365, window * 3))).isoformat()
        result = self._fetch_bars(code, start_date, end_date, "l3_bars")
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
            )
        return result

    def fetch_daily_bars_range(self, code: str, start_date: str, end_date: str) -> MarketDataResult[pd.DataFrame]:
        return self._fetch_bars(code, start_date, end_date, "l3_bars")

    def fetch_outcome_price(self, code: str, target_date: str) -> MarketDataResult[float]:
        start_date = (_parse_date(target_date) - timedelta(days=10)).isoformat()
        result = self._fetch_bars(code, start_date, target_date, "outcome_price")
        if result.value is None or result.value.empty:
            return _scalar_failure(result)
        row = result.value.iloc[-1]
        freshness = (_parse_date(target_date) - _parse_date(str(row["date"]))).days
        return MarketDataResult(
            float(row["close"]),
            "ok" if freshness == 0 else "degraded",
            result.source,
            result.fetched_at,
            fallback_reason=None if freshness == 0 else "NEAREST_AVAILABLE_PRICE",
            freshness_days=freshness,
            adjusted=result.adjusted,
            volume_unit=result.volume_unit,
        )

    def fetch_index_bars(self, symbol: str) -> MarketDataResult[pd.DataFrame]:
        start_date = (date.today() - timedelta(days=3650)).isoformat()
        try:
            code = to_baostock_index_code(symbol)
        except Exception as exc:
            return _exception_result(exc)
        return self._fetch_bars(code, start_date, date.today().isoformat(), "index_bars")

    def _fetch_bars(self, code: str, start_date: str, end_date: str, purpose: str) -> MarketDataResult[pd.DataFrame]:
        try:
            client_result = self._ensure_client()
            if isinstance(client_result, MarketDataResult):
                return client_result
            login_failure = self._ensure_login(client_result)
            if login_failure is not None:
                return login_failure
            rs = self._query_bars(client_result, code, start_date, end_date)
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            df = pd.DataFrame(rows, columns=rs.fields)
            return _normalize_baostock_bars(df, purpose)
        except Exception as exc:
            self._is_logged_in = False
            return _exception_result(exc)
        finally:
            if not self._in_context:
                try:
                    self._client.logout()
                except Exception:
                    pass
                self._is_logged_in = False

    def _ensure_client(self) -> Any | MarketDataResult[pd.DataFrame]:
        if self._client is not None:
            return self._client
        try:
            import baostock as baostock_module
        except Exception as exc:
            return _exception_result(exc)
        self._client = baostock_module
        return self._client

    def _ensure_login(self, client: Any) -> MarketDataResult[pd.DataFrame] | None:
        if self._is_logged_in:
            return None
        try:
            login = client.login()
        except Exception as exc:
            return _exception_result(exc)
        if getattr(login, "error_code", "0") != "0":
            return MarketDataResult(
                None,
                "failed",
                BAOSTOCK_SOURCE,
                _now(),
                error_code=REMOTE_DISCONNECTED,
                error_message=getattr(login, "error_msg", "baostock login failed"),
            )
        self._is_logged_in = True
        return None

    def _query_bars(self, client: Any, code: str, start_date: str, end_date: str) -> Any:
        rs = client.query_history_k_data_plus(
            to_baostock_stock_code(code),
            "date,code,open,high,low,close,volume,amount,adjustflag,tradestatus",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="3",
        )
        if getattr(rs, "error_code", "0") != "0":
            raise RuntimeError(getattr(rs, "error_msg", "baostock query failed"))
        return rs


class IsolatedBaoStockMarketDataProvider:
    """BaoStock provider wrapper that hard-times out socket hangs in a child process."""

    source = BAOSTOCK_SOURCE

    def __init__(self, timeout_seconds: float = DEFAULT_BAOSTOCK_TIMEOUT_SECONDS, runner: Any | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self._runner = runner or _run_provider_method_with_timeout

    def __enter__(self) -> IsolatedBaoStockMarketDataProvider:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return None

    def fetch_score_price(self, code: str, score_date: str) -> MarketDataResult[float]:
        return self._call("fetch_score_price", code, score_date)

    def fetch_l3_bars(self, code: str, end_date: str, window: int) -> MarketDataResult[pd.DataFrame]:
        return self._call("fetch_l3_bars", code, end_date, window)

    def fetch_daily_bars_range(self, code: str, start_date: str, end_date: str) -> MarketDataResult[pd.DataFrame]:
        return self._call("fetch_daily_bars_range", code, start_date, end_date)

    def fetch_outcome_price(self, code: str, target_date: str) -> MarketDataResult[float]:
        return self._call("fetch_outcome_price", code, target_date)

    def fetch_index_bars(self, symbol: str) -> MarketDataResult[pd.DataFrame]:
        return self._call("fetch_index_bars", symbol)

    def _call(self, method: str, *args: Any) -> MarketDataResult[Any]:
        try:
            return self._runner(method, args, self.timeout_seconds)
        except TimeoutError as exc:
            return MarketDataResult(
                None,
                "failed",
                BAOSTOCK_SOURCE,
                _now(),
                error_code=TIMEOUT,
                error_message=str(exc),
            )
        except Exception as exc:
            return _exception_result(exc)


def _run_provider_method_with_timeout(method: str, args: tuple[Any, ...], timeout_seconds: float) -> MarketDataResult[Any]:
    ctx = multiprocessing.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_baostock_worker, args=(method, args, child_conn))
    result_path: str | None = None
    process.start()
    try:
        child_conn.close()
        if not parent_conn.poll(timeout_seconds):
            _stop_process(process)
            raise TimeoutError(f"BaoStock provider call {method} exceeded {timeout_seconds:.1f}s")
        success, payload = parent_conn.recv()
        process.join(1)
        if process.is_alive():
            _stop_process(process)
        if success:
            result_path = str(payload)
            with open(result_path, "rb") as result_file:
                return pickle.load(result_file)
        message, child_traceback = payload
        raise RuntimeError(f"{message}\n{child_traceback}")
    finally:
        parent_conn.close()
        if process.is_alive():
            _stop_process(process)
        process.close()
        if result_path is not None:
            try:
                os.unlink(result_path)
            except OSError:
                pass


def _stop_process(process: multiprocessing.Process) -> None:
    process.terminate()
    process.join(1)
    if process.is_alive():
        process.kill()
        process.join(1)


def _baostock_worker(method: str, args: tuple[Any, ...], result_conn: Any) -> None:
    provider = BaoStockMarketDataProvider()
    result_path: str | None = None
    try:
        result = getattr(provider, method)(*args)
        with tempfile.NamedTemporaryFile(prefix="a_stock_lib_baostock_", suffix=".pickle", delete=False) as result_file:
            pickle.dump(result, result_file)
            result_path = result_file.name
        result_conn.send((True, result_path))
    except Exception as exc:
        if result_path is not None:
            try:
                os.unlink(result_path)
            except OSError:
                pass
        result_conn.send((False, (str(exc), traceback.format_exc())))
    finally:
        provider.close()
        result_conn.close()


def to_baostock_stock_code(code: str) -> str:
    normalized = code.strip().lower()
    if normalized.endswith((".sh", ".sz", ".bj")):
        normalized = f"{normalized[-2:]}.{normalized[:-3]}"
    elif normalized.startswith(("sh", "sz", "bj")) and not normalized.startswith(("sh.", "sz.", "bj.")):
        normalized = f"{normalized[:2]}.{normalized[2:]}"
    if normalized.startswith(("sh.", "sz.", "bj.")):
        return normalized
    if len(normalized) != 6 or not normalized.isdigit():
        raise ValueError(f"unsupported stock code: {code}")
    if normalized.startswith("6"):
        return f"sh.{normalized}"
    if normalized.startswith(("0", "3")):
        return f"sz.{normalized}"
    if normalized.startswith(("4", "8")):
        return f"bj.{normalized}"
    raise ValueError(f"unsupported stock code: {code}")


def to_baostock_index_code(symbol: str) -> str:
    normalized = symbol.strip().lower()
    if normalized in {"000300", "sh000300", "sh.000300"}:
        return "sh.000300"
    if normalized in {"000001", "sh000001", "sh.000001"}:
        return "sh.000001"
    return to_baostock_stock_code(symbol)


def _check_baostock_df(
    df: Any, purpose: str, fetched_at: str
) -> MarketDataResult[pd.DataFrame] | None:
    """Returns a failed result if df fails validation, None if it passes."""
    if df is None:
        return MarketDataResult(None, "failed", BAOSTOCK_SOURCE, fetched_at, error_code=EMPTY_RESPONSE)
    if not isinstance(df, pd.DataFrame):
        return MarketDataResult(
            None,
            "failed",
            BAOSTOCK_SOURCE,
            fetched_at,
            error_code=SCHEMA_CHANGED,
            error_message=f"expected pandas.DataFrame, got {type(df).__name__}",
        )
    if df.empty:
        return MarketDataResult(None, "failed", BAOSTOCK_SOURCE, fetched_at, error_code=EMPTY_RESPONSE)
    required = {"date", "open", "high", "low", "close"}
    if purpose == "l3_bars":
        required.add("volume")
    missing = required - set(df.columns)
    if missing:
        return MarketDataResult(
            None,
            "failed",
            BAOSTOCK_SOURCE,
            fetched_at,
            error_code=MISSING_COLUMNS,
            error_message=f"missing columns: {sorted(missing)}",
        )
    return None


def _normalize_baostock_bars(df: Any, purpose: str) -> MarketDataResult[pd.DataFrame]:
    fetched_at = _now()
    error = _check_baostock_df(df, purpose, fetched_at)
    if error is not None:
        return error
    keep = [col for col in ["date", "open", "high", "low", "close", "volume"] if col in df.columns]
    normalized = df[keep].copy()
    try:
        for col in [c for c in ["open", "high", "low", "close", "volume"] if c in normalized.columns]:
            normalized[col] = pd.to_numeric(normalized[col], errors="raise")
    except Exception as exc:
        return MarketDataResult(
            None,
            "failed",
            BAOSTOCK_SOURCE,
            fetched_at,
            error_code=SCHEMA_CHANGED,
            error_message=str(exc),
        )
    normalized = normalized.sort_values("date").reset_index(drop=True)
    return MarketDataResult(
        normalized,
        "ok",
        BAOSTOCK_SOURCE,
        fetched_at,
        adjusted="none",
        volume_unit=BAOSTOCK_VOLUME_UNIT,
    )


def _scalar_failure(result: MarketDataResult[pd.DataFrame]) -> MarketDataResult[float]:
    return MarketDataResult(
        None,
        "failed",
        result.source,
        result.fetched_at,
        error_code=result.error_code,
        error_message=result.error_message,
        adjusted=result.adjusted,
        volume_unit=result.volume_unit,
    )


def _exception_result(exc: Exception) -> MarketDataResult[pd.DataFrame]:
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
    return MarketDataResult(None, "failed", BAOSTOCK_SOURCE, _now(), error_code=code, error_message=message)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def _now() -> str:
    return datetime.now().isoformat()
