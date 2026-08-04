"""보통주 유니버스 필터(순수) — 보통주 통과 / 우선주·ETF·ETN·스팩·리츠 제외.

판정=순수 코드 규칙(코드 끝자리 + 이름 휴리스틱), 네트워크 0. 스펙(팀리드 지시) 경계 잠금.
"""
from __future__ import annotations

import pytest

from stock.universe import common_stocks, is_common_stock


def _s(ticker, name, market="KOSPI"):
    # sec_group 없는(구 캐시·파싱실패) 행 → 이름 휴리스틱 폴백 경로.
    return {"ticker": ticker, "name": name, "market": market}


def _sg(ticker, name, sec, market="KOSPI"):
    # sec_group 있는 행 → 그룹코드 결정적 필터 경로.
    return {"ticker": ticker, "name": name, "market": market, "sec_group": sec}


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


# ── 증권그룹구분코드 결정적 필터 (sec_group 있으면 이름 휴리스틱보다 우선) ────────

def test_sec_group_st_passes():
    # ST(주권) + 끝자리 0 → 통과(결정적).
    assert is_common_stock(_sg("005930", "삼성전자", "ST")) is True
    assert is_common_stock(_sg("247540", "에코프로비엠", "ST", "KOSDAQ")) is True


def test_sec_group_etf_etn_reit_excluded_deterministically():
    # ETF/ETN/리츠는 코드 끝자리 0이어도 그룹코드로 결정적 제외(이름 무관).
    assert is_common_stock(_sg("069500", "KODEX 200", "EF")) is False
    assert is_common_stock(_sg("530031", "삼성 레버리지 WTI원유 선물 ETN", "EN")) is False
    assert is_common_stock(_sg("330590", "롯데리츠", "RT")) is False


def test_sec_group_leaked_brand_etf_now_excluded():
    # ★실측 누수건: 신생 브랜드 ETF '1Q 미국배당TOP30'(EF)가 이제 그룹코드로 제외.
    #   이름 휴리스틱엔 '1Q' 브랜드가 없어 통과했던 것(sec_group=None 폴백이면 아래 대조).
    assert is_common_stock(_sg("0004G0", "1Q 미국배당TOP30", "EF")) is False
    assert is_common_stock(_sg("0005G0", "IBK K-AI반도체코어테크", "EF")) is False
    # 폴백(그룹코드 없음)에선 브랜드 미등록이라 누수됐음을 대조로 고정.
    assert is_common_stock(_s("0004G0", "1Q 미국배당TOP30")) is True


def test_sec_group_foreign_dr_fund_excluded():
    # 외국주권(FS)·주식예탁증서(DR)·투자회사(MF)·인프라(IF)·펀드클래스(PF) → 전부 제외(ST 아님).
    assert is_common_stock(_sg("900100", "동양생명보험(SDR)", "FS")) is False
    assert is_common_stock(_sg("900110", "이스트아시아홀딩스", "DR")) is False
    assert is_common_stock(_sg("094800", "맵스리얼티1", "MF")) is False
    assert is_common_stock(_sg("088980", "맥쿼리인프라", "IF")) is False
    assert is_common_stock(_sg("010660", "화천기공", "PF")) is False


def test_sec_group_preferred_still_excluded_by_code_even_if_st():
    # 우선주도 법적으로 ST(주권)지만 코드 끝자리≠0 규칙으로 계속 제외.
    assert is_common_stock(_sg("005935", "삼성전자우", "ST")) is False
    assert is_common_stock(_sg("00499K", "롯데지주우B", "ST")) is False


def test_sec_group_spac_excluded_by_name_backstop_even_if_st():
    # 스팩(SPAC)은 그룹코드가 ST(주권)라 그룹필터로 안 잡힘 → 이름 '스팩' backstop 으로 제외.
    assert is_common_stock(_sg("0004Y0", "디비금융제14호스팩", "ST")) is False
    assert is_common_stock(_sg("0037T0", "KB제32호스팩", "ST")) is False


def test_sec_group_recovers_name_heuristic_false_positive():
    # ★그룹코드의 우월성: 이름 휴리스틱의 '리츠' 부분일치가 잘못 제외하던 정식주(ST)를 복구.
    #   메리츠금융지주·블리츠웨이엔터테인먼트 = 실측 오제외건.
    assert is_common_stock(_sg("138040", "메리츠금융지주", "ST")) is True
    assert is_common_stock(_sg("369370", "블리츠웨이엔터테인먼트", "ST", "KOSDAQ")) is True
    # 폴백(그룹코드 없음)에선 '리츠' 부분일치로 오제외됨을 대조로 고정(=현행 버그).
    assert is_common_stock(_s("138040", "메리츠금융지주")) is False


def test_common_stocks_mixed_master_with_sec_group():
    master = [
        _sg("005930", "삼성전자", "ST"),
        _sg("005935", "삼성전자우", "ST"),        # 우선주(코드) 제외
        _sg("069500", "KODEX 200", "EF"),         # ETF 제외
        _sg("0004G0", "1Q 미국배당TOP30", "EF"),  # 브랜드 누수 → 이제 제외
        _sg("000660", "SK하이닉스", "ST"),
        _sg("330590", "롯데리츠", "RT"),           # 리츠 제외
        _sg("0004Y0", "디비금융제14호스팩", "ST"), # 스팩(이름 backstop) 제외
        _sg("138040", "메리츠금융지주", "ST"),      # '리츠' 오탐 복구 → 통과
    ]
    out = common_stocks(master)
    assert [s["ticker"] for s in out] == ["005930", "000660", "138040"]
    # 필드 그대로 보존(sec_group 포함).
    assert out[0]["sec_group"] == "ST"


def test_common_stocks_mixed_sec_group_and_fallback():
    # sec_group 있는 행은 결정적, 없는 행은 이름 휴리스틱 폴백 — 한 마스터에 혼재 가능(캐시 전환기).
    master = [
        _sg("069500", "KODEX 200", "EF"),  # 결정적 제외
        _s("102110", "TIGER 200"),          # 폴백 브랜드 제외
        _sg("005930", "삼성전자", "ST"),    # 결정적 통과
        _s("000660", "SK하이닉스"),          # 폴백 통과
    ]
    assert [s["ticker"] for s in common_stocks(master)] == ["005930", "000660"]


# ── 라이브(실 마스터) 그룹코드 필터 무결성 ────────────────────────────────────

@pytest.mark.live
def test_live_common_stocks_no_etf_leak_and_scale():
    """실 마스터 → common_stocks: ETF/리츠 누수 0·대표 보통주 포함·규모 로깅."""
    from collectors.stock_master import _fetch_all, load_stock_master

    master = _fetch_all()  # fresh(캐시 무시) — sec_group 채워짐
    out = common_stocks(master)
    by = {r["ticker"] for r in out}
    names = {r["name"] for r in out}
    # 대표 보통주 포함.
    assert "005930" in by  # 삼성전자
    assert "000660" in by  # SK하이닉스
    # ETF/리츠/누수건 제외.
    assert "069500" not in by  # KODEX 200
    assert "330590" not in by  # 롯데리츠
    assert "1Q 미국배당TOP30" not in names  # 실측 누수건
    # 비-ST 그룹코드가 결과에 하나도 없어야(결정적 필터 무결).
    assert all(r.get("sec_group") in (None, "ST") for r in out)
    # 스팩 이름 backstop.
    assert not any("스팩" in r["name"] for r in out)
    print(f"[live universe] master={len(master)} common={len(out)} "
          f"KOSPI={sum(1 for r in out if r['market'] == 'KOSPI')} "
          f"KOSDAQ={sum(1 for r in out if r['market'] == 'KOSDAQ')}")
