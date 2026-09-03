from __future__ import annotations

import pytest
import a_stock_lib.framework_scoring as framework_scoring

from a_stock_lib.contracts import (
    CycleStage,
    EvidenceConfidence,
    FrameworkKey,
    RatingTier,
    SubjectiveAssessment,
    SubjectiveCategory,
)
from a_stock_lib.framework_scoring import score_fundamentals


def _assessment(category: SubjectiveCategory, rating: RatingTier = RatingTier.HIGH) -> SubjectiveAssessment:
    return SubjectiveAssessment(category, rating, ["verified evidence"], EvidenceConfidence.HIGH)


def _subjective(*categories: SubjectiveCategory) -> list[SubjectiveAssessment]:
    return [_assessment(category) for category in categories]


@pytest.mark.parametrize(
    ("framework", "metrics", "subjective", "cycle"),
    [
        (
            "A",
            {
                "roe_3y_avg": 16,
                "net_profit_growth_3y": 16,
                "debt_ratio": 39,
                "gross_margin": 31,
                "gross_margin_stable": True,
            },
            _subjective(SubjectiveCategory.MOAT, SubjectiveCategory.INDUSTRY_POSITION),
            None,
        ),
        (
            "B",
            {
                "roe_weighted_annualized": 14,
                "nim": 1.9,
                "nim_yoy_decline_bp": 5,
                "nim_two_year_decline_bp": 10,
                "nim_three_periods_down": False,
                "bank_metrics_precise_latest": True,
                "npl_ratio": 0.9,
                "provision_coverage": 301,
                "capital_adequacy_ratio": 12,
            },
            _subjective(SubjectiveCategory.MOAT, SubjectiveCategory.INDUSTRY_POSITION),
            CycleStage.UPTREND,
        ),
        (
            "C",
            {
                "roe_3y_avg": 13,
                "eps": 2,
                "dps": 1,
                "dps_eps_same_period_basis": True,
                "profit_rises_with_commodity": True,
                "debt_ratio": 44,
                "stressed_forward_dividend_yield": 5.1,
                "reserve_life_years": 20,
            },
            _subjective(SubjectiveCategory.MOAT, SubjectiveCategory.INDUSTRY_POSITION),
            CycleStage.UPTREND,
        ),
        (
            "D",
            {
                "roe_industry_percentile": 29,
                "business_volume_growth": 6,
                "debt_ratio": 54,
                "stressed_forward_dividend_yield": 4.1,
                "current_dividend_yield": 4.5,
                "policy_price_limit": False,
                "dividend_yield_declined_two_years": False,
            },
            _subjective(SubjectiveCategory.FRANCHISE_SCARCITY, SubjectiveCategory.INDUSTRY_POSITION),
            CycleStage.UPTREND,
        ),
        (
            "E",
            {
                "roe_3y_avg": 21,
                "net_profit_growth_3y": 16,
                "gross_margin": 51,
                "inventory_turnover_days": 59,
            },
            _subjective(SubjectiveCategory.BRAND_CHANNEL, SubjectiveCategory.INDUSTRY_POSITION),
            None,
        ),
        (
            "F",
            {
                "revenue_growth_3y": 31,
                "gross_margin": 51,
                "gross_margin_stable": True,
                "rd_to_revenue": 16,
                "fcf_continuous_positive": True,
                "fcf_above_net_profit": True,
                "operating_cf_to_net_profit": 1.1,
            },
            _subjective(SubjectiveCategory.MOAT, SubjectiveCategory.INDUSTRY_POSITION),
            None,
        ),
    ],
)
def test_all_six_frameworks_close_at_sixty(
    framework: str,
    metrics: dict[str, object],
    subjective: list[SubjectiveAssessment],
    cycle: CycleStage | None,
) -> None:
    result = score_fundamentals(framework, metrics, subjective, cycle_stage=cycle)

    assert sum(item.max_score for item in result.dimensions) == 60
    assert result.subtotal == 60
    assert result.complete
    assert not result.blocked
    assert result.rule_version == "2026-08-23.v1"
    assert len(result.rule_hash) == 64


def test_c_growth_branch_keeps_sixty_points_and_applies_downtrend_discounts() -> None:
    result = score_fundamentals(
        FrameworkKey.C,
        {
            "roe_3y_avg": 13,
            "eps": 2,
            "dps": 0.5,
            "dps_eps_same_period_basis": True,
            "profit_rises_with_commodity": True,
            "debt_ratio": 44,
            "stressed_forward_dividend_yield": 8,
            "production_cagr_3y": 11,
            "equity_reserves_grew": True,
            "reserve_life_years": 20,
        },
        _subjective(SubjectiveCategory.MOAT, SubjectiveCategory.INDUSTRY_POSITION),
        cycle_stage=CycleStage.DOWNTREND,
    )

    scores = {item.key: item.score for item in result.dimensions}
    assert sum(item.max_score for item in result.dimensions) == 60
    assert scores["net_profit_trend"] == 5
    assert scores["stressed_forward_dividend_yield"] == 5
    assert result.complete


def test_missing_input_never_becomes_complete_investment_score() -> None:
    result = score_fundamentals(
        "E",
        {"roe_3y_avg": float("nan")},
        _subjective(SubjectiveCategory.BRAND_CHANNEL),
    )

    assert not result.complete
    assert "roe_3y_avg" in result.missing_inputs
    assert "subjective:行业地位" in result.missing_inputs


def test_red_line_blocks_but_preserves_mechanical_score() -> None:
    result = score_fundamentals(
        "D",
        {
            "roe_industry_percentile": 29,
            "business_volume_growth": 6,
            "debt_ratio": 76,
            "stressed_forward_dividend_yield": 4.1,
            "current_dividend_yield": 1.9,
            "policy_price_limit": False,
            "dividend_yield_declined_two_years": True,
        },
        _subjective(SubjectiveCategory.FRANCHISE_SCARCITY, SubjectiveCategory.INDUSTRY_POSITION),
        cycle_stage=CycleStage.UPTREND,
    )

    assert result.blocked
    assert "debt_ratio_above_75" in result.red_flags
    assert "dividend_decline_below_2" in result.red_flags
    assert result.subtotal > 0


def test_rule_hash_changes_with_executable_rule(monkeypatch) -> None:
    before = framework_scoring.framework_rule_hash("A")

    def _score_a_changed(metrics, assessments, cycle):
        return [], ["changed"], []

    monkeypatch.setattr(framework_scoring, "_score_a", _score_a_changed)

    assert framework_scoring.framework_rule_hash("A") != before


def test_rule_hash_fallback_when_getsource_fails(monkeypatch) -> None:
    def _fail_getsource(_):
        raise OSError("could not get source code")

    monkeypatch.setattr(framework_scoring.inspect, "getsource", _fail_getsource)
    framework_scoring._cached_rule_hash.cache_clear()
    fallback_hash = framework_scoring.framework_rule_hash("A")
    assert len(fallback_hash) == 64
    # Second call uses cache
    assert framework_scoring.framework_rule_hash("A") == fallback_hash
