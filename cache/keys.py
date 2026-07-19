"""캐시 키 컨벤션 — plan §4.

현재가는 캐시 대상이 아니므로 네임스페이스 자체를 만들지 않는다(원칙1).
"""
from __future__ import annotations

import hashlib


def macro_key(indicator: str) -> str:
    return f"macro:{indicator}"


def macro_history_key(indicator: str, months: int) -> str:
    """지표 월단위 히스토리 캐시 키.

    현재값은 캐시 금지(원칙1)지만 **확정 과거 히스토리는 캐시 가능** — `macro:` 프리픽스
    유지로 policy.ALLOWED_PREFIXES 를 통과한다(부분실패/불가 응답은 라우트가 미저장).
    """
    return f"macro:history:{indicator}:{months}m"


def regime_history_key(months: int) -> str:
    """국면 이동 궤적(월별 판정 재현) 캐시 키.

    지표 히스토리와 동일하게 **확정 과거값**이라 캐시 가능(`macro:history:` 프리픽스로 policy 통과).
    지표 단위(macro_history_key)와 구분해 `regime` 슬롯을 쓴다. 불가/실패 응답은 라우트가 미저장.
    """
    return f"macro:history:regime:{months}m"


def stock_meta_key(ticker: str) -> str:
    return f"stock:meta:{ticker}"


def stock_meta_sub_key(ticker: str, section: str) -> str:
    """섹션별 메타 서브키 (financials/basic 등).

    상위 stock_meta_key 와 동일하게 `stock:meta:` 프리픽스를 유지하므로 캐시
    정책(policy.ALLOWED_PREFIXES 화이트리스트, 원칙1)을 그대로 통과한다. 번들의
    섹션 단위 캐시(원칙2 명시 게이트)가 이 키로 financials·basic 메타만 저장한다.
    """
    return f"stock:meta:{ticker}:{section}"


def kis_token_key(env: str, app_key: str) -> str:
    """토큰 캐시 키 — env + app_key 해시로 **앱키별 격리**.

    유저별 KIS 키가 서로의 토큰을 밟지 않도록 app_key 를 키에 반영한다(원문 노출 방지:
    sha256 앞 12자). 프리픽스 `kis:token:` 유지 → 캐시 정책 화이트리스트(원칙1) 통과.
    """
    digest = hashlib.sha256(app_key.encode()).hexdigest()[:12]
    return f"kis:token:{env}:{digest}"
