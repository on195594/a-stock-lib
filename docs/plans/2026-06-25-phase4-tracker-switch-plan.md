# Phase 4 tracker 切换到 a-stock-lib 计划

日期：2026-06-25
最近状态更新：2026-06-26
状态：已执行完成，tracker 已切换到 `a-stock-lib==0.1.2`
范围：`~/a-stock-tracker/` 消费 `a-stock-lib==0.1.2`，退役 tracker 本地行情 Provider 副本，并已完成 BaoStock fallback 隔离超时 Provider 硬化。

> **2026-06-26 当前状态补充：** 本文档保留 Phase 4 初始实施计划和历史验收口径。在 Phase 4 切换后，为了隔离 BaoStock SDK socket hang 导致主进程挂死的风险，已将 fallback 报价 Provider 加硬为基于独立子进程与超时控制的 `IsolatedBaoStockMarketDataProvider`，版本 bump 至 `0.1.2`。当前 `a-stock-tracker` 锁定的依赖版本已更新为 `a-stock-lib==0.1.2`。本包全量测试用例数已增至 48 passed。

执行记录（历史）：2026-06-25 已在 `~/a-stock-tracker` 完成切换；`lib/market_data.py` 保留 tracker 门禁/cache wrapper，Tushare/BaoStock provider 来自 `a_stock_lib.providers.*`，本地 `lib/tushare_provider.py` 与 `lib/baostock_provider.py` 已删除。验证通过：tracker `pytest tests/ -q` 171 passed、`ruff check .` passed、`mypy` passed、`scripts/check_market_data_readiness.py` READY；a-stock-lib `pytest tests/ -v` 44 passed。agy 复查无 Blocker/High/Medium。

## 背景

`a-stock-lib` 已完成 Phase 3 本包侧硬化并发布本地 wheel 版本 `0.1.1`。当前 `a-stock-tracker` 仍使用自己的 `lib/market_data.py`、`lib/tushare_provider.py`、`lib/baostock_provider.py`，其中存在与 Phase 3 已修复问题同源的预存缺陷。

Phase 4 的目标不是做评分引擎重构，也不是引入 prompt/contracts 层，而是把 tracker 的市场数据 Provider 边界切换到版本化安装的 `a-stock-lib`，并保留 tracker 自己的数据库 audit/cache 编排。

## 目标

- `a-stock-tracker` 通过版本化依赖安装 `a-stock-lib==0.1.1`，不使用 `sys.path` 注入，不使用 editable install。
- tracker 的行情 Provider 实例来自 `a_stock_lib.providers.tushare_quotes` / `a_stock_lib.providers.baostock_quotes`。
- tracker 的 `MarketDataResult`、错误码、`CompositeMarketDataProvider` 等协议原语来自 `a_stock_lib.market_data`。
- tracker 保留本地的 `RemovedMarketDataProvider`、`get_default_market_data_provider()`、`get_market_data_backfill_provider()`、`MarketDataCacheService`，因为这些仍包含 tracker 专属环境门禁和数据库写入逻辑。
- tracker 本地 `lib/tushare_provider.py` 和 `lib/baostock_provider.py` 在兼容期后退役，避免两份 Provider 实现继续分叉。

## 非目标

- 不修改 `a-stock-research` / `a-stock-monitor`。
- 不改 scorer、weights、Gemini 定性评分、entry signal 或 prompt 规则。
- 不实现 `contracts.py`、`prompts/` canonical 源或评分引擎试点。
- 不变更 tracker 数据库 schema。
- 不改生产 cron 时间表。
- 不在 tests 中发真实网络请求。

## 前置条件

- `a-stock-lib` 当前提交包含 `0.1.1`：
  - `pyproject.toml` version 为 `0.1.1`
  - `a_stock_lib.__version__ == "0.1.1"`
  - `pytest tests/ -v` 为 `44 passed`
  - `python3 -m build` 已生成 `dist/a_stock_lib-0.1.1-py3-none-any.whl`
- `~/a-stock-tracker` 工作区干净。
- tracker 侧 `.venv` 可重建或可安装本地 wheel。
- tracker 侧现有测试在切换前有 baseline 结果。

## 改动边界

### a-stock-lib 仓库

只负责提供计划文档和已构建的版本化 wheel。Phase 4 执行期间除非发现 `a-stock-lib` 本身缺陷，否则不再修改本仓库代码。

涉及路径：

- `~/a-stock-lib/dist/a_stock_lib-0.1.1-py3-none-any.whl`
- `~/a-stock-lib/docs/plans/2026-06-25-phase4-tracker-switch-plan.md`

### a-stock-tracker 仓库

允许修改：

- `requirements.txt`
- `lib/market_data.py`
- `tests/test_market_data.py`
- `tests/test_pipeline.py`
- `scripts/probe_tushare_market_data.py`
- `README.md` 或 `docs/runbooks/market-data-provider-recovery.md` 中与 provider 位置相关的说明
- `CLAUDE.md` 中与 provider 位置相关的说明

只在第二个小提交中删除或停用：

- `lib/tushare_provider.py`
- `lib/baostock_provider.py`

禁止修改：

- `lib/cache.py` 的 schema 定义
- `pipeline.py` 的业务流程，除非测试暴露出 import 兼容问题且无法在 `lib/market_data.py` 包装层内解决
- `scorer.py`
- `gemini_scorer.py`
- `weights.json`
- cron 脚本和生产配置
- `tracker.db` 或任何本地数据库文件

## 推荐实施路线

### Step 0：切换前基线

在 `a-stock-tracker` 记录当前行为，不做任何代码修改：

```bash
cd ~/a-stock-tracker
git status --short
source .venv/bin/activate
pytest tests/ -q
ruff check .
mypy
python3 scripts/check_market_data_readiness.py
```

如果 baseline 已经失败，先判断失败是否与市场数据 Provider 无关。无关失败要记录并暂缓 Phase 4，避免把既有失败误归因到切换。

### Step 1：安装版本化 wheel

在 tracker 的虚拟环境中安装 `a-stock-lib==0.1.1` 对应 wheel：

```bash
cd ~/a-stock-tracker
source .venv/bin/activate
pip install ~/a-stock-lib/dist/a_stock_lib-0.1.1-py3-none-any.whl
python3 -c "import a_stock_lib; print(a_stock_lib.__version__)"
```

期望输出：

```text
0.1.1
```

随后更新 `requirements.txt`，推荐使用本地 wheel 路径而不是 editable install：

```text
--find-links ../a-stock-lib/dist
a-stock-lib==0.1.1
```

这里假设 `a-stock-tracker` 和 `a-stock-lib` 是同级目录。若部署环境不是同级目录，不要写死 `/home/lin/...` 绝对路径；改为在部署脚本中先把 wheel 放入统一 wheelhouse，再用 `--find-links <wheelhouse>` + `a-stock-lib==0.1.1` 安装。

### Step 2：收缩 `lib/market_data.py` 为 tracker 包装层

保留 tracker 专属逻辑：

- `ak = _RemovedAkshareShim()`
- `RemovedMarketDataProvider`
- `get_default_market_data_provider()`
- `get_market_data_backfill_provider()`
- `MarketDataCoverage`
- `MarketDataCacheService`

从 `a_stock_lib.market_data` 导入并重新导出共享原语：

- `MarketDataResult`
- `MarketDataStatus`
- `MarketDataProvider`
- `CompositeMarketDataProvider`
- 全部错误码常量
- `normalize_bars_result`
- `exception_result`
- `now`

为了降低测试和调用方改动，短期保留 tracker 旧私有函数名作为兼容别名：

```python
from a_stock_lib.market_data import normalize_bars_result as _normalize_bars_result
from a_stock_lib.market_data import exception_result as _exception_result
from a_stock_lib.market_data import now as _now
```

`get_default_market_data_provider()` 改为从共享包构造 Provider：

```python
from a_stock_lib.providers.tushare_quotes import TushareMarketDataProvider
from a_stock_lib.providers.baostock_quotes import BaoStockMarketDataProvider
```

注意：tracker 的启用门禁必须继续以 `os.environ["TUSHARE_TOKEN"]` 为唯一真理源。`pipeline.py` 和探针脚本已经负责把 tracker 项目根目录 `.env` 加载到 `os.environ`；`lib/market_data.py` 包装层不要再直接调用 `read_tushare_token()`，也不要通过 `TushareMarketDataProvider().token` 判断是否启用主源，否则单元测试中 `monkeypatch.delenv("TUSHARE_TOKEN")` 会被共享包默认 `.env` 兜底绕过，`SOURCE_DISABLED` 行为失效。

推荐写法：

```python
token = os.environ.get("TUSHARE_TOKEN", "")
if token:
    from a_stock_lib.providers.tushare_quotes import TushareMarketDataProvider
    from a_stock_lib.providers.baostock_quotes import BaoStockMarketDataProvider

    fallback = BaoStockMarketDataProvider()
    return CompositeMarketDataProvider(TushareMarketDataProvider(token=token), fallback)
return RemovedMarketDataProvider()
```

`get_market_data_backfill_provider()` 也必须基于显式环境变量判定。若要强制 BaoStock-only，调用方应显式把 `TUSHARE_TOKEN` 置为空字符串，避免 `pipeline.py` 的 `.env` loader 重新注入 token：

```python
if os.environ.get("TUSHARE_TOKEN"):
    return get_default_market_data_provider()
if os.environ.get("MARKET_DATA_ALLOW_BAOSTOCK_ONLY") == "1":
    from a_stock_lib.providers.baostock_quotes import BaoStockMarketDataProvider

    return BaoStockMarketDataProvider()
return RemovedMarketDataProvider()
```

### Step 3：更新测试导入

`tests/test_market_data.py` 当前直接从本地旧 Provider 文件导入：

- `from lib.baostock_provider import ...`
- `from lib.tushare_provider import ...`

切换为：

- `from a_stock_lib.providers.baostock_quotes import ...`
- `from a_stock_lib.providers.tushare_quotes import ...`

`from lib.market_data import ...` 可以先保留，因为 `lib/market_data.py` 是 tracker 兼容包装层，仍是 pipeline 的公共入口。

`scripts/probe_tushare_market_data.py` 也要在第一轮提交中同步改导入。该脚本当前直接依赖本地 Provider 文件；如果后续删除 `lib/tushare_provider.py` / `lib/baostock_provider.py`，但探针脚本未改，会导致生产健康检查直接 `ImportError`。

需要补充或调整的回归点：

- `get_default_market_data_provider()` 在没有 `TUSHARE_TOKEN` 环境变量时返回 `RemovedMarketDataProvider`，不会被共享包默认 `.env` 兜底绕过。
- `get_default_market_data_provider()` 在 `pipeline.py` 或 probe 已把 `.env` 加载进 `os.environ` 后返回 Tushare/BaoStock composite。
- `get_market_data_backfill_provider()` 在 `TUSHARE_TOKEN=""` 且 `MARKET_DATA_ALLOW_BAOSTOCK_ONLY=1` 时仍返回 BaoStock Provider。
- `CompositeMarketDataProvider` primary/fallback 双失败时保留 primary 失败原因。
- `_normalize_bars_result()` 对非 DataFrame 返回 `SCHEMA_CHANGED`，不会抛原生异常。
- `_exception_result()` 把 `time limit exceeded` 归类为 `TIMEOUT`。

### Step 4：第一轮验证

在 tracker 运行：

```bash
cd ~/a-stock-tracker
source .venv/bin/activate
pytest tests/test_market_data.py -q
pytest tests/test_pipeline.py -q
pytest tests/ -q
ruff check .
mypy
```

在 `a-stock-lib` 回归确认共享包未被误改：

```bash
cd ~/a-stock-lib
source .venv/bin/activate
pytest tests/ -v
```

### Step 5：dry-run 行情路径

真实网络调用只在人工授权后执行，不进入单元测试。建议顺序：

```bash
cd ~/a-stock-tracker
source .venv/bin/activate
python3 scripts/probe_tushare_market_data.py
python3 scripts/check_market_data_readiness.py
python3 pipeline.py market-data-backfill --start 2026-06-24 --end 2026-06-24
TUSHARE_TOKEN="" MARKET_DATA_ALLOW_BAOSTOCK_ONLY=1 python3 pipeline.py market-data-backfill --start 2026-06-24 --end 2026-06-24
python3 pipeline.py accuracy-report
```

注意执行顺序：如果 `scripts/check_market_data_readiness.py` 依赖最近一次 probe 报告，应先运行 `probe_tushare_market_data.py` 生成基于共享包 Provider 的新报告，再运行 readiness 检查。最终 dry-run 顺序以脚本实现为准，但不能让 readiness 只读取迁移前旧报告而假 PASS。

dry-run 后检查 audit：

```bash
sqlite3 tracker.db "
SELECT purpose, status, source, fallback_source, fallback_reason, error_code, COUNT(*)
FROM market_data_audit
WHERE run_date >= date('now', '-1 day')
GROUP BY purpose, status, source, fallback_source, fallback_reason, error_code
ORDER BY purpose, status, source;
"
```

验收重点：

- 没有新增 `SOURCE_DISABLED`，除非确实没有 token。
- `fallback_reason` 能看到 primary 失败原因，而不是只剩 fallback 报错。
- `source` 字段仍是 `tushare.daily`、`baostock.query_history_k_data_plus` 等既有语义，不因包名变化破坏历史统计。
- BaoStock fallback 只以 degraded 路径出现，不被 daily 生产写入当作主源。

### Step 6：退役旧 Provider 文件

只有在 Step 4 和 Step 5 通过后，才进入第二个小提交：

- 删除 `lib/tushare_provider.py`
- 删除 `lib/baostock_provider.py`
- 搜索并清理所有残留导入：

```bash
cd ~/a-stock-tracker
rg -n "lib\\.tushare_provider|lib\\.baostock_provider|from lib\\.market_data import .*_normalize_bars_result" .
```

如果仍有外部脚本或历史测试直接依赖旧路径，可先把两个旧文件改为轻量兼容转发模块，而不是立即删除：

```python
from a_stock_lib.providers.tushare_quotes import *  # noqa: F403
```

是否删除还是保留转发模块，由 Step 5 后的依赖搜索结果决定。

## 提交拆分

建议在 `a-stock-tracker` 中拆成两个提交：

1. `refactor: 切换tracker市场数据Provider到共享包`
   - 更新 `requirements.txt`
   - 收缩 `lib/market_data.py` 为包装层
   - 更新测试导入和回归测试
   - 更新 `scripts/probe_tushare_market_data.py` 的 Provider 导入
   - 不删除旧 provider 文件

2. `chore: 退役tracker本地行情Provider副本`
   - 删除或转发 `lib/tushare_provider.py`
   - 删除或转发 `lib/baostock_provider.py`
   - 更新 README/runbook 中的 provider 位置说明

这样如果退役旧文件暴露外部依赖，可以只回滚第二个提交。

## 回滚方案

执行 Phase 4 前先打安全标签，降低回滚时找错 commit 的风险：

```bash
cd ~/a-stock-tracker
git tag pre-a-stock-lib-phase4-$(date +%Y%m%d%H%M%S)
```

### 轻量回滚：保留依赖，恢复 tracker 包装层

适用：测试发现 `lib/market_data.py` 包装层行为不兼容，但 `a-stock-lib` 安装本身无害。

操作：

```bash
cd ~/a-stock-tracker
git revert <phase4-first-commit>
pytest tests/test_market_data.py -q
pytest tests/test_pipeline.py -q
```

### 完整回滚：恢复本地 Provider 副本

适用：生产 dry-run 或 audit 出现无法当场解释的数据源行为变化。

操作：

```bash
cd ~/a-stock-tracker
git revert <retire-provider-commit>
git revert <phase4-first-commit>
pip uninstall -y a-stock-lib
pip install -r requirements.txt
pytest tests/ -q
```

如果已对 `requirements.txt` 使用本地 wheel 路径，回滚后确认该行已移除。

不把 `git reset --hard` 作为默认回滚步骤。它适合一次性切回独立部署目录，但在共享工作区内容易误删未提交诊断信息；若生产环境需要硬切到安全 tag，应由 PM 明确确认目标 tag 和工作区备份后单独执行。

### 数据回滚

本计划不改 schema。若 dry-run 已写入 `market_data_audit` 或 `daily_bars`，不要直接删除生产库数据；先导出受影响行供审计：

```bash
sqlite3 tracker.db ".mode csv" ".headers on" "
SELECT * FROM market_data_audit
WHERE run_date >= date('now', '-1 day');
"
```

如果必须清理，只允许在明确 run_date、purpose、code 范围后单独执行，并另开任务审批。

## 验收标准

- `a-stock-tracker` 工作区切换前后均有明确测试记录。
- `requirements.txt` 明确锁定 `a-stock-lib==0.1.1`，并通过相对 `--find-links` 或部署 wheelhouse 找到 wheel，不使用 editable install，不写死 `/home/lin/...` 绝对路径。
- `pytest tests/ -q` 全绿。
- `ruff check .` 通过。
- `mypy` 通过，或只保留切换前已存在且记录过的无关失败。
- `scripts/check_market_data_readiness.py` 通过。
- `scripts/probe_tushare_market_data.py` 已改为导入共享包 Provider，并在 readiness 检查前生成新报告。
- dry-run market-data-backfill 后 audit 字段语义保持稳定。
- 显式 `TUSHARE_TOKEN="" MARKET_DATA_ALLOW_BAOSTOCK_ONLY=1` 的 BaoStock-only backfill dry-run 可运行。
- `rg -n "lib\\.tushare_provider|lib\\.baostock_provider" ~/a-stock-tracker` 无未处理依赖，或只剩有意保留的兼容转发模块。
- `a-stock-lib` 自身 `pytest tests/ -v` 仍为 `44 passed`。

## 主要风险

| 风险 | 触发条件 | 缓解 |
|---|---|---|
| `.env` token 兜底被 tracker 包装层提前短路 | 包装层调用 `read_tushare_token()` 或通过 `TushareMarketDataProvider().token` 做门禁 | 包装层只以 `os.environ["TUSHARE_TOKEN"]` 为真理源；需要 `.env` 时由 `pipeline.py` / probe 先加载到环境变量 |
| 本地 `MarketDataResult` 类型与共享包类型混用 | 部分代码仍从 `lib.market_data` 构造，部分直接从 `a_stock_lib.market_data` 构造 | `lib.market_data` 只做重新导出，避免双定义 |
| 测试仍依赖旧私有函数名 | `tests/test_market_data.py` 使用 `_normalize_bars_result` / `_exception_result` | 在包装层保留兼容别名，后续再单独清理 |
| 删除旧 Provider 文件破坏外部脚本 | 未搜索到非测试脚本直接导入 `lib.tushare_provider` | 删除前全仓 `rg`，必要时先改为转发模块 |
| 行情 audit 统计口径变化 | `source` / `fallback_reason` 字段含义变化 | dry-run 后按 purpose/status/source 聚合检查 |
| requirements 依赖路径不可移植 | 写死 `file:///home/lin/...` | 使用相对 `--find-links ../a-stock-lib/dist` 或部署 wheelhouse |

## 需要 agy 审查的问题

- 该计划是否遗漏 tracker 中仍必须保留在本地的职责。
- `lib/market_data.py` 作为兼容包装层是否足以降低改动面。
- `.env` token 兜底、BaoStock-only backfill、SOURCE_DISABLED 三条门禁是否完整。
- 回滚方案是否能覆盖测试失败和 dry-run 写入两类风险。
- 是否应删除旧 Provider 文件，还是先保留兼容转发模块一个版本。
