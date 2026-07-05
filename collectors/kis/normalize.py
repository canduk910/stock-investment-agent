"""KIS 응답 정규화 규칙 — plan §2.

KIS는 암호 같은 필드명(stck_prpr)과 숫자 문자열("70,500", "-1.23")을 준다.
여기서 snake_case 정규화 dict로 변환한다:
- 숫자 문자열 → float/int 코어스(부호·콤마 처리)
- 없는 필드는 None (KeyError 금지)

각 normalize_* 는 client.get이 돌려준 raw JSON body(dict)를 받는다.
현재가/호가 API는 output1(호가)·output2(예상체결)로 나뉘어 오므로 병합해서 읽는다.
"""
from __future__ import annotations

from typing import Any


def pick(d: dict | None, key: str) -> Any:
    """dict에서 키를 None-safe하게 조회 (KeyError 금지)."""
    if not isinstance(d, dict):
        return None
    return d.get(key)


def to_float(value: Any) -> float | None:
    """숫자 문자열(부호·콤마 포함)을 float로. 빈 값/None은 None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").strip()
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_int(value: Any) -> int | None:
    """숫자 문자열을 int로. 소수부가 있으면 버림(float 경유)."""
    f = to_float(value)
    return int(f) if f is not None else None


def _merge_outputs(body: dict, *keys: str) -> dict:
    """여러 output 섹션을 하나로 병합 (뒤 섹션이 우선). 호가/예상체결 통합용."""
    merged: dict = {}
    for key in keys:
        section = body.get(key)
        if isinstance(section, dict):
            merged.update({k: v for k, v in section.items() if v not in (None, "")})
    return merged


def normalize_balance(body: dict) -> dict:
    """주식잔고조회 → {holdings:[...], summary:{...}}."""
    holdings = []
    for row in body.get("output1", []) or []:
        holdings.append({
            "ticker": pick(row, "pdno"),
            "name": pick(row, "prdt_name"),
            "qty": to_int(pick(row, "hldg_qty")),
            "avg_price": to_float(pick(row, "pchs_avg_pric")),
            "current_price": to_float(pick(row, "prpr")),
            "eval_amount": to_float(pick(row, "evlu_amt")),
            "pnl_amount": to_float(pick(row, "evlu_pfls_amt")),
            "pnl_pct": to_float(pick(row, "evlu_pfls_rt")),
        })

    output2 = body.get("output2", []) or []
    s = output2[0] if output2 else {}
    summary = {
        "deposit": to_float(pick(s, "dnca_tot_amt")),
        "purchase_amount": to_float(pick(s, "pchs_amt_smtl_amt")),
        "eval_amount": to_float(pick(s, "evlu_amt_smtl_amt")),
        "pnl_amount": to_float(pick(s, "evlu_pfls_smtl_amt")),
        "total_eval": to_float(pick(s, "tot_evlu_amt")),
        "net_asset": to_float(pick(s, "nass_amt")),
    }
    return {"holdings": holdings, "summary": summary}


def normalize_quote(body: dict) -> dict:
    """주식현재가 호가/예상체결 → {ticker, price, change_rate, ask, bid, as_of}.

    output1(호가)·output2(예상체결)를 병합해 현재가/호가를 안전하게 읽는다.
    change_rate는 이 API가 제공하는 예상체결 전일대비율(antc_cntg_prdy_ctrt).
    """
    m = _merge_outputs(body, "output2", "output1")
    return {
        "ticker": pick(m, "stck_shrn_iscd"),
        "price": to_float(pick(m, "stck_prpr")),
        "change_rate": to_float(pick(m, "antc_cntg_prdy_ctrt")),
        "ask": to_float(pick(m, "askp1")),
        "bid": to_float(pick(m, "bidp1")),
        "as_of": pick(m, "aspr_acpt_hour"),
    }


def normalize_daily_chart(body: dict) -> dict:
    """국내주식기간별시세 → {ticker, candles:[{date,open,high,low,close,volume}]}."""
    summary = body.get("output1") or {}
    ticker = pick(summary, "stck_shrn_iscd")

    candles = []
    for row in body.get("output2", []) or []:
        candles.append({
            "date": pick(row, "stck_bsop_date"),
            "open": to_float(pick(row, "stck_oprc")),
            "high": to_float(pick(row, "stck_hgpr")),
            "low": to_float(pick(row, "stck_lwpr")),
            "close": to_float(pick(row, "stck_clpr")),
            "volume": to_int(pick(row, "acml_vol")),
        })
    return {"ticker": ticker, "candles": candles}


def normalize_multiprice(body: dict) -> dict:
    """관심종목(멀티종목) 시세 → {items:[{ticker, price, change_rate}]}.

    응답 필드명은 라이브 실응답으로 확정: inter_shrn_iscd(종목코드) /
    inter2_prpr(현재가) / prdy_ctrt(전일대비율). 필드 부재 시 None(graceful).
    """
    items = []
    for row in body.get("output", []) or []:
        items.append({
            "ticker": pick(row, "inter_shrn_iscd"),
            "price": to_float(pick(row, "inter2_prpr")),
            "change_rate": to_float(pick(row, "prdy_ctrt")),
        })
    return {"items": items}


def normalize_sector_index(body: dict, index_code: str) -> dict:
    """국내업종 현재지수 → {index_code, price, change, change_rate, volume, advancing, declining, unchanged}.

    지수 현재가(bstp_nmix_prpr)는 실시간 값이므로 캐시하지 않는다.
    """
    o = body.get("output") or {}
    return {
        "index_code": index_code,
        "price": to_float(pick(o, "bstp_nmix_prpr")),
        "change": to_float(pick(o, "bstp_nmix_prdy_vrss")),
        "change_rate": to_float(pick(o, "bstp_nmix_prdy_ctrt")),
        "volume": to_int(pick(o, "acml_vol")),
        "advancing": to_int(pick(o, "ascn_issu_cnt")),
        "declining": to_int(pick(o, "down_issu_cnt")),
        "unchanged": to_int(pick(o, "stnr_issu_cnt")),
    }


def normalize_stock_info(body: dict) -> dict:
    """주식기본조회 → {ticker, name, sector, listed_shares, capital, par_value, security_group}."""
    o = body.get("output") or {}
    return {
        "ticker": pick(o, "pdno"),
        "name": pick(o, "prdt_name"),
        "sector": pick(o, "idx_bztp_scls_cd_name"),
        "listed_shares": to_int(pick(o, "lstg_stqt")),
        "capital": to_float(pick(o, "cpta")),
        "par_value": to_float(pick(o, "papr")),
        "security_group": pick(o, "scty_grp_id_cd"),
    }
