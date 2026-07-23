"""종목명 gazetteer pre-gate 테스트 — 계획 §Layer A(결정적·hermetic·네트워크 0).

`chat.stock_gazetteer` 는 KRX 마스터를 감싸 "질문에 개별 종목명이 들어있는가"를 순수·결정적으로
판정한다. 네트워크·실 마스터에 의존하지 않도록 fake master 를 주입(`monkeypatch` +
`reset_cache()`)해 검증한다.
"""
from __future__ import annotations

import chat.stock_gazetteer as gz
from chat.stock_gazetteer import query_names_a_stock, reset_cache

# fake KRX 마스터: 개별주(len>=3) + 2글자 일반어 충돌주 + ETF/인버스/파생.
_FAKE_MASTER = [
    {"ticker": "089860", "name": "롯데렌탈", "market": "KOSPI"},
    {"ticker": "058610", "name": "에스피지", "market": "KOSDAQ"},
    {"ticker": "214150", "name": "클래시스", "market": "KOSDAQ"},
    {"ticker": "005930", "name": "삼성전자", "market": "KOSPI"},
    {"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI"},
    {"ticker": "001520", "name": "동양", "market": "KOSPI"},          # 2글자 → 제외
    {"ticker": "030200", "name": "KT", "market": "KOSPI"},           # 2글자 → 제외
    {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI"},    # ETF → 제외
    {"ticker": "133690", "name": "TIGER 미국나스닥100", "market": "KOSPI"},  # ETF → 제외
    {"ticker": "114800", "name": "KODEX 인버스", "market": "KOSPI"},  # 인버스 → 제외
]


def _inject(monkeypatch, master=_FAKE_MASTER):
    """fake master 주입 + in-process 캐시 클리어(실 마스터·네트워크 배제)."""
    monkeypatch.setattr(gz, "load_stock_master", lambda: list(master))
    reset_cache()


# ── 개별 종목명 탐지 ─────────────────────────────────────────────────────────


def test_detects_lesser_known_stock_names(monkeypatch):
    _inject(monkeypatch)
    assert query_names_a_stock("롯데렌탈 어때?") == "롯데렌탈"
    assert query_names_a_stock("에스피지 어떠냐") == "에스피지"
    assert query_names_a_stock("클래시스 어때?") == "클래시스"


def test_detects_famous_stock_names(monkeypatch):
    _inject(monkeypatch)
    assert query_names_a_stock("삼성전자 지금 어때") == "삼성전자"
    assert query_names_a_stock("SK하이닉스 실적 분석해줘") == "SK하이닉스"


# ── 시장·인덱스·ETF 질문은 비탐지(오탐 방지) ────────────────────────────────


def test_market_queries_do_not_match(monkeypatch):
    _inject(monkeypatch)
    assert query_names_a_stock("시장 어때?") is None
    assert query_names_a_stock("지금 국면 어때?") is None
    # 인덱스명은 마스터에 없어 자연히 비매치 + _EXCLUDE_MARKERS 이중 방어.
    assert query_names_a_stock("코스피 어때?") is None
    assert query_names_a_stock("코스닥 지금 어떤가?") is None


def test_etf_and_inverse_names_excluded(monkeypatch):
    _inject(monkeypatch)
    # ETF/인버스 이름 전체를 질문에 넣어도 gazetteer 에서 제외돼 비매치(시장·상품 오탐 방지).
    assert query_names_a_stock("KODEX 200 어때?") is None
    assert query_names_a_stock("TIGER 미국나스닥100 담을까") is None
    assert query_names_a_stock("KODEX 인버스 어때") is None


def test_two_char_names_excluded(monkeypatch):
    _inject(monkeypatch)
    # 2글자 이름(동양·KT)은 일반어·부분문자열 충돌 위험이라 len>=3 규칙으로 제외.
    assert query_names_a_stock("동양 어때?") is None
    assert query_names_a_stock("KT 지금 괜찮아?") is None


def test_plain_sentence_no_false_positive(monkeypatch):
    _inject(monkeypatch)
    assert query_names_a_stock("PER이 뭐야") is None
    assert query_names_a_stock("배당이 뭔지 설명해줘") is None
    assert query_names_a_stock("공포탐욕지수 지금 수준 알려줘") is None


# ── graceful / 엣지 ─────────────────────────────────────────────────────────


def test_empty_or_none_input(monkeypatch):
    _inject(monkeypatch)
    assert query_names_a_stock("") is None
    assert query_names_a_stock(None) is None  # type: ignore[arg-type]


def test_master_load_failure_is_graceful(monkeypatch):
    # 마스터 로드 실패 → override 없이 None(크래시 없음·기존 동작 유지).
    def _boom():
        raise RuntimeError("master unavailable")

    monkeypatch.setattr(gz, "load_stock_master", _boom)
    reset_cache()
    assert query_names_a_stock("롯데렌탈 어때?") is None


def test_master_loaded_only_once(monkeypatch):
    # in-process 싱글턴 캐시: 여러 질의에도 마스터는 1회만 로드.
    calls = {"n": 0}

    def _counting():
        calls["n"] += 1
        return list(_FAKE_MASTER)

    monkeypatch.setattr(gz, "load_stock_master", _counting)
    reset_cache()
    query_names_a_stock("롯데렌탈 어때?")
    query_names_a_stock("삼성전자 어때?")
    query_names_a_stock("시장 어때?")
    assert calls["n"] == 1


def test_longest_name_wins_on_overlap(monkeypatch):
    # 부분문자열이 겹칠 때 더 구체적(긴) 이름이 먼저 매칭되도록 긴 이름 우선 정렬.
    master = [
        {"ticker": "111111", "name": "에스피", "market": "KOSPI"},      # len 3
        {"ticker": "058610", "name": "에스피지", "market": "KOSDAQ"},    # len 4 (더 구체적)
    ]
    _inject(monkeypatch, master)
    assert query_names_a_stock("에스피지 어때?") == "에스피지"
