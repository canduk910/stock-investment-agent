# TOKENS & CSS SPEC — 디케이 투자에이전트 리디자인 (컨셉 A)

> 적용 원칙: 색은 `frontend/src/theme.css` 토큰만 수정/추가하고, 컴포넌트 CSS는 `var(--c-*)` 참조를 유지한다(SSOT).
> 백엔드 코드·API 계약은 변경하지 않는다.

## 1. theme.css — 토큰 변경표

### 1-1. 값 변경 (기존 토큰 유지, 값만 교체)
| 토큰 | 기존 | 신규 | 비고 |
|---|---|---|---|
| `--c-up` | `var(--c-blue)` (파랑) | `#e5322d` | **상승 = 빨강 (전 화면, 한국 관습)** |
| `--c-down` | `var(--c-text-secondary)` (회색) | `#2563eb` | **하락 = 파랑 (전 화면)** |
| `--c-bg` | `#f4f6fa` | `#f5f7fb` | 앱 배경 미세 조정 |
| `--c-border` | `#d8e0ea` | `#e2e8f2` | 카드 기본 테두리(더 옅게) |
| `--radius` | `12px` | `14px` | 카드 라운드 |
| `--shadow-card` | 기존 2단 | `0 1px 2px rgba(16,35,61,0.05), 0 8px 24px rgba(16,35,61,0.05)` | 셸 카드용 |

### 1-2. 신규 토큰
```css
/* 방향 소프트 배경(등락 칩·플래시) */
--c-up-soft: rgba(229, 50, 45, 0.08);
--c-down-soft: #e8f0fe;
--c-flat: #8a94a8;            /* 보합 텍스트 */
--c-flat-soft: #f0f3f9;       /* 보합 칩 배경 */
--c-up-onnavy: #ff7a75;       /* 네이비 카드 위 상승 표기 */

/* 브랜드/셸 */
--c-brand: #1d4ed8;           /* 워드마크 "디케이 투자에이전트" */
--c-navy-deep: #101b30;       /* 히어로/유저버블/현금비중 카드 */
--c-emph-onnavy: #f0913c;     /* 네이비 위 주황 값 */

/* 표면 보조 */
--c-surface-3: #f8fafd;       /* 메시지 영역·표 헤더·스켈레톤 밝은 톤 */
--c-border-soft: #e9edf5;     /* 로우 카드 테두리 */
--c-hairline: #f0f3f9;        /* 표 로우 구분선 */

/* 강조(주황) 소프트 계열 — 기존 --c-emph* 유지 + 보더 */
--c-emph-border: #f0c9a2;

/* 형태 */
--radius-lg: 16px;            /* 섹션 카드 */
--radius-xl: 18px;            /* 셸(챗/패널) 카드 */
--radius-pill: 999px;
```

### 1-3. 유지되는 토큰 (변경 금지)
- `--c-chart-up: #e5322d` / `--c-chart-down: #2563eb` — 캔들차트. `--c-up/--c-down`과 값이 같아졌지만 **토큰은 분리 유지**(klinecharts 주입 경로 `lib/theme.js::readChartPalette` 보존).
- `--c-emph: #e0670f`, `--c-emph-strong: #b8500a`, `--c-emph-soft: #fbe8d6` — 주황=강조(국면명·현금비중·목표가 상태·확인 CTA).
- `--c-danger: #d92d20`, `--c-danger-strong: #b42318` — **위험 경보 전용**(VIX 패닉 칩·손실경고 배너). 가격 방향에 쓰지 않는다. 상승 빨강(#e5322d)과 형태로 구분: 경보는 항상 채움 배너/칩 + ⚠.
- 텍스트 위계: `--c-black #0b111c`, `--c-navy #16233d`, `--c-text #1e2a44`, `--c-text-secondary #55617a`, `--c-text-muted #8a94a8`(+ 신규 보조 `#a3adc0`은 `--c-text-faint`로 추가 권장).

## 2. 타이포그래피
```css
/* index.html */
<link rel="stylesheet" href="...pretendardvariable-dynamic-subset.min.css">
/* styles.css body */
font-family: 'Pretendard Variable', Pretendard, -apple-system, BlinkMacSystemFont,
  'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
```
스케일(주요): 워드마크 16/800 · 섹션 제목 19/800(-0.02em) · 리포트 종목명 23/800 · 리포트 가격 36/800(모바일 28) · 히어로 순자산 38/800 · 현금비중 54/800 · 카드 값 23/800 · 본문 13~13.5 · 라벨 11~11.5 · 메타 10.5 · 캡션 10~11. 숫자는 전부 `font-variant-numeric: tabular-nums`.

## 3. 키프레임 (styles.css 추가)
```css
@keyframes stage-pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
@keyframes blink { to { visibility: hidden; } }
@keyframes marker-ring { 0%{box-shadow:0 0 0 0 rgba(37,99,235,.45)} 100%{box-shadow:0 0 0 12px rgba(37,99,235,0)} }
@keyframes rise-in { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
@keyframes shimmer { 0%{background-position:-420px 0} 100%{background-position:420px 0} }
@keyframes flash-up { 0%{background-color:rgba(229,50,45,.2)} 100%{background-color:transparent} }
@keyframes flash-down { 0%{background-color:rgba(37,99,235,.18)} 100%{background-color:transparent} }
/* 스켈레톤 공통 */
.skeleton { background: linear-gradient(90deg, var(--c-surface-2) 25%, var(--c-surface-3) 50%, var(--c-surface-2) 75%); background-size: 840px 100%; animation: shimmer 1.1s linear infinite; }
```

## 4. 파일별 변경 명세 (frontend/)
| 파일 | 변경 |
|---|---|
| `index.html` | Pretendard `<link>` 추가, `<title>디케이 투자에이전트</title>` |
| `src/theme.css` | §1 토큰 변경/추가 |
| `src/styles.css` | §3 키프레임 + 신규 클래스(topbar/alert-banner/segmented-tab/skeleton/wl-row/gauge/hero-card 등 — README 화면 명세 참조). 등락·손익 색 클래스는 `var(--c-up)/var(--c-down)` 참조 유지(토큰 교체만으로 빨/파 반영됨) + 소프트 배경 칩 클래스 추가 |
| `src/App.jsx` | 톱바 리브랜딩(CI SVG + 타이틀 + 상태 칩), 알림 배너 마크업 교체(주황, 톱바 아래 풀폭), 알림 CTA 상태(기본/켜짐). 폴링·전이 감지 로직은 그대로 |
| `src/components/RightPanel.jsx` | 퀵버튼 → 세그먼트 탭, 종목검색을 툴바 우측 인라인으로, 패널 전환 스켈레톤(450ms), `manage_watchlist` 라우팅 유지 |
| `src/components/WatchlistView.jsx` | 테이블 → 카드 로우(스파크라인·등락 칩·목표가 게이지). 인라인 목표가 편집(기존 TargetCell 로직 재사용) · 정렬 · partial 배너 유지. (선택) 시세 플래시 — 60s 갱신 시 변경 종목에 flash 클래스 1회 |
| `src/components/BalancePanel.jsx` | 네이비 히어로 카드(순자산+손익 pill) + 보조 카드 4 + 표. 부분실패 dashed 카드 + 재시도 |
| `src/components/RegimeGauge.jsx` | 2컬럼 재배치(사분면 카드 + 네이비 현금비중 카드 + 기여지표), 마커 pulse, 손실경고/누락 배너 스타일 교체 |
| `src/components/StockReportView.jsx`, `StatCard.jsx`, `FinancialTrendTable.jsx`, `AiReportPanel.jsx` | 헤더 대형 가격+등락 칩, 정량 카드 8종, 국면 정합성 주황 카드, 재무 표 카드화(overflow-x auto), AI 패널 상태(idle/loading skeleton/done 구조화 + 히스토리 델타 주황) |
| `src/components/ChatPanel.jsx`, `ChatMessage.jsx` | 버블(유저 네이비/봇 흰색)·체크리스트·커서·제안 칩·칩 hover. SSE 상태기계 로직 그대로 |
| `src/components/KLineChartPanel.jsx`, `src/lib/theme.js` | **변경 없음** (캔들 한국 관습 기적용, 지표선 남색·회색 유지) |
| `src/components/ManageWatchlistConfirm.jsx` | 스타일만 교체(확인=주황 채움) — confirm-before-write 유지 |
| `frontend/CLAUDE.md`, `.claude/skills/ui-design-system/SKILL.md` | **색 규칙 문구 개정 필수**: "상승=파랑/하락=회색(차트만 예외)" → "모든 주식 수치 상승=빨강/하락=파랑(사용자 확정). 주황=강조, 빨강 배너/칩=위험 경보 전용" |

## 5. 시맨틱 컬러 사용 규칙 (개정판)
1. **가격/손익 방향**: 상승·수익 = `--c-up`(빨강) / 하락·손실 = `--c-down`(파랑) / 보합 = `--c-flat`. 항상 ▲▼─ 글리프 병기(색만으로 구분 금지).
2. **강조(주황)**: 현재 국면명, 권장 현금비중, 목표가 도달/근접, 진입 검토 가능, 알림 배너, 변화 마커, 확인 CTA. "여기를 보라"의 뜻 — 위험 아님.
3. **위험(빨강 경보)**: VIX 패닉 칩, 손실경고 배너만. 채움형 배너/칩 + ⚠ 글리프로 상승 빨강 텍스트와 형태 구분.
4. **파랑**: 기본 액센트(버튼·링크·활성 셀·정보 배너) + 하락 방향. 정보 배너는 소프트(#e8f0fe) 형태라 하락 표기와 혼동 없음.
5. **남색/검정**: 제목·핵심 숫자·활성 탭·히어로 존. **회색**: 보조 텍스트·중립 상태·비활성.
