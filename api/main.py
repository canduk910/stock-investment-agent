"""로컬 백엔드 API (FastAPI) — 수집기를 JSON 으로 노출한다(plan §5).

로컬 우선: 이 앱은 AWS Lambda + API Gateway 의 로컬 스탠드인이다. 여기서 정의한
엔드포인트 계약을 그대로 React 프론트가 소비하고, 배포 시 Lambda 핸들러로 옮긴다.

원칙1(현재가 캐시 금지): 지표 현재값은 매 요청마다 수집한다(캐시 미경유).
"""
from __future__ import annotations

import datetime as _dt
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.deps import map_engine_input  # 국면 4지표 매핑 SSOT(IMP-06) — detail/report 경로와 공유
from cache.keys import macro_history_key, regime_history_key
from cache.local import LocalCache
from cache.policy import cache_if_clean
from collectors.fear_greed import fetch_fear_greed_history
from collectors.fred import fetch_fred_series_history
from collectors.macro_snapshot import collect_macro_indicators
from infra.config import fred_api_key
from infra.parallel import fetch_parallel
from macro.engine import indicator_meta, judge_regime, regime_breakdown
from macro.regime_history import build_trajectory, downsample_trajectory, trajectory_step

_log = logging.getLogger(__name__)

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


# DB 초기화 — 앱 로드 시 테이블 생성(존재하면 skip). 로컬 SQLite / 프로덕션 GCP Cloud SQL Postgres.
from infra.db import init_db  # noqa: E402

init_db()

# 공유 KIS 자격증명(__shared__) 1회 시드 — env KIS_* → 암호화 DB(프로덕션 전환용, idempotent·graceful).
from auth.kis_seed import seed_shared_kis_from_env  # noqa: E402

seed_shared_kis_from_env()

# 관리자 부트스트랩 — ADMIN_EMAILS(기본 dukkikim@yonsei.ac.kr)의 기존 유저를 is_admin 승격(idempotent·graceful).
from auth.admin_seed import seed_admins  # noqa: E402

seed_admins()

# 인증 라우터(회원가입/로그인/me) — 유저별 데이터 스코프의 진입점.
from api.auth import router as auth_router  # noqa: E402

app.include_router(auth_router)

# 대화기록 라우터(유저별 대화 목록·생성·메시지·삭제).
from api.conversations import router as conversations_router  # noqa: E402

app.include_router(conversations_router)

# 유저별 KIS 자격증명(등록/조회/삭제) — 암호화 저장·검증. 공유키 대체(유저 격리).
from api.kis_credentials import router as kis_credentials_router  # noqa: E402

app.include_router(kis_credentials_router)

# 관리자 라우터(유저 관리·이용 통계·질문 한도 제어) — get_admin_user 게이트(비관리자 403).
from api.admin import router as admin_router  # noqa: E402

app.include_router(admin_router)


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

from api.macro_outlook import router as macro_outlook_router  # noqa: E402  # 시황 요약(시장 국면 페이지)

app.include_router(macro_outlook_router)


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
        # 판정근거 카드용 — 4지표 값 + 구간(양호/중립/악화·탐욕/중립/공포) + 축·단위·임계·출처.
        # 누락 지표도 카드로 노출(value/zone=None). 국면 판정은 코드(엔진), 이건 그 근거 표면화.
        "indicator_breakdown": regime_breakdown(engine_input),
        "partial_failure": partial_failure,
    }


# 지표 히스토리 — 확정 과거값이라 캐시 가능(현재값 무캐시 원칙1과 무관). in-memory(_META_CACHE 패턴).
_MACRO_HISTORY_CACHE = LocalCache()
MACRO_HISTORY_TTL_SECONDS = 86400  # 1일(월단위 데이터라 자주 안 변함)
# 엔진 key → FRED series_id(fear_greed 는 CNN graphdata 별도 수집기).
_HISTORY_FRED_SERIES = {
    "yield_spread": "T10Y2Y",
    "hy_spread": "BAMLH0A0HYM2",
    "vix": "VIXCLS",
}


@app.get("/api/macro/indicators/{key}/history")
def macro_indicator_history(key: str, months: int = 12) -> dict:
    """국면 4지표 1개의 **월단위 히스토리(기본 1년)** — 판정근거 카드 클릭 시 조회.

    FRED 3지표(yield_spread/hy_spread/vix)는 월단위 다운샘플, fear_greed 는 CNN graphdata
    best-effort. 확정 과거값이라 캐시(`macro:history:`, TTL 1일; 불가·실패는 미저장). 불가·실패는
    `available:false`+note(항상 200 graceful). 국면 판정은 코드(엔진), 이건 원천값 표면화(판정 아님).

    반환: {key, label, unit, source, thresholds, months, points:[{date,value}], available, note?}.
    """
    meta = indicator_meta(key)
    if meta is None:  # 판정 4지표가 아닌 키(400 — 잘못된 조회 차단)
        raise HTTPException(status_code=400, detail=f"unknown indicator: {key}")
    months = max(1, min(months, 60))

    cache_key = macro_history_key(key, months)
    cached = _MACRO_HISTORY_CACHE.get(cache_key)
    if cached is not None:
        return cached

    points = None
    try:
        if key in _HISTORY_FRED_SERIES:
            points = fetch_fred_series_history(_HISTORY_FRED_SERIES[key], fred_api_key(), months=months)
        elif key == "fear_greed":
            points = fetch_fear_greed_history(months=months)
    except Exception:  # noqa: BLE001 — 외부 수집 실패는 삼키지 않되 available:false 로 graceful
        _log.warning("indicator history fetch failed: %s", key, exc_info=True)
        points = None

    available = bool(points)
    result = {
        "key": key,
        "label": meta["label"],
        "unit": meta["unit"],
        "source": meta["source"],
        "thresholds": meta["thresholds"],
        "months": months,
        "points": points or [],
        "available": available,
    }
    if not available:
        result["note"] = "이 지표는 히스토리를 제공하지 못했습니다(현재값만 참고하세요)."
    else:
        cache_if_clean(_MACRO_HISTORY_CACHE, cache_key, result, MACRO_HISTORY_TTL_SECONDS)
    return result


# 국면 이동 궤적 — 4지표 엔진 키(경기→심리 순, partial_failure 정렬용 SSOT).
_REGIME_ENGINE_KEYS = [*_HISTORY_FRED_SERIES, "fear_greed"]  # yield_spread, hy_spread, vix, fear_greed
_REGIME_TRAJECTORY_MAX_MONTHS = 60
_KST = _dt.timezone(_dt.timedelta(hours=9))  # 진행 중 당월 판정 기준(앱 KST 관습과 일치)


def _current_month_kst() -> str:
    """오늘(KST) 'YYYY-MM' — 진행 중 당월(부분 데이터) 제외 기준. 라우트가 빌더에 넘긴다(빌더는 순수)."""
    return _dt.datetime.now(_KST).strftime("%Y-%m")


@app.get("/api/macro/regime/history")
def macro_regime_history(months: int = 36) -> dict:
    """최근 N개월 **국면 이동 궤적**(경기×심리 매트릭스 족적) — 월별 지표를 판정 엔진에 재현.

    FRED 3지표(yield_spread/hy_spread/vix)의 월단위 히스토리 + 공포탐욕(CNN best-effort)을 **병렬**
    수집 → `macro.regime_history.build_trajectory` 가 월별로 `judge_regime` 을 돌려 (cycle_score,
    sentiment_score, regime, ...) 점을 만든다. **판정은 코드(엔진)·결정적**(과거 지표 재현), LLM 미개입.
    확정 과거값이라 캐시(`macro:history:regime:`, TTL 1일; 불가/실패는 미저장). **항상 200 graceful**.
    지표별 수집 실패는 그 지표만 제외(공포탐욕 결측이어도 심리축은 VIX 로 판정 → 궤적 유지).

    월별 원본은 창이 길수록 과밀·불규칙(라벨이 국면 전환마다)이라 **범위별 표본 간격으로 다운샘플**한다:
    1년(≤12개월)=분기(step 3) · 2년(≤24개월)=반기(6) · 3년+ = 연(12). 판정은 그대로 엔진 재현·표시 밀도만 조정.

    반환: {months, interval:"quarterly|semiannual|annual", step_months, points:[{date, cycle_score,
    sentiment_score, regime, recommended_cash_ratio, vix_panic, missing_indicators}], available,
    partial_failure, note?}.
    """
    months = max(1, min(months, _REGIME_TRAJECTORY_MAX_MONTHS))

    cache_key = regime_history_key(months)
    cached = _MACRO_HISTORY_CACHE.get(cache_key)
    if cached is not None:
        return cached

    # 4지표 월 시계열 병렬 수집 — 각 job 실패(예외/타임아웃)는 그 지표만 None(fetch_parallel graceful).
    jobs = {
        key: (lambda sid=sid: fetch_fred_series_history(sid, fred_api_key(), months=months))
        for key, sid in _HISTORY_FRED_SERIES.items()
    }
    jobs["fear_greed"] = lambda: fetch_fear_greed_history(months=months)
    results, _failed = fetch_parallel(jobs, max_workers=4, timeout=20.0)

    series_by_key = {k: v for k, v in results.items() if v}  # None·빈 시계열 제외
    partial_failure = [k for k in _REGIME_ENGINE_KEYS if k not in series_by_key]

    # 진행 중 당월(FRED 부분월 평균)은 결정적으로 제외 — 확정 과거값만 궤적/캐시에 남긴다.
    points = build_trajectory(series_by_key, exclude_month=_current_month_kst())  # 순수·결정적(엔진 재현)
    # 범위별 표본 간격으로 다운샘플(1년=분기·2년=반기·3년=연) — 월별 과밀·불규칙 라벨을 균일 밀도로.
    step, interval = trajectory_step(months)
    points = downsample_trajectory(points, step)
    available = bool(points)
    result = {
        "months": months,
        "interval": interval,
        "step_months": step,
        "points": points,
        "available": available,
        "partial_failure": partial_failure,
    }
    if not available:
        result["note"] = "국면 궤적을 불러오지 못했습니다(지표 히스토리 조회 실패)."
    else:
        cache_if_clean(_MACRO_HISTORY_CACHE, cache_key, result, MACRO_HISTORY_TTL_SECONDS)
    return result


# ─── 프로덕션: 빌드된 프론트(React/Vite dist) 정적 서빙 + SPA 폴백 ───────────────
# 단일 Cloud Run 서비스가 API(/api/*)와 프론트를 **같은 오리진**에서 서빙한다 → CORS·프론트
# 코드 변경 0, SSE(/api/chat/stream)도 그대로 동작. dist 가 없으면(로컬 개발·테스트) 블록 전체를
# skip → 기존 동작 무영향.
#
# ⚠ catch-all GET 라우트는 쓰지 않는다 — 그러면 POST 전용 /api 라우트의 405(Method Not Allowed)를
# 200 으로 가려버린다. 대신 **404 예외 핸들러**로 SPA 폴백을 한다: 비-API GET 요청이 매칭 라우트가
# 없어 404 가 날 때만 index.html 을 돌려준다. /api 경로·405·API 의 JSON 에러는 기본 처리 유지.
from pathlib import Path as _Path  # noqa: E402
from fastapi.exception_handlers import http_exception_handler as _default_http_handler  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from starlette.exceptions import HTTPException as _StarletteHTTPException  # noqa: E402

_DIST = _Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    _DIST_ROOT = str(_DIST.resolve())
    _INDEX = _DIST / "index.html"
    if (_DIST / "assets").is_dir():  # 해시 번들(JS/CSS)은 StaticFiles 로 직접 서빙.
        app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")

    @app.exception_handler(_StarletteHTTPException)
    async def _spa_fallback(request, exc):
        """비-API GET 404 → 실제 정적파일이면 그 파일, 아니면 SPA index.html. 그 외는 기본 처리.

        /api 경로·405·API JSON 에러(400/401/404/409 등)는 손대지 않고 기본 핸들러로 넘긴다.
        """
        if (
            exc.status_code == 404
            and request.method == "GET"
            and not request.url.path.startswith("/api")
        ):
            rel = request.url.path.lstrip("/")
            candidate = (_DIST / rel).resolve()
            if rel and candidate.is_file() and str(candidate).startswith(_DIST_ROOT):
                return FileResponse(str(candidate))  # 루트 정적파일(예: /vite.svg)
            return FileResponse(str(_INDEX))  # SPA 진입점
        return await _default_http_handler(request, exc)
