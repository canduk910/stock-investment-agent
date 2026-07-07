"""종목추정실적 normalize 테스트 — 공식 스펙(행=지표, 열=연도, output4 동적매핑) 고정.

삼성전자 실측 응답 축약(라이브 프로브 기반): output3 r1=EPS·r3=PER(÷10),
output4 의 'E' 접미사로 실적/추정 구분.
"""
from __future__ import annotations

from collectors.kis.normalize import normalize_estimate_perform

_BODY = {
    "output1": {"name1": "김한국", "estdate": "20260630", "rcmd_name": "매수", "item_kor_nm": "삼성전자"},
    "output2": [
        {"data1": "2589355", "data2": "3008709", "data3": "3336059", "data4": "7079979", "data5": "9301340"},  # 매출
        {"data1": "-143", "data2": "162", "data3": "109", "data4": "1122", "data5": "314"},  # 매출증감
        {"data1": "65670", "data2": "327260", "data3": "436011", "data4": "3767778", "data5": "5734259"},  # 영업
        {"data1": "-849", "data2": "3983", "data3": "332", "data4": "7641", "data5": "522"},  # 영업증감
        {"data1": "144734", "data2": "336214", "data3": "442610", "data4": "2937723", "data5": "4272591"},  # 순익
        {"data1": "-736", "data2": "1323", "data3": "316", "data4": "5637", "data5": "454"},  # 순익증감
    ],
    "output3": [
        {"data1": "452335", "data2": "753568", "data3": "905276", "data4": "4306887", "data5": "6298333"},  # EBITDA
        {"data1": "21310", "data2": "49500", "data3": "66050", "data4": "443617", "data5": "642957"},  # EPS
        {"data1": "-736", "data2": "1323", "data3": "334", "data4": "5716", "data5": "449"},  # EPS증감
        {"data1": "368", "data2": "107", "data3": "182", "data4": "61", "data5": "42"},  # PER
    ],
    "output4": [
        {"dt": "2023.12"}, {"dt": "2024.12"}, {"dt": "2025.12"}, {"dt": "2026.12E"}, {"dt": "2027.12E"},
    ],
}


def test_periods_mapped_by_output4():
    r = normalize_estimate_perform(_BODY)
    assert len(r["periods"]) == 5
    labels = [p["period"] for p in r["periods"]]
    assert labels == ["202312", "202412", "202512", "202612", "202712"]


def test_estimate_flag_from_E_suffix():
    r = normalize_estimate_perform(_BODY)
    flags = [p["is_estimate"] for p in r["periods"]]
    assert flags == [False, False, False, True, True]  # 2026.12E·2027.12E 만 추정


def test_eps_and_per_scaled_by_10():
    r = normalize_estimate_perform(_BODY)
    p2025 = r["periods"][2]
    assert p2025["eps"] == 6605.0  # 66050 ÷ 10 (inquire_price eps 6564 와 근사)
    assert p2025["per"] == 18.2    # 182 ÷ 10
    p2027 = r["periods"][4]
    assert p2027["eps"] == 64295.7  # 642957 ÷ 10 (예측 EPS)
    assert p2027["per"] == 4.2      # 42 ÷ 10


def test_income_rows_mapped():
    r = normalize_estimate_perform(_BODY)
    p2026 = r["periods"][3]
    assert p2026["revenue"] == 7079979.0       # output2 r0
    assert p2026["operating_income"] == 3767778.0  # output2 r2
    assert p2026["net_income"] == 2937723.0    # output2 r4


def test_header_fields():
    r = normalize_estimate_perform(_BODY)
    assert r["analyst"] == "김한국"
    assert r["est_date"] == "20260630"
    assert r["recommendation"] == "매수"


def test_uncovered_stock_empty_periods():
    # 리서치 미대상: output4 없음 → periods=[] (graceful, KeyError 금지)
    r = normalize_estimate_perform({"output1": {}, "output2": [], "output3": [], "output4": []})
    assert r["periods"] == []
    assert r["analyst"] is None


def test_missing_output3_rows_graceful():
    # SK하이닉스형: output3 가 3행뿐(PER 행 r3 부재) → per None, eps 는 r1 에서 정상
    body = {**_BODY, "output3": _BODY["output3"][:2]}  # r0,r1 만
    r = normalize_estimate_perform(body)
    assert r["periods"][2]["eps"] == 6605.0
    assert r["periods"][2]["per"] is None  # r3 없음 → None
