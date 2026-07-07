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


def _output_rows(body: dict) -> list:
    """output 섹션을 항상 리스트로 정규화.

    KIS 재무 API(income/ratio)는 행이 여러 개면 리스트, 하나면 단일 dict 로 오는
    변형이 있다(MCP 예제 finance_income_statement 가 `if not isinstance(list):
    [output]` 로 방어). 빈/부재는 [] (신규상장 재무 결측 graceful).
    """
    section = body.get("output")
    if isinstance(section, list):
        return section
    if isinstance(section, dict):
        return [section]
    return []


def normalize_price(body: dict) -> dict:
    """주식현재가 시세(FHKST01010100) → 라이브 밸류에이션 dict(단일 output).

    현재가·PER·PBR·EPS·BPS·52주 고저·시가총액 등 전부 실시간 값이므로 캐시 금지
    (원칙1). raw KIS 명(stck_prpr 등)을 노출하지 않고 clean snake 로 통일 —
    엔진(stock.summary)이 이 이름을 소비한다. as_of 는 이 응답에 조회시점 날짜
    필드가 없어(실시간 시세) None 으로 둔다(키는 계약상 유지).
    """
    o = body.get("output") or {}
    return {
        "ticker": pick(o, "stck_shrn_iscd"),
        "price": to_float(pick(o, "stck_prpr")),
        "change_rate": to_float(pick(o, "prdy_ctrt")),
        "per": to_float(pick(o, "per")),
        "pbr": to_float(pick(o, "pbr")),
        "eps": to_float(pick(o, "eps")),
        "bps": to_float(pick(o, "bps")),
        "week52_high": to_float(pick(o, "w52_hgpr")),
        "week52_low": to_float(pick(o, "w52_lwpr")),
        "market_cap": to_float(pick(o, "hts_avls")),
        "as_of": None,
    }


def normalize_income_statement(body: dict) -> list[dict]:
    """국내주식 손익계산서(FHKST66430200) → 연도별 [{period, revenue, operating_income, net_income}].

    period=stac_yymm(결산 년월). 순서는 KIS 응답 그대로(정렬은 엔진 stock.summary 가
    stac_yymm 오름차순으로 수행 — 부호역전 방지). 빈 output → [].
    """
    rows = []
    for row in _output_rows(body):
        rows.append({
            "period": pick(row, "stac_yymm"),
            "revenue": to_float(pick(row, "sale_account")),
            "operating_income": to_float(pick(row, "bsop_prti")),
            "net_income": to_float(pick(row, "thtr_ntin")),
        })
    return rows


def normalize_financial_ratio(body: dict) -> list[dict]:
    """국내주식 재무비율(FHKST66430300) → 연도별 [{period, eps, bps, roe}].

    roe 는 roe_val 필드에서 취득. 빈 output → [].
    """
    rows = []
    for row in _output_rows(body):
        rows.append({
            "period": pick(row, "stac_yymm"),
            "eps": to_float(pick(row, "eps")),
            "bps": to_float(pick(row, "bps")),
            "roe": to_float(pick(row, "roe_val")),
        })
    return rows


# 종목추정실적(estimate_perform) 응답 구조 — 행=지표, 열 data1~5=결산연도(output4 가 라벨).
_EST_EPS_SCALE = 10.0  # output3 EPS·PER 은 0.1 스케일(라이브 검증: 2025 EPS×10 ≈ inquire_price eps)


def _est_col(section: list, row_idx: int, col_idx: int):
    """output{2,3}[row_idx].data{col_idx+1} → float. 행/열 부재 시 None(KeyError 금지)."""
    if not isinstance(section, list) or row_idx >= len(section):
        return None
    return to_float(pick(section[row_idx], f"data{col_idx + 1}"))


def normalize_estimate_perform(body: dict) -> dict:
    """종목추정실적(HHKST668300C0) → {analyst, est_date, recommendation, periods:[...]}.

    output4 로 각 열(data1~5)의 결산년월·실적/추정('E')을 동적 매핑한다(열 위치 하드코딩 금지).
    output2: r0 매출·r2 영업이익·r4 순이익(억원). output3: r1 EPS·r3 PER(÷_EST_EPS_SCALE).
    리서치 미대상 종목은 output4 가 비어 periods=[] (graceful).
    """
    o1 = body.get("output1") or {}
    o2 = body.get("output2") or []
    o3 = body.get("output3") or []
    o4 = body.get("output4") or []

    periods = []
    for i, dtrow in enumerate(o4):
        dt = pick(dtrow, "dt")  # 예 "2026.12E"
        if not dt:
            continue
        label = str(dt).upper().replace("E", "").replace(".", "").strip()  # "202612"
        eps_raw = _est_col(o3, 1, i)
        per_raw = _est_col(o3, 3, i)
        periods.append({
            "period": label,
            "is_estimate": "E" in str(dt).upper(),
            "revenue": _est_col(o2, 0, i),
            "operating_income": _est_col(o2, 2, i),
            "net_income": _est_col(o2, 4, i),
            "eps": eps_raw / _EST_EPS_SCALE if eps_raw is not None else None,
            "per": per_raw / _EST_EPS_SCALE if per_raw is not None else None,
        })

    return {
        "analyst": pick(o1, "name1"),
        "est_date": pick(o1, "estdate"),
        "recommendation": pick(o1, "rcmd_name"),
        "periods": periods,
    }
