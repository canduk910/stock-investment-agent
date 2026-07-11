"""KIS HTTP 클라이언트 — 조회 API의 유일한 HTTP 경계.

MCP 검증 예제(kis_auth._url_fetch)의 GET 호출 규약을 어댑터로 옮긴 것:
env별 도메인 분기 + 인증 헤더(authorization Bearer/appkey/appsecret/tr_id/
custtype) 주입. 매매 주문 계열은 구현하지 않는다(조회 전용).

테스트는 이 get()만 responses로 mock하고, 정규화·정책 로직은 실제 코드로 통과한다.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable

import requests

from collectors.kis.errors import KisApiError, TOKEN_ERROR_MSG_CODES

logger = logging.getLogger(__name__)

# KIS 공식 도메인 — 실전(prod) / 모의(vps)
KIS_DOMAINS = {
    "real": "https://openapi.koreainvestment.com:9443",
    "demo": "https://openapivts.koreainvestment.com:29443",
}

# 전이성(5xx·유량) 실패 재시도 정책 — 짧은 지수 backoff+jitter. 인증/파라미터는 비재시도.
_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 0.5  # 초: 0.5, 1.0 … (유량 창(초 단위) 통과에 충분·타임아웃 15s 여유 내)
_SLEEP = time.sleep  # 테스트에서 patch 가능한 간접 참조(backoff 대기 무력화)


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
        """GET 호출 후 JSON body(dict)를 그대로 반환. 정규화는 호출자가 담당.

        두 종류의 실패를 각각 자가치유한다:
        - **토큰 무효/만료(EGW00121/00123)**: 캐시된 토큰이 KIS에서 무효화된 경우
          (우리 expires_at 이 미래여도 외부 재발급 등으로 무효화 가능). **토큰을 강제
          재발급**한 뒤(같은 죽은 토큰으로 재시도하면 무의미) backoff 없이 재시도.
        - **전이성 5xx·유량제한(EGW00201)**: 짧은 지수 backoff 후 재시도.
        인증(그 외)·파라미터 오류는 재시도 없이 즉시 표면화. 소진·비재시도는 KisApiError.
        """
        stale_token: str | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            token = self._resolve_token(stale_token)
            try:
                return self._request(tr_id, path, params, extra_headers, token)
            except KisApiError as err:
                if attempt == _MAX_ATTEMPTS:
                    raise
                if err.msg_cd in TOKEN_ERROR_MSG_CODES:
                    # 죽은 토큰 → 다음 시도는 강제 재발급(이 토큰을 stale 로 전달).
                    stale_token = token
                    logger.warning(
                        "KIS 토큰 무효(%s) — 강제 재발급 후 재시도 %d/%d tr_id=%s",
                        err.msg_cd, attempt, _MAX_ATTEMPTS, tr_id,
                    )
                    continue  # backoff 없이 즉시(토큰만 새로 받으면 됨)
                if not err.retryable:
                    raise
                delay = _BACKOFF_BASE * (2 ** (attempt - 1)) + random.uniform(0, 0.1)
                logger.warning(
                    "KIS 재시도 %d/%d tr_id=%s status=%s msg_cd=%s (%.2fs 후)",
                    attempt, _MAX_ATTEMPTS, tr_id, err.status, err.msg_cd, delay,
                )
                _SLEEP(delay)
        raise AssertionError("unreachable")  # 루프는 항상 return/raise 로 종료

    def _resolve_token(self, stale_token: str | None) -> str:
        """토큰 획득. stale_token 이 주어지면 provider 에 강제 재발급을 요청한다.

        provider 가 stale_token 인자를 지원하지 않는 경우(고정 토큰/테스트 더블)는
        인자 없이 호출한다(하위호환).
        """
        if stale_token is not None:
            try:
                return self._token_provider(stale_token=stale_token)
            except TypeError:
                return self._token_provider()
        return self._token_provider()

    def _request(
        self,
        tr_id: str,
        path: str,
        params: dict[str, Any],
        extra_headers: dict[str, str] | None,
        token: str,
    ) -> dict:
        """단발 GET — 실패(HTTP 5xx/4xx 또는 rt_cd != "0")를 KisApiError 로 표면화."""
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

        # ★본문을 먼저 읽는다(raise_for_status 로 버리지 않음) — KIS 는 HTTP 5xx 에도
        #   rt_cd/msg_cd/msg1 을 실어 주는 경우가 많다(유량제한 EGW00201 등). 비-JSON
        #   본문(게이트웨이 HTML 등)은 방어적으로 None 처리 후 status 로만 표면화한다.
        try:
            body = resp.json()
        except ValueError:
            body = None
        parsed = body if isinstance(body, dict) else {}
        status = resp.status_code
        msg_cd = parsed.get("msg_cd")
        msg1 = parsed.get("msg1")

        # KIS 실패는 (a) HTTP 5xx/4xx 또는 (b) HTTP 200 + rt_cd != "0". rt_cd 는 규약상
        # 문자열이나 타입 비순응(int 0 등)을 정상 오인 raise 하지 않도록 str() 비교한다.
        rt_cd = parsed.get("rt_cd")
        http_error = status >= 400
        rt_error = rt_cd is not None and str(rt_cd) != "0"
        if http_error or rt_error:
            if msg1 is None and body is None:
                # 비-JSON 오류 본문 — 상태 + 짧은 텍스트 스냅샷으로 최소한의 단서 보존.
                msg1 = f"HTTP {status} {(resp.text or '')[:200]}".strip()
            # ⚠ 로그에 토큰/appkey/appsecret 은 남기지 않는다(tr_id·status·msg 만).
            logger.warning(
                "KIS 오류 tr_id=%s status=%s msg_cd=%s msg1=%s",
                tr_id, status, msg_cd, msg1,
            )
            raise KisApiError(msg_cd, msg1, tr_id, status=status)
        return body
