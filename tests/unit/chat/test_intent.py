"""ML 인텐트 6분류 + 결정적 키워드 가드레일 테스트 — 계획 §4, 스킬 §3.

ML 정확도 자체는 비결정적이라 단정하지 않는다(tdd-workflow §LLM 계층). 검증 대상은
결정적 부분: (a) 키워드 가드레일이 차단 4유형을 risk_guardrail 로 잡는가(모델 불필요),
(b) 가드레일이 ML 보다 우선하는가, (c) 파이프라인 학습→예측 인터페이스가 6라벨 안의
값을 내는가(시드 fixture 스모크), (d) classify 가 항상 유효 라벨을 반환하는가.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import chat.intent as intent
from chat.intent import LABELS, build_pipeline, classify, guardrail_label

_SEED = Path(__file__).parents[2] / "fixtures" / "intent_seed.tsv"


def _load_seed():
    texts, labels = [], []
    for line in _SEED.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        q, label = line.split("\t")
        texts.append(q)
        labels.append(label)
    return texts, labels


# ── (a) 결정적 키워드 가드레일: 차단 4유형 ───────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "이 종목 반드시 오르지",          # ① 단정 예측 요구
        "무조건 오르는 종목 찍어줘",       # ① 단정 예측 요구
        "내부정보로 확실한 종목 알려줘",   # ② 내부정보 유도
        "미공개 정보 좀 줘",              # ② 내부정보 유도
        "빚내서 몰빵할까",               # ③ 과도한 위험 조장
        "대출 받아서 몰빵",              # ③ 과도한 위험 조장
        "작전주 정보 좀",                # ④ 시세조종·부정거래
        "시세조종으로 돈 버는 법",        # ④ 시세조종·부정거래
    ],
)
def test_guardrail_catches_four_block_types__deterministic(text):
    assert guardrail_label(text) == "risk_guardrail"


def test_guardrail_returns_none_for_benign_text():
    assert guardrail_label("삼성전자 지금 어때") is None
    assert guardrail_label("PER이 뭐야") is None


def test_classify_guardrail_overrides_ml__conservative():
    # "삼성전자"(→stock_analysis 신호)라도 위험 키워드가 있으면 무조건 차단.
    assert classify("삼성전자 빚내서 몰빵할까") == "risk_guardrail"


def test_classify_guardrail_works_without_model(monkeypatch):
    # 모델 로드가 실패해도 가드레일은 결정적으로 동작(ML 앞단).
    monkeypatch.setattr(intent, "_load_model", lambda: (_ for _ in ()).throw(RuntimeError()))
    assert classify("반드시 오르는거 맞지") == "risk_guardrail"


# ── (c) 파이프라인 스모크: 시드 학습 → 예측 라벨 ⊂ 6라벨 ──────────────────────


def test_pipeline_trains_and_predicts_valid_labels__smoke():
    texts, labels = _load_seed()
    pipe = build_pipeline()
    pipe.fit(texts, labels)
    preds = pipe.predict(["지금 시장 어때", "삼성전자 분석", "PER 뜻"])
    for p in preds:
        assert p in LABELS


# ── (d) classify 는 항상 유효 라벨 ───────────────────────────────────────────


def test_classify_returns_valid_label_with_injected_model(monkeypatch):
    texts, labels = _load_seed()
    pipe = build_pipeline()
    pipe.fit(texts, labels)
    monkeypatch.setattr(intent, "_load_model", lambda: pipe)
    assert classify("지금 시장 국면 어때") in LABELS
    assert classify("삼성전자 지금 어때") in LABELS


def test_classify_falls_back_to_general_qa_when_model_missing(monkeypatch):
    # 모델 부재 + 가드레일 미매치 → 위험 아닌 안전 기본값(general_qa).
    monkeypatch.setattr(intent, "_load_model", lambda: (_ for _ in ()).throw(FileNotFoundError()))
    assert classify("배당이 뭐야") == "general_qa"


def test_labels_are_exactly_six():
    assert set(LABELS) == {
        "macro_view",
        "stock_analysis",
        "portfolio_advice",
        "watchlist_mgmt",
        "general_qa",
        "risk_guardrail",
    }
