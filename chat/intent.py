"""인텐트 7분류 — ML 사전분류 + 결정적 키워드 가드레일 + 종목명 gazetteer — 계획 §4, 스킬 §3.

세 층:
1. 결정적 키워드 가드레일(guardrail_label) — ML 보다 **먼저** 적용. 차단 4유형
   (① 단정 예측 요구 ② 내부정보 유도 ③ 과도한 위험 조장 ④ 시세조종)을 정규식으로
   보수적으로 risk_guardrail 에 귀속한다. risk_guardrail 차단은 코드가 결정한다
   (LLM 판정 아님 — 안전 원칙).
2. ML 분류기(build_pipeline) — TfidfVectorizer(char_wb (2,4)) + LogisticRegression.
   한글을 형태소 분석기 없이 char n-gram 으로 처리한다. 학습·산출은 intent_train.py,
   런타임은 joblib 모델을 1회 로드해 predict.
3. 종목명 gazetteer override(stock_gazetteer) — ML 이 macro_view 로 예측했더라도 질문에
   실제 개별 KRX 종목명(len>=3)이 들어있으면 stock_analysis 로 결정적 재분류(비유명주가
   시장 국면 패널로 새던 버그 해소). 순수 문자열 매칭, macro_view 예측일 때만 발동.

classify(text)는 가드레일 우선 → ML → 종목명 override → 유효 라벨 검증 순으로, 항상 7라벨 중
하나를 반환한다. 모델 부재/오류 시 위험이 아닌 안전 기본값 general_qa 로 폴백(크래시 금지).
"""
from __future__ import annotations

import re
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from chat.stock_gazetteer import query_names_a_stock

# 7분류 라벨(스킬 §3 표). risk_guardrail 은 차단 경로.
# analyst_report: 애널리스트/증권사 리포트 수집·검색·목표주가·투자의견 조회(콘텐츠 툴 흐름).
LABELS = (
    "macro_view",
    "stock_analysis",
    "portfolio_advice",
    "watchlist_mgmt",
    "general_qa",
    "analyst_report",
    "risk_guardrail",
)

# 산출 모델 경로(intent_train.py 가 생성, 런타임이 로드).
MODEL_PATH = Path(__file__).parent / "models" / "intent_clf.joblib"

# 결정적 가드레일 키워드 — 차단 4유형을 보수적으로 포착(경계 사례는 risk_guardrail 귀속).
# ① 단정 예측 요구 ② 내부정보 유도 ③ 과도한 위험 조장 ④ 시세조종·부정거래.
_GUARDRAIL_KEYWORDS = (
    # ① 단정 예측 요구
    "반드시 오르",
    "무조건 오르",
    "확실히 오르",
    "확실히 올라",
    "확실한 종목",
    "확실히 먹는",
    "떡상 확실",
    # ② 내부정보 유도
    "내부정보",
    "내부 정보",
    "미공개 정보",
    "미공개정보",
    # ③ 과도한 위험 조장
    "몰빵",
    "빚내서",
    "빚 내서",
    "대출 받아서",
    "대출받아서",
    "전재산",
    "전 재산",
    "풀매수",
    # ④ 시세조종·부정거래
    "작전주",
    "작전 세력",
    "시세조종",
    "시세 조종",
    "주가조작",
)
_GUARDRAIL_RE = re.compile("|".join(re.escape(k) for k in _GUARDRAIL_KEYWORDS))


def guardrail_label(text: str) -> str | None:
    """위험 키워드 매치 시 'risk_guardrail', 아니면 None(결정적, 모델 불필요)."""
    return "risk_guardrail" if _GUARDRAIL_RE.search(text or "") else None


def build_pipeline() -> Pipeline:
    """분류 파이프라인 정의(단일 출처) — 학습 스크립트·런타임·테스트가 공유.

    char_wb (2,4): 한글을 단어경계 내 문자 n-gram 으로 벡터화(형태소 분석기 없이).
    """
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))),
            ("clf", LogisticRegression(max_iter=1000)),
        ]
    )


_model = None


def _load_model():
    """joblib 모델을 모듈 1회 로드(캐시). 파일 없으면 예외 → classify 가 폴백 처리."""
    global _model
    if _model is None:
        _model = joblib.load(MODEL_PATH)
    return _model


def classify(text: str) -> str:
    """텍스트 → 7라벨. 가드레일 최우선 → ML → 종목명 override → 유효성 검증. 항상 유효 라벨 반환."""
    # 1. 결정적 가드레일(ML 무시, 보수적 차단). 위험은 gazetteer override 보다 먼저 선차단.
    guarded = guardrail_label(text)
    if guarded:
        return guarded
    # 2. ML 예측. 모델 부재/오류는 위험이 아닌 안전 기본값으로 폴백(크래시 금지).
    try:
        label = _load_model().predict([text])[0]
    except Exception:
        return "general_qa"
    if label not in LABELS:
        return "general_qa"
    # 3. 결정적 종목명 override — ML 이 macro_view 로 예측했더라도 질문에 실제 개별 종목명이
    #    들어있으면 시장 전체가 아니라 특정 종목을 묻는 것이므로 stock_analysis 로 재분류한다.
    #    (비유명주 "롯데렌탈 어때?" 가 시장 국면 패널로 새던 문제. 판정=코드·순수 문자열 매칭.)
    #    stock_analysis 는 intent_panel 매핑이 없어 LLM 의 show_stock_report 가 살아남는다(최소·안전).
    #    gazetteer 실패는 무해 — ML 예측 유지(크래시 금지).
    if label == "macro_view":
        try:
            if query_names_a_stock(text):
                return "stock_analysis"
        except Exception:
            pass
    return label
