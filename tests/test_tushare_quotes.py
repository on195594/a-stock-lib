from __future__ import annotations

from a_stock_lib.providers.tushare_quotes import TushareMarketDataProvider


def test_tushare_provider_constructs_without_token():
    provider = TushareMarketDataProvider(token=None)
    assert provider.token is None


def test_tushare_provider_reads_token_from_env(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "fake-token-123")
    provider = TushareMarketDataProvider()
    assert provider.token == "fake-token-123"
