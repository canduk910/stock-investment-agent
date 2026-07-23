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
_DATASET = Path(__file__).parents[3] / "data" / "intent_dataset.tsv"


def _load_tsv(path: Path):
    texts, labels = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        q, label = line.split("\t")
        texts.append(q)
        labels.append(label)
    return texts, labels


def _load_seed():
    return _load_tsv(_SEED)


# 정당한 잔고·손익·포트폴리오·추가편입 조회 — 절대 risk_guardrail 로 오분류되면 안 되는 표현.
# (실측: 개선 전 모델이 "내 잔고 확인해줄래?" 등을 risk_guardrail 로 하드블록했다.)
_BENIGN_MUST_NOT_BLOCK = [
    "내 잔고 확인해줄래?",
    "손실 난 종목 알려줘",
    "지금 보고 있는 잔고에서 손실 난 종목과 손익 알려줘",
    "평가손익 정리해줘",
    "내 계좌 수익률 정리해줘",
    "포트폴리오 조정안 만들어줘",
    "추가편입 후보 종목 알려줘",
]


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


# ── (e) 데이터셋 품질(정밀도): 정당 조회는 risk_guardrail 로 분류되지 않는다 ────────
# data/intent_dataset.tsv 로 파이프라인을 즉석 학습해 검증한다(tfidf+lbfgs 는 고정 데이터에
# 결정적 → 안정적 테스트). 모델 파일이 아니라 '데이터셋 품질'을 검증하므로 재학습 동기화와 무관.


@pytest.mark.skipif(not _DATASET.exists(), reason="production dataset 부재(라이브 데이터셋 필요)")
def test_dataset_does_not_misclassify_benign_as_risk():
    texts, labels = _load_tsv(_DATASET)
    pipe = build_pipeline()
    pipe.fit(texts, labels)
    preds = pipe.predict(_BENIGN_MUST_NOT_BLOCK)
    misfires = [q for q, p in zip(_BENIGN_MUST_NOT_BLOCK, preds) if p == "risk_guardrail"]
    assert not misfires, f"정당 조회가 risk_guardrail 로 오분류됨: {misfires}"


@pytest.mark.skipif(not _DATASET.exists(), reason="production dataset 부재")
def test_classify_does_not_block_benign_queries():
    # 통합 경로(guardrail 정규식 → 커밋된 모델)로도 정당 조회는 차단되지 않아야 한다.
    misfires = [q for q in _BENIGN_MUST_NOT_BLOCK if classify(q) == "risk_guardrail"]
    assert not misfires, f"classify 가 정당 조회를 차단함: {misfires}"


def test_labels_are_exactly_seven():
    # 강화: 애널리스트 리포트 수집·검색을 별도 인텐트(analyst_report)로 인식(7분류).
    assert set(LABELS) == {
        "macro_view",
        "stock_analysis",
        "portfolio_advice",
        "watchlist_mgmt",
        "general_qa",
        "analyst_report",
        "risk_guardrail",
    }


# 애널리스트/리포트 확보·검색 질의 — 강화로 analyst_report 인텐트로 분류되어야 하고 절대 위험 아님.
_REPORT_QUERIES = [
    "삼성전자 애널리스트 리포트 확보해줘",
    "이 종목 증권사 리포트 가져와",
    "LG이노텍 목표주가 리포트 찾아줘",
    "업로드한 리포트에서 목표주가 검색해줘",
    "네이버 애널리스트 리포트 수집해줘",
]


@pytest.mark.skipif(not _DATASET.exists(), reason="production dataset 부재")
def test_report_queries_classify_as_analyst_report():
    # 데이터셋 즉석 학습(tfidf+lbfgs 결정적) → 리포트 질의가 analyst_report 로 분류되고
    # risk_guardrail 로 오분류되지 않는지(강화 효과 + 안전) 검증.
    texts, labels = _load_tsv(_DATASET)
    pipe = build_pipeline()
    pipe.fit(texts, labels)
    preds = list(pipe.predict(_REPORT_QUERIES))
    assert all(p != "risk_guardrail" for p in preds), f"리포트 질의 위험 오분류: {preds}"
    # 다수가 analyst_report 로 분류(ML이라 전수 단정은 피하되 대다수는 맞아야 강화 효과 입증).
    assert sum(p == "analyst_report" for p in preds) >= 4, f"리포트 인텐트 미인식: {preds}"


# ── (f) Layer A: 종목명 gazetteer → macro_view→stock_analysis override ────────
# 비유명 종목("롯데렌탈 어때?")이 ML=macro_view 로 오분류돼 시장 국면 패널이 뜨던 문제를,
# 질문에 실제 개별 종목명이 있으면 stock_analysis 로 결정적 재분류해 해소한다.


class _FakeModel:
    """predict([text]) 가 고정 라벨을 내는 스텁(ML 예측 대체)."""

    def __init__(self, label: str):
        self._label = label

    def predict(self, X):  # noqa: N803 (sklearn 인터페이스)
        return [self._label]


def test_macro_view_with_stock_name_reclassified_to_stock_analysis(monkeypatch):
    monkeypatch.setattr(intent, "_load_model", lambda: _FakeModel("macro_view"))
    monkeypatch.setattr(intent, "query_names_a_stock", lambda t: "롯데렌탈")
    assert classify("롯데렌탈 어때?") == "stock_analysis"


def test_macro_view_without_stock_name_stays_macro(monkeypatch):
    monkeypatch.setattr(intent, "_load_model", lambda: _FakeModel("macro_view"))
    monkeypatch.setattr(intent, "query_names_a_stock", lambda t: None)
    assert classify("지금 시장 국면 어때?") == "macro_view"


def test_override_only_applies_to_macro_view(monkeypatch):
    # 종목명이 있어도 예측이 macro_view 가 아니면 라벨을 바꾸지 않는다(예측 보존).
    monkeypatch.setattr(intent, "query_names_a_stock", lambda t: "삼성전자")
    for label in ("stock_analysis", "analyst_report", "portfolio_advice", "watchlist_mgmt", "general_qa"):
        monkeypatch.setattr(intent, "_load_model", lambda label=label: _FakeModel(label))
        assert classify("삼성전자 어때?") == label


def test_gazetteer_not_consulted_for_non_macro_predictions(monkeypatch):
    # 단락 평가: macro_view 가 아니면 gazetteer 를 호출조차 하지 않는다(불필요 연산 0).
    called = {"n": 0}

    def _spy(t):
        called["n"] += 1
        return "삼성전자"

    monkeypatch.setattr(intent, "query_names_a_stock", _spy)
    monkeypatch.setattr(intent, "_load_model", lambda: _FakeModel("stock_analysis"))
    classify("삼성전자 어때?")
    assert called["n"] == 0


def test_guardrail_takes_precedence_over_gazetteer(monkeypatch):
    # 위험 키워드는 gazetteer/override 보다 먼저 차단 → gazetteer 미호출(선차단 불변).
    called = {"n": 0}

    def _spy(t):
        called["n"] += 1
        return "롯데렌탈"

    monkeypatch.setattr(intent, "query_names_a_stock", _spy)
    monkeypatch.setattr(intent, "_load_model", lambda: _FakeModel("macro_view"))
    assert classify("롯데렌탈 빚내서 몰빵할까") == "risk_guardrail"
    assert called["n"] == 0


def test_gazetteer_exception_is_graceful(monkeypatch):
    # gazetteer 가 예상치 못하게 예외를 내도 classify 는 죽지 않고 ML 예측(macro_view)을 유지.
    monkeypatch.setattr(intent, "_load_model", lambda: _FakeModel("macro_view"))

    def _boom(t):
        raise RuntimeError("gazetteer down")

    monkeypatch.setattr(intent, "query_names_a_stock", _boom)
    assert classify("롯데렌탈 어때?") == "macro_view"


# ── (g) Layer A: KRX 비유명주는 종목분석으로 결정적 라우팅 ──────────────────────
# 보고된 버그(비유명 KRX주가 시장 국면 패널로 새던 문제)는 gazetteer override 가 결정적으로
# 해소한다 — ML 이 macro 로 예측해도 질문의 KRX 종목명(len>=3)이 stock_analysis 로 재분류.
# classify() 통합 경로(가드레일+ML+gazetteer)로 검증한다(사용자 실제 동작·커밋 모델 staleness 에 강건).
_KRX_STOCK_QUERIES = [
    "롯데렌탈 어때?",
    "에스피지 어떠냐",
    "클래시스 어때?",
    "에스비비테크 어떤가?",
    "리노공업 지금 괜찮아?",
    "파크시스템스 어때?",
]


def test_krx_stock_queries_route_to_stock_analysis():
    misrouted = [q for q in _KRX_STOCK_QUERIES if classify(q) != "stock_analysis"]
    assert not misrouted, f"KRX 비유명주가 종목분석으로 라우팅되지 않음: {misrouted}"


# ── (h) Layer B 균형: 매크로·포트폴리오는 stock_analysis 로 새지 않는다 ─────────────
# 적대적 검증(Finding 1·2)이 잡은 회귀 방지: Layer B 의 "{종목명} 어때?" 보강이 짧은 조회형을
# stock 으로 끌어당겨 매크로(지수/시장 + FX/원자재/금리/인플레) · 포트폴리오 질문이 stock 으로
# 새면 각각 시장국면·잔고 패널의 결정적 라우팅을 잃는다. 데이터셋 즉석 학습(tfidf+lbfgs 결정적)으로
# 데이터 품질을 잠근다(커밋 모델 동기화와 무관 — 데이터가 균형인지 검증).
_MACRO_QUERIES = [
    # 지수/시장
    "지금 국면 어때?", "코스피 지금 어때?", "요즘 장 어때?", "증시 분위기 어때?",
    # FX/원자재/금리/인플레
    "환율 요즘 어떤가", "달러 강세 지금 어떤가", "유가 지금 어때", "국제유가 어때",
    "인플레이션 지금 어떤가", "물가 요즘 어때", "금리 지금 어떤가", "원자재 시장 어떤가",
    # 통화명·외래어 침체·해외지수(적대적 재검증 Finding 후속 — 이 니치가 재학습 회귀로 새지 않게 잠금)
    "엔화 어때", "위안화 어때", "리세션 우려 어때", "스태그플레이션 어때", "나스닥 어때", "S&P500 어때",
]
_PORTFOLIO_QUERIES = [
    "내 자산 배분 괜찮아?", "보유 비중 괜찮아?", "내 포트 비중 어때", "자산배분 지금 어떤가",
]


@pytest.mark.skipif(not _DATASET.exists(), reason="production dataset 부재")
def test_macro_queries_do_not_leak_to_stock_analysis():
    texts, labels = _load_tsv(_DATASET)
    pipe = build_pipeline()
    pipe.fit(texts, labels)
    preds = pipe.predict(_MACRO_QUERIES)
    leaked = [(q, p) for q, p in zip(_MACRO_QUERIES, preds) if p == "stock_analysis"]
    assert not leaked, f"매크로 질의가 stock_analysis 로 누수(시장국면 패널 라우팅 상실): {leaked}"


@pytest.mark.skipif(not _DATASET.exists(), reason="production dataset 부재")
def test_portfolio_queries_do_not_leak_to_stock_analysis():
    texts, labels = _load_tsv(_DATASET)
    pipe = build_pipeline()
    pipe.fit(texts, labels)
    preds = pipe.predict(_PORTFOLIO_QUERIES)
    leaked = [(q, p) for q, p in zip(_PORTFOLIO_QUERIES, preds) if p == "stock_analysis"]
    assert not leaked, f"포트폴리오 질의가 stock_analysis 로 누수(잔고 패널 라우팅 상실): {leaked}"
