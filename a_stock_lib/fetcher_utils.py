from __future__ import annotations

from typing import Any

import pandas as pd


def detect_split_ratio(
    fhps_df: Any, latest_report_year: int | None
) -> tuple[float, str | None]:
    """Detect post-report-period stock splits and return cumulative dilution factor.

    Returns (ratio, ex_date_str) where ratio=0.0 means no qualifying split found.
    Uses getattr(fhps_df, 'empty', True) defensively so non-DataFrame inputs return
    (0.0, None) instead of raising AttributeError.
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
