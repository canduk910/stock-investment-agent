"""네이버 시황(market outlook) 리포트 → 구조화 요약 생성(chat/analyst_report.py 패턴 재사용).

PDF 원문 텍스트(rag.ingest.extract_text) + 메타(증권사·제목·작성일)를 컨텍스트로 CHAT_MODEL 에
JSON 요약을 요청 → MarketOutlookSummary 검증 → 실패 1회 재요청 → 폴백. 안전: 이건 '시황 리포트의
내용을 요약'하는 것 — 에이전트의 시장 판정이 아니라 출처 귀속·면책. 시장 국면 판정은 코드(매크로 엔진).
"""
from __future__ import annotations

import logging
from datetime import datetime

from chat.market_outlook_schema import MarketOutlookSummary
from chat.structured_summary import generate_validated, make_client, wrap_failure, wrap_success
from infra.timeutil import KST

_log = logging.getLogger(__name__)

_MAX_TEXT_CHARS = 8000  # 요약 컨텍스트 원문 상한(프롬프트 예산)
_FALLBACK_MESSAGE = "시황 요약을 생성하지 못했습니다."

# 서버 하루 1회 자동 수집 가드(모듈 전역·프로세스 단위). 프론트 `mo_autofetch_date` 가드와 동형 —
# stale 이어도 하루에 한 번만 동기 수집을 시도한다(주말/공휴일 무자료 시 매 질문 재수집 폭주 방지).
# 시도 전에 세팅하므로 실패해도 그날 재시도하지 않는다.
_LAST_OUTLOOK_ATTEMPT: str | None = None
_OUTLOOK_COLLECT_TIMEOUT = 45.0  # 동기 수집 대기 상한(초). 초과 시 백그라운드 계속·그 턴은 기존분 사용.


def _build_summary_prompt(text: str, meta: dict) -> str:
    m = meta or {}
    return f"""너는 증권사 '시황(시장 전망) 리포트'를 '요약'하는 도우미다. 아래 리포트 원문을 읽고 JSON 으로 요약하라.

[리포트 메타] 증권사={m.get('broker', '')} · 제목={m.get('title', '')} · 작성일={m.get('date', '')}

[리포트 원문(발췌)]
{(text or '')[:_MAX_TEXT_CHARS]}

[규칙 — 반드시 지켜라]
- 이건 해당 증권사의 **시장 전체 시황 전망**이다(개별 종목·목표주가 아님). **네 자신의 시장 판정이 아니라, "리포트에 따르면" 내용을 그대로 요약·인용**한다.
- 시장전망에는 리포트가 밝힌 시장 스탠스(긍정적/중립/신중 등)를 리포트 표현대로 담아라.
- 세줄요약: 리포트 시황을 **3줄**로 압축하라(각 줄 짧은 한 문장, 정확히 3개 이하·최소 1개, 리포트 내용 인용). 카드 미리보기용 핵심만.
- 핵심요지 1~5개(리포트의 시황 논지·근거). 리스크요인 1~5개 — 없으면 ["리포트에 명시된 리스크 없음"].
- 면책고지에는 "이 요약은 해당 증권사 시황 리포트의 내용이며 투자 판단·매매 권유가 아니다. 참고용이며 면허 있는 투자자문이 아니다."를 담아라.
- JSON 키(한글): 증권사, 제목, 시장전망, 요약, 세줄요약(문자열 배열, 최대 3), 핵심요지(문자열 배열), 리스크요인(문자열 배열), 면책고지.

JSON 객체 하나만 출력하라."""


def format_market_outlook_context(entry: dict) -> str:
    """저장된 시황 리포트 entry(메타+summary) → 챗 세션 핀 컨텍스트용 사람가독 텍스트.

    애널리스트의 `format_report_context` 대응 — 다만 시황은 **시장 전체**라 종목·목표주가가 없고
    '시장전망'이 있다. 프론트가 요약 본문을 신뢰전송하지 않는다(서버가 store 에서 조회한 entry 로 만듦
    → 환각·조작 차단). summary 없으면 메타만으로 최소 블록.
    """
    s = entry.get("summary") or {}
    broker = s.get("증권사") or entry.get("broker", "")
    lines = [f"- 증권사: {broker}", f"- 제목: {s.get('제목') or entry.get('title', '')}"]
    if entry.get("date"):
        lines.append(f"- 작성일: {entry['date']}")
    if s.get("시장전망"):
        lines.append(f"- 시장전망(리포트가 밝힌 시장 방향): {s['시장전망']}")
    if s.get("요약"):
        lines.append(f"- 요약: {s['요약']}")
    for k in ("핵심요지", "리스크요인"):
        vals = s.get(k) or []
        if vals:
            lines.append(f"- {k}: " + " / ".join(str(v) for v in vals))
    if s.get("면책고지"):
        lines.append(f"- 면책: {s['면책고지']}")
    return "\n".join(lines)


def build_recent_outlook_context(limit: int = 3, max_chars: int = 1500, *, store=None) -> str | None:
    """최근 저장 시황 요약 N개 → 챗 프롬프트 주입용 컨텍스트 텍스트. 없으면 None(graceful).

    시장 전반 질문(macro_view)에 **국면 판정과 함께 근거**로 실린다. 저장된 per-report 요약만
    조합하므로 **PDF 재다운로드·LLM 추가호출 0**(벡터검색 불요 — 시황은 시장 전체·최근 소수 고정).
    각 리포트는 `format_market_outlook_context` 로 포맷하고 `max_chars` 로 프롬프트 예산을 제한한다.
    """
    try:
        if store is None:
            from chat.market_outlook_store import default_store

            store = default_store()
        reports = (store.list_reports() or [])[:limit]
    except Exception:
        return None  # 조회 실패는 컨텍스트 없이 진행(graceful)
    if not reports:
        return None
    blocks = [
        f"[시황 리포트 {i}]\n{format_market_outlook_context(entry)}"
        for i, entry in enumerate(reports, 1)
    ]
    return "\n\n".join(blocks)[:max_chars]


def _today_stamp_kst() -> str:
    """KST 오늘 날짜를 저장 date 포맷("YY.MM.DD")으로 — 네이버/저장 date 와 문자열 비교 가능.

    저장 `date`(예 "26.07.20")·프론트 `todayStampKST()`(Intl 서울 TZ)와 동일 포맷이라
    stale 판정을 사전순(zero-padded → 시간순) 문자열 비교로 할 수 있다.
    """
    return datetime.now(KST).strftime("%y.%m.%d")


def outlook_is_stale(today_stamp: str, *, store=None) -> bool:
    """저장된 최신 시황 작성일이 today_stamp 보다 오래됐으면(또는 없으면) True.

    - 최신(첫) `date` 가 없거나 today_stamp 미만 → True(수집 대상). 빈 store 도 True.
    - 문자열 비교: "YY.MM.DD" zero-padded 라 사전순 = 시간순(프로젝트 수명 내 동일 세기 가정).
    - **조회 실패는 크래시 없이 False**(수집 시도 안 함 — 안전한 no-op). 프론트 isOutlookStale 대응.
    """
    try:
        if store is None:
            from chat.market_outlook_store import default_store

            store = default_store()
        reports = store.list_reports() or []
    except Exception:
        return False  # 조회 실패는 stale 로 보지 않는다(불필요 수집 방지·크래시 금지)
    if not reports:
        return True
    latest = (reports[0] or {}).get("date")
    if not latest:
        return True
    return latest < today_stamp


def _reset_outlook_attempt() -> None:
    """테스트용 — 하루 1회 자동 수집 가드(`_LAST_OUTLOOK_ATTEMPT`) 전역 리셋."""
    global _LAST_OUTLOOK_ATTEMPT
    _LAST_OUTLOOK_ATTEMPT = None


def ensure_fresh_outlook(
    *,
    today_stamp: str | None = None,
    store=None,
    client=None,
    limit: int = 8,
    timeout: float = _OUTLOOK_COLLECT_TIMEOUT,
) -> str:
    """시장 질문 턴에서 저장 시황이 stale 이면 **그 턴에 동기 수집**한 뒤 상태 문자열 반환.

    반환 status(절대 예외를 내지 않는다 — 챗 흐름이 시황 수집으로 깨지지 않음, 전면 graceful):
      - "fresh"        : 이미 최신(no-op).
      - "collected"    : 동기 수집 완료(이번 턴부터 최신 컨텍스트 사용).
      - "attempted"    : 타임아웃 — 백그라운드 계속, 그 턴은 기존 저장분 사용(다음 질문부터 최신).
      - "skipped_guard": 오늘 이미 시도(하루 1회 가드).
      - "error"        : 수집/판정 실패(그 턴은 기존 저장분·있으면).

    하루 1회 가드(`_LAST_OUTLOOK_ATTEMPT`): 오늘 이미 시도했으면 재수집하지 않는다. **시도 전에
    가드를 세팅**해 실패해도 그날 재시도하지 않는다(프론트 `mo_autofetch_date` 가드 동형).
    """
    global _LAST_OUTLOOK_ATTEMPT
    try:
        stamp = today_stamp or _today_stamp_kst()
        if not outlook_is_stale(stamp, store=store):
            return "fresh"
        if _LAST_OUTLOOK_ATTEMPT == stamp:
            return "skipped_guard"
        _LAST_OUTLOOK_ATTEMPT = stamp  # 시도 전 가드 세팅(실패해도 그날 재시도 안 함)
    except Exception:
        return "error"

    import concurrent.futures as _f

    from chat import market_outlook_service

    ex = _f.ThreadPoolExecutor(max_workers=1)
    try:
        fut = ex.submit(
            market_outlook_service.fetch_and_summarize, limit=limit, client=client, store=store
        )
        fut.result(timeout=timeout)
        return "collected"
    except _f.TimeoutError:
        # 타임아웃 — 백그라운드 스레드는 계속 수집(shutdown wait=False 로 블록 안 함).
        _log.warning("ensure_fresh_outlook: collection timed out after %.0fs (background continues)", timeout)
        return "attempted"
    except Exception as e:  # noqa: BLE001 — 전면 graceful(수집 실패로 챗이 깨지지 않음)
        _log.warning("ensure_fresh_outlook: collection failed: %s", e)
        return "error"
    finally:
        # 성공/에러면 스레드가 이미 끝나 즉시 정리, 타임아웃이면 wait=False 로 백그라운드 지속.
        ex.shutdown(wait=False)


def summarize_market_outlook(text: str, meta: dict, *, client=None) -> dict:
    """시황 리포트 원문 → {summary|None, validation_failed}. 항상 dict(크래시 없음).

    빈 텍스트·검증 실패·OpenAI 예외는 validation_failed=True(폴백).
    """
    # 빈 원문(추출 실패 PDF 등) → LLM 미호출 폴백(비용 0·graceful).
    if not text or not text.strip():
        return wrap_failure(_FALLBACK_MESSAGE)
    if client is None:
        client = make_client()
    prompt = _build_summary_prompt(text, meta)
    # 생성→검증(1회 재시도 포함)은 공통 코어. 반환 포장도 공통 래퍼(shape SSOT — structured_summary).
    summary = generate_validated(client, prompt, MarketOutlookSummary)
    if summary is not None:
        return wrap_success(summary)
    return wrap_failure(_FALLBACK_MESSAGE)
