from __future__ import annotations

import os

import pytest

from a_stock_lib.market_data import (
    PERMISSION_DENIED,
    RATE_LIMITED,
    REMOTE_DISCONNECTED,
    TIMEOUT,
    MarketDataResult,
)
from a_stock_lib.providers.tushare_common import (
    TushareRateLimiter,
    _freshness_days,
    call_with_network_retry,
    classify_tushare_exception,
)


class _FakeClock:
    def __init__(self) -> None:
        self.current = 100.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += seconds


def test_default_suite_starts_without_external_credentials() -> None:
    for name in ("TUSHARE_TOKEN", "TG_TOKEN", "TG_CHAT_ID", "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"):
        assert name not in os.environ


def test_market_data_result_carries_ingestion_metadata() -> None:
    result = MarketDataResult(
        value=1,
        status="ok",
        source="test",
        fetched_at="2026-07-20T00:00:00",
        source_as_of="2026-07-18",
        request_fingerprint="abc123",
        row_count=1,
    )

    assert result.source_as_of == "2026-07-18"
    assert result.request_fingerprint == "abc123"
    assert result.row_count == 1


@pytest.mark.parametrize(
    ("fetched_at", "source_as_of", "expected"),
    [
        ("2026-08-23T12:00:00", "2026-08-23", 0),
        ("2026-08-23T12:00:00", "2026-08-20", 3),
        ("2026-08-23T12:00:00", None, None),
    ],
)
def test_freshness_days_uses_observation_date(
    fetched_at: str, source_as_of: str | None, expected: int | None
) -> None:
    assert _freshness_days(fetched_at, source_as_of) == expected


def test_rate_limiter_spaces_calls_below_configured_ceiling() -> None:
    fake = _FakeClock()
    limiter = TushareRateLimiter(calls_per_minute=120, clock=fake.monotonic, sleep=fake.sleep)

    limiter.wait()
    limiter.wait()
    limiter.wait()

    assert fake.sleeps == pytest.approx([0.5, 0.5])


def test_rate_limiter_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError, match="calls_per_minute"):
        TushareRateLimiter(calls_per_minute=0)


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (RuntimeError("抱歉，您没有权限访问该接口，权限由积分决定"), PERMISSION_DENIED),
        (RuntimeError("每分钟最多访问该接口180次，访问频次超限"), RATE_LIMITED),
        (TimeoutError("read timed out"), TIMEOUT),
        (ConnectionError("remote disconnected"), REMOTE_DISCONNECTED),
    ],
)
def test_classify_tushare_exception_uses_stable_error_categories(
    exc: Exception,
    expected: str,
) -> None:
    code, _ = classify_tushare_exception(exc)
    assert code == expected


def test_classify_tushare_exception_redacts_token() -> None:
    code, message = classify_tushare_exception(
        RuntimeError("request failed for secret-token-123"),
        token="secret-token-123",
    )

    assert code is not None
    assert "secret-token-123" not in message
    assert "[REDACTED]" in message


def test_network_timeout_is_retried_once() -> None:
    calls = 0
    fake = _FakeClock()
    limiter = TushareRateLimiter(calls_per_minute=180, clock=fake.monotonic, sleep=fake.sleep)

    def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("temporary")
        return "ok"

    assert call_with_network_retry(flaky, limiter=limiter) == "ok"
    assert calls == 2


def test_generic_api_error_with_timeout_text_is_not_retried() -> None:
    calls = 0
    limiter = TushareRateLimiter(calls_per_minute=180, clock=lambda: 0.0, sleep=lambda _: None)

    def fail() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("API timeout quota message")

    with pytest.raises(RuntimeError, match="quota"):
        call_with_network_retry(fail, limiter=limiter)

    assert calls == 1
