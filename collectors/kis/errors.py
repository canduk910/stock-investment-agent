"""KIS 조회 API 오류 표면화 — plan §1 (환각 차단 원칙 직결).

KIS는 실패해도 HTTP 200 + body에 rt_cd != "0", msg_cd, msg1 로 응답한다.
raise_for_status 만으로는 이 실패 body가 통과해 normalize 단계에서 전 필드가
조용한 None 이 되고, 예외가 아니므로 번들 partial_failure 에도 잡히지 않는다.
client.get 에서 rt_cd 를 검사해 이 예외로 표면화한다.

주의(경계): msg_cd/msg1 은 uapi 조회/주문 응답 envelope 에만 존재한다.
토큰(/oauth2/tokenP)·웹소켓(/oauth2/Approval) 성공 응답에는 rt_cd 자체가 없어
client.get 경로를 타지 않는다(토큰은 auth.request_token 이 별도 처리).
"""
from __future__ import annotations


class KisApiError(RuntimeError):
    """KIS 조회 응답이 rt_cd != "0" 실패를 반환했을 때 발생.

    msg_cd/msg1/tr_id 를 보존해 상위에서 레이트리밋(EGW00133 등) 백오프 분기를
    열어둔다(plan §1, KIS 근거 조사 §4). 메시지에 셋 다 포함해 로그만으로도
    원인 진단이 가능하게 한다.
    """

    def __init__(self, msg_cd, msg1, tr_id):
        self.msg_cd = msg_cd
        self.msg1 = msg1
        self.tr_id = tr_id
        super().__init__(
            f"KIS API 오류 tr_id={tr_id} msg_cd={msg_cd} msg1={msg1}"
        )
