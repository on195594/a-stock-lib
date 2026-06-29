# Fetcher 工具函数提取计划

**日期**：2026-06-29
**目标**：消除送转复权 bug 需要修两处的重复维护问题，同时修复已知生产 bug
**范围**：两步独立提交，不合并

---

## 第一步（C）：修复 tracker 已知 bug（独立 commit）

**预估工时**：30 分钟

### 文件：`~/a-stock-tracker/lib/fetcher.py`

**Fix 1 — `timed_call_with_retry` UnboundLocalError（生产 bug）**

当前代码（约 L68-82）问题：for 循环前未初始化 `result`，`max_retries=0` 时循环体不执行，`return result` 抛 `UnboundLocalError`。

修复：在 for 循环之前添加：
```python
result: Any = ("ERROR", "no attempts made")
```

**Fix 2 — `avg_of` 缺少 None 守卫**

当前 `avg_of`（约 L100）调用了 `series.tail(n)`，但没有检查 `series is None`。a-stock-research 的版本已有此防护。

修复：在函数体首行添加：
```python
if series is None:
    return None
```

### 验收标准
- `pytest ~/a-stock-tracker/tests/ -v` 全通过
- 新增 1 个测试：`timed_call_with_retry(fn, max_retries=0)` 返回失败结果而非抛异常

---

## 第二步（A）：提取 `_detect_split_ratio` 到共享库（独立 commit）

**预估工时**：2 小时

### 新建文件：`~/a-stock-lib/a_stock_lib/fetcher_utils.py`

内容：

```python
from __future__ import annotations

from typing import Any

import pandas as pd


def detect_split_ratio(
    fhps_df: Any, latest_report_year: int | None
) -> tuple[float, str | None]:
    """Detect post-report-period stock splits and return cumulative dilution factor.

    Returns (ratio, ex_date_str) where ratio=0.0 means no qualifying split found.
    """
    if fhps_df is None or getattr(fhps_df, "empty", True) or not latest_report_year:
        return 0.0, None
    ratio_col = "送转股份-送转总比例"
    date_col = "除权除息日"
    prog_col = "方案进度"
    if ratio_col not in fhps_df.columns or date_col not in fhps_df.columns:
        return 0.0, None
    df = fhps_df.copy()
    df["_ex_date"] = pd.to_datetime(df[date_col], errors="coerce")
    df["_ratio"] = pd.to_numeric(df[ratio_col], errors="coerce").fillna(0)
    cutoff = pd.Timestamp(f"{latest_report_year}-12-31")
    today = pd.Timestamp.now().normalize()
    cond = (df["_ex_date"] > cutoff) & (df["_ex_date"] <= today) & (df["_ratio"] > 0)
    if prog_col in df.columns:
        cond = cond & (df[prog_col] == "实施分配")
    recent = df[cond]
    if recent.empty:
        return 0.0, None
    recent = recent.sort_values("_ex_date")
    latest_ex_date = recent.iloc[-1]["_ex_date"].strftime("%Y-%m-%d")
    factor = 1.0
    for _, row in recent.iterrows():
        factor *= 1.0 + float(row["_ratio"]) / 10
    return round(factor - 1.0, 6), latest_ex_date
```

注意：
- 函数名去掉前缀下划线（`detect_split_ratio` 而非 `_detect_split_ratio`），因为这是公开 API
- 参数名统一为 `fhps_df`（tracker 版本的防御性写法更好：`getattr(fhps_df, 'empty', True)`）
- 需要在 `a_stock_lib/__init__.py` 确认 `fetcher_utils` 无需显式导出（按需 import 即可）

### 新建测试：`~/a-stock-lib/tests/test_fetcher_utils.py`

至少包含：
1. `test_detect_split_ratio_no_data`：fhps_df=None 返回 (0.0, None)
2. `test_detect_split_ratio_no_qualifying_split`：无最新年报后送转，返回 (0.0, None)
3. `test_detect_split_ratio_single_split`：10转2（ratio=2.0），返回 (0.2, 除权日)
4. `test_detect_split_ratio_future_ignored`：除权日 > today，不计入
5. `test_detect_split_ratio_before_report_ignored`：除权日在最新年报之前，不计入
6. `test_detect_split_ratio_not_implemented_ignored`：方案进度≠实施分配，不计入

### 行为变更说明（codex 审查 I-1 采纳）

共享版本使用 `getattr(fhps_df, "empty", True)` 替代 research 原来的 `div_df.empty`。
对于非 DataFrame 的输入，原来会抛 `AttributeError`，共享版本会静默返回 `(0.0, None)`（更防御）。
这是行为改进而非破坏性变更，但需显式知晓。

### 新增步骤：版本 bump（codex 审查 I-2 采纳）

在创建 `fetcher_utils.py` 之后、安装之前，bump a-stock-lib 版本：

```bash
# 1. 更新 a_stock_lib/__init__.py 中的 __version__ = "0.1.3"
# 2. 更新 pyproject.toml 中的 version = "0.1.3"
# 3. 重新构建 wheel（如需安装到系统 Python）
cd ~/a-stock-lib && python3 -m build
sudo pip3 install dist/a_stock_lib-0.1.3-*.whl --force-reinstall
# 4. 在 tracker venv 里更新
source ~/a-stock-tracker/.venv/bin/activate
pip install ~/a-stock-lib/dist/a_stock_lib-0.1.3-*.whl --force-reinstall
```

### 修改：`~/a-stock-research/fetcher.py`

- 删除 `_detect_split_ratio` 函数体（L416-457 约）
- 在文件顶部 import 区域添加：
  ```python
  from a_stock_lib.fetcher_utils import detect_split_ratio as _detect_split_ratio
  ```
- 其余调用点不变（本地别名 `_detect_split_ratio` 保持调用兼容）

### 修改：`~/a-stock-tracker/lib/fetcher.py`

- 删除 `_detect_split_ratio` 函数体（L280-313 约）
- 在文件顶部 import 区域添加：
  ```python
  from a_stock_lib.fetcher_utils import detect_split_ratio as _detect_split_ratio
  ```
- 其余调用点不变

### 验收标准
- `pytest ~/a-stock-lib/tests/ -v` 全通过（含新 test_fetcher_utils.py）
- `pytest ~/a-stock-tracker/tests/ -v` 全通过（集成验证 tracker 侧 import 正常）
- `python3 -c "from a_stock_lib.fetcher_utils import detect_split_ratio; print('ok')"` 成功（验证系统 Python 可用，research skill 侧）
- `python3 -c "import a_stock_lib; print(a_stock_lib.__version__)"` 输出 `0.1.3`

---

## 风险与缓解

| 风险 | 缓解方式 |
|------|---------|
| a-stock-lib 版本变更同时影响两系统 | 提取后版本从 0.1.2 升到 0.1.3，tracker venv 和系统 Python 均需更新安装 |
| research skill 用系统 Python 的 a-stock-lib | 提取前已验证 `python3 -c "import a_stock_lib"` 成功；提取后用 `--force-reinstall` 确保 0.1.3 生效 |
| tracker venv 里的 a-stock-lib 版本 | 执行版本 bump 步骤：激活 tracker venv → pip install 新 wheel |

---

## 不在本计划范围内

- `parse_float`、`timed_call`、`avg_of` 的共享提取（agy/codex 审查认为收益边际递减）
- `cmd_fetch` 主流程合并（两者业务逻辑完全不同）
- Monorepo 重组（优先级低于代码去重）
