"""워치리스트(모듈 3) — 신규 진입 후보 감시. plan §3·WEEK 10.

모듈 2(stock.summary)의 분석 엔진을 재사용하되 질문 방향만 "비중 조정"→"신규 진입"으로
바꾼다. 진입신호는 regime_gate 를 그대로 소비(regime-agnostic), 저장은 durable 사용자 상태.
"""
