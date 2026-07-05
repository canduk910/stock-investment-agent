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

app = FastAPI(title="투자 에이전트 데이터 API", version="0.1.0")

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


@app.get("/api/macro/indicators")
def macro_indicators() -> dict:
    """매크로 지표 스냅샷(§5.1 병렬 + partial_failure).

    IndicatorPoint 의 as_of(date)는 FastAPI 인코더가 ISO 문자열로 직렬화한다.
    """
    return collect_macro_indicators(fred_api_key())
