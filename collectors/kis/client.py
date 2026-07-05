"""KIS HTTP 클라이언트 — 조회 API의 유일한 HTTP 경계.

MCP 검증 예제(kis_auth._url_fetch)의 GET 호출 규약을 어댑터로 옮긴 것:
env별 도메인 분기 + 인증 헤더(authorization Bearer/appkey/appsecret/tr_id/
custtype) 주입. 매매 주문 계열은 구현하지 않는다(조회 전용).

테스트는 이 get()만 responses로 mock하고, 정규화·정책 로직은 실제 코드로 통과한다.
"""
from __future__ import annotations

from typing import Any, Callable

import requests

from collectors.kis.errors import KisApiError

# KIS 공식 도메인 — 실전(prod) / 모의(vps)
KIS_DOMAINS = {
    "real": "https://openapi.koreainvestment.com:9443",
    "demo": "https://openapivts.koreainvestment.com:29443",
}


class KisClient:
    """토큰 provider 를 주입받아 KIS 조회 API를 호출한다.

    token_provider: str | Callable[[], str]. 문자열이면 내부에서 (lambda: s)로
    감싸 저장한다(하위호환/테스트 편의). 매 get() 마다 provider() 로 fresh 토큰을
    획득하므로 장수명 프로세스에서 토큰이 갱신돼도 다음 호출이 새 토큰을 쓴다(plan §2).
    """

    def __init__(
        self,
        config,
        token_provider: "str | Callable[[], str]",
        timeout: int = 10,
    ):
        self._config = config
        if isinstance(token_provider, str):
            fixed = token_provider
            self._token_provider: Callable[[], str] = lambda: fixed
        else:
            self._token_provider = token_provider
        self.env = config.env  # 어댑터가 env별 TR_ID를 고르기 위해 참조
        self._base_url = KIS_DOMAINS[config.env]
        self._timeout = timeout

    def get(
        self,
        tr_id: str,
        path: str,
        params: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        """GET 호출 후 JSON body(dict)를 그대로 반환. 정규화는 호출자가 담당."""
        token = self._token_provider()
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self._config.app_key,
            "appsecret": self._config.app_secret,
            "tr_id": tr_id,
            "custtype": "P",  # 개인
        }
        if extra_headers:
            headers.update(extra_headers)

        resp = requests.get(
            self._base_url + path,
            headers=headers,
            params=params,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        body = resp.json()

        # KIS 실패는 HTTP 200 + rt_cd != "0" 로 내려온다(plan §1). rt_cd 부재(None)는
        # 토큰/웹소켓 등 envelope 없는 응답 대비로 통과시키고, 존재하면서 "0" 이 아닐
        # 때만 표면화한다. rt_cd 는 문자열이므로 반드시 "0" 과 문자열 비교한다.
        rt_cd = body.get("rt_cd") if isinstance(body, dict) else None
        # rt_cd 는 규약상 문자열이나, 타입 비순응 응답(int 0 등)을 정상으로 오인
        # raise 하지 않도록 str() 로 정규화해 비교한다.
        if rt_cd is not None and str(rt_cd) != "0":
            raise KisApiError(body.get("msg_cd"), body.get("msg1"), tr_id)
        return body
