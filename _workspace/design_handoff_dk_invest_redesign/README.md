# Handoff: 디케이 투자에이전트 — 프론트엔드 UX 리디자인 (컨셉 A "Refined Pro")

## Overview
`stock-investment-agent` 저장소의 프론트엔드(React + Vite, `frontend/`)를 리디자인한 결과물입니다.
좌측 상시 채팅 + 우측 동적 패널이라는 기존 정보 구조는 유지하면서, 다음을 전면 개선합니다:

- **팔레트**: 흰색/회색/파랑/남색/검정 5계열 + 강조 주황(보색). 단, **모든 주식 수치(등락률·손익·재무 YoY·캔들)는 한국 시장 관습인 상승=빨강 / 하락=파랑**을 적용 (사용자 확정 — 기존 "상승=파랑/하락=회색" 전역 규칙을 대체).
- **타이포**: Pretendard Variable 도입, 큰 숫자 스케일(tabular-nums).
- **브랜드**: 서비스명 "디케이 투자에이전트", DK 모노그램 CI(남색 스퀘어 + 흰 DK + 주황 다이아몬드), 타이틀 파랑(#1d4ed8).
- **킥**: 스파크라인, 목표가 근접 게이지, 가격 갱신 플래시, 스켈레톤 로딩, 마이크로 모션.

⚠️ **백엔드(API·판정 로직)는 변경 대상이 아닙니다.** 이 핸드오프는 `frontend/` 렌더링 계층만 다룹니다.

## About the Design Files
이 번들의 HTML 파일은 **HTML로 제작된 디자인 레퍼런스(프로토타입)**입니다 — 의도된 룩과 동작을 보여주는 참고물이지, 그대로 복사해 쓰는 프로덕션 코드가 아닙니다.
할 일은 이 디자인을 **대상 코드베이스(React + Vite, 기존 컴포넌트 구조와 `theme.css` 토큰 시스템) 안에서 재구현**하는 것입니다. 기존 컴포넌트 파일 구조(`App.jsx`, `RightPanel.jsx`, `WatchlistView.jsx` 등)를 유지하고 CSS 클래스/토큰만 교체·확장하는 방식을 권장합니다.

- `1 리디자인 A — Refined Pro.dc.html` — **최종 확정 디자인** (모든 화면 + 상태 + 인터랙션 데모). 브라우저에서 열어 직접 조작해 보세요(같은 폴더의 `support.js` 필요).
- `0 Current UI 재현.dc.html` — 현재 UI의 충실 재현(비교 기준용).

## Fidelity
**High-fidelity (hifi)** — 색·타이포·간격·radius·상태·카피가 최종값입니다. 픽셀 단위로 재현하되, 코드베이스의 기존 패턴(토큰 참조 `var(--c-*)`, BEM식 클래스)으로 구현하세요.

## Screens / Views

### 0. 앱 셸 (App.jsx + styles.css)
- **톱바** (밝은 헤더): 흰 배경(#ffffff), 하단 1px #e2e8f2. 내부 max-width 1440, padding 10px 28px, min-height 64px, flex + wrap.
  - **CI**: 34×34 SVG — rx 9 남색(#16233d) 스퀘어 + 우상단 6×6 주황(#e0670f) 다이아몬드(rotate 45°) + 중앙 "DK" 흰색 13.5px/900.
  - **타이틀**: "디케이 투자에이전트" 16px/800, letter-spacing -0.02em, **#1d4ed8**. 아래 "DK INVESTMENT AGENT" 9.5px/600, ls 0.14em, #a3adc0.
  - **상태 칩**: `현재 국면 · 확장` (bg #fbe8d6, border #f0c9a2, text #b8500a, 12px/700, radius 999) · `권장 현금비중 20%` (bg #f0f3f9, border #e2e8f2, text #55617a + 값 #16233d/700) · (VIX 패닉 시) `⚠ VIX 패닉` (bg #d92d20, border #b42318, 흰 글씨).
  - **알림 CTA**: "목표가 알림 켜기" — 기본 주황 소프트(bg #fbe8d6/border #f0c9a2/text #b8500a), hover 주황 채움(#e0670f, 흰 글씨), 켜짐 상태 = 주황 채움 + "✓ 알림 켜짐". radius 9px.
- **목표가 알림 배너** (앱 레벨, 톱바 바로 아래 풀폭): bg #fbe8d6, border-bottom #f0c9a2. 주황 다이아몬드 8px + "목표가 알림"(800, #b8500a) + 내용(#8a5a2b) + 우측 [관심종목 보기](주황 채움 pill) [닫기](outline pill). far→near/reached **전이 시에만** 표시(기존 App.jsx 60s 폴링 + `detectTargetAlerts` 로직 그대로, 스타일만 교체).
- **본문 그리드**: max-width 1440, padding 24px 28px 40px, `grid-template-columns: minmax(340px, 420px) 1fr`, gap 24. **<1100px: 1컬럼 스택**(챗 sticky 해제, 메시지 영역 max-height 420px). **<640px: 모바일** — 패딩 14~16px, 톱바 캡션 숨김, 리포트 가격 36→28px, 차트 440→340px.

### 1. 챗 패널 (ChatPanel.jsx / ChatMessage.jsx)
- 카드: 흰 배경, border #e2e8f2, radius 18, shadow `0 1px 2px rgba(16,35,61,0.05), 0 8px 24px rgba(16,35,61,0.05)`, 데스크톱에서 sticky(top 24) + height calc(100vh - 112px).
- 헤더: 34×34 네이비(#101b30) radius 11 아이콘(주황 다이아몬드 8px) + "투자 챗봇" 15px/700 + 서브 11.5px #8a94a8 + 우측 "온라인"(파랑 dot 7px).
- 메시지 영역: bg #f8fafd, padding 20, gap 14. **빈 상태**: "이렇게 물어보세요" + 제안 칩 4개(흰 pill, hover 파랑 테두리 + translateY(-1px)). 제안: "지금 시장 어때?" / "삼성전자 어때?" / "내 잔고 보여줘" / "카카오 목표가 4만원으로 바꿔줘".
- **버블**: 사용자 = 네이비 #101b30 + 흰 글씨, radius 16/16/5/16, shadow. 봇 = 흰색 + border #e9edf5, radius 16/16/16/5. 13.5px, line-height 1.65, white-space: pre-wrap. 등장 애니메이션 rise-in 0.25s(6px 위로).
- **스트리밍**: 토큰 전 = 진행 단계 체크리스트(질문 분석→시장 국면 조회→답변 작성 중→정리 중; 완료 ✓ #1d4ed8 / 현재 ● #2563eb 700 + 1s 펄스 / 대기 ○ #a3adc0). 토큰 중 = 텍스트 + 2px 파랑 깜빡 커서. 완료 = 액션 칩("종목 리포트 열기 ↗" 등 — bg #e8f0fe, border #bcd3fb, text #1d4ed8, hover 파랑 채움) → 우측 패널 전환.
- 입력줄: input bg #f5f7fb radius 12, 전송 버튼 파랑 채움(#2563eb, hover #1d4ed8) radius 12/700. 로딩 중 비활성(opacity 0.55) + "전송 중".
- 하단 면책 10.5px #a3adc0 상시.

### 2. 우측 동적 패널 (RightPanel.jsx)
- 카드 셸: 챗 카드와 동일 스타일. max-height calc(100vh - 112px), 내부 스크롤.
- **세그먼트 탭**: 트랙 bg #f0f3f9 radius 12 padding 4; 탭 [관심종목|시장 국면|내 잔고|종목 리포트] — 활성: 네이비 #16233d 채움 + 흰 글씨 700 + shadow, 비활성: 투명 #55617a 500. white-space nowrap, transition 0.18s. 우측에 인라인 종목검색(input 150px + 조회 버튼; 형식 오류 시 회색 안내문 — `/^[0-9A-Za-z]{6}$/`).
- **패널 전환 스켈레톤**: 전환 시 450ms — 제목 바(150×20) + 로우 3개(64px, radius 14) + 블록(180px), shimmer 1.1s(#eef2f8↔#f7fafd, 순차 delay 0.08s) + "불러오는 중…".

### 3. 관심종목 (WatchlistView.jsx) — 랜딩
- 헤더: "관심종목" 19px/800 + 국면 서브텍스트 + 정렬 select(등록순/등락률순/목표가 근접순 — 프론트 재정렬, 재조회 없음).
- **카드 로우**(테이블 대체): 흰 카드 radius 14 border #e9edf5, padding 14px 18px, flex-wrap. hover: translateY(-1px) + shadow + border #d3dcea.
  - 종목명 14.5px/700 남색 + 코드·사유 11px #a3adc0
  - **스파크라인** 90×28 SVG(30pt), 선색 = 등락 방향색, 끝점 dot r2.2
  - 현재가 15px/700 검정 + **등락 칩**: ▲+1.05% (상승: text #e5322d, bg rgba(229,50,45,0.08) / 하락: text #2563eb, bg #e8f0fe / 보합: #8a94a8, #f0f3f9), 12px/700, radius 999
  - PER / PBR 13px/600
  - **목표가 + 근접 게이지**: "목표가 68,000원 (+5.7%)" 11px + 4px 게이지(트랙 #eef2f8, 채움 = 도달/근접 시 주황 #e0670f, 그 외 #c2cdda; width = clamp(6,100, 100−|거리%|×9)) + **[설정/변경] 인라인 편집** — 클릭 시 number input(92px) + [저장](파랑 채움) [취소], "비우고 저장하면 목표가 해제" 힌트. 저장 시 목표가 상태(도달=current≤target / 근접=+5% 이내) 재계산.
  - 진입 배지: `진입 검토 가능`(주황 소프트 #fbe8d6/#f0c9a2/#b8500a) · `밸류에이션 부담`(회색 #f0f3f9/#e2e8f2/#55617a) + [제거] ghost pill
- **가격 갱신 플래시**: 6s마다 임의 종목 시세 틱 → 가격 셀 배경 0.9s 플래시(상승 rgba(229,50,45,0.2)→투명 / 하락 rgba(37,99,235,0.18)→투명).
- **부분 실패**: 파랑 소프트 배너 "일부 종목 시세 일시 조회 불가(코드) · 나머지는 정상 표시" + 해당 로우 가격 "조회 불가"(#a3adc0)·등락 "—". 전체 에러 화면 금지.
- 하단 캡션: "상승 빨강 · 하락 파랑 — 한국 시장 관습 · 목표가 게이지는 매수 관점 근접도".

### 4. 시장 국면 (RegimeGauge.jsx)
- 헤더: "시장 국면" 19px/800 + "규칙 기반 판정 · LLM 미개입" + 신뢰도 pill(높음=네이비 채움).
- 2컬럼 grid(auto-fit, minmax 280px):
  - **사분면**: bg #f8fafd 카드 안 2×2(회복/확장/수축/과열), 셀 radius 12 min-height 86, 활성 = 파랑 #2563eb 채움 + border #1d4ed8 + 800. **위치 마커**: 14px 네이비 dot + 흰 테두리 3px + `marker-ring` 1.8s 무한 펄스(파랑 링 확산). 상/하단에 축 캡션(공포·심리·탐욕 / 경기·심리 값).
  - **권장 현금비중**: 네이비 #101b30 카드, 값 54px/800 **주황 #f0913c** + 국면 해설(국면명 주황 700). 아래 **기여 지표** 카드: 축 라벨(경기/심리 10.5px #a3adc0) + 지표명 + 방향 pill(양호·탐욕 ▲ = #1d4ed8/#e8f0fe, 악화·공포 ▼ = #55617a/#f0f3f9).
- **VIX 패닉 시**: 헤더 아래 빨강 경보 배너(bg #d92d20, border #b42318, 흰 글씨) "⚠ 역발상 관점: 급락장 매수 제안 — 손실 위험이 큽니다…" — **빨강은 위험 경보 전용**(가격 상승 빨강과 형태로 구분: 경보는 항상 배너/칩).
- 부분 실패 시: 파랑 소프트 배너 "일부 지표 누락: … · 남은 지표로만 판정".

### 5. 내 잔고 (BalancePanel.jsx)
- **네이비 히어로 카드**(#101b30, radius 16): "순자산" 라벨 + 38px/800 흰 값 + 평가손익 pill(상승: bg rgba(229,50,45,0.18), text #ff7a75 — 네이비 위 밝은 빨강) + 캡션.
- 보조 카드 4(예수금/매입금액/평가금액/보유 종목): auto-fit minmax(150px,1fr), 17px/700.
- 보유종목 표: thead bg #f8fafd 11.5px, 로우 hover #f8fafd, 손익 = 금액+수익률 2줄 우측 정렬, 방향색 빨/파 + ▲▼ 글리프(색만으로 구분 금지).
- **부분 실패**: dashed 카드(#c2cdda dashed, bg #f8fafd) "잔고 일시 조회 불가 (증권사 응답 지연)" + [↻ 재시도](파랑 채움). 면책 캡션 유지.

### 6. 종목 종합리포트 (StockReportView.jsx + 하위)
- 헤더: 종목명 23px/800 + 코드/업종 칩 + [☆ 관심종목 추가](hover 주황 소프트) | 우측 현재가 36px/800 + 등락 칩(빨/파) + "기준일 · 시세는 실시간 직접 조회".
- **정량 카드 8**(auto-fit minmax 170px): 라벨 11.5px → 값 23px/800(tabular; 매출 CAGR + = 빨강, 영업이익 − = 파랑) → 메타 10.5px. 밸류에이션 카드는 네이비 pill 배지("고평가" — 색으로 우열 암시 금지, 3라벨 동일 톤).
- **가격 차트**: 흰 카드, 900×440 (캔들 상승 #e5322d/하락 #2563eb, MA20 남색 1.3px, VOL 바 방향색 45%, RSI 남색 + 30/70 점선, 52주 고저 #c2cdda 점선 + 우측 태그, 현재가 남색 실선 + 태그). 범례(상승/하락/MA20) 우상단. *실구현은 klinecharts 유지 — `lib/theme.js::readChartPalette` 변경 불필요(이미 한국 관습).*
- **국면 정합성**: 주황 소프트 카드(bg #fbf4ec, border #f2ddc4) + 주황 다이아몬드 + 국면명 주황.
- 재무 표 2개(minmax(min(400px,100%),1fr), 카드 overflow-x auto): YoY 칩 ▲빨강/▼파랑 10.5px/700.
- **AI 종합 서술 패널** (AiReportPanel.jsx): [AI 리포트 생성](파랑 채움) [과거 평가 보기](outline).
  - idle: 안내문 / loading: 텍스트 스켈레톤 3줄(shimmer) + 버튼 "생성 중…" / **done**: `종합의견 · 긍정적` 배지(긍정적=파랑 소프트 / 중립=회색 / 신중=주황) + "생성 시점 국면 · 확장(주황)" + 요약 문단 + 투자 포인트 ul + 리스크 요인 ul(스키마상 최소 1개) + 국면 정합성 + 면책.
  - 히스토리 토글: 최신순 리스트 — 의견 배지 + 날짜·국면 + **변화 마커**("의견 중립→긍정적 · 국면 회복→확장", 주황 700).
  - 하단 코드고정 면책 상시.

### 7. 관심종목 관리 확인 카드 (ManageWatchlistConfirm.jsx)
- 챗 자연어 편집(예: "카카오 목표가 4만원으로 바꿔줘") → 우측 패널에 확인 카드. 질문 15px/700 + "AI는 제안만 합니다 — [확인]을 눌러야 반영됩니다(자동 매매·자동 실행 아님)" + [확인](주황 채움 #e0670f, saving 시 "반영 중…") [취소](회색). 완료 → "반영했습니다…" + [닫기 · 관심종목 보기]. **confirm-before-write 원칙 유지.**

## Interactions & Behavior
- 패널 전환: 탭/칩/검색/배너 → 450ms 스켈레톤 → 본문. 챗 응답 완료 시 자동 전환.
- 호버: 카드 translateY(-1px) + shadow-raise(0.16s) / 버튼 색 전환(0.15s) / 표 로우 bg.
- 모션: rise-in(버블·AI 결과), stage-pulse(1s), blink 커서(1s), marker-ring(1.8s), shimmer(1.1s), flash-up/down(0.9s ease-out), 게이지 width 0.4s ease.
- 반응형: ≥1100 2컬럼(챗 sticky) / <1100 스택 / <640 모바일 패딩·타이포 축소.
- 검증: 종목코드 6자 영숫자(`lib/ticker.js` SSOT) — 불량 시 조회 없이 회색 안내. 목표가 음수/비수치 무시, 빈 값 = 해제.

## State Management
기존 구조 유지: `App`이 `rightPanelSpec` 단일 소유, 알림 폴링(60s) App 레벨. 추가 UI 상태 — `panelLoading`(전환 스켈레톤), `editTicker/editDraft`(목표가 인라인 편집), `aiState: idle|loading|done` + `aiHistOpen`, `manageState: ask|saving|done`, `notifOn`, `alertVisible`, `flash{ticker,dir}`(시세 틱). 데이터 fetch 계약(번들/watchlist/balance/regime API, partial_failure 200 응답)은 변경 없음.

## Design Tokens
`TOKENS_AND_CSS_SPEC.md` 참조 (theme.css 교체값 + 신규 토큰 + 파일별 변경 명세).

## Assets
- **폰트**: Pretendard Variable — `https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css` (index.html `<link>`; 셀프호스팅 권장)
- **DK CI**: 외부 에셋 없음 — 인라인 SVG (README §0 스펙, 디자인 파일 topbar에 원본 코드)
- 아이콘: 별도 아이콘 폰트 없음. 글리프(▲▼─, ✓●○, ⚠, ☆, ✕, ↻)만 사용.

## Files
- `1 리디자인 A — Refined Pro.dc.html` — 최종 디자인(전 화면·상태·인터랙션). Tweaks: landingTab / showSparklines / demoPartialFailure / vixPanic
- `0 Current UI 재현.dc.html` — 현재 UI 재현(비교 기준)
- `support.js` — 디자인 파일 실행 런타임(같은 폴더에 두고 열기)
- `TOKENS_AND_CSS_SPEC.md` — 토큰 맵 + 파일별 변경 명세

## ⚠️ 저장소 문서 갱신 필요
`frontend/CLAUDE.md`와 `.claude/skills/ui-design-system/SKILL.md`의 색 규칙("상승=파랑/하락=회색, 차트만 예외")을 이번 사용자 결정(**모든 주식 수치 상승=빨강/하락=파랑**)에 맞게 개정해야 합니다. 그렇지 않으면 이후 에이전트 작업이 리디자인을 "위반"으로 되돌릴 수 있습니다. 주황=강조, 빨강 배너/칩=위험 경보 역할은 유지됩니다.
