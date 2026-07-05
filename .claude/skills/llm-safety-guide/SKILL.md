---
name: llm-safety-guide
description: "투자 챗봇의 시스템 프롬프트 조립(build_prompt.py), OpenAI function calling(chat.py), 팝업 툴 정의, 인텐트 6분류, Pydantic 리포트 스키마, 안전·윤리 요건 구현 규칙. 챗봇, 프롬프트, LLM 호출, 팝업 툴, 인텐트 분류, 리포트 스키마 작업(구현·수정·프롬프트 튜닝)을 하기 전에 반드시 이 스킬을 읽을 것."
---

# LLM 계층 구현 가이드 — 설명만 하는 LLM

원본 스펙: `invest_develop_PLAN.md` §5·§6.2~6.5·§10·§12. 이 계층의 존재 이유는 하나다: **판정은 코드가 했고, LLM은 그 결과를 설명만 한다.**

## 1. 시스템 프롬프트 조립 (build_prompt.py)

### 기준표는 타이핑하지 말고 생성하라

임계값 숫자를 프롬프트 문자열에 직접 쓰면, 코드 상수가 바뀔 때 프롬프트가 낡는다(3중 일관성 위반). 반드시 quant 모듈의 상수를 import해 `build_criteria_text()`로 생성한다:

```python
def build_criteria_text() -> str:
    lines = ["[국면 판정 기준 — 시스템이 이 규칙으로 판정함]"]
    for key, label in INDICATOR_LABELS.items():
        parts = [f"{v}이면 {k}" for k, v in THRESHOLDS.get(key, {}).items()]
        lines.append(f"- {label}: {', '.join(parts)}")
    lines.append("- 신용·금리 지표는 가중치 2, 변동성·심리 지표는 가중치 1")
    lines.append(f"- 예외: VIX > {VIX_PANIC}이면 다른 지표와 무관하게 수축 (패닉 오버라이드)")
    return "\n".join(lines)
```

### 시스템 프롬프트 필수 블록 (누락 시 QA 실패)

1. 역할: 판단 보조자 — 자동매매 아님, 면허 있는 자문 아님
2. **[국면 판정 출처 고정]**: "아래 판정은 시스템이 계산한 결과다. 재판정·숫자 변경 금지. 너의 역할은 기준에 근거해 '왜 이렇게 나왔는지' 설명하는 것"
3. 기준표 (자동 생성) + 현재 판정 결과 주입 (`judgement` dict의 regime/현금비중/신뢰도/votes/key_drivers/raw_data/override)
4. `REGIME_PARAMS[국면]` 주입 — "국면 PER 상한 12 vs 이 종목 18" 식 인용 근거
5. 설명 지침: 컨텍스트 외 숫자 금지 / 단정 표현("반드시 오른다") 금지 / 손실 위험 환기 / 전문용어에 짧은 설명
6. 팝업 도구 사용 규칙

`judgement`는 매 호출마다 최신 값을 주입한다 — 세션 시작 시 1회가 아니다.

## 2. chat.py — function calling + text/popups 분리

- 모델: OpenAI `gpt-4o`, `tools=TOOLS, tool_choice="auto"`
- 응답을 `{"text": msg.content or "", "popups": [{"name", "args"}, ...]}`로 분리 반환 — text는 말풍선, popups는 프론트의 팝업 트리거. **이 shape이 프론트와의 계약이다. 바꾸면 frontend-engineer에게 알릴 것.**
- LLM은 팝업에 들어갈 데이터를 만들지 않는다. "무엇을 띄울지"만 결정하고, 실데이터는 프론트가 API에서 직접 조회한다.

### 팝업 툴 3종 (파라미터는 enum으로 제한)

| 툴 | 파라미터 | 
|---|---|
| `show_macro_dashboard` | `highlight`: regime \| cash_ratio \| indicators |
| `show_stock_report` | `ticker`(6자리), `stock_name`, `focus`: fundamental \| technical \| both |
| `show_watchlist` | `sort_by`: registered \| change_rate \| near_target |

각 툴 description에 **"언제 호출하는지"와 "언제 호출하지 않는지"를 모두** 쓴다(오발동 방지). 예: show_stock_report — "특정 종목의 분석을 요청할 때 호출. 용어 설명(general_qa)이나 시장 전반 질문에는 호출하지 않음."

## 3. 인텐트 6분류 라우팅 (플랜 §12)

| 인텐트 | 경로 | 팝업 |
|---|---|---|
| `macro_view` | 규칙 엔진 결과 설명 | show_macro_dashboard |
| `stock_analysis` | 종목 리포트 | show_stock_report |
| `portfolio_advice` | 보유+국면 비교 | (텍스트) |
| `watchlist_mgmt` | 워치리스트 CRUD | show_watchlist |
| `general_qa` | 정적 설명 | (텍스트) |
| `risk_guardrail` | **차단·경고** | (차단 응답) |

- 초기 구현은 few-shot 프롬프트 분류. 학습 데이터: `investment_intent_dataset_1000.txt` (형식: `질문<TAB>라벨`)
- **risk_guardrail을 가장 먼저 판별**하고, 경계 사례는 보수적으로 guardrail에 귀속
- 차단 4유형: ① 단정 예측 요구("반드시 오르지?") ② 내부정보 유도 ③ 과도한 위험 조장("빚내서/몰빵") ④ 시세조종·부정거래. ③은 거절이 아니라 위험 환기 + 분산 안내로 방향 전환

## 4. [P2] StockReport Pydantic 스키마

```python
class StockReport(BaseModel):
    종합의견: Literal["긍정적", "중립", "신중"]   # "매수/매도" 라벨은 타입에서 원천 배제
    요약: str
    투자포인트: list[str] = Field(max_length=3)
    리스크요인: list[str] = Field(min_length=1, max_length=3)  # 최소 1개 강제 — 장밋빛 방지
    국면정합성: str      # REGIME_PARAMS 인용
    면책고지: str        # 필수 — 누락 시 검증 실패
```

- 안전 요건을 프롬프트 지시가 아니라 **스키마 레벨에서 강제**하는 것이 포인트 — 지시는 어길 수 있지만 검증 실패는 재시도된다
- 검증 실패 시: 1회 재요청 → 재실패 시 정량 요약만으로 리포트 표시 + "AI 서술 생성 실패" 안내
- 검증 통과분은 DynamoDB `stock_report` 테이블에 저장 (히스토리 데모 포인트)

## 5. 안전 체크리스트 (구현 내내, 플랜 §10)

- 매수/매도 주문 API 호출 없음 (제안까지만)
- LLM 출력에 단정 표현 없음 — 프롬프트 지시 + (P2) 스키마 enum 이중 방어
- 모든 숫자는 조회 데이터 출처 — LLM 생성 숫자 금지
- 손실 위험 환기 + "면허 있는 자문 아님" 고지 상시
- API 키 하드코딩 금지
- 사용자에게 보여주는 시세는 항상 실시간 조회
