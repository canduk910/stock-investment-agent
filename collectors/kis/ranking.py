"""KIS 국내주식 순위 어댑터 — MCP 검증 시가총액 상위(market_cap, FHPST01740000).

시가총액 상위 종목 리스트(종목코드·종목명·현재가·등락률·시총)를 **1콜**로 반환한다 —
대순환 스크리너의 스캔 유니버스 확보용. 조회 전용(매매 아님).

⚠ **파라미터 키는 소문자**(MCP 확정 — 재무 API 대소문자 혼합 함정 선례처럼 임의 통일 금지,
`collectors/CLAUDE.md`). 순위 API는 라이브값이라 캐시 없음. real 전용 경향(순위 TR) — 실패는
호출측 graceful.
"""
from __future__ import annotations

from collectors.kis import normalize

API_PATH = "/uapi/domestic-stock/v1/ranking/market-cap"
TR_ID = "FHPST01740000"  # real/demo 공통 문자열(순위는 real 전용 경향 — 라이브 게이트로 확정)

# 시장 → fid_input_iscd (MCP 확정 허용값). 라우트가 사용자 market → iscd 매핑에 이 SSOT를 쓴다.
MARKET_ISCD = {"all": "0000", "kospi": "0001", "kosdaq": "1001", "kospi200": "2001"}


def market_cap_rank(client, iscd: str = "0000", market: str = "J") -> list[dict]:
    """시가총액 상위 종목 리스트 → [{ticker, name, rank, price, change_rate, market_cap}].

    iscd: 0000 전체 / 0001 거래소(코스피) / 1001 코스닥 / 2001 코스피200 (MCP 검증 허용값).
    파라미터 키는 소문자 그대로 전달(KIS 파라미터 오류 방지).
    """
    params = {
        "fid_input_price_2": "",           # 가격 상한(공란=전체)
        "fid_cond_mrkt_div_code": market,  # J:KRX
        "fid_cond_scr_div_code": "20174",  # Unique key(고정)
        "fid_div_cls_code": "0",           # 0 전체 / 1 보통주 / 2 우선주
        "fid_input_iscd": iscd,
        "fid_trgt_cls_code": "0",          # 대상 전체
        "fid_trgt_exls_cls_code": "0",     # 제외 없음
        "fid_input_price_1": "",           # 가격 하한(공란=전체)
        "fid_vol_cnt": "",                 # 최소 거래량(공란=전체)
    }
    body = client.get(TR_ID, API_PATH, params)
    return normalize.normalize_market_cap_rank(body)
