"""인텐트 학습 데이터 생성 스크립트 — 계획 §4. (비결정적·유료, LLM 호출)

OpenAI(CHAT_MODEL 상수)로 [질문→라벨] 쌍을 라벨별 균형 있게 다량 생성해
data/intent_dataset.tsv(`질문<TAB>라벨`)로 저장한다. 산출 데이터셋은 커밋, 학습은
intent_train.py 가 담당(생성/학습 분리 — 생성은 비결정적·유료라 CI 에서 제외).

**주의**: 이 스크립트는 OPENAI_API_KEY 와 유효한 모델 접근이 필요하다(유료). 런타임
챗봇/테스트는 이 스크립트를 호출하지 않는다 — 오직 오프라인 데이터셋 생성용.

실행: `uv run python -m chat.intent_gen [라벨당_개수]`  (기본 60)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from openai import OpenAI

from chat.intent import LABELS
from chat.tools import CHAT_MODEL
from infra.config import openai_api_key

_ROOT = Path(__file__).resolve().parents[1]
_OUT = _ROOT / "data" / "intent_dataset.tsv"

# 라벨별 생성 지침 — 라우팅 의도·차단 4유형 예시를 프롬프트에 명시(스킬 §3).
_LABEL_BRIEFS = {
    "macro_view": "시장 전반·경기 국면·현재 현금비중·매크로 지표(금리차·VIX·공포탐욕)를 묻는 질문.",
    "stock_analysis": "특정 개별 종목(삼성전자·005930 등)의 분석·밸류에이션·기술적·실적을 묻는 질문.",
    "portfolio_advice": "사용자 본인의 보유 종목·자산배분·비중 조정·리밸런싱을 상담하는 질문.",
    "watchlist_mgmt": "관심종목(워치리스트) 조회·추가·삭제·정렬 등 목록 관리 질문.",
    "general_qa": "투자 용어·개념(PER·배당·ETF·분산투자 등)을 묻는 일반 지식 질문.",
    "analyst_report": (
        "특정 종목의 애널리스트/증권사 리포트를 수집·확보·검색하거나, 목표주가·투자의견 등 "
        "리포트 내용을 조회·요약해 달라는 질문('삼성전자 리포트 확보해줘', '이 종목 애널리스트 "
        "목표주가 리포트 찾아줘', '업로드한 리포트에서 검색해줘')."
    ),
    "risk_guardrail": (
        "차단 대상. 4유형을 고루 섞어라: "
        "① 단정 예측 요구('반드시 오르지?'), ② 내부정보 유도('내부정보 있어?'), "
        "③ 과도한 위험 조장('빚내서/몰빵/전재산'), ④ 시세조종·부정거래('작전주 정보')."
    ),
}


def _gen_for_label(client: OpenAI, label: str, n: int) -> list[str]:
    """한 라벨에 대해 n개의 한국어 질문을 생성해 리스트로 반환(JSON 배열 강제).

    _LABEL_BRIEFS[label] 지침을 프롬프트에 실어 그 인텐트에 정확히 해당하는 질문만 뽑는다.
    특히 risk_guardrail 은 차단 대상 4유형을 고루 섞도록 지시(하드블록 학습 커버리지).
    """
    brief = _LABEL_BRIEFS[label]
    prompt = (
        f"너는 한국어 투자 챗봇의 학습데이터 생성기다. 아래 인텐트에 해당하는 "
        f"자연스러운 한국어 사용자 질문을 {n}개 만들어라.\n\n"
        f"[인텐트: {label}]\n{brief}\n\n"
        f"규칙: 실제 개인 투자자가 쓸 법한 구어체·다양한 표현. 서로 겹치지 않게. "
        f'JSON 객체 하나만 출력: {{"questions": ["...", "..."]}}'
    )
    # response_format=json_object 로 파싱 안정성 확보. CHAT_MODEL_PARAMS 는 추론형 모델 필수
    # 파라미터(reasoning_effort='none' 등)를 매 create() 에 병합하는 단일 출처(chat 계층과 동일 규칙).
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        **CHAT_MODEL_PARAMS,
    )
    data = json.loads(resp.choices[0].message.content)
    questions = data.get("questions", [])
    # 개행·탭 제거(TSV 안전 — 탭이 섞이면 `질문<TAB>라벨` 컬럼이 깨진다), 공백 질문 제외.
    return [q.replace("\t", " ").replace("\n", " ").strip() for q in questions if q.strip()]


def generate(per_label: int = 60) -> Path:
    """모든 라벨을 순회하며 per_label 개씩 생성 → TSV 로 저장. 반환은 저장 경로.

    라벨별로 균형 있게(각 per_label 개) 뽑아 특정 인텐트 편중을 막는다 — 편중되면 char n-gram
    분류기가 소수 라벨을 못 배운다. 산출 TSV 는 커밋하고, 학습은 intent_train.py 가 별도로 한다.
    """
    client = OpenAI(api_key=openai_api_key())
    rows: list[tuple[str, str]] = []
    for label in LABELS:
        print(f"생성 중: {label} ({per_label}개)...")
        for q in _gen_for_label(client, label, per_label):
            rows.append((q, label))

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    # `질문<TAB>라벨\n` 한 줄 = 한 샘플. intent_train.py 가 이 포맷을 그대로 읽는다(계약).
    with _OUT.open("w", encoding="utf-8") as f:
        for q, label in rows:
            f.write(f"{q}\t{label}\n")
    print(f"저장: {_OUT.relative_to(_ROOT)} ({len(rows)}행)")
    return _OUT


if __name__ == "__main__":
    # CLI 인자로 라벨당 개수 조절(기본 60). 오프라인 데이터셋 생성 전용 진입점.
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    generate(n)
