"""Deterministic, report-only fundamental scoring for frameworks A-F."""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from a_stock_lib.contracts import (
    CycleStage,
    FrameworkKey,
    RatingTier,
    SubjectiveAssessment,
    SubjectiveCategory,
    required_subjective_categories,
)


@dataclass(frozen=True)
class DimensionScore:
    key: str
    score: float
    max_score: float
    reason: str
    missing: bool = False


@dataclass(frozen=True)
class FrameworkScore:
    framework: FrameworkKey
    rule_version: str
    rule_hash: str
    dimensions: tuple[DimensionScore, ...]
    subtotal: float
    complete: bool
    missing_inputs: tuple[str, ...]
    red_flags: tuple[str, ...]

    @property
    def blocked(self) -> bool:
        return bool(self.red_flags)


Metrics = Mapping[str, Any]
RULE_VERSION = "2026-08-23.v1"
_RULE_SIGNATURES = {
    FrameworkKey.A: "A|roe15:15/10|growth10:15/8|debt10:40/60|margin10|moat10|position5",
    FrameworkKey.B: "B|roe15:13/9|nim10|npl15:1/1.5|provision10:300/150|moat5|position5",
    FrameworkKey.C: "C|roe10:12/8|profit10|debt10:45/65|yield15:5/3|reserve10|position5|growth-branch",
    FrameworkKey.D: "D|roe-percentile10:30/50|volume10:5/0|debt10:55/70|yield15:4/2.5|franchise10|position5",
    FrameworkKey.E: "E|roe15:20/12|growth10:15/8|margin15:50/30|inventory10:60/120|brand5|position5",
    FrameworkKey.F: "F|revenue15:30/15|margin15:50/30|rd10:15/8|orders10|cash5|position5",
}


def framework_rule_hash(framework: FrameworkKey | str) -> str:
    key = framework if isinstance(framework, FrameworkKey) else FrameworkKey(framework.upper())
    payload = f"{RULE_VERSION}|{_RULE_SIGNATURES[key]}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def score_fundamentals(
    framework: FrameworkKey | str,
    metrics: Metrics,
    subjective: Sequence[SubjectiveAssessment],
    *,
    cycle_stage: CycleStage | None = None,
) -> FrameworkScore:
    """Score one framework without writing state or producing an action."""
    key = framework if isinstance(framework, FrameworkKey) else FrameworkKey(framework.upper())
    assessments = {item.category: item for item in subjective}
    scorers = {
        FrameworkKey.A: _score_a,
        FrameworkKey.B: _score_b,
        FrameworkKey.C: _score_c,
        FrameworkKey.D: _score_d,
        FrameworkKey.E: _score_e,
        FrameworkKey.F: _score_f,
    }
    dimensions, red_flags, gates = scorers[key](metrics, assessments, cycle_stage)
    missing = [item.key for item in dimensions if item.missing]
    missing.extend(gates)
    missing.extend(
        f"subjective:{category.value}"
        for category in required_subjective_categories(key)
        if category not in assessments
    )
    return FrameworkScore(
        framework=key,
        rule_version=RULE_VERSION,
        rule_hash=framework_rule_hash(key),
        dimensions=tuple(dimensions),
        subtotal=round(sum(item.score for item in dimensions), 2),
        complete=not missing,
        missing_inputs=tuple(dict.fromkeys(missing)),
        red_flags=tuple(red_flags),
    )


def _number(metrics: Metrics, key: str) -> float | None:
    value = metrics.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _boolean(metrics: Metrics, key: str) -> bool | None:
    value = metrics.get(key)
    return value if isinstance(value, bool) else None


def _missing(key: str, maximum: float) -> DimensionScore:
    return DimensionScore(key, 0.0, maximum, "missing", True)


def _higher(key: str, value: float | None, excellent: float, passed: float, maximum: float) -> DimensionScore:
    if value is None:
        return _missing(key, maximum)
    if value > excellent:
        return DimensionScore(key, maximum, maximum, f"{value:g}>{excellent:g}")
    if value > passed:
        return DimensionScore(key, maximum / 2, maximum, f"{value:g}>{passed:g}")
    return DimensionScore(key, 0.0, maximum, f"{value:g}<=pass threshold")


def _lower(key: str, value: float | None, excellent: float, passed: float, maximum: float) -> DimensionScore:
    if value is None:
        return _missing(key, maximum)
    if value < excellent:
        return DimensionScore(key, maximum, maximum, f"{value:g}<{excellent:g}")
    if value < passed:
        return DimensionScore(key, maximum / 2, maximum, f"{value:g}<{passed:g}")
    return DimensionScore(key, 0.0, maximum, f"{value:g}>=pass threshold")


def _subjective(
    key: str,
    category: SubjectiveCategory,
    assessments: Mapping[SubjectiveCategory, SubjectiveAssessment],
    maximum: float,
) -> DimensionScore:
    item = assessments.get(category)
    if item is None:
        return _missing(key, maximum)
    score = maximum if item.rating is RatingTier.HIGH else maximum / 2
    return DimensionScore(key, score, maximum, f"{item.rating.value}; evidence={len(item.evidence)}")


def _scaled(item: DimensionScore, factor: float, reason: str) -> DimensionScore:
    return DimensionScore(item.key, round(item.score * factor, 2), item.max_score, f"{item.reason}; {reason}", item.missing)


def _common_red_flags(metrics: Metrics) -> list[str]:
    value = metrics.get("red_flags", ())
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return list(value)
    return ["invalid_red_flags"] if value not in (None, ()) else []


def _score_a(metrics: Metrics, assessments, _cycle):
    debt = _number(metrics, "debt_ratio")
    debt_item = _lower("debt_ratio", debt, 40, 60, 10)
    interest_debt = _number(metrics, "interest_bearing_to_total_debt")
    if debt is not None and 60 <= debt <= 75 and interest_debt is not None and interest_debt < 40:
        debt_item = DimensionScore("debt_ratio", 5, 10, "capital-intensive debt exception")
    gross_margin = _number(metrics, "gross_margin")
    stable = _boolean(metrics, "gross_margin_stable")
    if gross_margin is None or stable is None:
        margin_item = _missing("gross_margin_stability", 10)
    elif gross_margin > 30 and stable:
        margin_item = DimensionScore("gross_margin_stability", 10, 10, "margin>30 and stable")
    elif stable:
        margin_item = DimensionScore("gross_margin_stability", 5, 10, "no material decline")
    else:
        margin_item = DimensionScore("gross_margin_stability", 0, 10, "margin declining")
    red = _common_red_flags(metrics)
    goodwill = _number(metrics, "goodwill_to_assets")
    pledge = _number(metrics, "controller_pledge_ratio")
    if goodwill is not None and goodwill > 30:
        red.append("goodwill_to_assets_above_30")
    if _boolean(metrics, "receivables_sustained_surge"):
        red.append("receivables_sustained_surge")
    if _boolean(metrics, "operating_cf_consecutive_negative"):
        red.append("operating_cf_consecutive_negative")
    if pledge is not None and pledge > 70:
        red.append("controller_pledge_above_70")
    return [
        _higher("roe_3y_avg", _number(metrics, "roe_3y_avg"), 15, 10, 15),
        _higher("net_profit_growth_3y", _number(metrics, "net_profit_growth_3y"), 15, 8, 10),
        debt_item,
        margin_item,
        _subjective("moat", SubjectiveCategory.MOAT, assessments, 10),
        _subjective("industry_position", SubjectiveCategory.INDUSTRY_POSITION, assessments, 5),
    ], red, []


def _score_b(metrics: Metrics, assessments, cycle):
    nim = _number(metrics, "nim")
    yoy = _number(metrics, "nim_yoy_decline_bp")
    two_year = _number(metrics, "nim_two_year_decline_bp")
    three_down = _boolean(metrics, "nim_three_periods_down")
    precise = _boolean(metrics, "bank_metrics_precise_latest")
    if nim is None or yoy is None or two_year is None or three_down is None or precise is None:
        nim_item = _missing("nim_trend", 10)
    elif nim <= 1.4 or yoy > 15 or two_year > 25:
        nim_item = DimensionScore("nim_trend", 0, 10, "NIM floor/trend red band")
    elif nim > 1.8 and yoy <= 5 and two_year <= 10 and not three_down:
        nim_item = DimensionScore("nim_trend", 10 if precise else 5, 10, "NIM excellent; precision cap applied" if not precise else "NIM excellent")
    else:
        nim_item = DimensionScore("nim_trend", 5, 10, "NIM pass band")
    npl = _lower("npl_ratio", _number(metrics, "npl_ratio"), 1.0, 1.5, 15)
    provision = _higher("provision_coverage", _number(metrics, "provision_coverage"), 300, 150, 10)
    if precise is False:
        npl = _scaled(npl, min(1.0, 7.5 / npl.score) if npl.score else 1.0, "imprecise-data cap")
        provision = _scaled(provision, min(1.0, 5 / provision.score) if provision.score else 1.0, "imprecise-data cap")
    red = _common_red_flags(metrics)
    capital = _number(metrics, "capital_adequacy_ratio")
    if capital is not None and capital < 10:
        red.append("capital_adequacy_below_10")
    if _boolean(metrics, "npl_two_years_rising") and (npl_value := _number(metrics, "npl_ratio")) is not None and npl_value > 2:
        red.append("npl_rising_above_2")
    if _boolean(metrics, "core_tier1_capital_declining"):
        red.append("core_tier1_capital_declining")
    gates = [] if cycle is not None else ["cycle_stage"]
    return [
        _higher("roe_weighted_annualized", _number(metrics, "roe_weighted_annualized"), 13, 9, 15),
        nim_item,
        npl,
        provision,
        _subjective("moat", SubjectiveCategory.MOAT, assessments, 5),
        _subjective("industry_position", SubjectiveCategory.INDUSTRY_POSITION, assessments, 5),
    ], red, gates


def _score_c(metrics: Metrics, assessments, cycle):
    dps = _number(metrics, "dps")
    eps = _number(metrics, "eps")
    same_basis = _boolean(metrics, "dps_eps_same_period_basis")
    growth = bool(dps is not None and eps is not None and eps > 0 and same_basis and dps / eps < 0.4)
    profit_rises = _boolean(metrics, "profit_rises_with_commodity")
    if eps is None or profit_rises is None:
        profit = _missing("net_profit_trend", 10)
    elif profit_rises:
        profit = DimensionScore("net_profit_trend", 10, 10, "rises with commodity")
    elif eps >= 0:
        profit = DimensionScore("net_profit_trend", 5, 10, "not loss-making")
    else:
        profit = DimensionScore("net_profit_trend", 0, 10, "loss-making")
    yield_max = 5 if growth else 15
    stressed_yield = _number(metrics, "stressed_forward_dividend_yield")
    if stressed_yield is not None and cycle is CycleStage.DOWNTREND:
        stressed_yield *= 0.7
    yield_item = _higher("stressed_forward_dividend_yield", stressed_yield, 5, 3, yield_max)
    if cycle is CycleStage.DOWNTREND:
        profit = _scaled(profit, 0.5, "downtrend discount")
    dimensions = [
        _higher("roe_3y_avg", _number(metrics, "roe_3y_avg"), 12, 8, 10),
        profit,
        _lower("debt_ratio", _number(metrics, "debt_ratio"), 45, 65, 10),
        yield_item,
    ]
    if growth:
        production = _number(metrics, "production_cagr_3y")
        reserves_grew = _boolean(metrics, "equity_reserves_grew")
        if production is None or reserves_grew is None:
            dimensions.append(_missing("production_reserve_delivery", 10))
        elif production > 10 and reserves_grew:
            dimensions.append(DimensionScore("production_reserve_delivery", 10, 10, "production>10 and reserves grew"))
        elif production > 5 or reserves_grew:
            dimensions.append(DimensionScore("production_reserve_delivery", 5, 10, "production/reserves pass"))
        else:
            dimensions.append(DimensionScore("production_reserve_delivery", 0, 10, "growth not delivered"))
    reserve = _subjective("reserve_competitiveness", SubjectiveCategory.MOAT, assessments, 10)
    if _boolean(metrics, "commodity_long_term_downtrend"):
        reserve = _scaled(reserve, 0.5, "long-term commodity downtrend")
    dimensions.extend([
        reserve,
        _subjective("industry_position", SubjectiveCategory.INDUSTRY_POSITION, assessments, 5),
    ])
    red = _common_red_flags(metrics)
    debt = _number(metrics, "debt_ratio")
    reserve_life = _number(metrics, "reserve_life_years")
    if debt is not None and debt > 70:
        red.append("debt_ratio_above_70")
    if reserve_life is not None and reserve_life < 10:
        red.append("reserve_life_below_10")
    return dimensions, red, [] if cycle is not None else ["cycle_stage"]


def _score_d(metrics: Metrics, assessments, cycle):
    business_growth = _number(metrics, "business_volume_growth")
    if business_growth is None:
        business = _missing("business_volume_growth", 10)
    elif business_growth > 5:
        business = DimensionScore("business_volume_growth", 10, 10, "growth>5")
    elif business_growth >= 0:
        business = DimensionScore("business_volume_growth", 5, 10, "non-negative growth")
    else:
        business = DimensionScore("business_volume_growth", 0, 10, "negative growth")
    yield_item = _higher("stressed_forward_dividend_yield", _number(metrics, "stressed_forward_dividend_yield"), 4, 2.5, 15)
    if _boolean(metrics, "policy_price_limit"):
        business = _scaled(business, 0.7, "policy-price discount")
        yield_item = _scaled(yield_item, 0.7, "policy-price discount")
    if cycle is CycleStage.DOWNTREND:
        yield_item = _scaled(yield_item, 0.7, "downtrend discount")
    if _boolean(metrics, "dividend_yield_declined_two_years"):
        yield_item = _scaled(yield_item, 0.5, "two-year dividend decline")
    roe_percentile = _number(metrics, "roe_industry_percentile")
    roe_item = _lower("roe_industry_percentile", roe_percentile, 30, 50, 10)
    red = _common_red_flags(metrics)
    debt = _number(metrics, "debt_ratio")
    current_yield = _number(metrics, "current_dividend_yield")
    if debt is not None and debt > 75:
        red.append("debt_ratio_above_75")
    if _boolean(metrics, "dividend_yield_declined_two_years") and current_yield is not None and current_yield < 2:
        red.append("dividend_decline_below_2")
    return [
        roe_item,
        business,
        _lower("debt_ratio", debt, 55, 70, 10),
        yield_item,
        _subjective("franchise_scarcity", SubjectiveCategory.FRANCHISE_SCARCITY, assessments, 10),
        _subjective("industry_position", SubjectiveCategory.INDUSTRY_POSITION, assessments, 5),
    ], red, [] if cycle is not None else ["cycle_stage"]


def _score_e(metrics: Metrics, assessments, _cycle):
    red = _common_red_flags(metrics)
    for key in ("inventory_accumulating_two_years", "channel_stuffing", "price_increase_resisted"):
        if _boolean(metrics, key):
            red.append(key)
    return [
        _higher("roe_3y_avg", _number(metrics, "roe_3y_avg"), 20, 12, 15),
        _higher("net_profit_growth_3y", _number(metrics, "net_profit_growth_3y"), 15, 8, 10),
        _higher("gross_margin", _number(metrics, "gross_margin"), 50, 30, 15),
        _lower("inventory_turnover_days", _number(metrics, "inventory_turnover_days"), 60, 120, 10),
        _subjective("brand_channel", SubjectiveCategory.BRAND_CHANNEL, assessments, 5),
        _subjective("industry_position", SubjectiveCategory.INDUSTRY_POSITION, assessments, 5),
    ], red, []


def _score_f(metrics: Metrics, assessments, _cycle):
    margin = _number(metrics, "gross_margin")
    margin_stable = _boolean(metrics, "gross_margin_stable")
    if margin is None or margin_stable is None:
        margin_item = _missing("gross_margin_trend", 15)
    elif margin > 50 and margin_stable:
        margin_item = DimensionScore("gross_margin_trend", 15, 15, "margin>50 and stable")
    elif margin > 30 and margin_stable:
        margin_item = DimensionScore("gross_margin_trend", 7.5, 15, "margin>30 and stable")
    else:
        margin_item = DimensionScore("gross_margin_trend", 0, 15, "margin/trend below threshold")
    fcf_positive = _boolean(metrics, "fcf_continuous_positive")
    fcf_gt_profit = _boolean(metrics, "fcf_above_net_profit")
    ocf_ratio = _number(metrics, "operating_cf_to_net_profit")
    if fcf_positive is None or fcf_gt_profit is None or ocf_ratio is None:
        cash_item = _missing("operating_cash_flow_quality", 5)
    elif fcf_positive and fcf_gt_profit:
        cash_item = DimensionScore("operating_cash_flow_quality", 5, 5, "FCF positive and above profit")
    elif ocf_ratio > 0.8:
        cash_item = DimensionScore("operating_cash_flow_quality", 2.5, 5, "OCF/profit>0.8")
    else:
        cash_item = DimensionScore("operating_cash_flow_quality", 0, 5, "cash conversion below threshold")
    red = _common_red_flags(metrics)
    for key in (
        "nonrecurring_profit_above_30",
        "top5_customers_above_50_without_contract",
        "core_technical_leader_left",
        "rd_spend_declined_two_years",
        "goodwill_assets_above_20",
    ):
        if _boolean(metrics, key):
            red.append(key)
    return [
        _higher("revenue_growth_3y", _number(metrics, "revenue_growth_3y"), 30, 15, 15),
        margin_item,
        _higher("rd_to_revenue", _number(metrics, "rd_to_revenue"), 15, 8, 10),
        _subjective("order_visibility", SubjectiveCategory.MOAT, assessments, 10),
        cash_item,
        _subjective("industry_position", SubjectiveCategory.INDUSTRY_POSITION, assessments, 5),
    ], red, []
