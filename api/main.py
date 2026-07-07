"""로컬 백엔드 API (FastAPI) — 수집기를 JSON 으로 노출한다(plan §5).

로컬 우선: 이 앱은 AWS Lambda + API Gateway 의 로컬 스탠드인이다. 여기서 정의한
엔드포인트 계약을 그대로 React 프론트가 소비하고, 배포 시 Lambda 핸들러로 옮긴다.

원칙1(현재가 캐시 금지): 지표 현재값은 매 요청마다 수집한다(캐시 미경유).
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from collectors.macro_snapshot import collect_macro_indicators
from infra.config import fred_api_key
from macro.engine import judge_regime

app = FastAPI(title="투자 에이전트 데이터 API", version="0.1.0")

# 국면 판정 입력 매핑 — 수집기 dict 키 → 엔진 입력 키(단일 출처).
# 엔진은 yield_spread 를 쓰지만 수집기는 FRED 시리즈명 t10y2y 로 노출한다.
# dollar_index·gdp 는 수집되더라도 §4 4지표 판정에 안 쓰므로 여기에 없다.
_REGIME_INPUT_MAP = {
    "t10y2y": "yield_spread",
    "hy_spread": "hy_spread",
    "vix": "vix",
    "fear_greed": "fear_greed",
}

# Vite 개발 서버(5173)에서의 브라우저 호출 허용.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# 종목 종합리포트 번들(§6.5) — GET /api/detail/{ticker}/bundle.
# 라우터를 별도 모듈로 분리(2단계 병렬 + partial_failure + 캐시 게이트는 api/detail.py).
from api.detail import router as detail_router  # noqa: E402
from api.stocks import router as stocks_router  # noqa: E402

app.include_router(detail_router)
app.include_router(stocks_router)


@app.get("/api/macro/indicators")
def macro_indicators() -> dict:
    """매크로 지표 스냅샷(§5.1 병렬 + partial_failure).

    IndicatorPoint 의 as_of(date)는 FastAPI 인코더가 ISO 문자열로 직렬화한다.
    """
    return collect_macro_indicators(fred_api_key())


@app.get("/api/macro/regime")
def macro_regime() -> dict:
    """매크로 국면 판정(§4·§6.1) — 결정적 엔진, LLM 미개입.

    흐름: macro_snapshot 으로 실시간 수집(현재값 캐시 미경유, 원칙1) → 국면 4지표
    중 값이 있는 것만 IndicatorPoint.value 를 꺼내 엔진 입력 dict 로 매핑(누락·실패는
    제외, 임의 기본값 금지) → judge_regime 호출 → 판정 계약을 그대로 전개하고
    indicators_used(엔진에 실제 넣은 값)·partial_failure(국면 4지표 중 못 쓴 것)를 덧붙인다.

    반환 = {...judgement(엔진 계약), indicators_used, partial_failure}.
    엔진 계약(2축)은 regime/recommended_cash_ratio/confidence/axes/key_drivers/
    params/vix_panic/missing_indicators/raw_data (구 votes·override → axes·vix_panic).
    axes.cycle·axes.sentiment 는 {score,sign} dict, key_drivers 의 tuple(label,axis,
    direction)은 FastAPI 인코더가 각각 JSON 객체·배열로 직렬화한다.
    """
    snapshot = collect_macro_indicators(fred_api_key())
    indicators = snapshot["indicators"]

    engine_input: dict = {}
    partial_failure: list[str] = []
    for collector_key, engine_key in _REGIME_INPUT_MAP.items():
        point = indicators.get(collector_key)
        # 실패(None)·부분실패(value=None)·키 부재 모두 판정에서 제외하고 기록만.
        if point is not None and point.get("value") is not None:
            engine_input[engine_key] = point["value"]
        else:
            partial_failure.append(engine_key)

    judgement = judge_regime(engine_input)
    return {
        **judgement,
        "indicators_used": dict(engine_input),
        "partial_failure": partial_failure,
    }
