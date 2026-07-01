from __future__ import annotations

import pytest

from a_stock_lib.contracts import (
    CycleStage,
    CycleStageAssessment,
    EvidenceConfidence,
    FrameworkDecision,
    FrameworkKey,
    RatingTier,
    SubjectiveAssessment,
    SubjectiveCategory,
    parse_cycle_stage_tag,
    parse_subjective_assessment_tags,
)


def test_contract_enums_and_dataclasses_construct() -> None:
    framework = FrameworkDecision(FrameworkKey.A, confident=True)
    cycle = CycleStageAssessment(CycleStage.UPTREND, "订单改善")
    subjective = SubjectiveAssessment(
        SubjectiveCategory.MOAT,
        RatingTier.HIGH,
        ["高毛利稳定"],
        EvidenceConfidence.HIGH,
    )

    assert framework.framework.value == "A"
    assert framework.confident is True
    assert cycle.stage.value == "上行期"
    assert cycle.rationale == "订单改善"
    assert SubjectiveCategory.INDUSTRY_POSITION.value == "行业地位"
    assert SubjectiveCategory.FRANCHISE_SCARCITY.value == "特许经营稀缺性"
    assert SubjectiveCategory.BRAND_CHANNEL.value == "品牌渠道"
    assert subjective.category == SubjectiveCategory.MOAT
    assert subjective.rating.value == "优档"
    assert RatingTier.LOW.value == "格档"
    assert subjective.evidence == ["高毛利稳定"]
    assert subjective.confidence.value == "高"
    assert EvidenceConfidence.MEDIUM.value == "中"
    assert EvidenceConfidence.LOW.value == "低"


@pytest.mark.parametrize(
    ("stage", "rationale"),
    [
        (CycleStage.UPTREND, "需求恢复，库存下降"),
        (CycleStage.PEAK, "盈利处于高位"),
        (CycleStage.DOWNTREND, "价格回落"),
        (CycleStage.TROUGH, "估值和盈利均处低位"),
    ],
)
def test_parse_cycle_stage_tag_valid_values(stage: CycleStage, rationale: str) -> None:
    result = parse_cycle_stage_tag(f'正文 周期位置[阶段={stage.value}；依据="{rationale}"] 结论')

    assert result == CycleStageAssessment(stage=stage, rationale=rationale)


def test_parse_cycle_stage_tag_no_tag_returns_none() -> None:
    assert parse_cycle_stage_tag("报告正文没有结构化周期标签") is None


def test_parse_cycle_stage_tag_malformed_stage_returns_none() -> None:
    assert parse_cycle_stage_tag('周期位置[阶段=震荡期；依据="区间波动"]') is None


@pytest.mark.parametrize(
    "text",
    [
        "周期位置[阶段=上行期]",
        '周期位置[阶段=上行期；依据=""]',
        '周期位置[阶段=上行期；依据="   "]',
    ],
)
def test_parse_cycle_stage_tag_missing_or_empty_rationale_returns_none(text: str) -> None:
    assert parse_cycle_stage_tag(text) is None


def test_parse_cycle_stage_tag_two_tags_returns_none() -> None:
    text = '周期位置[阶段=上行期；依据="需求恢复"] 周期位置[阶段=顶部区；依据="盈利高位"]'

    assert parse_cycle_stage_tag(text) is None


def test_parse_subjective_assessment_tags_all_categories_valid() -> None:
    text = (
        '护城河[评级=优；证据="转换成本高";"客户粘性强";置信度=高]\n'
        '行业地位[评级=格；证据="市占率较低";置信度=中]\n'
        '特许经营稀缺性[评级=优；证据="牌照稀缺";置信度=低]\n'
        '品牌渠道[评级=格；证据="渠道覆盖弱";置信度=高]'
    )

    result = parse_subjective_assessment_tags(text)

    assert result == [
        SubjectiveAssessment(
            SubjectiveCategory.MOAT,
            RatingTier.HIGH,
            ["转换成本高", "客户粘性强"],
            EvidenceConfidence.HIGH,
        ),
        SubjectiveAssessment(
            SubjectiveCategory.INDUSTRY_POSITION,
            RatingTier.LOW,
            ["市占率较低"],
            EvidenceConfidence.MEDIUM,
        ),
        SubjectiveAssessment(
            SubjectiveCategory.FRANCHISE_SCARCITY,
            RatingTier.HIGH,
            ["牌照稀缺"],
            EvidenceConfidence.LOW,
        ),
        SubjectiveAssessment(
            SubjectiveCategory.BRAND_CHANNEL,
            RatingTier.LOW,
            ["渠道覆盖弱"],
            EvidenceConfidence.HIGH,
        ),
    ]


def test_parse_subjective_assessment_tags_malformed_rating_skipped() -> None:
    text = (
        '护城河[评级=强；证据="壁垒强";置信度=高]\n'
        '行业地位[评级=格；证据="排名靠后";置信度=中]'
    )

    assert parse_subjective_assessment_tags(text) == [
        SubjectiveAssessment(
            SubjectiveCategory.INDUSTRY_POSITION,
            RatingTier.LOW,
            ["排名靠后"],
            EvidenceConfidence.MEDIUM,
        )
    ]


def test_parse_subjective_assessment_tags_zero_evidence_skipped() -> None:
    text = (
        '护城河[评级=优；证据=;置信度=高]\n'
        '品牌渠道[评级=优；证据="渠道强";置信度=高]'
    )

    assert parse_subjective_assessment_tags(text) == [
        SubjectiveAssessment(
            SubjectiveCategory.BRAND_CHANNEL,
            RatingTier.HIGH,
            ["渠道强"],
            EvidenceConfidence.HIGH,
        )
    ]


def test_parse_subjective_assessment_tags_duplicate_category_keeps_first_valid() -> None:
    text = (
        '护城河[评级=优；证据="先出现";置信度=高]\n'
        '护城河[评级=格；证据="后出现";置信度=低]'
    )

    assert parse_subjective_assessment_tags(text) == [
        SubjectiveAssessment(
            SubjectiveCategory.MOAT,
            RatingTier.HIGH,
            ["先出现"],
            EvidenceConfidence.HIGH,
        )
    ]


def test_parse_subjective_assessment_tags_empty_input_returns_empty_list() -> None:
    assert parse_subjective_assessment_tags("") == []


def test_parse_subjective_assessment_tags_inline_chinese_prose_before_category() -> None:
    text = '本公司的护城河[评级=优；证据="转换成本高";置信度=高]'

    assert parse_subjective_assessment_tags(text) == [
        SubjectiveAssessment(
            SubjectiveCategory.MOAT,
            RatingTier.HIGH,
            ["转换成本高"],
            EvidenceConfidence.HIGH,
        )
    ]


def test_parse_tags_allow_closing_bracket_inside_quoted_text() -> None:
    cycle = parse_cycle_stage_tag('周期位置[阶段=上行期；依据="需求回升[参考1]"]')
    subjective = parse_subjective_assessment_tags('护城河[评级=优；证据="转换成本高[参考1]";置信度=高]')

    assert cycle == CycleStageAssessment(CycleStage.UPTREND, "需求回升[参考1]")
    assert subjective == [
        SubjectiveAssessment(
            SubjectiveCategory.MOAT,
            RatingTier.HIGH,
            ["转换成本高[参考1]"],
            EvidenceConfidence.HIGH,
        )
    ]


def test_parse_tags_allow_newline_inside_quoted_text() -> None:
    cycle = parse_cycle_stage_tag('周期位置[阶段=上行期；依据="需求回升\n盈利改善"]')
    subjective = parse_subjective_assessment_tags('护城河[评级=优；证据="转换成本高\n客户粘性强";置信度=高]')

    assert cycle == CycleStageAssessment(CycleStage.UPTREND, "需求回升\n盈利改善")
    assert subjective == [
        SubjectiveAssessment(
            SubjectiveCategory.MOAT,
            RatingTier.HIGH,
            ["转换成本高\n客户粘性强"],
            EvidenceConfidence.HIGH,
        )
    ]
