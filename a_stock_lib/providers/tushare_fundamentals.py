from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from a_stock_lib.market_data import MarketDataResult, now
from a_stock_lib.providers.tushare_common import (
    DEFAULT_ENV_PATH,
    TushareProviderBase,
    request_fingerprint,
    read_tushare_token as read_tushare_token,
)

TUSHARE_FUNDAMENTALS_SOURCE = "tushare.stock_basic"
_INDUSTRY_PARAMS = {"exchange": "", "list_status": "L", "fields": "ts_code,industry"}
DEFAULT_CACHE_PATH = (
    Path.home() / ".cache" / "a_stock_lib" / "tushare_industry_map.json"
)
DEFAULT_TTL_SECONDS = 30 * 24 * 3600  # 30天，行业分类极少变化，不需要高频刷新


class TushareFundamentalsProvider(TushareProviderBase):
    """批量获取全市场行业分类，本地缓存（默认30天TTL），非逐股高频查询。"""

    def __init__(
        self,
        token: str | None = None,
        cache_path: Path = DEFAULT_CACHE_PATH,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        client: Any | None = None,
        env_path: Path = DEFAULT_ENV_PATH,
    ) -> None:
        super().__init__(token=token, client=client, env_path=env_path)
        self.cache_path = Path(cache_path)
        self.ttl_seconds = ttl_seconds

    def fetch_industry_map(
        self, force_refresh: bool = False
    ) -> MarketDataResult[dict[str, str]]:
        if not force_refresh:
            cached = self._read_cache()
            if cached is not None:
                return cached
        result = self._request_frame(
            TUSHARE_FUNDAMENTALS_SOURCE,
            "stock_basic",
            _INDUSTRY_PARAMS,
            {"ts_code", "industry"},
        )
        if result.value is None:
            return result
        df = result.value
        clean_df = df.dropna(subset=["industry"])
        industry_map = {
            str(row["ts_code"]).split(".")[0]: industry
            for _, row in clean_df.iterrows()
            if (industry := str(row["industry"]).strip())
        }
        try:
            self._write_cache(industry_map)
        except OSError as exc:
            return MarketDataResult(
                industry_map,
                "degraded",
                result.source,
                result.fetched_at,
                fallback_reason="CACHE_WRITE_FAILED",
                error_message=str(exc),
                freshness_days=0,
                request_fingerprint=result.request_fingerprint,
                row_count=len(industry_map),
            )
        return MarketDataResult(
            industry_map,
            result.status,
            result.source,
            result.fetched_at,
            freshness_days=0,
            request_fingerprint=result.request_fingerprint,
            row_count=len(industry_map),
        )

    def _read_cache(self) -> MarketDataResult[dict[str, str]] | None:
        if not self.cache_path.exists():
            return None
        try:
            payload = json.loads(self.cache_path.read_text())
            age_seconds = time.time() - payload["fetched_at_epoch"]
            if age_seconds > self.ttl_seconds:
                return None
            return MarketDataResult(
                payload["industry_map"],
                "ok",
                TUSHARE_FUNDAMENTALS_SOURCE,
                payload["fetched_at"],
                freshness_days=int(age_seconds / 86400),
                request_fingerprint=request_fingerprint("stock_basic", _INDUSTRY_PARAMS),
                row_count=len(payload["industry_map"]),
            )
        except Exception:
            return None

    def _write_cache(self, industry_map: dict[str, str]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "industry_map": industry_map,
                "fetched_at": now(),
                "fetched_at_epoch": time.time(),
            },
            ensure_ascii=False,
        )
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.cache_path.parent,
                prefix=f".{self.cache_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_file.write(payload)
                temp_file.flush()
                os.fsync(temp_file.fileno())
                temp_path = Path(temp_file.name)
            temp_path.replace(self.cache_path)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()
