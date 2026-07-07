# W08 frontend-engineer — 종목 종합리포트 UI + KLineChartPanel(klinecharts)

작업 #12. TDD(Red→Green→Refactor). 순수 로직을 `src/lib/`로 분리해 vitest(vite-native)로 검증.
컴포넌트는 data-engineer의 실제 번들 계약(`w08_data-engineer_bundle.md`)을 소비(필드 추측 0).

## 테스트 목록(스펙 근거) → 구현 (test-first 증거)

테스트 러너 부재(devDeps=vite만) → **vitest 도입**(vite-native, 최소 footprint). `npm test`=`vitest run`.
매핑·판정 분기를 순수 함수로 분리해 브라우저 없이 검증(스냅샷 남발 금지, 경계 계약만).

### Phase 1 — 차트 데이터 매핑 (`src/lib/chartData.test.js`, 13 케이스)
Red(스켈레톤 `null`/`[]` → assertion 실패 14건 확인) → Green(`src/lib/chartData.js`):
- `dateToTimestamp` — 'YYYYMMDD'→UTC epoch(ms) 결정적 변환 / 연·월·일 경계 / 8자리 숫자 허용 /
  잘못된 형식·존재하지 않는 날짜(롤오버 역검증)→null(임의 날짜 렌더 금지)
- `candlesToKline` — 번들 candles→klinecharts KLineData 매핑 / **timestamp 오름차순 정렬**(klinecharts 요건) /
  문자열·콤마 숫자 강제변환 / date 파싱불가·OHLC 결측 행 제외 / volume 결측=0 / 비배열→[]

### Phase 2 — 리포트 표현 분기 (`src/lib/reportLogic.test.js`, 8 케이스)
Red 확인 → Green(`src/lib/reportLogic.js`):
- `sectionFailed(partial_failure, section)` — 문자열 리스트/객체 리스트 방어 / 비배열→false
  (계약 근거: 번들 partial_failure ⊂ {basic,valuation,financials,chart,regime}, 문자열)
- `isValuationReady(summary)` — avg_per·valuation_label 둘 다 non-null 게이트(하나라도 null→"판정 준비 중")
  (계약 근거: 계획 §avg_per 라이브 검증 게이트, 임의 라벨 금지)
- `yoyChange(curr, prev)` — 재무 YoY 방향(up/down/flat/null) + 전기 0·음수·결측→pct=null(0나눗셈·부호역전 방지)

**결과: `npm test` → 2 files, 21 passed.** `npm run build` → 0 error(klinecharts 번들 포함).

## 컴포넌트 ↔ 데이터 매핑표 (번들 계약 소비처)

| 컴포넌트 | 소비 필드 | 처리 |
|---|---|---|
| `StockReport`(컨테이너) | — | 티커 입력 → `fetchStockBundle` 1회. 네트워크/HTTP 오류=백엔드 미연결 → 샘플 폴백(배너 명시). partial_failure(정상200)는 그대로 렌더 |
| `StockReportView`(3단 조립) | 전체 bundle | 섹션별 `failed()`=sectionFailed∨null → "일시 조회 불가", 나머지 정상(전체 에러 화면 없음) |
| 헤더 | `basic.name/sector`, `valuation.price/change_rate/as_of` | 등락률 파랑(↑)/회색(↓). **as_of는 실데이터 항상 null → 조건부 숨김** |
| 상단 카드(`StatCard`×6) | `summary.{rev_cagr,op_cagr,current_per,avg_per,per_vs_avg,valuation_label,rsi,ma20_gap_pct,pos_52w_pct,sample_years}` | CAGR×100 표시 · PER vs **N년**평균(sample_years, '5년' 하드코딩 없음) · 밸류에이션 남색 알약 · isValuationReady=false → "판정 준비 중"(muted) |
| 기술적 `KLineChartPanel` | `chart.candles`, `indicator_config.{ma_period,rsi_period}`, `valuation.{week52_high,week52_low,price}` | 아래 "차트" 참조 |
| 국면정합성 | `regime_gate.{regime,per_max,pbr_max,per_over,pbr_over,entry_blocked,note}` | 국면명=주황(강조), note 사실서술. regime 실패 시 regime_gate=null → 패널 숨김 |
| 기본적 `FinancialTrendTable` | `financials.income[{period,revenue,operating_income,net_income}]`, `financials.ratio[{period,eps,bps,roe}]` | 기간 오름차순, YoY ▲(파랑)/▼(회색)만. roe(←roe_val) 정합 |
| 하단 | — | W09 LLM 서술 placeholder + **면책고지 코드 고정 상시노출**(회색, 빨강 아님) |

## 사용 API
- `GET /api/detail/{ticker}/bundle` (Vite 프록시 `/api`→127.0.0.1:8000) — `src/api.js`의 `fetchStockBundle(ticker)`. 1회 호출(N+1 금지). 섹션 실패(200+partial_failure)는 throw 안 함.

## klinecharts 팔레트 테마 방식
- 버전: **klinecharts@9.8.12 고정**(npm `latest`가 10.0.0-beta3라 안정 v9로 고정).
- theme.css 토큰은 canvas에서 CSS var()를 못 쓰므로 `src/lib/theme.js`의 `readChartPalette()`가
  **getComputedStyle로 구체 hex 토큰(--c-blue 등)을 읽어** JS로 주입(SSOT 유지). 시맨틱 별칭(--c-up)은
  var() 참조라 브라우저별 편차 → 구체 토큰을 읽고 상승/하락 역할에 매핑. 폴백 hex는 토큰 부재(SSR/테스트) 대비.
- `setStyles`: candle up=파랑/down=회색(노보더=색동일), grid·axis=회색, 지표 선=파랑·남색, VOL 바=파랑/회색.
  **함정(수정 반영)**: klinecharts는 `lines`/`bars` 배열 스타일을 '요소 통째 교체'로 병합 →
  부분객체({color}만) 주면 `dashedValue` undefined로 그리기 중 크래시(내부 drawImp가 dashedValue[0] 접근).
  → 반드시 **완전한 스타일 객체**(`{style,smooth,size,dashedValue,color}` / bars는 border* 포함)로 주입. ohlc 기본(초록/빨강)도 방어적 override.
- 지표: 메인 페인 캔들+MA(ma_period), 하단 서브페인 VOL·RSI(rsi_period). 52주 고저·현재가 = `priceLine` 오버레이(값 라벨).
  오버레이 실패해도 값은 칩(현재가 파랑/52주최고 남색/52주최저 회색)으로 병기.
- 생명주기: useEffect init→setStyles·지표 / cleanup에서 `dispose`(누수 방지). 데이터·오버레이는 별도 effect(candles/valuation 의존). 각 klinecharts 호출 try/catch(버전차 방어).
- **검증(puppeteer headless 캡처)**: 캔들 파랑/회색·MA20 파랑·VOL 파랑/회색·RSI 남색·52주/현재가 3선 정상.
  `Cannot read properties of undefined (reading '0')`(위 dashedValue 함정) → 완전객체 주입으로 해소, 재캡처 0 pageerror.
  puppeteer-core는 검증 후 제거(앱 의존성 아님).

## 뷰 진입 방법
- `App.jsx` = `<MacroDashboard/>` + `<StockReport/>`(대시보드 하단 두 번째 섹션). W08 최소 진입:
  티커 입력(기본 005930) + 조회. 팝업/챗 라우팅은 W09(과도 라우팅 지양).
- 실행: 백엔드 `uv run uvicorn api.main:app --port 8000` + `cd frontend && npm run dev` → `http://localhost:5173`.
  백엔드 없이도 샘플 fixture(`src/fixtures/sampleBundle.js`, 번들 계약 준수)로 3단 리포트 전체 렌더.

## 안전 게이트(프론트)
- 주문 API 참조 0(buy/sell/order/주문 grep 0) · 하드코딩 hex 0(theme.css=SSOT, theme.js=토큰 폴백만) ·
  초록·황색 0(주석의 "금지" 문구뿐) · 현재가 무캐시(fetchStockBundle 매 조회, 현재가선=valuation.price 실시간).

## 계약상 확인 지점 (해결됨)
1. **`summary.rev_cagr`/`op_cagr` 단위 → 리더 확정: 이미 %**(엔진 `stock/summary.py::_cagr`가 ×100 반환, `stock/CLAUDE.md` 단위 규약 명문화). **`cagrPct`에서 ×100 제거** 완료(프론트 ×100 재적용 금지). fixture도 `rev_cagr:2.5`·`op_cagr:-14.0`으로 정합. 재검증: `npm test` 21 passed · `npm run build` 0 error.
2. `per_vs_avg`·`ma20_gap_pct`·`pos_52w_pct`는 **이미 %**, `rsi`는 0~100 — 그대로 표시(변경 없음, 확정).
3. `AVG_PER_VERIFIED=False`(data-engineer) 유지 시 avg_per/per_vs_avg/valuation_label=None → 상단 카드가 "판정 준비 중"으로 정상 표시(의도된 게이트). 라이브 검증 True 전환 시 자동으로 값·배지 노출.
