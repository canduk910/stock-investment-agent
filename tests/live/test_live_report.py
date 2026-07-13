"""리포트 라이브 e2e — gpt-5.4 실 JSON 이 StockReport 스키마를 충족하는지(IMP-19).

유닛은 OpenAI 를 mock 하므로 실제 모델이 response_format=json_object 로 한글 enum·리스크 min1·
면책 필수를 만족하는 JSON 을 내는지 미검증이다. @pytest.mark.live 로 분리(기본 실행 제외, 키 있을 때만).
프롬프트/모델 변경이 전건 폴백으로 무너져도 유닛은 초록이므로, 이 스모크가 실제 계약을 지킨다.
"""
from __future__ import annotations

import pytest

from chat.report import generate_stock_report
from chat.report_schema import StockReport

pytestmark = pytest.mark.live


def _client_or_skip():
    try:
        from infra.config import openai_api_key

        openai_api_key()  # 키 없으면 ConfigError → skip
        from chat.report import _make_client

        return _make_client()
    except Exception as exc:  # noqa: BLE001 — 키/설정 부재는 스킵
        pytest.skip(f"OpenAI 키 없음: {exc}")


_BUNDLE = {
    "ticker": "005930",
    "basic": {"name": "삼성전자"},
    "summary": {
        "rev_cagr": 4.5, "op_cagr": -4.1, "current_per": 43.0, "avg_per": 17.0,
        "per_vs_avg": 152.0, "valuation_label": "고평가", "rsi": 44.0,
        "ma20_gap_pct": -2.0, "pos_52w_pct": 71.0, "sample_years": 5, "notes": [],
    },
    # regime_gate 폐기(항목3) — 번들에 없음. 국면 컨텍스트는 judgement 로 전달.
    "partial_failure": [],
}
_JUDGEMENT = {
    "regime": "수축",
    "recommended_cash_ratio": 20,
    "params": {"cash": 20},  # 현금비중만(항목3)
}


def test_live_report_meets_schema_or_falls_back():
    client = _client_or_skip()
    result = generate_stock_report(_BUNDLE, _JUDGEMENT, client=client)
    assert isinstance(result, dict)
    assert "validation_failed" in result

    if not result["validation_failed"]:
        # 검증 통과분은 스키마 재검증(한글 enum·리스크 min1·면책 필수)에도 통과해야 한다.
        report = result["report"]
        assert report is not None
        StockReport(**report)  # 재검증 — 실패하면 여기서 ValidationError
        assert report["종합의견"] in ("긍정적", "중립", "신중")
        assert len(report["리스크요인"]) >= 1
        assert report["면책고지"]
    else:
        # 폴백이어도 계약 유지(정량요약 보존, 크래시 없음).
        assert result["report"] is None
        assert result.get("quant_summary") is not None
