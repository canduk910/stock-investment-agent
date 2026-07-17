# 실행 노트북 — 디케이 투자에이전트 (과제 제출용)

`투자에이전트_실행노트북.ipynb` 는 프로젝트가 아래 5개 요소를 어떻게 구현했는지 **설명 + 로컬 실행 데모**로
보여준다.

1. **Intent Classification** — `chat/intent.py` (7분류 TF-IDF char n-gram + LogisticRegression + 결정적 위험 가드레일)
2. **Prompt Routing** — `chat/build_prompt.py` (필수 블록·기준표 자동생성 + `tool_choice=auto`)
3. **RAG 기반 문서 검색** — `rag/` (pdfplumber 청킹 · text-embedding-3-small · numpy 코사인)
4. **Tool Calling** — `chat/chat.py`·`chat/tools.py` (OpenAI function calling: 표시 툴 / 콘텐츠 툴)
5. **UI 구성** — `frontend/` (좌 채팅 + 우 동적 패널 · `popupRouter.js`)

## 실행 방법

```bash
# 1) 의존성 설치(프로젝트 루트에서)
uv sync

# 2) .venv 를 Jupyter 커널로 등록
.venv/bin/python -m ipykernel install --user --name stock-agent --display-name "Stock Agent (.venv)"

# 3) 노트북 실행 (커널: Stock Agent(.venv) 선택)
uv run --with jupyterlab jupyter lab notebooks/투자에이전트_실행노트북.ipynb
```

## 키 요구사항

- `chat/build_prompt.py` · `chat/intent.py` · `macro/engine.py` · `chat/tools.py` (1·2·5 섹션 + 스키마)는
  **키 없이 동작**한다.
- RAG 임베딩(3 섹션)·chat 실행(4 섹션)은 프로젝트 루트 `.env` 의 **`OPENAI_API_KEY`** 가 필요하다
  (키가 없으면 해당 셀이 graceful 하게 건너뛴다). `.env.example` 참고.

노트북에는 실행 출력이 이미 채워져 있어 키 없이도 결과를 확인할 수 있다.

## 강화 내역

인텐트 분류기가 애널리스트 리포트 수집/검색 요청을 인식하지 못하던 문제(데이터셋에 리포트 질의 0건)를
**7번째 라벨 `analyst_report` 신설 + 데이터셋 55개 보강 + 재학습**으로 강화했다(1 섹션에서 시연).
