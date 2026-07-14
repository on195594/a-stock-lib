from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from a_stock_lib.market_data import EMPTY_RESPONSE, TIMEOUT, MarketDataResult
from a_stock_lib.providers.validated_realtime_quotes import (
    QuoteObservation,
    ValidatedRealtimeQuoteProvider,
    validate_quote_observation,
)


NOW_UTC = datetime(2026, 7, 14, 2, 0, tzinfo=timezone.utc)  # 10:00 Asia/Shanghai
TRADING_DATES = [date(2026, 7, 13), date(2026, 7, 14)]


class FakeSource:
    def __init__(self, result: MarketDataResult[QuoteObservation]) -> None:
        self.result = result

    def fetch_quote(self, code: str) -> MarketDataResult[QuoteObservation]:
        return self.result


def ok(source: str, price: float = 10.0, quote_time: str = '09:59:00', quote_date: str = '2026-07-14') -> MarketDataResult[QuoteObservation]:
    return MarketDataResult(
        QuoteObservation(price, quote_date, quote_time, source),
        'ok', source, NOW_UTC.isoformat(),
    )


def failed(source: str, code: str = EMPTY_RESPONSE) -> MarketDataResult[QuoteObservation]:
    return MarketDataResult(None, 'failed', source, NOW_UTC.isoformat(), error_code=code)


def provider(primary, eastmoney, tencent) -> ValidatedRealtimeQuoteProvider:
    return ValidatedRealtimeQuoteProvider(
        FakeSource(primary), FakeSource(eastmoney), FakeSource(tencent), TRADING_DATES,
        clock=lambda: NOW_UTC,
    )


def test_primary_success_does_not_need_fallback_agreement() -> None:
    result = provider(ok('sina'), failed('eastmoney'), failed('tencent')).fetch_quote('600000')

    assert result.status == 'ok'
    assert result.value is not None
    assert result.value.source == 'sina'
    assert result.value.degraded is False


def test_dual_fallback_success_uses_eastmoney_and_records_both() -> None:
    result = provider(failed('sina'), ok('eastmoney', 10.0), ok('tencent', 10.03)).fetch_quote('600000')

    assert result.status == 'degraded'
    assert result.value is not None
    assert result.value.price == 10.0
    assert set(result.value.verification) == {'eastmoney', 'tencent'}


def test_dual_fallback_uses_verifier_name_when_chosen_source_omits_it() -> None:
    east = MarketDataResult(
        QuoteObservation(10.0, '2026-07-14', '09:59:00', 'eastmoney'),
        'ok', 'eastmoney', NOW_UTC.isoformat(),
    )
    tencent = MarketDataResult(
        QuoteObservation(
            10.0, '2026-07-14', '09:59:00', 'tencent', instrument_name='测试公司'
        ),
        'ok', 'tencent', NOW_UTC.isoformat(),
    )

    result = provider(failed('sina'), east, tencent).fetch_quote('600000')

    assert result.value is not None
    assert result.value.instrument_name == '测试公司'


@pytest.mark.parametrize('bad_result', [failed('tencent'), failed('tencent', TIMEOUT)])
def test_one_fallback_failure_or_timeout_fails_closed(bad_result) -> None:
    result = provider(failed('sina'), ok('eastmoney'), bad_result).fetch_quote('600000')

    assert result.status == 'failed'
    assert result.value is None


@pytest.mark.parametrize(
    'price', [float('nan'), float('inf'), float('-inf'), True, False]
)
def test_non_finite_or_boolean_prices_fail_closed(price) -> None:
    result = provider(
        failed('sina'),
        ok('eastmoney', price),
        ok('tencent', 10.0),
    ).fetch_quote('600000')

    assert result.status == 'failed'
    assert result.value is None


def test_degraded_primary_is_not_laundered_into_ok() -> None:
    degraded = MarketDataResult(
        QuoteObservation(10.0, '2026-07-14', '09:59:00', 'sina'),
        'degraded',
        'sina',
        NOW_UTC.isoformat(),
    )

    result = provider(
        degraded,
        ok('eastmoney', 10.0),
        ok('tencent', 10.0),
    ).fetch_quote('600000')

    assert result.status == 'degraded'
    assert result.value is not None
    assert result.value.source == 'eastmoney'


def test_calendar_exception_is_returned_as_failure() -> None:
    def broken_calendar():
        raise RuntimeError('calendar unavailable')

    quote_provider = ValidatedRealtimeQuoteProvider(
        FakeSource(ok('sina')),
        FakeSource(ok('eastmoney')),
        FakeSource(ok('tencent')),
        broken_calendar,
        clock=lambda: NOW_UTC,
    )

    result = quote_provider.fetch_quote('600000')

    assert result.status == 'failed'
    assert 'calendar unavailable' in (result.error_message or '')


def test_naive_clock_is_returned_as_failure() -> None:
    quote_provider = ValidatedRealtimeQuoteProvider(
        FakeSource(ok('sina')),
        FakeSource(ok('eastmoney')),
        FakeSource(ok('tencent')),
        TRADING_DATES,
        clock=lambda: NOW_UTC.replace(tzinfo=None),
    )

    result = quote_provider.fetch_quote('600000')

    assert result.status == 'failed'
    assert 'timezone-aware' in (result.error_message or '')


def test_fallback_sources_must_be_independent() -> None:
    result = provider(
        failed('sina'),
        ok('duplicate', 10.0),
        ok('duplicate', 10.0),
    ).fetch_quote('600000')

    assert result.status == 'failed'


@pytest.mark.parametrize(
    ('max_age', 'max_difference'),
    [
        (-1, 0.003), (True, 0.003), (1.5, 0.003),
        (120, -0.1), (120, float('nan')), (120, 1.0), (120, False),
    ],
)
def test_invalid_provider_thresholds_are_rejected(max_age, max_difference) -> None:
    with pytest.raises(ValueError):
        ValidatedRealtimeQuoteProvider(
            FakeSource(ok('sina')),
            FakeSource(ok('eastmoney')),
            FakeSource(ok('tencent')),
            TRADING_DATES,
            max_intraday_age_seconds=max_age,
            max_relative_difference=max_difference,
        )


def test_fallback_trade_date_mismatch_fails_closed() -> None:
    result = provider(
        failed('sina'), ok('eastmoney'), ok('tencent', quote_date='2026-07-13')
    ).fetch_quote('600000')

    assert result.status == 'failed'


def test_intraday_freshness_120_second_boundary_is_inclusive() -> None:
    observation = QuoteObservation(10.0, '2026-07-14', '09:58:00', 'sina')

    assert validate_quote_observation(observation, NOW_UTC, TRADING_DATES) is None
    assert 'stale' in validate_quote_observation(
        QuoteObservation(10.0, '2026-07-14', '09:57:59', 'sina'),
        NOW_UTC,
        TRADING_DATES,
    )


def test_price_difference_0_3_percent_boundary_is_inclusive() -> None:
    accepted = provider(failed('sina'), ok('eastmoney', 100.0), ok('tencent', 100.3)).fetch_quote('600000')
    rejected = provider(failed('sina'), ok('eastmoney', 100.0), ok('tencent', 100.31)).fetch_quote('600000')

    assert accepted.status == 'degraded'
    assert rejected.status == 'failed'


def test_non_trading_preopen_requires_previous_trade_date() -> None:
    preopen = datetime(2026, 7, 14, 1, 0, tzinfo=timezone.utc)  # 09:00 Shanghai

    assert validate_quote_observation(
        QuoteObservation(10.0, '2026-07-13', '15:00:00', 'sina'),
        preopen,
        TRADING_DATES,
    ) is None
    assert 'stale trade date' in validate_quote_observation(
        QuoteObservation(10.0, '2026-07-14', '09:00:00', 'sina'),
        preopen,
        TRADING_DATES,
    )
