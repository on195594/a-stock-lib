from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import pytest

from a_stock_lib.market_data import SCHEMA_CHANGED
from a_stock_lib.providers.tushare_fundamentals import TushareFundamentalsProvider, read_tushare_token


class _FakeProClient:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def stock_basic(self, exchange, list_status, fields):
        return self._df


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": ["600036.SH", "002594.SZ"],
            "industry": ["银行", "汽车整车"],
        }
    )


def test_fetch_industry_map_returns_ok_with_mapping(tmp_path):
    provider = TushareFundamentalsProvider(
        token="fake-token",
        cache_path=tmp_path / "cache.json",
        client=_FakeProClient(_sample_df()),
    )
    result = provider.fetch_industry_map()
    assert result.status == "ok"
    assert result.value == {"600036": "银行", "002594": "汽车整车"}


def test_fetch_industry_map_without_token_fails(tmp_path, monkeypatch):
    # token=None falls back to reading the real ~/a-stock-tracker/.env; stub that
    # lookup so the test doesn't depend on whether this machine has a real token.
    monkeypatch.setattr(
        "a_stock_lib.providers.tushare_fundamentals.read_tushare_token", lambda *a, **k: None
    )
    provider = TushareFundamentalsProvider(token=None, cache_path=tmp_path / "cache.json")
    result = provider.fetch_industry_map()
    assert result.status == "failed"
    assert result.error_code == "AUTH_MISSING"


def test_fetch_industry_map_reads_token_from_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "env-token-123")
    provider = TushareFundamentalsProvider(
        token=None,
        cache_path=tmp_path / "cache.json",
        env_path=tmp_path / "missing.env",
        client=_FakeProClient(_sample_df()),
    )

    result = provider.fetch_industry_map()

    assert provider.token == "env-token-123"
    assert result.status == "ok"


def test_fetch_industry_map_reads_token_from_custom_env_path(tmp_path, monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("TUSHARE_TOKEN=file-token-456\n")
    provider = TushareFundamentalsProvider(
        token=None,
        cache_path=tmp_path / "cache.json",
        env_path=env_path,
        client=_FakeProClient(_sample_df()),
    )

    result = provider.fetch_industry_map()

    assert provider.token == "file-token-456"
    assert result.status == "ok"


def test_read_tushare_token_handles_spaces_comments_and_directories(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text('TUSHARE_TOKEN = "file-token-789" # comment\n')

    assert read_tushare_token(env_path) == "file-token-789"
    assert read_tushare_token(tmp_path) is None


def test_fetch_industry_map_uses_cache_within_ttl(tmp_path):
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "industry_map": {"600036": "银行"},
                "fetched_at": "2026-06-23T00:00:00",
                "fetched_at_epoch": time.time(),
            }
        )
    )
    provider = TushareFundamentalsProvider(
        token="fake-token", cache_path=cache_path, ttl_seconds=3600
    )
    result = provider.fetch_industry_map()
    assert result.status == "ok"
    assert result.value == {"600036": "银行"}


def test_fetch_industry_map_treats_corrupt_cache_as_miss(tmp_path):
    cache_path = tmp_path / "cache.json"
    cache_path.write_text("{")
    provider = TushareFundamentalsProvider(
        token="fake-token",
        cache_path=cache_path,
        ttl_seconds=3600,
        client=_FakeProClient(_sample_df()),
    )

    result = provider.fetch_industry_map()

    assert result.status == "ok"
    assert result.value == {"600036": "银行", "002594": "汽车整车"}


def test_fetch_industry_map_ignores_stale_cache(tmp_path):
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "industry_map": {"600036": "银行"},
                "fetched_at": "2020-01-01T00:00:00",
                "fetched_at_epoch": time.time() - 999999,
            }
        )
    )
    provider = TushareFundamentalsProvider(
        token="fake-token",
        cache_path=cache_path,
        ttl_seconds=3600,
        client=_FakeProClient(_sample_df()),
    )
    result = provider.fetch_industry_map()
    assert result.value == {"600036": "银行", "002594": "汽车整车"}


def test_write_cache_preserves_existing_cache_when_replace_fails(tmp_path, monkeypatch):
    cache_path = tmp_path / "cache.json"
    existing_payload = {
        "industry_map": {"600036": "银行"},
        "fetched_at": "2026-06-23T00:00:00",
        "fetched_at_epoch": time.time(),
    }
    cache_path.write_text(json.dumps(existing_payload))
    provider = TushareFundamentalsProvider(token="fake-token", cache_path=cache_path)

    def fail_replace(self, target):
        if self.name.startswith(".cache.json."):
            raise OSError("simulated replace failure")
        return original_replace(self, target)

    original_replace = Path.replace
    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        provider._write_cache({"002594": "汽车整车"})

    assert json.loads(cache_path.read_text()) == existing_payload


def test_fetch_industry_map_empty_response_fails(tmp_path):
    provider = TushareFundamentalsProvider(
        token="fake-token",
        cache_path=tmp_path / "cache.json",
        client=_FakeProClient(pd.DataFrame()),
    )
    result = provider.fetch_industry_map()
    assert result.status == "failed"
    assert result.error_code == "EMPTY_RESPONSE"


def test_fetch_industry_map_schema_changed_when_required_columns_missing(tmp_path):
    provider = TushareFundamentalsProvider(
        token="fake-token",
        cache_path=tmp_path / "cache.json",
        client=_FakeProClient(pd.DataFrame({"code": ["600036.SH"], "industry": ["银行"]})),
    )

    result = provider.fetch_industry_map()

    assert result.status == "failed"
    assert result.error_code == SCHEMA_CHANGED
    assert result.value is None


def test_fetch_industry_map_drops_nan_industries_and_normalizes_values(tmp_path):
    provider = TushareFundamentalsProvider(
        token="fake-token",
        cache_path=tmp_path / "cache.json",
        client=_FakeProClient(
            pd.DataFrame(
                {
                    "ts_code": ["600036.SH", "002594.SZ", "000001.SZ", "300750.SZ"],
                    "industry": [" 银行 ", float("nan"), None, 123],
                }
            )
        ),
    )

    result = provider.fetch_industry_map()

    assert result.status == "ok"
    assert result.value == {"600036": "银行", "300750": "123"}
