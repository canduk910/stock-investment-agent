"""INDICATOR_LABELS 상수 회귀 테스트 — W09 프롬프트 기준표 씨앗(3중 일관성).

build_criteria_text()(chat/build_prompt.py)가 이 상수를 import 해 엔진키→한글 라벨을
단일 출처로 삼는다. THRESHOLDS/INDICATOR_KEYS 와 키 집합이 어긋나면 기준표가 낡거나
누락되므로 여기서 고정한다(tdd-workflow §LLM 계층: 3중 일관성 자동 회귀).
"""
from __future__ import annotations

from macro.engine import INDICATOR_KEYS, INDICATOR_LABELS


def test_indicator_labels_covers_exactly_indicator_keys__consistency():
    # 판정 4지표와 라벨 키 집합이 정확히 일치(누락·잉여 금지).
    assert set(INDICATOR_LABELS) == set(INDICATOR_KEYS)


def test_indicator_labels_values_are_korean_labels__single_source():
    assert INDICATOR_LABELS["yield_spread"] == "장단기 금리차"
    assert INDICATOR_LABELS["hy_spread"] == "HY 신용스프레드"
    assert INDICATOR_LABELS["vix"] == "VIX 변동성"
    assert INDICATOR_LABELS["fear_greed"] == "공포탐욕지수"


def test_indicator_labels_ordering_matches_indicator_keys__stable_criteria():
    # 기준표 라인 순서 안정성(경기축 → 심리축) — 판정 4지표 순서와 동일.
    assert tuple(INDICATOR_LABELS.keys()) == tuple(INDICATOR_KEYS)
