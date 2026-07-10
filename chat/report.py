"""구조화 종목 리포트 생성·검증·폴백 — llm-safety-guide §4 (P2). LLM은 설명만.

흐름:
1. bundle(정량요약·국면게이트)·judgement 를 컨텍스트로 CHAT_MODEL 에 JSON 생성을 요청한다
   (response_format=json_object). 정량 판정은 이미 코드가 확정했고, LLM 은 그 결과를
   구조화된 서술로 '설명'만 한다(새 숫자·판정 금지).
2. 응답 JSON → StockReport 검증. 안전 요건(종합의견 enum·리스크 최소1·면책 필수)은
   스키마가 강제한다(chat/report_schema.py).
3. 검증 실패(JSON 파싱 실패/ValidationError) → **1회 재요청** → 그래도 실패면 **폴백**:
   정량요약만 + "AI 서술 생성 실패" 안내 + validation_failed=True. §5.1 부분실패 보존 —
   리포트가 죽지 않고 정량요약은 남는다.

반환 계약(프론트·저장소 소비):
  성공: {"report": <StockReport dict>, "validation_failed": False, "quant_summary": <summary>}
  폴백: {"report": None, "validation_failed": True, "message": "AI 서술 생성 실패 ...",
        "quant_summary": <summary>}
안전: OpenAI 예외도 크래시 없이 폴백. 라이브 미호출은 테스트가 client 를 주입해 보장.
"""
from __future__ import annotations

import json

from pydantic import ValidationError

from chat.build_prompt import ENTRY_SIGNAL_RULES, build_criteria_text
from chat.report_schema import StockReport
from chat.tools import CHAT_MODEL

_FALLBACK_MESSAGE = (
    "AI 서술 생성 실패 — 정량 분석 요약만 표시합니다. 아래 수치는 코드가 계산한 값입니다."
)


def _make_client():
    """기본 OpenAI 클라이언트(키는 환경변수에서만). 테스트는 client 를 주입한다."""
    from openai import OpenAI

    from infra.config import openai_api_key

    return OpenAI(api_key=openai_api_key())


def _regime_block(judgement: dict, gate: dict) -> str:
    """국면 컨텍스트 — judgement 결측이면 '국면 데이터 없음'을 명시(근거 없는 국면 서술 유인 차단).

    챗봇 build_prompt 의 missing_line 정신과 동일: 없는 국면·상한 숫자를 지어내지 않게 못박고,
    국면정합성은 '판단 보류'로 유도한다(폴백이 검증 실패 때만 걸리는 구멍을 프롬프트에서 선제 차단).
    """
    regime = judgement.get("regime")
    if not regime:
        return (
            "[국면 데이터]\n"
            "- 현재 국면 데이터를 수집하지 못했다(FRED 등 실패) — 국면·현금비중·상한 숫자를 지어내지 마라.\n"
            "- 국면정합성 필드에는 '현재 국면 데이터 없음 — 국면 기준 대비 판단은 보류'라고 서술하라."
        )
    cash = judgement.get("recommended_cash_ratio", "")
    missing = judgement.get("missing_indicators") or []
    missing_line = (
        f"- 수집 실패로 제외된 지표: {', '.join(missing)} — 언급 시 '데이터 없음'으로 다뤄라.\n"
        if missing
        else ""
    )
    return (
        "[국면 게이트]\n"
        f"- 현재 국면: {regime} / 권장 현금비중: {cash}%\n"
        f"{missing_line}"
        f"{json.dumps(gate, ensure_ascii=False, indent=2)}"
    )


def _entry_emphasis(gate: dict) -> str:
    """게이트 값 파생 강조(하드코딩 없음) — 진입차단·밸류 초과를 종합의견에 반영시킨다."""
    if gate.get("entry_blocked"):
        return (
            "- 현재는 신규 진입 억제(single_cap=0) 국면이다 — 종합의견을 낙관(긍정적)으로 몰지"
            " 말고, 이 종목은 관찰 대상으로만 서술하라."
        )
    if gate.get("per_over") or gate.get("pbr_over"):
        return (
            "- 이 종목은 현재 국면의 밸류에이션 상한(PER/PBR)을 초과한다 — 국면정합성에 상한"
            " 초과 사실을 명시하고 종합의견에 반영하라."
        )
    return "- 국면 게이트상 신규 진입이 차단되지 않았고 밸류에이션도 상한 이내다(사실 서술만, 매수 권유 아님)."


def _build_report_prompt(bundle: dict, judgement: dict) -> str:
    """리포트 생성용 시스템 프롬프트 — 정량요약·국면게이트를 근거로 '설명'만 시킨다.

    build_prompt(챗봇)와 같은 안전 원칙: 재판정·숫자 생성 금지, 컨텍스트 밖 숫자 금지,
    단정 표현 금지, 면책 고지. 다만 출력은 자유 텍스트가 아니라 StockReport JSON 스키마.
    """
    ticker = bundle.get("ticker", "")
    basic = bundle.get("basic") or {}
    name = basic.get("name") or basic.get("stock_name") or ticker
    summary = bundle.get("summary") or {}
    gate = bundle.get("regime_gate") or {}

    schema_hint = (
        '{"종합의견": "긍정적|중립|신중 중 하나", "요약": "문자열", '
        '"투자포인트": ["최대 3개"], "리스크요인": ["최소 1개, 최대 3개"], '
        '"국면정합성": "현재 국면 상한 대비 서술", "면책고지": "참고용·자문 아님 고지"}'
    )

    return f"""너는 개인 투자자를 돕는 금융 분석 보조자다. 아래 정량 분석 결과를 '설명'하는
구조화 리포트를 JSON 으로 생성하라. 판정·숫자는 이미 코드가 계산했다 — 너는 재판정하거나
새 숫자를 지어내지 않는다.

[판정 기준표 — 시스템이 이 규칙으로 판정함]
{build_criteria_text()}

[대상 종목]
- 종목: {name} ({ticker})

[정량 분석 결과 — 이 값만 근거로 설명]
{json.dumps(summary, ensure_ascii=False, indent=2)}

{_regime_block(judgement, gate)}

[진입 신호 — 서술 규칙(챗봇과 동일 SSOT)]
{_entry_emphasis(gate)}
{ENTRY_SIGNAL_RULES}

[생성 규칙 — 안전]
- 반드시 아래 JSON 스키마 형태로만 답하라(추가 텍스트·마크다운 금지):
{schema_hint}
- 종합의견은 "긍정적"·"중립"·"신중" 중 하나만. "매수/매도" 같은 명령형 라벨은 쓰지 마라.
- 리스크요인은 최소 1개 이상 반드시 포함하라(장밋빛 리포트 금지).
- 위 컨텍스트 밖의 숫자를 지어내지 마라. "반드시 오른다" 같은 단정 표현 금지.
- 국면정합성에는 위 국면 게이트/데이터에 근거해 서술하라(국면 데이터가 없으면 '판단 보류').
- 면책고지에는 "이 설명은 참고용이며 면허 있는 투자자문이 아니다"를 반드시 담아라."""


def _request_report(client, prompt: str) -> str:
    """CHAT_MODEL 에 JSON 리포트 1회 요청 → content 문자열."""
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "system", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or ""


def _parse_and_validate(content: str) -> StockReport | None:
    """content(JSON) → StockReport. 파싱·검증 실패는 None(폴백 판단은 호출부)."""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    try:
        return StockReport(**data)
    except (ValidationError, TypeError):
        return None


def generate_stock_report(bundle: dict, judgement: dict, *, client=None) -> dict:
    """정량요약을 근거로 구조화 리포트 생성·검증. 실패 시 1회 재요청 → 폴백.

    반환은 항상 dict(크래시 없음). validation_failed=True 면 report=None + 정량요약만.
    """
    if client is None:
        client = _make_client()

    summary = bundle.get("summary")
    prompt = _build_report_prompt(bundle, judgement)

    # 최초 시도 + 검증 실패 시 1회 재요청(총 2회). 예외도 폴백으로 흡수.
    for _ in range(2):
        try:
            content = _request_report(client, prompt)
        except Exception:
            break  # OpenAI 예외 → 폴백(크래시 금지)
        report = _parse_and_validate(content)
        if report is not None:
            return {
                "report": report.model_dump(),
                "validation_failed": False,
                "quant_summary": summary,
            }

    # 재요청까지 실패 → 폴백(정량요약만, §5.1 부분실패 보존).
    return {
        "report": None,
        "validation_failed": True,
        "message": _FALLBACK_MESSAGE,
        "quant_summary": summary,
    }
