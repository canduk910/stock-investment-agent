"""워치리스트 상수 — 단일 출처. plan §"constants.py".

SORT_KEYS 는 chat/tools.py show_watchlist enum(LLM-facing SSOT)·프론트 watchlistLogic.js 와
반드시 일치(test_sort_keys_consistency 로 강제). WATCHLIST_MAX_ITEMS 는 KIS 레이트리밋 보호
상한(리스트 enrich 는 종목별 inquire_price 병렬 호출이라 종목 수에 비례).
"""
from __future__ import annotations

# 정렬 기준 — show_watchlist sort_by enum 과 동일 순서.
#   registered = 등록순(added_at), change_rate = 등락률, near_target = 목표가 근접.
SORT_KEYS: tuple[str, ...] = ("registered", "change_rate", "near_target")

# 단일 로컬 사용자 기본 키(DynamoDB PK 계약 (user_id, ticker) 유지).
DEFAULT_USER_ID = "local"

# KIS 레이트리밋 보호 상한(리스트 enrich = 종목별 병렬 시세 조회).
WATCHLIST_MAX_ITEMS = 30

# 목표가 근접 판정 임계(%). |distance_to_target| <= 이 값이면 'near'.
NEAR_TARGET_THRESHOLD_PCT = 3.0

# durable 사용자 상태 저장 경로(캐시 아님 — .cache/ 는 로컬 스탠드인 관례 공유).
WATCHLIST_STORE_PATH = ".cache/watchlist.json"
