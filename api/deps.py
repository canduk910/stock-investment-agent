"""라우트 공용 의존성 — {ticker} 검증(IMP-02) + 국면 판정 매핑/빌더 SSOT(IMP-06).

두 가지 공용 자산:
1. assert_valid_ticker — 모든 {ticker} 라우트 진입부의 400 검증.
2. 국면 4지표 매핑(_REGIME_INPUT_MAP·map_engine_input)과 build_judgement 의 **단일 출처**.
   이전엔 매핑 dict 가 api/main.py 와 api/detail.py 에 글자 그대로 두 벌 있었다 — 지표를
   한쪽만 고치면 챗봇/매크로 경로와 종목/워치리스트/리포트 경로가 서로 다른 국면 입력을
   쓰게 되어 3중 일관성이 조용히 깨진다. 매핑을 여기 한 곳으로 모은다.
   (macro_regime 의 live_judgement 는 테스트가 내부 수집기를 patch 하므로 api/main.py 에
    남기되, 매핑만 이 모듈을 소비한다.)

deps 는 api.* 를 import 하지 않는다(collectors·infra·macro·watchlist.models 만) →
api/main·api/detail 이 deps 를 import 해도 사이클 없음.
"""
from __future__ import annotations

import re

from fastapi import HTTPException

from collectors.macro_snapshot import collect_macro_indicators
from infra.config import fred_api_key
from macro.engine import judge_regime
from watchlist.models import TICKER_PATTERN  # ticker.js SSOT 와 동일 규칙(단일 출처)

_TICKER_RE = re.compile(TICKER_PATTERN)

# 국면 4지표: 수집기 dict 키 → 엔진 입력 키(**단일 출처**). 엔진은 yield_spread 를 쓰지만
# 수집기는 FRED 시리즈명 t10y2y 로 노출한다. dollar_index·gdp 는 §4 판정 4지표가 아니라 제외.
_REGIME_INPUT_MAP = {
    "t10y2y": "yield_spread",
    "hy_spread": "hy_spread",
    "vix": "vix",
    "fear_greed": "fear_greed",
}


def assert_valid_ticker(ticker: str) -> None:
    """6자 영숫자(^[0-9A-Za-z]{6}$)가 아니면 400.

    불량 코드가 KIS 조회(토큰·레이트리밋)·OpenAI 생성(비용)·히스토리 저장(파일 오염)을
    트리거하기 전에 라우트 진입부에서 차단한다. 모든 {ticker} 라우트가 이 한 함수를 공유.
    """
    if not _TICKER_RE.match(ticker or ""):
        raise HTTPException(status_code=400, detail=f"invalid ticker: {ticker}")


def map_engine_input(snapshot: dict) -> tuple[dict, list[str]]:
    """수집 스냅샷 → (엔진 입력 dict, 못 쓴 국면지표 목록). 단일 매핑 출처.

    실패(None)·부분실패(value=None)·키 부재는 판정에서 제외하고 partial_failure 에 기록만
    한다(임의 기본값 금지). macro_regime·챗봇 live judgement·종목/워치리스트/리포트가 공유.
    """
    indicators = snapshot["indicators"]
    engine_input: dict = {}
    partial_failure: list[str] = []
    for collector_key, engine_key in _REGIME_INPUT_MAP.items():
        point = indicators.get(collector_key)
        if point is not None and point.get("value") is not None:
            engine_input[engine_key] = point["value"]
        else:
            partial_failure.append(engine_key)
    return engine_input, partial_failure


def build_judgement() -> dict:
    """실시간 수집 → 매핑 → judge_regime → 판정만 반환(partial_failure 불필요한 소비처용).

    종목 번들·워치리스트·리포트가 최신 국면을 얻는 단일 출처. 실패는 호출부가 잡아
    regime_gate=None 처리(부분실패 보존). (macro_regime·챗봇은 partial_failure 도 필요해
    api/main.py::live_judgement 을 쓰며, 그 역시 이 모듈의 map_engine_input 을 소비한다.)
    """
    snapshot = collect_macro_indicators(fred_api_key())
    engine_input, _partial_failure = map_engine_input(snapshot)
    return judge_regime(engine_input)
