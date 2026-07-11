"""KIS 조회 API 오류 표면화 — plan §1 (환각 차단 원칙 직결).

KIS는 실패를 두 형태로 내려준다:
1. HTTP 200 + body `rt_cd != "0"`(+`msg_cd`/`msg1`) — 정상 실패 응답(대부분).
2. **HTTP 5xx** — 게이트웨이/유량제한(예: `EGW00201` 초당 거래건수 초과)·서버 오류.
   본문에도 `rt_cd`/`msg_cd`/`msg1` 이 실려 오는 경우가 많다.

`client.get` 이 두 경우 모두 이 예외로 표면화한다. `raise_for_status` 만으로는
(2)의 본문이 통째로 버려져 "왜 실패했는지"를 못 본다(진짜 원인 관측 불능).
그러면 normalize 단계에서 전 필드가 조용한 None 이 되거나 bare HTTPError 로만
잡혀 근본 원인 진단이 막힌다. `status_code` 를 보존해 상위/로그가 5xx·유량제한을
전이성(재시도 가능)으로 분기할 수 있게 한다.

주의(경계): msg_cd/msg1 은 uapi 조회/주문 응답 envelope 에만 존재한다.
토큰(/oauth2/tokenP)·웹소켓(/oauth2/Approval) 성공 응답에는 rt_cd 자체가 없어
client.get 경로를 타지 않는다(토큰은 auth.request_token 이 별도 처리).
"""
from __future__ import annotations

# 전이성(재시도 가능) KIS 게이트웨이/유량 코드 — 잠시 후 재시도하면 풀리는 부류.
#   EGW00201 = 초당 거래건수 초과(유량제한). 필요 시 실측으로 확장.
RETRYABLE_MSG_CODES = frozenset({"EGW00201"})

# 토큰 무효/만료 코드 — 캐시된 토큰이 (외부 재발급 등으로) KIS에서 무효화됐을 때.
#   EGW00123 = 기간이 만료된 token · EGW00121 = 유효하지 않은 token.
#   이때는 backoff 재시도가 아니라 **토큰 강제 재발급 후 재시도**가 필요하다(같은 죽은
#   토큰으로 재시도하면 계속 실패). 우리 expires_at 이 미래여도 KIS가 무효화할 수 있다.
TOKEN_ERROR_MSG_CODES = frozenset({"EGW00121", "EGW00123"})


class KisApiError(RuntimeError):
    """KIS 조회 응답이 실패(rt_cd != "0") 또는 HTTP 5xx 로 내려왔을 때 발생.

    msg_cd/msg1/tr_id/status_code 를 보존해 상위에서 레이트리밋·전이성 분기를
    열어둔다. 메시지에 넷 다 포함해 로그만으로도 원인 진단이 가능하게 한다.
    """

    def __init__(self, msg_cd, msg1, tr_id, status=None):
        self.msg_cd = msg_cd
        self.msg1 = msg1
        self.tr_id = tr_id
        self.status = status  # HTTP status code(있으면). rt_cd 실패(200)면 200/None.
        super().__init__(
            f"KIS API 오류 tr_id={tr_id} status={status} msg_cd={msg_cd} msg1={msg1}"
        )

    @property
    def retryable(self) -> bool:
        """전이성(재시도 가치) 여부 — HTTP 5xx 이거나 유량제한 msg_cd.

        인증(토큰)·파라미터 오류는 재시도해도 그대로 실패하고 되레 부하만 늘리므로
        False(즉시 표면화). 5xx·유량은 짧은 backoff 후 재시도로 자가치유 가능.
        """
        s = self.status
        if s is not None and 500 <= int(s) <= 599:
            return True
        return self.msg_cd in RETRYABLE_MSG_CODES
