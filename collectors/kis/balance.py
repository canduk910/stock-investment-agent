"""주식잔고조회 어댑터 — MCP 검증 inquire_balance(TTTC8434R/VTTC8434R).

현재가(prpr)를 포함하므로 캐시하지 않는다(원칙1) — cache 인자를 받지 않는다.
"""
from __future__ import annotations

from collectors.kis import normalize

API_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"
TR_ID = {"real": "TTTC8434R", "demo": "VTTC8434R"}


def inquire_balance(client, cano: str, acnt_prdt_cd: str) -> dict:
    """계좌 보유종목·요약 조회 → {holdings, summary}."""
    params = {
        "CANO": cano,
        "ACNT_PRDT_CD": acnt_prdt_cd,
        "AFHR_FLPR_YN": "N",
        "OFL_YN": "",
        "INQR_DVSN": "02",  # 종목별
        "UNPR_DVSN": "01",
        "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "00",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
    }
    body = client.get(TR_ID[client.env], API_PATH, params)
    return normalize.normalize_balance(body)
