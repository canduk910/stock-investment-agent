"""KIS 인증 토큰 발급·재사용 테스트 — plan §2, §5.

MCP로 검증한 실제 auth_token 계약(POST /oauth2/tokenP, 응답
access_token/token_type/expires_in)을 fixture로 고정하고,
HTTP 경계만 responses로 mock한다. 토큰 재사용/재발급 정책은 실제 코드로 통과.
"""
from __future__ import annotations

import json
import threading
import time

import pytest
import responses

from cache.keys import kis_token_key
from cache.local import LocalCache
from collectors.kis import auth
from infra.config import KisConfig

CONFIG = KisConfig(app_key="APPKEY", app_secret="APPSECRET", env="real", account_no="12345678-01")
TOKEN_URL = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"


def _register_token(fixture):
    responses.add(responses.POST, TOKEN_URL, json=fixture, status=200)


@pytest.fixture(autouse=True)
def _reset_auth_module_state():
    """모듈 전역(backoff negative cache)을 테스트 간 격리한다."""
    auth._LAST_REFRESH_FAILURE.clear()
    yield
    auth._LAST_REFRESH_FAILURE.clear()


@responses.activate
def test_request_token_normalizes_and_computes_expiry(load_fixture):
    """응답을 정규화하고 발급 시각 기준 expires_at(epoch)을 계산한다."""
    fixture = load_fixture("kis_auth_token")
    _register_token(fixture)

    result = auth.request_token(CONFIG, clock=lambda: 1000.0)

    assert result["access_token"] == fixture["access_token"]
    assert result["token_type"] == "Bearer"
    # expires_in(86400) 초 뒤가 만료 시각
    assert result["expires_at"] == 1000.0 + 86400


@responses.activate
def test_token_refreshed_when_absent(load_fixture):
    """캐시에 토큰이 없으면 발급하고 저장한다."""
    fixture = load_fixture("kis_auth_token")
    _register_token(fixture)
    cache = LocalCache(clock=lambda: 1000.0)

    token = auth.get_token(CONFIG, cache, clock=lambda: 1000.0)

    assert token == fixture["access_token"]
    assert len(responses.calls) == 1  # 실제 발급 1회
    assert cache.get(kis_token_key("real"))["access_token"] == fixture["access_token"]


@responses.activate
def test_token_reused_when_not_near_expiry():
    """만료 여유가 충분하면 재발급 없이 캐시 토큰을 재사용한다(KIS 차단 방지)."""
    _register_token({"should": "not be called"})
    cache = LocalCache(clock=lambda: 1000.0)
    cache.set(
        kis_token_key("real"),
        {"access_token": "CACHED", "token_type": "Bearer", "expires_at": 1000.0 + 86400},
        ttl_seconds=86400,
    )

    token = auth.get_token(CONFIG, cache, clock=lambda: 1000.0)

    assert token == "CACHED"
    assert len(responses.calls) == 0  # HTTP 미호출 = 재사용


@responses.activate
def test_token_refreshed_when_near_expiry(load_fixture):
    """만료 임박(<1h)이면 재발급한다."""
    fixture = load_fixture("kis_auth_token")
    _register_token(fixture)
    cache = LocalCache(clock=lambda: 1000.0)
    cache.set(
        kis_token_key("real"),
        {"access_token": "STALE", "token_type": "Bearer", "expires_at": 1000.0 + 1800},  # 30분 남음
        ttl_seconds=1800,
    )

    token = auth.get_token(CONFIG, cache, clock=lambda: 1000.0)

    assert token == fixture["access_token"]  # 새 토큰
    assert len(responses.calls) == 1


def test_get_token_single_flight_issues_once(monkeypatch):
    """동시 N개 스레드가 갱신을 시도해도 발급은 정확히 1회여야 한다(plan §2).

    KIS는 토큰 재발급을 분당 1회 수준으로 제한하므로 스탬피드가 곧 차단이다.
    env별 락 + double-checked locking 으로 첫 스레드만 발급하고, 대기 후 진입한
    스레드는 캐시에 이미 채워진 토큰을 재조회해 발급을 스킵함을 검증한다.
    결정성: fake request_token 이 락 보유 구간에서 짧게 대기해 나머지 스레드를
    락에 몰리게 하고, 시작을 barrier 로 동기화한다.
    """
    n_threads = 8
    cache = LocalCache(clock=lambda: 1000.0)
    call_count = {"n": 0}
    count_lock = threading.Lock()
    start = threading.Barrier(n_threads, timeout=5)  # worker 조기 사망 시 무한 hang 방지

    def fake_request_token(config, clock=time.time):
        with count_lock:
            call_count["n"] += 1
        time.sleep(0.02)  # 락 보유 구간을 넓혀 나머지 스레드를 대기시킨다
        return {
            "access_token": "FRESH",
            "token_type": "Bearer",
            "expires_at": clock() + 86400,
        }

    monkeypatch.setattr(auth, "request_token", fake_request_token)

    results: list[str] = []
    results_lock = threading.Lock()

    def worker():
        start.wait()
        token = auth.get_token(CONFIG, cache, clock=lambda: 1000.0)
        with results_lock:
            results.append(token)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert not any(t.is_alive() for t in threads), "스레드가 5s 내 종료 실패(hang)"

    assert call_count["n"] == 1  # 락 + double-check → 발급 정확히 1회
    assert results == ["FRESH"] * n_threads


def test_get_token_rejection_fallback_returns_existing_when_still_valid(monkeypatch):
    """발급 거절 시 완전 만료 전이면 기존 토큰을 반환한다(예외 없음, plan §2).

    near-expiry(30분 남음: <1h margin 이라 재발급 시도하나 >0 이라 완전 만료는 아님)
    캐시 토큰 + request_token 예외 → graceful 폴백(무한 재시도 금지).
    """
    cache = LocalCache(clock=lambda: 1000.0)
    cache.set(
        kis_token_key("real"),
        {"access_token": "NEAR", "token_type": "Bearer", "expires_at": 1000.0 + 1800},
        ttl_seconds=1800,
    )

    def boom(config, clock=time.time):
        raise RuntimeError("EGW00133 접근토큰 발급 잠시 후 다시 시도하십시오")

    monkeypatch.setattr(auth, "request_token", boom)

    token = auth.get_token(CONFIG, cache, clock=lambda: 1000.0)

    assert token == "NEAR"  # 예외 없이 기존 토큰 재사용


def test_get_token_rejection_reraises_when_no_valid_token(monkeypatch):
    """발급 거절 + 유효 토큰 부재(또는 완전 만료)면 예외를 재전파한다(plan §2)."""
    cache = LocalCache(clock=lambda: 1000.0)  # 빈 캐시

    def boom(config, clock=time.time):
        raise RuntimeError("발급 실패")

    monkeypatch.setattr(auth, "request_token", boom)

    with pytest.raises(RuntimeError):
        auth.get_token(CONFIG, cache, clock=lambda: 1000.0)


def test_get_token_rejection_backoff_caps_retries(monkeypatch):
    """거절 폴백 중 backoff 창 안에서는 재발급을 재시도하지 않는다(plan §2).

    near-expiry(<1h) 창에서 KIS가 rate-limit(EGW00133)으로 거절하는 동안,
    KisClient.get()이 매 호출마다 provider()->get_token()을 부르면 발급 요청이
    호출당 1회씩 폭주해 '재발급 남발 방지' 목표와 충돌한다. backoff negative
    cache로 창 안 재시도를 단락하고, 창 경과 후에만 1회 더 시도함을 검증한다.
    """
    cache = LocalCache(clock=lambda: 1000.0)
    cache.set(
        kis_token_key("real"),
        {"access_token": "NEAR", "token_type": "Bearer", "expires_at": 1000.0 + 1800},
        ttl_seconds=1800,
    )
    calls = {"n": 0}

    def boom(config, clock=time.time):
        calls["n"] += 1
        raise RuntimeError("EGW00133 접근토큰 발급 잠시 후 다시 시도")

    monkeypatch.setattr(auth, "request_token", boom)

    now = {"t": 1000.0}
    clk = lambda: now["t"]  # noqa: E731

    # backoff 창 안: 100회 호출 → 실제 발급 시도는 1회, 나머지는 stale 반환
    for _ in range(100):
        assert auth.get_token(CONFIG, cache, clock=clk) == "NEAR"
    assert calls["n"] == 1

    # 창 경과 후: 1회 더 시도 허용
    now["t"] = 1000.0 + auth.REFRESH_BACKOFF_SECONDS + 1
    assert auth.get_token(CONFIG, cache, clock=clk) == "NEAR"
    assert calls["n"] == 2


@responses.activate
def test_make_token_provider_returns_callable_yielding_token(load_fixture):
    """make_token_provider 는 get_token 을 감싼 callable 을 반환한다(live/프로덕션 배선)."""
    fixture = load_fixture("kis_auth_token")
    _register_token(fixture)
    cache = LocalCache(clock=lambda: 1000.0)

    provider = auth.make_token_provider(CONFIG, cache)

    assert callable(provider)
    assert provider() == fixture["access_token"]
