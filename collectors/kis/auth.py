"""KIS OAuth 접근토큰 발급·재사용 — plan §2, kis-data-pipeline 스킬 §1.3.

MCP 검증 auth_token 예제(POST /oauth2/tokenP)를 어댑터화:
- 응답(access_token/token_type/expires_in)을 정규화하고 만료 시각(epoch)을 계산.
- 토큰은 24h 유효하고 재발급 남발 시 KIS가 차단하므로, FileCache에 저장해
  만료 임박(<1h) 아닐 때만 재사용한다.

앱키/시크릿은 infra.config가 환경변수에서만 로드(하드코딩 금지).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Callable

import requests

from cache.base import Cache
from cache.keys import kis_token_key
from cache.policy import is_cacheable
from collectors.kis.client import KIS_DOMAINS

logger = logging.getLogger(__name__)

TOKEN_PATH = "/oauth2/tokenP"
# 만료 1시간 전이면 재발급 (여유분)
REFRESH_MARGIN_SECONDS = 3600
# 재발급 거절(rate-limit 등) 후 이 창 동안은 재시도하지 않고 stale 토큰을 쓴다.
# KIS 토큰 발급 제한이 분당 1회 수준이라 60초로 맞춘다(순차 재시도 폭주 방지).
REFRESH_BACKOFF_SECONDS = 60

# env별 재발급 락 — 동시 갱신 스탬피드 방지(plan §2). 모듈 전역 dict 를
# guard 락으로 lazy 생성한다(KIS는 토큰 재발급을 분당 1회 수준으로 제한).
_REFRESH_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
# env별 마지막 재발급 실패 시각(epoch) — backoff 단락용 negative cache.
_LAST_REFRESH_FAILURE: dict[str, float] = {}


def _refresh_lock(cache_key: str) -> threading.Lock:
    """토큰 캐시 키별(=env+app_key) 재발급 락을 lazy 생성해 반환(double-checked).

    앱키별 토큰 격리(유저별 KIS 키) → 락도 캐시 키 단위로 나눠 서로 다른 키의
    재발급이 불필요하게 직렬화되지 않게 한다.
    """
    lock = _REFRESH_LOCKS.get(cache_key)
    if lock is None:
        with _LOCKS_GUARD:
            lock = _REFRESH_LOCKS.get(cache_key)
            if lock is None:
                lock = threading.Lock()
                _REFRESH_LOCKS[cache_key] = lock
    return lock


def request_token(config, clock: Callable[[], float] = time.time) -> dict:
    """실제 토큰 발급 호출 후 정규화 dict 반환.

    반환: {"access_token", "token_type", "expires_at"(epoch)}
    """
    url = KIS_DOMAINS[config.env] + TOKEN_PATH
    headers = {"content-type": "application/json"}
    data = {
        "grant_type": "client_credentials",
        "appkey": config.app_key,
        "appsecret": config.app_secret,
    }
    resp = requests.post(url, data=json.dumps(data), headers=headers, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    expires_in = int(body["expires_in"])
    return {
        "access_token": body["access_token"],
        "token_type": body.get("token_type", "Bearer"),
        "expires_at": clock() + expires_in,
    }


def _is_reusable(entry, clock: Callable[[], float]) -> bool:
    """만료 여유가 margin 이상이면 재발급 없이 재사용 가능."""
    return bool(entry) and (entry["expires_at"] - clock()) > REFRESH_MARGIN_SECONDS


def _in_backoff(cache_key: str, entry, clock: Callable[[], float]) -> bool:
    """최근 재발급 실패 후 backoff 창 안이고, 기존 토큰이 완전 만료 전이면 True.

    이 창 동안은 재발급을 재시도하지 않고 stale 토큰을 재사용해, rate-limit
    중 순차 호출이 발급 요청을 폭주시키는 것을 막는다(plan §2). 캐시 키별(=env+app_key).
    """
    if not (entry and (entry["expires_at"] - clock()) > 0):
        return False
    last_fail = _LAST_REFRESH_FAILURE.get(cache_key)
    return last_fail is not None and (clock() - last_fail) < REFRESH_BACKOFF_SECONDS


def get_token(
    config,
    cache: Cache,
    clock: Callable[[], float] = time.time,
    stale_token: str | None = None,
) -> str:
    """캐시된 토큰이 만료 임박이 아니면 재사용, 아니면 재발급 후 저장(plan §2).

    동시 갱신 스탬피드를 막기 위해 재발급 구간을 env별 락으로 감싸고, 락 획득 후
    캐시를 재조회한다(double-checked locking): 대기 중 다른 스레드가 이미 갱신했으면
    그 토큰을 반환하고 발급을 스킵한다. 발급이 거절(예외)되면 완전 만료 전 기존
    토큰이 있으면 그대로 반환(무한 재시도 금지)하고 실패 시각을 기록해, backoff 창
    동안은 재시도 없이 stale 토큰을 재사용한다(순차 재시도 폭주 방지). 완전 만료
    상태에서 발급이 거절되면 예외를 재전파한다.

    **stale_token(강제 재발급)**: 데이터 호출이 EGW00123(만료 토큰) 등으로 거절돼
    "이 토큰은 죽었다"가 확인된 경우 그 토큰 문자열을 넘긴다. 우리 expires_at 이
    미래여도(=`_is_reusable`이 True여도) 죽은 토큰이므로 재사용 검사를 건너뛰고 재발급
    한다. 단 동시 요청 폭주 방지를 위해 **캐시에 이미 다른(새) 토큰이 있으면**(다른
    스레드가 방금 재발급) 그걸 반환한다. 강제 재발급 실패는 죽은 토큰으로 폴백하지
    않고 예외를 전파한다(죽은 토큰 반환 무의미).

    한계: threading.Lock 기반 single-flight 는 in-process 에서만 유효하다.
    다중 프로세스/워커(예: Lambda 인스턴스 여럿)가 동시에 near-expiry 를 맞으면
    각 프로세스가 1회씩 발급할 수 있고, FileCache 쓰기도 원자적이지 않다. 로컬
    우선 범위에선 수용하며, 프로덕션 다중 인스턴스는 분산 락/원자적 쓰기로 보강한다.
    """
    key = kis_token_key(config.env, config.app_key)  # env+app_key 격리(유저별 KIS 키)
    entry = cache.get(key)
    forcing = stale_token is not None

    if not forcing:
        if _is_reusable(entry, clock):
            return entry["access_token"]
        # 재발급 거절 직후 backoff 창: 락 경합 없이 즉시 stale 토큰 재사용
        if _in_backoff(key, entry, clock):
            return entry["access_token"]
    elif entry and entry.get("access_token") != stale_token:
        return entry["access_token"]  # 다른 스레드가 이미 재발급 → 그 토큰 사용

    with _refresh_lock(key):
        # double-check: 대기 중 다른 스레드가 이미 갱신/실패했으면 발급 스킵
        entry = cache.get(key)
        if not forcing:
            if _is_reusable(entry, clock):
                return entry["access_token"]
            if _in_backoff(key, entry, clock):
                return entry["access_token"]
        elif entry and entry.get("access_token") != stale_token:
            return entry["access_token"]  # 락 대기 중 다른 스레드가 재발급 완료

        try:
            fresh = request_token(config, clock=clock)
        except Exception:
            # 거절 폴백: 강제 재발급이 아니고(죽은 토큰 확정 아님) 완전 만료 전이면
            # 기존 토큰 재사용 + 실패 시각 기록(backoff). 강제 재발급 실패는 전파.
            if not forcing and entry and (entry["expires_at"] - clock()) > 0:
                _LAST_REFRESH_FAILURE[key] = clock()
                logger.warning(
                    "KIS 토큰 재발급 거절 — 완전 만료 전 기존 토큰으로 폴백(env=%s, "
                    "%ds backoff)",
                    config.env,
                    REFRESH_BACKOFF_SECONDS,
                )
                return entry["access_token"]
            raise

        _LAST_REFRESH_FAILURE.pop(key, None)  # 발급 성공 → backoff 해제
        ttl = max(int(fresh["expires_at"] - clock()), 0)
        is_cacheable(key)  # 정책 경유 일관성 가드(kis:token: 은 허용)
        cache.set(key, fresh, ttl_seconds=ttl)
        return fresh["access_token"]


def make_token_provider(config, cache: Cache) -> Callable[..., str]:
    """get_token 을 감싼 provider(callable) 반환 — KisClient 배선용(plan §2).

    KisClient 가 매 get() 마다 이 provider() 를 호출해 fresh 토큰을 얻는다. 토큰이
    무효화돼 KIS가 거절하면 KisClient 가 `provider(stale_token=죽은토큰)` 으로 강제
    재발급을 요청한다. 캐시/락/폴백 정책은 전부 get_token 에 위임한다.
    """
    def provider(stale_token: str | None = None) -> str:
        return get_token(config, cache, stale_token=stale_token)

    return provider
