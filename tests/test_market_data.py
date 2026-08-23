import tomllib
from pathlib import Path

import a_stock_lib
from a_stock_lib.market_data import MarketDataResult


def test_package_versions_match() -> None:
    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())

    assert a_stock_lib.__version__ == project["project"]["version"]


def test_market_data_result_defaults() -> None:
    result = MarketDataResult(1.23, "ok", "test.source", "2026-06-23T10:00:00")

    assert result.value == 1.23
    assert result.status == "ok"
    assert result.adjusted == "none"
    assert result.volume_unit == "unknown"
    assert result.error_code is None
