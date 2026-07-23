"""종목명 gazetteer — 인텐트 분류 결정적 pre-gate (판정=코드).

KRX 마스터(`collectors.stock_master`)를 재사용해 "질문에 실제 개별 종목명이 들어있는가"를 판정한다.
`chat/intent.py::classify()` 가 ML=macro_view 로 오분류했을 때, 질문에 종목명이 있으면(시장 전체가 아니라
특정 종목을 묻는 것이므로) stock_analysis 로 재분류하는 데 쓴다. LLM/확률 없이 순수 문자열 매칭 —
결정적·graceful(마스터 로드 실패해도 override 없이 기존 동작 유지).

**방향 주의: 종목명 ⊆ 질문**(`name in text`)으로 검사한다. 반대(질문 ⊆ 종목명, `search_stocks` 방식)는
"코스피"가 인덱스 추종 상품명("KODEX 코스피200")의 부분문자열이라 시장 질문을 오탐한다 — 우리는 인덱스/ETF
이름을 아예 제외하고 name⊆query 로만 본다.

저수준 유지: `api.stocks` 를 import 하지 않고(그 방향은 사이클 위험) `collectors.stock_master.load_stock_master`
를 직접 감싸 in-process 로 1회 캐시한다(chat→collectors 는 tools/view_context 선례로 사이클 없음).
"""
from __future__ import annotations

from collectors.stock_master import load_stock_master

# ETF/ETN/인덱스/레버리지/인버스/선물 표식 — 개별 주식 gazetteer 에서 제외(시장·상품 질문 오탐 방지).
_EXCLUDE_MARKERS: tuple[str, ...] = (
    "KODEX", "TIGER", "KBSTAR", "KOSEF", "ARIRANG", "HANARO", "KOACT",
    "SOL", "ACE", "PLUS", "RISE", "히어로즈", "TIMEFOLIO", "KIWOOM", "마이티",
    "ETN", "레버리지", "인버스", "선물", "코스피", "코스닥",
)
# 2글자 이름은 일반어(동양/대상/기아…)와 충돌해 부분문자열 오탐 → len>=3 만 인식(사용자 결정).
_MIN_NAME_LEN = 3

_GAZETTEER: list[str] | None = None  # 긴 이름 우선 정렬된 종목명 리스트(in-process 1회 캐시)


def _is_excluded(name: str) -> bool:
    upper = name.upper()
    return any(marker.upper() in upper for marker in _EXCLUDE_MARKERS)


def _build_gazetteer(master: list[dict]) -> list[str]:
    """master → 개별 주식 이름 리스트(ETF/인덱스 제외·len>=3), **긴 이름 우선 정렬**(순수·결정적).

    긴 이름을 먼저 두면 부분문자열이 겹칠 때 더 구체적인 이름이 먼저 매칭된다.
    """
    names = set()
    for stock in master:
        name = (stock.get("name") or "").strip()
        if len(name) < _MIN_NAME_LEN or _is_excluded(name):
            continue
        names.add(name)
    return sorted(names, key=lambda n: (-len(n), n))


def _load_gazetteer() -> list[str]:
    """gazetteer 를 lazy·1회 로드해 캐시(`_load_model` 패턴). 마스터 실패 → `[]`(override 없음·크래시 없음)."""
    global _GAZETTEER
    if _GAZETTEER is None:
        try:
            _GAZETTEER = _build_gazetteer(load_stock_master())
        except Exception:
            _GAZETTEER = []
    return _GAZETTEER


def query_names_a_stock(text: str) -> str | None:
    """질문에 개별 종목명(len>=3·ETF/인덱스 제외)이 부분문자열로 들어있으면 그 이름, 없으면 None.

    순수(캐시 읽기)·예외 없음·긴 이름 우선. 결정적(LLM/확률/랜덤 0).
    """
    if not text:
        return None
    try:
        gazetteer = _load_gazetteer()
    except Exception:
        return None
    for name in gazetteer:
        if name in text:
            return name
    return None


def reset_cache() -> None:
    """테스트 훅 — in-process gazetteer 캐시 클리어(fake master 재주입용)."""
    global _GAZETTEER
    _GAZETTEER = None
