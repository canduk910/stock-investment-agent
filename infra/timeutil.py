"""시간 헬퍼 SSOT — UTC now(datetime/ISO 문자열)와 KST 타임존의 단일 출처.

배경(리팩토링 RF: 2026-07-29):
- `def _utcnow(): return datetime.now(timezone.utc)` 정의가 SQLAlchemy 모델 4곳
  (auth/models·auth/kis_models·chat/history_models·chat/report_models)과 store 2곳에,
- `def _now_iso(): ...isoformat()` 정의가 라우트/스토어 4곳 + 인라인 2곳(스크리너)에,
- `_KST = timezone(timedelta(hours=9))` 정의가 2곳(auth/usage·api/main)에 산재해 있었다.
  같은 값을 여러 곳에 복제하면 한쪽만 고치는 회귀가 가능하므로 여기로 단일화한다.

계약(행동 보존):
- utcnow(): timezone-aware UTC datetime — SQLAlchemy Column(default=...)에 그대로 쓸 수 있는
  0-인자 callable 이어야 한다(호출 시점 평가).
- now_iso(): utcnow() 의 ISO8601 문자열 표현(마이크로초·+00:00 오프셋 포함) — 기존 각 모듈의
  `_now_iso()` 와 문자열 포맷이 동일해야 저장 포맷(관심종목 added_at 등)이 불변이다.
- KST: 한국 표준시(UTC+9) 고정 오프셋 — 사용량 리셋(auth/usage)·진행 중 당월 제외(api/main)
  등 "한국 날짜 경계" 판정에 공용. DST 없음이므로 고정 오프셋으로 충분하다.

주의: 각 사용처는 `from infra.timeutil import utcnow as _utcnow` 처럼 **모듈-로컬 별칭**으로
가져온다 — 기존 이름을 보존해 테스트 monkeypatch(모듈 속성 치환)와 기존 import 경로
(`from chat.report_models import _utcnow` 등)가 그대로 동작한다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# 한국 표준시(UTC+9). 한국은 서머타임이 없어 고정 오프셋으로 충분하다.
KST = timezone(timedelta(hours=9))


def utcnow() -> datetime:
    """현재 시각을 timezone-aware UTC datetime 으로 반환(naive 금지 — 비교/직렬화 안전)."""
    return datetime.now(timezone.utc)


def now_iso() -> str:
    """현재 UTC 시각의 ISO8601 문자열(예: '2026-07-29T05:00:00.123456+00:00').

    저장 포맷 계약: 기존 각 모듈의 `_now_iso()` 와 동일한 표현이어야
    관심종목 added_at·리포트 created_at 등 기존 저장 데이터와 형식이 섞이지 않는다.
    """
    return utcnow().isoformat()
