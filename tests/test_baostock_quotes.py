from __future__ import annotations

from a_stock_lib.providers.baostock_quotes import BaoStockMarketDataProvider


def test_baostock_provider_constructs():
    provider = BaoStockMarketDataProvider()
    assert provider is not None
