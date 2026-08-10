from a_stock_lib.market_data import MarketDataResult


def test_market_data_result_defaults() -> None:
    result = MarketDataResult(1.23, "ok", "test.source", "2026-06-23T10:00:00")

    assert result.value == 1.23
    assert result.status == "ok"
    assert result.adjusted == "none"
    assert result.volume_unit == "unknown"
    assert result.error_code is None
