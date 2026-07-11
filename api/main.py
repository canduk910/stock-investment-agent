"""로컬 백엔드 API (FastAPI) — 수집기를 JSON 으로 노출한다(plan §5).

로컬 우선: 이 앱은 AWS Lambda + API Gateway 의 로컬 스탠드인이다. 여기서 정의한
엔드포인트 계약을 그대로 React 프론트가 소비하고, 배포 시 Lambda 핸들러로 옮긴다.

원칙1(현재가 캐시 금지): 지표 현재값은 매 요청마다 수집한다(캐시 미경유).
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.deps import map_engine_input  # 국면 4지표 매핑 SSOT(IMP-06) — detail/report 경로와 공유
from collectors.macro_snapshot import collect_macro_indicators
from infra.config import fred_api_key
from macro.engine import judge_regime

app = FastAPI(title="투자 에이전트 데이터 API", version="0.1.0")

# Vite 개발 서버(5173)에서의 브라우저 호출 허용. POST 는 /api/chat(챗봇) 때문에 필요.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["*"],
)


def live_judgement() -> tuple[dict, dict, list[str]]:
    """실시간 수집(캐시 미경유) → 매핑(deps SSOT) → judge_regime.

    반환 (judgement, indicators_used, partial_failure). macro_regime 과 챗봇이 최신 국면을
    얻는 단일 출처. 매핑은 api.deps.map_engine_input 이 SSOT(IMP-06) — 종목/워치리스트/리포트
    경로(api.deps.build_judgement)와 **같은 매핑**을 쓴다. 수집기·판정 심볼은 이 모듈
    네임스페이스에 남겨(collect_macro_indicators·judge_regime) 라우트 테스트가 경계로 patch 한다.
    """
    snapshot = collect_macro_indicators(fred_api_key())
    engine_input, partial_failure = map_engine_input(snapshot)
    judgement = judge_regime(engine_input)
    return judgement, engine_input, partial_failure


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# 종목 종합리포트 번들(§6.5) — GET /api/detail/{ticker}/bundle.
# 라우터를 별도 모듈로 분리(2단계 병렬 + partial_failure + 캐시 게이트는 api/detail.py).
from api.detail import router as detail_router  # noqa: E402
from api.stocks import router as stocks_router  # noqa: E402

app.include_router(detail_router)
app.include_router(stocks_router)

# 챗봇(§6.2~6.5) — POST /api/chat. live judgement 는 위 live_judgement() 재사용.
from api.chat import router as chat_router  # noqa: E402

app.include_router(chat_router)

# 워치리스트(§3 모듈 3) — GET/POST/DELETE/PATCH /api/watchlist (CRUD + 진입신호 국면 게이트).
# 라우트는 api.detail 의 _build_kis_client·_build_judgement 재사용(api.main 미참조 → 사이클 없음).
from api.watchlist import router as watchlist_router  # noqa: E402

app.include_router(watchlist_router)

# 종목 구조화 리포트(§6.5b P2) — POST/GET /api/detail/{ticker}/report[/history].
from api.report import router as report_router  # noqa: E402

app.include_router(report_router)

# 계좌 잔고(포트폴리오) — GET /api/balance (조회 전용, 우측 패널). 단일 사용자 계정은 config.
from api.reports import router as reports_router  # noqa: E402  # 증권사 리포트 PDF RAG(색인/상태)

app.include_router(reports_router)

from api.balance import router as balance_router  # noqa: E402

app.include_router(balance_router)


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
    judgement, engine_input, partial_failure = live_judgement()
    return {
        **judgement,
        "indicators_used": dict(engine_input),
        "partial_failure": partial_failure,
    }
