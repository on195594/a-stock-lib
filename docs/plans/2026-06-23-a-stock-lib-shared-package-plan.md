# a-stock-lib 共享包骨架 Implementation Plan

> **For agentic workers:** 本计划按 PM(Claude)/开发(`codex exec`)/审查(`agy`) 三方协作流水线执行，不使用 superpowers:subagent-driven-development 或 superpowers:executing-plans——PM 把每个 Task 作为独立 contract 派给 `codex exec`，`codex` 写完后 PM 派 `agy` 做对抗审查，`agy` 发现的问题直接打回给 `codex` 修，修完 PM 复查决定是否再打回（最多2轮，2轮仍卡住升级给用户）。Steps 用 checkbox(`- [ ]`)语法追踪。

**Goal:** 新建独立的 `~/a-stock-lib/` Python 包，把 `a-stock-tracker/lib/market_data.py` 里跟数据库无关的 Provider 协议原语（`MarketDataResult`/错误码/`MarketDataProvider` Protocol/`CompositeMarketDataProvider`）**复制**（不挪走、不删除原文件）进去并解耦审计写入耦合，同时把 `tushare_provider.py`/`baostock_provider.py` 两个行情 Provider 实现迁移进来，新增一个全新的 Tushare 基本面 Provider（用 `stock_basic` 接口批量拉取行业分类，替代 `a-stock-research` 里不稳定的 AKShare 接口）。

**Architecture:** 三层中 Provider 层的骨架搭建。`a_stock_lib/market_data.py` 是纯协议定义（无 IO），`a_stock_lib/providers/*.py` 是具体实现（行情用 Tushare/BaoStock，基本面新增 Tushare `stock_basic`）。本计划完成后 `a-stock-lib` 是一个可以单独 `pip install` 的包，但**没有任何项目实际切换过去用它**——tracker 继续用自己原有的 `lib/`，这是设计文档里"tracker 零风险敞口"那条原则的落地。

**Tech Stack:** Python 3.11+，`pandas`，`tushare`（可选依赖），`baostock`（可选依赖），`pytest`，`setuptools` build backend。

## Global Constraints

- **不修改 `~/a-stock-tracker/lib/` 下任何文件**——本计划只在 `~/a-stock-lib/` 新建文件，原仓库保持只读引用（`cp` 复制内容，不剪切、不 `git mv`）
- 所有新增函数必须有参数和返回值类型注解（项目编码规范）
- 异常处理：不裸 `raise Exception`，外部依赖（tushare/baostock SDK）失败要转换成 `MarketDataResult(status="failed", error_code=...)`，不让原始异常冒泡到调用方
- `TUSHARE_TOKEN` 不写进代码或配置文件，运行时从 `~/a-stock-tracker/.env` 读取（路径可通过构造参数覆盖，默认值是这个）
- 每个 Task 完成后必须跑 `pytest` 全绿才能进入下一个 Task

---

## 文件结构

```
~/a-stock-lib/
├── pyproject.toml
├── .gitignore
├── a_stock_lib/
│   ├── __init__.py          # __version__ = "0.1.0"
│   ├── market_data.py       # 纯协议：MarketDataResult/错误码/Protocol/CompositeMarketDataProvider
│   └── providers/
│       ├── __init__.py
│       ├── tushare_quotes.py        # 复制自 tushare_provider.py，只改 import 路径
│       ├── baostock_quotes.py       # 复制自 baostock_provider.py，只改 import 路径
│       └── tushare_fundamentals.py  # 新增：stock_basic 行业批量查询
└── tests/
    ├── test_market_data.py
    ├── test_tushare_quotes.py
    ├── test_baostock_quotes.py
    └── test_tushare_fundamentals.py
```

---

### Task 1: 包骨架 + pyproject.toml

**Files:**
- Create: `~/a-stock-lib/pyproject.toml`
- Create: `~/a-stock-lib/.gitignore`
- Create: `~/a-stock-lib/a_stock_lib/__init__.py`
- Create: `~/a-stock-lib/a_stock_lib/providers/__init__.py`

**Interfaces:**
- Produces: `a_stock_lib.__version__: str`，后续每次发版本时手动 bump

- [ ] **Step 1: 创建目录结构**

```bash
mkdir -p ~/a-stock-lib/a_stock_lib/providers ~/a-stock-lib/tests
cd ~/a-stock-lib && git init
```

- [ ] **Step 2: 写 pyproject.toml**

```toml
[project]
name = "a-stock-lib"
version = "0.1.0"
description = "Shared market-data provider primitives for a-stock-tracker / a-stock-research / a-stock-monitor"
requires-python = ">=3.11"
dependencies = [
    "pandas",
]

[project.optional-dependencies]
tushare = ["tushare"]
baostock = ["baostock"]
dev = ["pytest"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["a_stock_lib*"]
```

- [ ] **Step 3: 写 .gitignore**

```
__pycache__/
*.pyc
dist/
build/
*.egg-info/
.pytest_cache/
.venv/
```

- [ ] **Step 4: 写 `a_stock_lib/__init__.py`**

```python
"""Shared market-data provider primitives for the a-stock-* projects."""

__version__ = "0.1.0"
```

- [ ] **Step 5: 写空的 `a_stock_lib/providers/__init__.py`**

```python
"""Concrete provider implementations (Tushare/BaoStock quotes, Tushare fundamentals)."""
```

- [ ] **Step 6: 装成 editable 模式验证包结构没问题（仅本地开发期间用 -e，发布给消费方时改用 Task 6 的 wheel 方式）**

```bash
cd ~/a-stock-lib && python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python3 -c "import a_stock_lib; print(a_stock_lib.__version__)"
```

Expected: 打印 `0.1.0`，无报错

- [ ] **Step 7: Commit**

```bash
cd ~/a-stock-lib
git add pyproject.toml .gitignore a_stock_lib/
git commit -m "chore: a-stock-lib 包骨架"
```

---

### Task 2: 纯 Provider 协议原语（`market_data.py`）

**Files:**
- Create: `~/a-stock-lib/a_stock_lib/market_data.py`
- Test: `~/a-stock-lib/tests/test_market_data.py`

**Interfaces:**
- Consumes: 无（这是最底层模块）
- Produces:
  - `MarketDataResult[T]` dataclass，字段：`value: T | None`, `status: Literal["ok","degraded","failed"]`, `source: str`, `fetched_at: str`, `fallback_source: str | None = None`, `fallback_reason: str | None = None`, `error_code: str | None = None`, `error_message: str | None = None`, `freshness_days: int | None = None`, `adjusted: str = "none"`, `volume_unit: str = "unknown"`
  - 错误码常量：`REMOTE_DISCONNECTED`, `TIMEOUT`, `RATE_LIMITED`, `EMPTY_RESPONSE`, `SCHEMA_CHANGED`, `MISSING_COLUMNS`, `INSUFFICIENT_WINDOW`, `SOURCE_STALE`, `MIXED_SOURCE_VOLUME_UNSAFE`, `UNKNOWN_ERROR`, `SOURCE_DISABLED`, `AUTH_MISSING`, `PERMISSION_DENIED`（均为同名字符串常量，如 `TIMEOUT = "TIMEOUT"`）
  - `MarketDataProvider` Protocol：5个方法签名见下方代码
  - `CompositeMarketDataProvider(primary, fallback=None)` 类，方法 `fetch_score_price`/`fetch_l3_bars`/`fetch_daily_bars_range`/`fetch_outcome_price`/`fetch_index_bars`
  - `normalize_bars_result(df, source, purpose) -> MarketDataResult[pd.DataFrame]`（注意：去掉了原 tracker 版本的前导下划线，这是公开给 providers 用的工具函数，不是私有实现细节）
  - `exception_result(source, exc) -> MarketDataResult[pd.DataFrame]`（同样去掉前导下划线，公开）
  - `now() -> str`（同样公开，去掉前导下划线）

这是从 `~/a-stock-tracker/lib/market_data.py` 里**只复制不依赖 `lib.cache` 的部分**（原文件第1-162行 + 190-235行），跳过 `_RemovedAkshareShim`/`RemovedMarketDataProvider`（tracker 专属的"行情已禁用"策略，不是通用库该有的东西）和 `MarketDataCacheService`（依赖 `lib.cache`，留在 tracker 自己的代码里，不进共享包）。

- [ ] **Step 1: 写测试（先写测试，再写实现）**

```python
# tests/test_market_data.py
from __future__ import annotations

import pandas as pd
import pytest

from a_stock_lib.market_data import (
    EMPTY_RESPONSE,
    MISSING_COLUMNS,
    TIMEOUT,
    CompositeMarketDataProvider,
    MarketDataResult,
    exception_result,
    normalize_bars_result,
)


def test_market_data_result_defaults():
    result = MarketDataResult(1.23, "ok", "test.source", "2026-06-23T10:00:00")
    assert result.value == 1.23
    assert result.status == "ok"
    assert result.adjusted == "none"
    assert result.volume_unit == "unknown"
    assert result.error_code is None


class _FakeProvider:
    def __init__(self, result: MarketDataResult):
        self._result = result

    def fetch_score_price(self, code, score_date):
        return self._result

    def fetch_l3_bars(self, code, end_date, window):
        return self._result

    def fetch_daily_bars_range(self, code, start_date, end_date):
        return self._result

    def fetch_outcome_price(self, code, target_date):
        return self._result

    def fetch_index_bars(self, symbol):
        return self._result


def test_composite_provider_uses_primary_when_ok():
    primary = _FakeProvider(MarketDataResult(1.0, "ok", "primary.src", "t"))
    fallback = _FakeProvider(MarketDataResult(2.0, "ok", "fallback.src", "t"))
    composite = CompositeMarketDataProvider(primary, fallback)
    result = composite.fetch_score_price("600036", "2026-06-23")
    assert result.value == 1.0
    assert result.source == "primary.src"


def test_composite_provider_falls_back_and_marks_degraded():
    primary = _FakeProvider(
        MarketDataResult(None, "failed", "primary.src", "t", error_code=TIMEOUT)
    )
    fallback = _FakeProvider(MarketDataResult(2.0, "ok", "fallback.src", "t"))
    composite = CompositeMarketDataProvider(primary, fallback)
    result = composite.fetch_score_price("600036", "2026-06-23")
    assert result.value == 2.0
    assert result.status == "degraded"
    assert result.fallback_source == "primary.src"
    assert result.fallback_reason == TIMEOUT


def test_composite_provider_no_fallback_returns_primary_failure():
    primary = _FakeProvider(
        MarketDataResult(None, "failed", "primary.src", "t", error_code=TIMEOUT)
    )
    composite = CompositeMarketDataProvider(primary, fallback=None)
    result = composite.fetch_score_price("600036", "2026-06-23")
    assert result.status == "failed"
    assert result.error_code == TIMEOUT


def test_normalize_bars_result_renames_chinese_columns():
    df = pd.DataFrame(
        {"日期": ["2026-06-23"], "开盘": [10.0], "最高": [11.0], "最低": [9.5], "收盘": [10.5], "成交量": [1000]}
    )
    result = normalize_bars_result(df, "test.source", "l3_bars")
    assert result.status == "ok"
    assert list(result.value.columns) == ["date", "open", "high", "low", "close", "volume"]


def test_normalize_bars_result_empty_df_fails():
    result = normalize_bars_result(pd.DataFrame(), "test.source", "l3_bars")
    assert result.status == "failed"
    assert result.error_code == EMPTY_RESPONSE


def test_normalize_bars_result_missing_columns_fails():
    df = pd.DataFrame({"日期": ["2026-06-23"], "收盘": [10.5]})
    result = normalize_bars_result(df, "test.source", "l3_bars")
    assert result.status == "failed"
    assert result.error_code == MISSING_COLUMNS


def test_exception_result_classifies_timeout():
    result = exception_result("test.source", Exception("Connection timeout after 30s"))
    assert result.error_code == TIMEOUT
```

- [ ] **Step 2: 跑测试确认失败（模块还不存在）**

```bash
cd ~/a-stock-lib && source .venv/bin/activate
pytest tests/test_market_data.py -v
```

Expected: `ModuleNotFoundError: No module named 'a_stock_lib.market_data'`

- [ ] **Step 3: 写实现**

```python
# a_stock_lib/market_data.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, Literal, Protocol, TypeVar

import pandas as pd

T = TypeVar("T")

MarketDataStatus = Literal["ok", "degraded", "failed"]

REMOTE_DISCONNECTED = "REMOTE_DISCONNECTED"
TIMEOUT = "TIMEOUT"
RATE_LIMITED = "RATE_LIMITED"
EMPTY_RESPONSE = "EMPTY_RESPONSE"
SCHEMA_CHANGED = "SCHEMA_CHANGED"
MISSING_COLUMNS = "MISSING_COLUMNS"
INSUFFICIENT_WINDOW = "INSUFFICIENT_WINDOW"
SOURCE_STALE = "SOURCE_STALE"
MIXED_SOURCE_VOLUME_UNSAFE = "MIXED_SOURCE_VOLUME_UNSAFE"
UNKNOWN_ERROR = "UNKNOWN_ERROR"
SOURCE_DISABLED = "SOURCE_DISABLED"
AUTH_MISSING = "AUTH_MISSING"
PERMISSION_DENIED = "PERMISSION_DENIED"


@dataclass(frozen=True)
class MarketDataResult(Generic[T]):
    value: T | None
    status: MarketDataStatus
    source: str
    fetched_at: str
    fallback_source: str | None = None
    fallback_reason: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    freshness_days: int | None = None
    adjusted: str = "none"
    volume_unit: str = "unknown"


class MarketDataProvider(Protocol):
    def fetch_score_price(self, code: str, score_date: str) -> MarketDataResult[float]:
        ...

    def fetch_l3_bars(self, code: str, end_date: str, window: int) -> MarketDataResult[pd.DataFrame]:
        ...

    def fetch_daily_bars_range(self, code: str, start_date: str, end_date: str) -> MarketDataResult[pd.DataFrame]:
        ...

    def fetch_outcome_price(self, code: str, target_date: str) -> MarketDataResult[float]:
        ...

    def fetch_index_bars(self, symbol: str) -> MarketDataResult[pd.DataFrame]:
        ...


class CompositeMarketDataProvider:
    """Primary/fallback provider. Fallback results are marked degraded."""

    def __init__(self, primary: MarketDataProvider, fallback: MarketDataProvider | None = None):
        self.primary = primary
        self.fallback = fallback

    def __enter__(self) -> CompositeMarketDataProvider:
        if hasattr(self.primary, "__enter__"):
            self.primary.__enter__()
        if self.fallback and hasattr(self.fallback, "__enter__"):
            self.fallback.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if hasattr(self.primary, "__exit__"):
            self.primary.__exit__(exc_type, exc_val, exc_tb)
        if self.fallback and hasattr(self.fallback, "__exit__"):
            self.fallback.__exit__(exc_type, exc_val, exc_tb)

    def fetch_score_price(self, code: str, score_date: str) -> MarketDataResult[float]:
        return self._fetch("fetch_score_price", code, score_date)

    def fetch_l3_bars(self, code: str, end_date: str, window: int) -> MarketDataResult[pd.DataFrame]:
        return self._fetch("fetch_l3_bars", code, end_date, window)

    def fetch_daily_bars_range(self, code: str, start_date: str, end_date: str) -> MarketDataResult[pd.DataFrame]:
        return self._fetch("fetch_daily_bars_range", code, start_date, end_date)

    def fetch_outcome_price(self, code: str, target_date: str) -> MarketDataResult[float]:
        return self._fetch("fetch_outcome_price", code, target_date)

    def fetch_index_bars(self, symbol: str) -> MarketDataResult[pd.DataFrame]:
        return self._fetch("fetch_index_bars", symbol)

    def _fetch(self, method: str, *args: Any) -> MarketDataResult[Any]:
        primary_result = getattr(self.primary, method)(*args)
        if primary_result.status != "failed" or self.fallback is None:
            return primary_result
        fallback_result = getattr(self.fallback, method)(*args)
        if fallback_result.status == "failed":
            return fallback_result
        return MarketDataResult(
            fallback_result.value,
            "degraded",
            fallback_result.source,
            fallback_result.fetched_at,
            fallback_source=primary_result.source,
            fallback_reason=primary_result.error_code or primary_result.fallback_reason or "PRIMARY_FAILED",
            freshness_days=fallback_result.freshness_days,
            adjusted=fallback_result.adjusted,
            volume_unit=fallback_result.volume_unit,
        )


def normalize_bars_result(df: Any, source: str, purpose: str) -> MarketDataResult[pd.DataFrame]:
    fetched_at = now()
    if df is None or getattr(df, "empty", False):
        return MarketDataResult(None, "failed", source, fetched_at, error_code=EMPTY_RESPONSE)
    rename_map = {
        "日期": "date",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
    }
    normalized = df.rename(columns=rename_map).copy()
    required = {"date", "close"}
    if purpose == "l3_bars":
        required.add("volume")
    if not required.issubset(set(normalized.columns)):
        return MarketDataResult(
            None,
            "failed",
            source,
            fetched_at,
            error_code=MISSING_COLUMNS,
            error_message=f"missing columns: {sorted(required - set(normalized.columns))}",
        )
    keep = [col for col in ["date", "open", "high", "low", "close", "volume"] if col in normalized.columns]
    return MarketDataResult(normalized[keep], "ok", source, fetched_at, adjusted="none", volume_unit="share")


def exception_result(source: str, exc: Exception) -> MarketDataResult[pd.DataFrame]:
    message = str(exc)
    lowered = message.lower()
    if "timeout" in lowered:
        code = TIMEOUT
    elif "disconnect" in lowered or "connection" in lowered:
        code = REMOTE_DISCONNECTED
    elif "rate" in lowered or "limit" in lowered:
        code = RATE_LIMITED
    else:
        code = UNKNOWN_ERROR
    return MarketDataResult(None, "failed", source, now(), error_code=code, error_message=message)


def now() -> str:
    return datetime.now().isoformat()
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_market_data.py -v
```

Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add a_stock_lib/market_data.py tests/test_market_data.py
git commit -m "feat: 移植纯Provider协议原语（MarketDataResult/CompositeMarketDataProvider）"
```

---

### Task 3: 迁移 Tushare/BaoStock 行情 Provider

**Files:**
- Create: `~/a-stock-lib/a_stock_lib/providers/tushare_quotes.py`（复制自 `~/a-stock-tracker/lib/tushare_provider.py`）
- Create: `~/a-stock-lib/a_stock_lib/providers/baostock_quotes.py`（复制自 `~/a-stock-tracker/lib/baostock_provider.py`）
- Test: `~/a-stock-lib/tests/test_tushare_quotes.py`
- Test: `~/a-stock-lib/tests/test_baostock_quotes.py`

**Interfaces:**
- Consumes: `a_stock_lib.market_data.{MarketDataResult, 各错误码常量}`（Task 2 产出）
- Produces: `TushareMarketDataProvider`, `BaoStockMarketDataProvider` 类（签名跟原 tracker 版本完全一致，外部调用方无感）

这两个文件已经核实过**只依赖 `lib.market_data`，没有其它 tracker 专属耦合**，所以是纯复制+改 import 路径，不需要重写逻辑。

- [ ] **Step 1: 复制文件**

```bash
cp ~/a-stock-tracker/lib/tushare_provider.py ~/a-stock-lib/a_stock_lib/providers/tushare_quotes.py
cp ~/a-stock-tracker/lib/baostock_provider.py ~/a-stock-lib/a_stock_lib/providers/baostock_quotes.py
```

- [ ] **Step 2: 改 import 路径（两个文件的唯一改动）**

`tushare_quotes.py` 第11行：

```python
# 改前
from lib.market_data import (
# 改后
from a_stock_lib.market_data import (
```

`baostock_quotes.py` 第8行：

```python
# 改前
from lib.market_data import (
# 改后
from a_stock_lib.market_data import (
```

- [ ] **Step 3: 写 smoke test 确认两个文件能正常 import 且类存在**

```python
# tests/test_tushare_quotes.py
from __future__ import annotations

from a_stock_lib.providers.tushare_quotes import TushareMarketDataProvider


def test_tushare_provider_constructs_without_token():
    provider = TushareMarketDataProvider(token=None)
    assert provider.token is None


def test_tushare_provider_reads_token_from_env(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "fake-token-123")
    provider = TushareMarketDataProvider()
    assert provider.token == "fake-token-123"
```

```python
# tests/test_baostock_quotes.py
from __future__ import annotations

from a_stock_lib.providers.baostock_quotes import BaoStockMarketDataProvider


def test_baostock_provider_constructs():
    provider = BaoStockMarketDataProvider()
    assert provider is not None
```

- [ ] **Step 4: 跑测试**

```bash
pytest tests/test_tushare_quotes.py tests/test_baostock_quotes.py -v
```

Expected: 3 passed（已核实`BaoStockMarketDataProvider.__init__(self, client: Any | None = None)`，无必填参数，`BaoStockMarketDataProvider()`可以直接构造成功）

- [ ] **Step 5: Commit**

```bash
git add a_stock_lib/providers/tushare_quotes.py a_stock_lib/providers/baostock_quotes.py tests/test_tushare_quotes.py tests/test_baostock_quotes.py
git commit -m "feat: 迁移Tushare/BaoStock行情Provider（复制+改import路径）"
```

---

### Task 4: 新增 Tushare 基本面 Provider（行业分类批量查询）

**Files:**
- Create: `~/a-stock-lib/a_stock_lib/providers/tushare_fundamentals.py`
- Test: `~/a-stock-lib/tests/test_tushare_fundamentals.py`

**Interfaces:**
- Consumes: `a_stock_lib.market_data.{MarketDataResult, AUTH_MISSING, EMPTY_RESPONSE, UNKNOWN_ERROR, now}`（Task 2 产出）
- Produces: `TushareFundamentalsProvider` 类，方法 `fetch_industry_map(force_refresh: bool = False) -> MarketDataResult[dict[str, str]]`（返回 `{6位代码: 行业名}` 全市场映射）

这是全新功能（design doc 5.2/6.2节已实测验证可行：120积分免费档，一次调用拿全市场~5500行，本来就该批量缓存不是逐股查询）。

- [ ] **Step 1: 写测试（mock tushare client，不需要真实token）**

```python
# tests/test_tushare_fundamentals.py
from __future__ import annotations

import json
import time

import pandas as pd
import pytest

from a_stock_lib.providers.tushare_fundamentals import TushareFundamentalsProvider


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


def test_fetch_industry_map_without_token_fails(tmp_path):
    provider = TushareFundamentalsProvider(token=None, cache_path=tmp_path / "cache.json")
    result = provider.fetch_industry_map()
    assert result.status == "failed"
    assert result.error_code == "AUTH_MISSING"


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


def test_fetch_industry_map_empty_response_fails(tmp_path):
    provider = TushareFundamentalsProvider(
        token="fake-token",
        cache_path=tmp_path / "cache.json",
        client=_FakeProClient(pd.DataFrame()),
    )
    result = provider.fetch_industry_map()
    assert result.status == "failed"
    assert result.error_code == "EMPTY_RESPONSE"
```

- [ ] **Step 2: 跑测试确认失败（模块不存在）**

```bash
pytest tests/test_tushare_fundamentals.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: 写实现**

```python
# a_stock_lib/providers/tushare_fundamentals.py
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from a_stock_lib.market_data import (
    AUTH_MISSING,
    EMPTY_RESPONSE,
    UNKNOWN_ERROR,
    MarketDataResult,
    now,
)

TUSHARE_FUNDAMENTALS_SOURCE = "tushare.stock_basic"
DEFAULT_CACHE_PATH = Path.home() / ".cache" / "a_stock_lib" / "tushare_industry_map.json"
DEFAULT_TTL_SECONDS = 30 * 24 * 3600  # 30天，行业分类极少变化，不需要高频刷新
DEFAULT_ENV_PATH = Path.home() / "a-stock-tracker" / ".env"


def read_tushare_token(env_path: Path = DEFAULT_ENV_PATH) -> str | None:
    """从 tracker 的 .env 文件读取 TUSHARE_TOKEN，三个消费方共用同一份token。"""
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("TUSHARE_TOKEN="):
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return None


class TushareFundamentalsProvider:
    """批量获取全市场行业分类，本地缓存（默认30天TTL），非逐股高频查询。"""

    def __init__(
        self,
        token: str | None = None,
        cache_path: Path = DEFAULT_CACHE_PATH,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        client: Any | None = None,
    ) -> None:
        self.token = token if token is not None else read_tushare_token()
        self.cache_path = Path(cache_path)
        self.ttl_seconds = ttl_seconds
        self._client = client

    def fetch_industry_map(self, force_refresh: bool = False) -> MarketDataResult[dict[str, str]]:
        if not force_refresh:
            cached = self._read_cache()
            if cached is not None:
                return cached
        if not self.token:
            return MarketDataResult(
                None,
                "failed",
                TUSHARE_FUNDAMENTALS_SOURCE,
                now(),
                error_code=AUTH_MISSING,
                error_message="TUSHARE_TOKEN not found",
            )
        try:
            client = self._client or self._build_client()
            df = client.stock_basic(exchange="", list_status="L", fields="ts_code,industry")
        except Exception as exc:
            return MarketDataResult(
                None, "failed", TUSHARE_FUNDAMENTALS_SOURCE, now(), error_code=UNKNOWN_ERROR, error_message=str(exc)
            )
        if df is None or df.empty:
            return MarketDataResult(None, "failed", TUSHARE_FUNDAMENTALS_SOURCE, now(), error_code=EMPTY_RESPONSE)
        industry_map = {
            str(row["ts_code"]).split(".")[0]: row["industry"]
            for _, row in df.iterrows()
            if row.get("industry")
        }
        self._write_cache(industry_map)
        return MarketDataResult(industry_map, "ok", TUSHARE_FUNDAMENTALS_SOURCE, now())

    def _build_client(self) -> Any:
        import tushare as ts

        ts.set_token(self.token)
        return ts.pro_api()

    def _read_cache(self) -> MarketDataResult[dict[str, str]] | None:
        if not self.cache_path.exists():
            return None
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
        )

    def _write_cache(self, industry_map: dict[str, str]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(
                {"industry_map": industry_map, "fetched_at": now(), "fetched_at_epoch": time.time()},
                ensure_ascii=False,
            )
        )
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_tushare_fundamentals.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add a_stock_lib/providers/tushare_fundamentals.py tests/test_tushare_fundamentals.py
git commit -m "feat: 新增Tushare stock_basic行业分类批量Provider"
```

---

### Task 5: 全量回归 + 构建可发布的版本化 wheel

**Files:**
- 无新文件，验证性 Task

**Interfaces:**
- Consumes: Task 1-4 全部产出
- Produces: `dist/a_stock_lib-0.1.0-py3-none-any.whl`（后续消费方安装这个具体版本号的wheel，不是 `-e` 软链接，呼应设计文档6.1节"真正的版本化安装"决策）

- [ ] **Step 1: 跑全量测试**

```bash
cd ~/a-stock-lib && source .venv/bin/activate
pytest tests/ -v
```

Expected: 17 passed（Task2的9个 + Task3的3个 + Task4的5个，必须全绿）

- [ ] **Step 2: 构建wheel**

```bash
pip install build
python3 -m build
ls dist/
```

Expected: 生成 `a_stock_lib-0.1.0-py3-none-any.whl` 和对应的 `.tar.gz`

- [ ] **Step 3: 在一个全新的scratch venv里验证wheel能正常安装+使用（不依赖`-e`软链接，验证"版本化安装"真的可行）**

```bash
python3 -m venv /tmp/a_stock_lib_smoke_test
source /tmp/a_stock_lib_smoke_test/bin/activate
pip install ~/a-stock-lib/dist/a_stock_lib-0.1.0-py3-none-any.whl
python3 -c "
from a_stock_lib.market_data import MarketDataResult
from a_stock_lib.providers.tushare_fundamentals import TushareFundamentalsProvider
print('import ok, version check:')
import a_stock_lib
print(a_stock_lib.__version__)
"
deactivate
rm -rf /tmp/a_stock_lib_smoke_test
```

Expected: 打印 `import ok, version check:` 和 `0.1.0`，无报错——这一步证明了消费方（tracker/research/monitor）将来可以用具体版本号的wheel安装，不需要依赖源码软链接

- [ ] **Step 4: Commit dist产物不入库（已在.gitignore排除），但记录这次验证**

```bash
cd ~/a-stock-lib
git log --oneline
```

确认前面4个Task的commit都在，无需额外commit（这一步是纯验证，没有新文件要提交）。

---

## 验证方式（整个Plan完成后的总验收）

1. `cd ~/a-stock-lib && pytest tests/ -v` 全绿
2. `python3 -m build` 成功生成 wheel，且能在全新 venv 里 `pip install` 后正常 `import`
3. `cd ~/a-stock-tracker && git status` 确认 `lib/` 目录下没有任何文件被改动（这是本计划的硬约束——tracker 零风险敞口）
4. `cd ~/a-stock-tracker && pytest tests/ -v` 全绿（证明本计划完全没碰过tracker，原有测试不受影响）

完成以上4条，本Plan（Phase 1的核心部分）即为完成。Phase 1剩余的 `contracts.py`/`prompts/`渲染脚本，以及 Phase 2（research接入+评分引擎试点+护城河证据语法收紧），各自工作量和未决细节还不少，会在这个Plan跑完、过PM/agy审查后再写成独立的下一份Plan，不在这份文档里硬塞占位任务。
