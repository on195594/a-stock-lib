"""Typed contracts for LLM-output to code-consumption boundaries.

These types formalize framework routing, cycle-stage judgment, and
subjective-quality ratings that downstream consumers historically handled
with free-text and regex heuristics.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class FrameworkKey(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"


@dataclass(frozen=True)
class FrameworkDecision:
    framework: FrameworkKey
    # Captured for future use, not currently consumed by any caller.
    confident: bool


class CycleStage(str, Enum):
    UPTREND = "上行期"
    PEAK = "顶部区"
    DOWNTREND = "下行期"
    TROUGH = "底部区"


@dataclass(frozen=True)
class CycleStageAssessment:
    stage: CycleStage
    rationale: str


class SubjectiveCategory(str, Enum):
    MOAT = "护城河"
    INDUSTRY_POSITION = "行业地位"
    FRANCHISE_SCARCITY = "特许经营稀缺性"
    BRAND_CHANNEL = "品牌渠道"


# Framework prose uses different business labels for the same normalized
# quality dimension.  Downstream validators must compare the parsed enum set,
# not the display strings emitted by checklist/framework documents.
FRAMEWORK_SUBJECTIVE_CATEGORY_MAP: dict[FrameworkKey, dict[str, SubjectiveCategory]] = {
    FrameworkKey.A: {
        "护城河": SubjectiveCategory.MOAT,
        "行业地位": SubjectiveCategory.INDUSTRY_POSITION,
    },
    FrameworkKey.B: {
        "护城河": SubjectiveCategory.MOAT,
        "行业地位": SubjectiveCategory.INDUSTRY_POSITION,
    },
    FrameworkKey.C: {
        "储量竞争力": SubjectiveCategory.MOAT,
        "行业地位": SubjectiveCategory.INDUSTRY_POSITION,
    },
    FrameworkKey.D: {
        "特许经营稀缺性": SubjectiveCategory.FRANCHISE_SCARCITY,
        "行业地位": SubjectiveCategory.INDUSTRY_POSITION,
    },
    FrameworkKey.E: {
        "品牌/渠道": SubjectiveCategory.BRAND_CHANNEL,
        "行业地位": SubjectiveCategory.INDUSTRY_POSITION,
    },
    FrameworkKey.F: {
        "订单能见度/客户留存": SubjectiveCategory.MOAT,
        "行业地位": SubjectiveCategory.INDUSTRY_POSITION,
    },
}


def required_subjective_categories(framework: FrameworkKey | str) -> frozenset[SubjectiveCategory]:
    """Return normalized subjective categories required by a framework."""
    key = framework if isinstance(framework, FrameworkKey) else FrameworkKey(framework.upper())
    return frozenset(FRAMEWORK_SUBJECTIVE_CATEGORY_MAP[key].values())


class RatingTier(str, Enum):
    HIGH = "优档"
    LOW = "格档"


class EvidenceConfidence(str, Enum):
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


@dataclass(frozen=True)
class SubjectiveAssessment:
    category: SubjectiveCategory
    rating: RatingTier
    evidence: list[str]
    # Captured for future use, not currently consumed by any caller.
    confidence: EvidenceConfidence


_CYCLE_TAG_RE = re.compile(r'周期位置\[(?P<body>(?:"[^"]*"|[^\]])*)\]')
_CYCLE_BODY_RE = re.compile(r'^\s*阶段=(?P<stage>[^；;]+)[；;]依据="(?P<rationale>[\s\S]*)"\s*$')
_SUBJECTIVE_TAG_RE = re.compile(r'(?P<category>护城河|行业地位|特许经营稀缺性|品牌渠道)\[(?P<body>(?:"[^"]*"|[^\]])*)\]')
_SUBJECTIVE_BODY_RE = re.compile(
    r"^\s*评级=(?P<rating>[^；;]+)[；;]证据=(?P<evidence>[\s\S]*)[；;]置信度=(?P<confidence>[^；;]+)\s*$"
)
_EVIDENCE_RE = re.compile(r'"(?P<evidence>[^"]*)"')
_EVIDENCE_LIST_RE = re.compile(r'^\s*"[^"]*"(?:[；;]"[^"]*")*\s*$')


def parse_cycle_stage_tag(text: str) -> CycleStageAssessment | None:
    matches = list(_CYCLE_TAG_RE.finditer(text))
    if len(matches) != 1:
        return None

    body_match = _CYCLE_BODY_RE.fullmatch(matches[0].group("body"))
    if body_match is None:
        return None

    try:
        stage = CycleStage(body_match.group("stage").strip())
    except ValueError:
        return None

    rationale = body_match.group("rationale").strip()
    if not rationale:
        return None

    return CycleStageAssessment(stage=stage, rationale=rationale)


def parse_subjective_assessment_tags(text: str) -> list[SubjectiveAssessment]:
    assessments: list[SubjectiveAssessment] = []
    seen_categories: set[SubjectiveCategory] = set()
    rating_map = {"优": RatingTier.HIGH, "格": RatingTier.LOW}

    for match in _SUBJECTIVE_TAG_RE.finditer(text):
        assessment = _parse_subjective_assessment_tag(
            match.group("category"),
            match.group("body"),
            rating_map,
        )
        if assessment is None or assessment.category in seen_categories:
            continue
        assessments.append(assessment)
        seen_categories.add(assessment.category)

    return assessments


def _parse_subjective_assessment_tag(
    category_text: str,
    body: str,
    rating_map: dict[str, RatingTier],
) -> SubjectiveAssessment | None:
    category = _parse_subjective_category(category_text)
    if category is None:
        return None

    body_match = _SUBJECTIVE_BODY_RE.fullmatch(body)
    if body_match is None:
        return None

    rating = rating_map.get(body_match.group("rating").strip())
    if rating is None:
        return None

    evidence = _parse_evidence_list(body_match.group("evidence"))
    if evidence is None:
        return None

    try:
        confidence = EvidenceConfidence(body_match.group("confidence").strip())
    except ValueError:
        return None

    return SubjectiveAssessment(
        category=category,
        rating=rating,
        evidence=evidence,
        confidence=confidence,
    )


def _parse_subjective_category(category_text: str) -> SubjectiveCategory | None:
    try:
        return SubjectiveCategory(category_text)
    except ValueError:
        return None


def _parse_evidence_list(evidence_text: str) -> list[str] | None:
    if _EVIDENCE_LIST_RE.fullmatch(evidence_text) is None:
        return None

    evidence = [match.group("evidence").strip() for match in _EVIDENCE_RE.finditer(evidence_text)]
    if not evidence or any(item == "" for item in evidence):
        return None
    return evidence
