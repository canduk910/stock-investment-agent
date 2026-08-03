"""보통주 유니버스 필터(순수) — 보통주 통과 / 우선주·ETF·ETN·스팩·리츠 제외.

판정=순수 코드 규칙(코드 끝자리 + 이름 휴리스틱), 네트워크 0. 스펙(팀리드 지시) 경계 잠금.
"""
from __future__ import annotations

from stock.universe import common_stocks, is_common_stock


def _s(ticker, name, market="KOSPI"):
    return {"ticker": ticker, "name": name, "market": market}


# ── 보통주 통과 ───────────────────────────────────────────────────────────────

def test_common_stocks_pass_kospi_and_kosdaq():
    # 코드 끝자리 0 + 보통주 이름 → 통과(코스피·코스닥 모두)
    assert is_common_stock(_s("005930", "삼성전자", "KOSPI")) is True
    assert is_common_stock(_s("000660", "SK하이닉스", "KOSPI")) is True
    assert is_common_stock(_s("035720", "카카오", "KOSPI")) is True
    assert is_common_stock(_s("247540", "에코프로비엠", "KOSDAQ")) is True


# ── 우선주 제외(코드 끝자리 ≠ 0) ──────────────────────────────────────────────

def test_preferred_stock_excluded_by_code_last_digit():
    assert is_common_stock(_s("005935", "삼성전자우")) is False   # 끝자리 5
    assert is_common_stock(_s("005385", "현대차2우B")) is False   # 끝자리 5
    assert is_common_stock(_s("00499K", "롯데지주우B")) is False  # 끝자리 K(신형우선주)


# ── ETF/ETN 제외(코드 끝 0 이어도 이름 브랜드/키워드로) ───────────────────────

def test_etf_excluded_by_brand_even_if_code_ends_zero():
    # 069500 KODEX 200 은 코드 끝자리 0(코드규칙 통과)이지만 브랜드로 제외 → 2층 필터 검증
    assert is_common_stock(_s("069500", "KODEX 200")) is False
    assert is_common_stock(_s("102110", "TIGER 200")) is False
    assert is_common_stock(_s("278530", "KODEX 200TR")) is False
    # 공백 없이 브랜드 접두(startswith)
    assert is_common_stock(_s("192090", "TIGER차이나전기차SOLACTIVE")) is False


def test_etn_leverage_inverse_spac_reit_excluded_by_keyword():
    assert is_common_stock(_s("530031", "삼성 레버리지 WTI원유 선물 ETN")) is False
    assert is_common_stock(_s("580011", "신한 인버스 2X 나스닥 ETN")) is False
    assert is_common_stock(_s("438330", "에스케이증권제10호스팩")) is False
    assert is_common_stock(_s("330590", "롯데리츠")) is False
    assert is_common_stock(_s("130680", "KOSEF 국고채10년 채권형")) is False


def test_new_manager_etf_brands_and_active_excluded():
    # 신생/소형 운용사 ETF 브랜드 누수 방어
    assert is_common_stock(_s("471040", "KIWOOM 미국S&P500")) is False
    assert is_common_stock(_s("475050", "마이티 200TR")) is False
    assert is_common_stock(_s("500001", "TRUSTON 주주가치액티브")) is False
    assert is_common_stock(_s("500002", "에셋플러스 글로벌일등기업포커스10")) is False
    # '액티브' 키워드(브랜드 무관)
    assert is_common_stock(_s("500003", "BNK 카카오그룹포커스액티브")) is False
    # 공백 뒤에만 매칭하는 브랜드 — ETF 는 제외, 동명 접두 정식 종목은 보존
    assert is_common_stock(_s("500004", "BNK 스마트카")) is False
    assert is_common_stock(_s("138930", "BNK금융지주")) is True   # 정식 종목(오탐 없어야)
    assert is_common_stock(_s("192080", "TIME 미국S&P500")) is False


def test_legit_stocks_not_over_filtered():
    # 브랜드 접두·키워드와 겹치는 정식 종목이 살아남아야(과필터 방지)
    assert is_common_stock(_s("005070", "코스모신소재")) is True      # code endswith 0
    assert is_common_stock(_s("005160", "동국산업")) is True
    assert is_common_stock(_s("007700", "F&F홀딩스")) is True
    assert is_common_stock(_s("037560", "LG헬로비전")) is True
    assert is_common_stock(_s("001260", "남광토건")) is True
    assert is_common_stock(_s("005190", "동성제약")) is True
    assert is_common_stock(_s("020000", "한섬")) is True


# ── 리스트 필터 + 순서 보존 ───────────────────────────────────────────────────

def test_common_stocks_filters_and_preserves_order():
    master = [
        _s("005930", "삼성전자"),
        _s("005935", "삼성전자우"),      # 우선주 제외
        _s("069500", "KODEX 200"),       # ETF 제외
        _s("000660", "SK하이닉스"),
        _s("330590", "롯데리츠"),         # 리츠 제외
        _s("247540", "에코프로비엠", "KOSDAQ"),
    ]
    out = common_stocks(master)
    assert [s["ticker"] for s in out] == ["005930", "000660", "247540"]
    # 필드 그대로 보존
    assert out[2] == {"ticker": "247540", "name": "에코프로비엠", "market": "KOSDAQ"}


def test_common_stocks_graceful_on_empty_and_bad_rows():
    assert common_stocks([]) == []
    assert common_stocks(None) == []  # None 방어
    # 이름 없는 행·짧은 코드는 제외(크래시 없음)
    assert common_stocks([_s("00593", "짧은코드"), _s("005930", "")]) == []
