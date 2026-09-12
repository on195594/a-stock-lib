from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from a_stock_lib.market_data import MISSING_COLUMNS
from a_stock_lib.providers.tushare_fundamentals import (
    TushareFundamentalsProvider,
    read_tushare_token,
)


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
    assert result.request_fingerprint is not None
    assert result.freshness_days == 0
    assert result.source_as_of is None
    assert result.row_count == 2


def test_fetch_industry_map_without_token_fails(tmp_path, monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    provider = TushareFundamentalsProvider(
        token=None,
        cache_path=tmp_path / "cache.json",
        env_path=tmp_path / "missing.env",
    )
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
    fetched_at_epoch = time.time()
    cache_path.write_text(
        json.dumps(
            {
                "industry_map": {"600036": "银行"},
                "fetched_at": datetime.fromtimestamp(fetched_at_epoch).isoformat(),
                "fetched_at_epoch": fetched_at_epoch,
            }
        )
    )
    provider = TushareFundamentalsProvider(
        token="fake-token", cache_path=cache_path, ttl_seconds=3600
    )
    result = provider.fetch_industry_map()
    assert result.status == "ok"
    assert result.value == {"600036": "银行"}
    assert result.source_as_of is None
    assert result.request_fingerprint
    assert result.row_count == 1


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
    fetched_at_epoch = time.time() - 999999
    cache_path.write_text(
        json.dumps(
            {
                "industry_map": {"600036": "银行"},
                "fetched_at": datetime.fromtimestamp(fetched_at_epoch).isoformat(),
                "fetched_at_epoch": fetched_at_epoch,
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
    fetched_at_epoch = time.time()
    existing_payload = {
        "industry_map": {"600036": "银行"},
        "fetched_at": datetime.fromtimestamp(fetched_at_epoch).isoformat(),
        "fetched_at_epoch": fetched_at_epoch,
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


def test_fetch_industry_map_degrades_when_cache_write_fails(tmp_path, monkeypatch):
    provider = TushareFundamentalsProvider(
        token="fake-token",
        cache_path=tmp_path / "cache.json",
        client=_FakeProClient(_sample_df()),
    )

    def fail_write(_value: dict[str, str]) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(provider, "_write_cache", fail_write)

    result = provider.fetch_industry_map()

    assert result.status == "degraded"
    assert result.value == {"600036": "银行", "002594": "汽车整车"}
    assert result.fallback_reason == "CACHE_WRITE_FAILED"


def test_fetch_industry_map_empty_response_fails(tmp_path):
    provider = TushareFundamentalsProvider(
        token="fake-token",
        cache_path=tmp_path / "cache.json",
        client=_FakeProClient(pd.DataFrame(columns=["ts_code", "industry"])),
    )
    result = provider.fetch_industry_map()
    assert result.status == "failed"
    assert result.error_code == "EMPTY_RESPONSE"


def test_fetch_industry_map_schema_changed_when_required_columns_missing(tmp_path):
    provider = TushareFundamentalsProvider(
        token="fake-token",
        cache_path=tmp_path / "cache.json",
        client=_FakeProClient(
            pd.DataFrame({"code": ["600036.SH"], "industry": ["银行"]})
        ),
    )

    result = provider.fetch_industry_map()

    assert result.status == "failed"
    assert result.error_code == MISSING_COLUMNS
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


def _write_industry_cache(
    path: Path,
    industry_map: object,
    fetched_at_epoch: int | float,
    fetched_at: object | None = None,
) -> None:
    if fetched_at is None:
        fetched_at = datetime.fromtimestamp(float(fetched_at_epoch)).isoformat()
    path.write_text(
        json.dumps(
            {
                "industry_map": industry_map,
                "fetched_at": fetched_at,
                "fetched_at_epoch": fetched_at_epoch,
            }
        )
    )


def test_read_cached_industry_map_is_cache_only_and_returns_fresh_mapping(
    tmp_path, monkeypatch
):
    cache_path = tmp_path / "cache.json"
    _write_industry_cache(cache_path, {"600036": " 银行 "}, time.time())
    provider = TushareFundamentalsProvider(cache_path=cache_path, ttl_seconds=3600)
    monkeypatch.setattr(provider, "_request_frame", lambda *args, **kwargs: pytest.fail("network"))
    monkeypatch.setattr(provider, "_write_cache", lambda *args, **kwargs: pytest.fail("write"))
    before = cache_path.read_bytes()

    result = provider.read_cached_industry_map()

    assert result.status == "ok"
    assert result.value == {"600036": "银行"}
    assert result.error_code is None
    assert result.fallback_reason is None
    assert cache_path.read_bytes() == before


@pytest.mark.parametrize(
    ("age", "status", "error_code", "has_value"),
    [
        (7200, "failed", "CACHE_STALE", False),
        (-60, "failed", "CACHE_FUTURE_TIMESTAMP", False),
    ],
)
def test_read_cached_industry_map_distinguishes_stale_and_future_timestamp(
    tmp_path, age, status, error_code, has_value
):
    cache_path = tmp_path / "cache.json"
    _write_industry_cache(cache_path, {"600036": "银行"}, time.time() - age)
    provider = TushareFundamentalsProvider(cache_path=cache_path, ttl_seconds=3600)

    result = provider.read_cached_industry_map()

    assert result.status == status
    assert result.error_code == error_code
    assert result.fallback_reason == error_code
    assert (result.value is not None) is has_value


def test_read_cached_industry_map_distinguishes_missing_and_corrupt(tmp_path):
    cache_path = tmp_path / "cache.json"
    provider = TushareFundamentalsProvider(cache_path=cache_path)

    missing = provider.read_cached_industry_map()
    cache_path.write_text("{")
    corrupt = provider.read_cached_industry_map()

    assert (missing.status, missing.error_code, missing.fallback_reason) == (
        "failed",
        "CACHE_MISSING",
        "CACHE_MISSING",
    )
    assert (corrupt.status, corrupt.error_code, corrupt.fallback_reason) == (
        "failed",
        "CACHE_CORRUPT",
        "CACHE_CORRUPT",
    )


@pytest.mark.parametrize(
    ("fetched_at", "epoch", "error_code"),
    [
        ("not-a-date", 1, "CACHE_MALFORMED"),
        ("2000-01-01T00:00:00", 10**400, "CACHE_MALFORMED"),
        ("2099-01-01T00:00:00", time.time(), "CACHE_FUTURE_TIMESTAMP"),
        ("2000-01-01T00:00:00", time.time(), "CACHE_MALFORMED"),
    ],
)
def test_read_cached_industry_map_rejects_invalid_or_inconsistent_timestamps(
    tmp_path, fetched_at, epoch, error_code
):
    cache_path = tmp_path / "cache.json"
    _write_industry_cache(cache_path, {"600036": "银行"}, epoch, fetched_at)

    result = TushareFundamentalsProvider(cache_path=cache_path).read_cached_industry_map()

    assert result.status == "failed"
    assert result.value is None
    assert result.error_code == error_code


def test_read_cached_industry_map_translates_invalid_utf8_to_corrupt(tmp_path):
    cache_path = tmp_path / "cache.json"
    cache_path.write_bytes(b"\xff")

    result = TushareFundamentalsProvider(cache_path=cache_path).read_cached_industry_map()

    assert result.status == "failed"
    assert result.value is None
    assert result.error_code == "CACHE_CORRUPT"


@pytest.mark.parametrize(
    "industry_map",
    [
        {},
        {"60036": "银行"},
        {"６０００３６": "银行"},
        {"600036": "   "},
        {"600036": "银行", "bad": "汽车"},
        [["600036", "银行"]],
    ],
)
def test_read_cached_industry_map_rejects_whole_malformed_mapping(
    tmp_path, industry_map
):
    cache_path = tmp_path / "cache.json"
    _write_industry_cache(cache_path, industry_map, time.time())
    provider = TushareFundamentalsProvider(cache_path=cache_path)

    result = provider.read_cached_industry_map()

    assert result.status == "failed"
    assert result.value is None
    assert result.error_code == "CACHE_MALFORMED"
    assert result.fallback_reason == "CACHE_MALFORMED"
