"""현재 보고 있는 화면(잔고·관심종목·종목상세) 스냅샷을 서버가 조회해 컴팩트 텍스트로 만든다.

챗 세션 핀(`Session.view_context`)에 실려 후속 질문이 그 화면 데이터를 근거로 답하게 한다.
`build_view_context(kind, args)` 단일 진입 — 데이터 보유 kind(balance/watchlist/stock_report)만
**서버가 재조회**(프론트가 본문을 신뢰전송하지 않음 — 환각/조작 차단, report_context 선례 동일).

안전:
- 절대 예외를 올리지 않는다(전체 wrap). KIS/FRED 실패 → 짧은 "일시 조회 불가" 노트 또는 None.
- 첫 줄 `기준시각`(조회 시각) — 스냅샷 staleness 를 프롬프트가 환기(_VIEW_CONTEXT_HEADER).
- 여기 값은 LLM 이 '인용'만 하고 매수/매도 판정은 코드·게이트가 한다. 애널리스트 의견은 출처 귀속.
- 현재가 무캐시(원칙1): 스냅샷은 조회 시점 라이브(캐시 배선 없음).
"""
from __future__ import annotations

from datetime import datetime, timezone

# 데이터 보유 kind SSOT — 엔드포인트·프론트 매핑이 공유. 그 외(macro_dashboard·manage_watchlist)는
# 컨텍스트 없음(국면은 이미 시스템 프롬프트 ③④⑤, manage 는 제안 액션).
DATA_BEARING_KINDS = frozenset({"balance", "watchlist", "stock_report"})

_MAX_CHARS = 1500  # 전체 문자열 상한(프롬프트 예산 보호)
_TOP_HOLDINGS = 8
_TOP_WATCHLIST = 10
_TOP_ANALYST = 2
_BRIEF_CHARS = 80  # 애널리스트 요약 원라인 길이


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(v) -> str:
    """정수 천단위(결측/비수치는 '—')."""
    if v is None:
        return "—"
    try:
        return f"{float(v):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _pct(v) -> str:
    """소수 1자리(결측은 '—')."""
    if v is None:
        return "—"
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
        return "—"


def _signed_pct(v) -> str:
    """부호 있는 등락률(+/-, 결측은 '—')."""
    if v is None:
        return "—"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{'+' if n > 0 else ''}{n:.2f}"


def _safe_judgement():
    """국면 판정(build_judgement)을 안전 호출 — FRED 실패 시 None(진입게이트는 국면 없어도 graceful)."""
    try:
        from api.deps import build_judgement

        return build_judgement()
    except Exception:
        return None


def _stamp(body: str) -> str:
    """기준시각 헤더 + 본문, 전체 길이 상한 truncate."""
    return f"기준시각: {_now_iso()}\n{body}"[:_MAX_CHARS]


def _resolve(user, db):
    """뷰 컨텍스트용 KIS 해석(본인 등록키 → 공유 → env). ResolvedKis(client, cano, prdt, source).

    **테스트 monkeypatch 경계**. user/db 없으면(챗 인라인 P2 경로) env fallback — 자격증명 없으면
    NoKisCredentials 전파(호출측 try/except 가 "조회 불가"로 흡수).
    """
    from api.detail import resolve_kis_client

    return resolve_kis_client(user, db)


def build_view_context(
    kind: str, args: dict | None, *, user=None, db=None
) -> str | None:
    """현재 화면 kind → 컴팩트 스냅샷 텍스트, 또는 None(비데이터/조회불가). 절대 예외 없음.

    user/db 주입 시 **본인 KIS 키/계좌**로 조회(로그인 핀 경로, api/chat.py). 미주입 시 공유/env
    fallback(챗 인라인 P2 same-turn 경로) — P1 핀이 authoritative 라 허용.
    """
    args = args or {}
    try:
        if kind == "balance":
            return _balance_context(user, db)
        if kind == "watchlist":
            return _watchlist_context(user, db)
        if kind == "stock_report":
            return _stock_context(args, user, db)
        return None  # 비데이터 kind
    except Exception:
        return None  # 최종 방어 — 어떤 실패도 챗/엔드포인트를 깨지 않는다


def _balance_context(user, db) -> str:
    from collectors.kis import balance as kis_balance

    try:
        resolved = _resolve(user, db)  # 본인 계좌 → 공유 → env
        data = kis_balance.inquire_balance(resolved.client, resolved.cano, resolved.prdt)
    except Exception:
        return _stamp("[내 잔고] 잔고 일시 조회 불가")

    summary = data.get("summary") or {}
    holdings = data.get("holdings") or []
    lines = [
        "[내 잔고]",
        f"순자산 {_num(summary.get('net_asset'))}원 · 예수금 {_num(summary.get('deposit'))}원 · "
        f"총평가 {_num(summary.get('total_eval'))}원 · 평가손익 {_num(summary.get('pnl_amount'))}원",
    ]
    for h in holdings[:_TOP_HOLDINGS]:
        lines.append(
            f"- {h.get('name') or h.get('ticker')}({h.get('ticker')}): {_num(h.get('qty'))}주 · "
            f"평가 {_num(h.get('eval_amount'))}원 · 손익 {_num(h.get('pnl_amount'))}원"
            f"({_signed_pct(h.get('pnl_pct'))}%)"
        )
    if len(holdings) > _TOP_HOLDINGS:
        lines.append(f"…외 {len(holdings) - _TOP_HOLDINGS}종목")
    if not holdings:
        lines.append("보유 종목 없음")
    return _stamp("\n".join(lines))


def _watchlist_context(user, db) -> str:
    from watchlist.constants import DEFAULT_USER_ID, WATCHLIST_STORE_PATH
    from watchlist.service import build_watchlist_view
    from watchlist.store import JsonFileWatchlistStore

    try:
        store = JsonFileWatchlistStore(WATCHLIST_STORE_PATH)
        client = _resolve(user, db).client
        view = build_watchlist_view(store, DEFAULT_USER_ID, client, _safe_judgement())
    except Exception:
        return _stamp("[관심종목] 관심종목 일시 조회 불가")

    items = view.get("items") or []
    regime = view.get("regime") or {}
    lines = ["[관심종목]"]
    if regime.get("regime"):
        lines.append(f"현재 국면 {regime.get('regime')}")  # 국면은 현금비중만 관리(종목별 진입게이트 없음)
    if not items:
        lines.append("관심종목이 비어 있음")
    for it in items[:_TOP_WATCHLIST]:
        target = it.get("target_price")
        target_s = (
            f"목표가 {_num(target)}원[{it.get('target_status')}]"
            if target is not None
            else "목표가 미설정"
        )
        lines.append(
            f"- {it.get('stock_name') or it.get('ticker')}({it.get('ticker')}): "
            f"현재가 {_num(it.get('current_price'))}원({_signed_pct(it.get('change_rate'))}%) · "
            f"PER {_pct(it.get('per'))} · {target_s}"
        )
    if len(items) > _TOP_WATCHLIST:
        lines.append(f"…외 {len(items) - _TOP_WATCHLIST}종목")
    pf = view.get("partial_failure") or []
    if pf:
        lines.append(f"(일부 종목 시세 조회 실패: {', '.join(map(str, pf))})")
    return _stamp("\n".join(lines))


def _stock_context(args: dict, user, db) -> str | None:
    from api.deps import assert_valid_ticker

    ticker = (args.get("ticker") or "").strip()
    try:
        assert_valid_ticker(ticker)
    except Exception:
        return None  # 불량 ticker → 컨텍스트 없음(잘못된 조회 트리거 방지)

    from collectors.kis import inquire_price as ip
    from stock.summary import _pos_52w

    name = args.get("stock_name") or ticker
    lines = [f"[종목 상세 · {name}({ticker})]"]
    try:
        client = _resolve(user, db).client
        val = ip.inquire_price(client, ticker)
    except Exception:
        val = None
    if val:
        pos = _pos_52w(val.get("price"), val.get("week52_high"), val.get("week52_low"))
        lines.append(
            f"현재가 {_num(val.get('price'))}원({_signed_pct(val.get('change_rate'))}%) · "
            f"PER {_pct(val.get('per'))} · PBR {_pct(val.get('pbr'))} · 52주위치 {_pct(pos)}%"
        )
    else:
        lines.append("종목 시세 일시 조회 불가")

    # 애널리스트 top-2 원라인(0 KIS) — '리포트가 밝힌 의견' 출처 귀속(에이전트 판정 아님).
    try:
        from chat.analyst_store import default_store

        entries = default_store().list_reports(ticker)[:_TOP_ANALYST]
    except Exception:
        entries = []
    if entries:
        lines.append("(아래는 각 증권사 리포트가 밝힌 의견 — 에이전트 판정 아님)")
        for e in entries:
            s = e.get("summary") or {}
            broker = s.get("증권사") or e.get("broker") or "증권사"
            opinion = s.get("투자의견") or "의견 명시 없음"
            target = s.get("목표주가") or "목표가 없음"
            brief = (s.get("요약") or "")[:_BRIEF_CHARS]
            lines.append(f"- [{broker}] 의견 {opinion} · 목표가 {target} — {brief}")
    return _stamp("\n".join(lines))
