# frontend/ — React + Vite

## 실행
- 백엔드 먼저: `uv run uvicorn api.main:app --port 8000` → 프론트: `npm run dev`.
- **`http://localhost:5173`로 연다** — Vite가 IPv6 localhost에 바인딩하므로 `127.0.0.1:5173`은 안 될 수 있다.
- Vite dev가 `/api`를 `http://127.0.0.1:8000`으로 프록시 → 개발 중 CORS 불필요.

## 디자인 (반드시 준수)
- 팔레트는 **흰색/회색/파랑/남색/검정 5계열로 제한**. 빨강·초록·황색 금지. 상승=파랑, 하락=회색(금융 관행의 빨강/초록을 의도적으로 안 씀 — "단정 금지" 원칙과 정합).
- 색은 **`src/theme.css` 토큰(`var(--c-*)`)만** 참조. 컴포넌트에 hex 하드코딩 금지. 전체 규칙: `ui-design-system` 스킬.

## 계약
- `GET /api/macro/indicators` → `{indicators, partial_failure}` 소비. 지표가 `null`이면 "일시 조회 불가" 카드로 표시하고 나머지는 정상 렌더(부분 실패 보존). 지표 키·shape은 백엔드(`api/main.py`)와 일치해야 한다.
- 화면은 단계적으로 성장: 1단계 지표 대시보드(완료) → W07 국면 게이지 → W08 종목 리포트 → W09~10 챗봇/팝업. 새 화면도 같은 토큰을 조합해 한 제품처럼 보이게.
