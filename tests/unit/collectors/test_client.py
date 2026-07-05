"""KIS HTTP 클라이언트 경계 테스트 — plan §2.

KisClient.get은 테스트가 mock하는 유일한 HTTP 경계다. env별 도메인 분기,
인증 헤더(authorization/appkey/appsecret/tr_id/custtype) 주입을 검증한다.
"""
from __future__ import annotations

import pytest
import requests
import responses

from collectors.kis.client import KisClient
from collectors.kis.errors import KisApiError
from infra.config import KisConfig

REAL_CONFIG = KisConfig(app_key="APPKEY", app_secret="APPSECRET", env="real", account_no="12345678-01")
DEMO_CONFIG = KisConfig(app_key="APPKEY", app_secret="APPSECRET", env="demo", account_no="12345678-01")
PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"


@responses.activate
def test_get_injects_auth_headers_and_returns_json():
    url = "https://openapi.koreainvestment.com:9443" + PATH
    responses.add(responses.GET, url, json={"rt_cd": "0", "output1": []}, status=200)
    client = KisClient(REAL_CONFIG, token_provider="TOKEN123")

    body = client.get("TTTC8434R", PATH, params={"CANO": "12345678"})

    assert body == {"rt_cd": "0", "output1": []}
    sent = responses.calls[0].request
    assert sent.headers["authorization"] == "Bearer TOKEN123"
    assert sent.headers["appkey"] == "APPKEY"
    assert sent.headers["appsecret"] == "APPSECRET"
    assert sent.headers["tr_id"] == "TTTC8434R"
    assert sent.headers["custtype"] == "P"


@responses.activate
def test_real_env_uses_prod_domain():
    url = "https://openapi.koreainvestment.com:9443" + PATH
    responses.add(responses.GET, url, json={"ok": True}, status=200)
    KisClient(REAL_CONFIG, token_provider="T").get("TR", PATH, params={})
    assert responses.calls[0].request.url.startswith("https://openapi.koreainvestment.com:9443")


@responses.activate
def test_demo_env_uses_vps_domain():
    url = "https://openapivts.koreainvestment.com:29443" + PATH
    responses.add(responses.GET, url, json={"ok": True}, status=200)
    KisClient(DEMO_CONFIG, token_provider="T").get("TR", PATH, params={})
    assert responses.calls[0].request.url.startswith("https://openapivts.koreainvestment.com:29443")


@responses.activate
def test_extra_headers_merged():
    url = "https://openapi.koreainvestment.com:9443" + PATH
    responses.add(responses.GET, url, json={"ok": True}, status=200)
    KisClient(REAL_CONFIG, token_provider="T").get("TR", PATH, params={}, extra_headers={"tr_cont": "N"})
    assert responses.calls[0].request.headers["tr_cont"] == "N"


@responses.activate
def test_http_error_raises():
    """HTTP 에러는 rt_cd 검사보다 먼저 raise_for_status 에서 HTTPError 로 잡힌다.

    KisApiError(rt_cd 표면화)와 경계를 명시적으로 고정한다.
    """
    url = "https://openapi.koreainvestment.com:9443" + PATH
    responses.add(responses.GET, url, json={"msg": "fail"}, status=500)
    with pytest.raises(requests.exceptions.HTTPError):
        KisClient(REAL_CONFIG, token_provider="T").get("TR", PATH, params={})


@responses.activate
def test_token_provider_called_fresh_each_get__plan_2():
    """매 get() 마다 token_provider() 로 fresh 토큰을 획득한다(plan §2).

    장수명 프로세스(Lambda 웜)에서 토큰이 갱신돼도 다음 get 이 새 토큰을 쓰도록
    고정 토큰이 아니라 provider(callable) 를 주입한다.
    """
    url = "https://openapi.koreainvestment.com:9443" + PATH
    responses.add(responses.GET, url, json={"rt_cd": "0"}, status=200)
    tokens = iter(["T1", "T2"])
    client = KisClient(REAL_CONFIG, token_provider=lambda: next(tokens))

    client.get("TR", PATH, params={})
    client.get("TR", PATH, params={})

    assert responses.calls[0].request.headers["authorization"] == "Bearer T1"
    assert responses.calls[1].request.headers["authorization"] == "Bearer T2"


@responses.activate
def test_token_provider_accepts_plain_string__plan_2():
    """문자열 토큰은 내부에서 (lambda: s)로 감싸 하위호환/테스트 편의를 유지한다."""
    url = "https://openapi.koreainvestment.com:9443" + PATH
    responses.add(responses.GET, url, json={"rt_cd": "0"}, status=200)
    KisClient(REAL_CONFIG, token_provider="STRTOK").get("TR", PATH, params={})
    assert responses.calls[0].request.headers["authorization"] == "Bearer STRTOK"


@responses.activate
def test_error_rt_cd_raises_kis_api_error__plan_1():
    """HTTP 200 + rt_cd != '0' 실패 body 를 KisApiError 로 표면화한다(plan §1).

    KIS 실패는 200 으로 내려오므로 raise_for_status 로는 잡히지 않는다.
    msg_cd/msg1/tr_id 를 보존해 상위 백오프(EGW00133 등) 분기를 열어둔다.
    """
    url = "https://openapi.koreainvestment.com:9443" + PATH
    responses.add(
        responses.GET,
        url,
        json={"rt_cd": "1", "msg_cd": "EGW00133", "msg1": "잠시 후 다시 시도하십시오."},
        status=200,
    )
    with pytest.raises(KisApiError) as exc_info:
        KisClient(REAL_CONFIG, token_provider="T").get("MYTR", PATH, params={})

    err = exc_info.value
    assert err.msg_cd == "EGW00133"
    assert err.msg1 == "잠시 후 다시 시도하십시오."
    assert err.tr_id == "MYTR"
    message = str(err)
    assert "EGW00133" in message
    assert "잠시 후 다시 시도하십시오." in message
    assert "MYTR" in message


@responses.activate
def test_error_rt_cd_without_msg_fields_is_graceful__plan_1():
    """msg_cd/msg1 이 없는 에러 body 도 KisApiError(None, None, tr_id)로 안전하게 표면화."""
    url = "https://openapi.koreainvestment.com:9443" + PATH
    responses.add(responses.GET, url, json={"rt_cd": "1"}, status=200)
    with pytest.raises(KisApiError) as exc_info:
        KisClient(REAL_CONFIG, token_provider="T").get("MYTR", PATH, params={})

    err = exc_info.value
    assert err.msg_cd is None
    assert err.msg1 is None
    assert err.tr_id == "MYTR"
    assert "MYTR" in str(err)  # 메시지 조립이 None 필드로 깨지지 않는다


@responses.activate
def test_rt_cd_integer_zero_passes__plan_1():
    """타입 비순응(정수 rt_cd 0) 응답을 정상으로 처리한다(거짓 표면화 방지)."""
    url = "https://openapi.koreainvestment.com:9443" + PATH
    responses.add(responses.GET, url, json={"rt_cd": 0, "output1": []}, status=200)
    body = KisClient(REAL_CONFIG, token_provider="T").get("TR", PATH, params={})
    assert body == {"rt_cd": 0, "output1": []}


@responses.activate
def test_rt_cd_zero_passes__plan_1():
    """rt_cd == '0' 정상 응답은 그대로 통과(회귀)."""
    url = "https://openapi.koreainvestment.com:9443" + PATH
    responses.add(responses.GET, url, json={"rt_cd": "0", "output1": []}, status=200)
    body = KisClient(REAL_CONFIG, token_provider="T").get("TR", PATH, params={})
    assert body == {"rt_cd": "0", "output1": []}


@responses.activate
def test_rt_cd_absent_passes__plan_1():
    """rt_cd 부재 body 는 통과(토큰/웹소켓 응답 대비 + 기존 mock 회귀)."""
    url = "https://openapi.koreainvestment.com:9443" + PATH
    responses.add(responses.GET, url, json={"ok": True}, status=200)
    body = KisClient(REAL_CONFIG, token_provider="T").get("TR", PATH, params={})
    assert body == {"ok": True}
