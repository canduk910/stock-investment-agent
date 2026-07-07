"""국내주식 종목추정실적 어댑터 — MCP 공식 스펙 검증 estimate_perform(HHKST668300C0).

리서치본부 월간 추정(거래소·코스닥 ~160개 종목 한정). 실적연도(Actual)와
추정연도(Estimate)를 한 응답에 준다 — 예측 PER/EPS 의 원천.

## 응답 구조 (공식 스펙 — 행=지표, 열 data1~5=결산연도)
- output1: 종목 헤더(애널리스트명 name1, 추정기준일 estdate, 투자의견 rcmd_name).
  ⚠ 스펙의 한글 컬럼 라벨은 ELW 템플릿 복붙 오류라 신뢰 불가 — 실제 필드명으로 읽는다.
- output2(6행): 추정 손익. r0 매출·r1 매출증감·r2 영업이익·r3 영업이익증감·r4 순이익·r5 순이익증감.
- output3(≤8행): 투자지표. r0 EBITDA·r1 EPS·r2 EPS증감·r3 PER·r4 EV/EBITDA·r5 ROE·r6 부채비율·r7 이자보상.
  (PBR 없음. EPS·PER 은 0.1 스케일 → /10. 라이브 교차검증: 2025 EPS×10 ≈ inquire_price eps.)
- output4: output4[i].dt 가 data(i+1) 열의 결산년월 라벨. 접미사 'E' 유무로 실적/추정 구분
  (열 위치는 매년 이동 → 하드코딩 금지, output4 로 동적 매핑).

모의(demo) 미지원·real 전용. SHT_CD 는 앞자리 'A' 없이 6자리 숫자.
"""
from __future__ import annotations

from collectors.kis import normalize

API_PATH = "/uapi/domestic-stock/v1/quotations/estimate-perform"
TR_ID = "HHKST668300C0"


def estimate_perform(client, ticker: str) -> dict:
    """종목추정실적 조회 → {analyst, est_date, recommendation, periods:[...]}.

    periods 각 원소: {period, is_estimate, revenue, operating_income, net_income, eps, per}.
    리서치 미대상 종목은 빈 periods → 소비자가 "예측 미제공"으로 graceful 처리.
    """
    body = client.get(TR_ID, API_PATH, {"SHT_CD": ticker})
    return normalize.normalize_estimate_perform(body)
