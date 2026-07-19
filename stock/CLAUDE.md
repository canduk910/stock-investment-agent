# stock/ — 종목 정량요약 엔진 (규칙 기반, LLM 미개입)

> 코드에서 자명하지 않은 결정·계약만. 판정은 전부 결정적 순수 함수(dict→dict), LLM 절대 미개입(macro/ 와 동일 철학).

## 순수 함수 계약 (summary.py)
- `build_stock_summary(basic, financials, valuation, chart)` → **항상 고정 10키**(rev_cagr, op_cagr, current_per, avg_per, per_vs_avg, valuation_label, rsi, ma20_gap_pct, pos_52w_pct, **ma_grand_cycle**) + sample_years + notes. 미산출은 **키 삭제가 아니라 None**(macro `_result` 계약과 동형). 외부 fetch·LLM 없음.
- 입력은 **정규화된 필드명**만 소비(raw KIS 명 금지): valuation.`price`/`per`/`week52_high`/`week52_low`, income[].`revenue`/`operating_income`, ratio[].`eps`, financials.`year_end_prices`{period: close}. 조정기준 검증(contract-integrity)으로 이 이름들이 SSOT.
- **단위(중요·계약)**: 숫자 % 필드는 전부 **퍼센트**로 반환한다 — `rev_cagr`/`op_cagr`(예 10.0 = 10%, 엔진이 ×100), `per_vs_avg`, `ma20_gap_pct`, `pos_52w_pct`(0~100). `rsi`는 0~100. **프론트는 이 값에 ×100을 다시 하지 않는다**(rev_cagr/op_cagr는 이름에 `_pct`가 없지만 스펙 §6.5a 이름 유지일 뿐, 단위는 %). W08 통합에서 프론트가 CAGR를 비율로 오해해 ×100한 버그를 이 규약으로 고정.

## avg_per — 자기 과거평균 PER의 데이터 게이트 (가장 중요)
- 과거 PER 시계열을 직접 주는 KIS API가 **없다**. 연도별 EPS(재무비율) × 결산기말 종가(월봉)로 근사한다. 결산기말 종가는 **오케스트레이터(api/detail.py)가 조회해 year_end_prices 로 주입**(엔진은 fetch 안 함 → 순수성 유지).
- **`constants.AVG_PER_VERIFIED` 게이트**: EPS 와 종가의 조정기준(액면분할)이 어긋나면 "그럴듯하지만 틀린" PER→valuation_label 이 나온다(결측보다 나쁨, 적대적 검증 critical). **[2026-07-07 라이브 검증 통과 → True]** 삼성전자(50:1 분할)로 `tests/live/test_live_stock_bundle.py` 4게이트 확인(23년 히스토리·PER_year 자릿수 튐 없음=조정기준 일치·real 도메인·일봉 100/회). 어댑터 조정기준/소스를 바꾸면 다시 False 로 내리고 재검증. 나머지 8필드는 게이트와 무관.
- **분기 interim 혼입 주의**(라이브 발견): KIS 재무는 20년+ 연간에 최신 분기(예 `202603`)를 섞어 준다 → `_recent_annual_periods` 가 **최빈 결산월 연간만** 남기고 그중 **최근 `FINANCIALS_LOOKBACK_YEARS`(5)** 만 avg_per·CAGR 에 쓴다(스펙 "5년 평균"). interim 을 CAGR 종점/avg_per 표본에 쓰면 왜곡(단위 테스트는 깨끗한 연간만 써서 못 잡음 — 라이브가 잡음).
- **한계(trailing PER)와 보완**: current_per 는 후행(과거 EPS 기준)이라 주가가 실적을 선반영하면 튄다. 라이브 실측(2026-07 삼성): 주가 1년새 6배(52주 60,200→374,500) 상승이 record EPS 6,564 를 앞질러 현재 PER≈45 → 5년평균 17 대비 "고평가 +181%". **이 후행 착시를 `forward_valuation`(예측 PER)이 보완한다** — 삼성 예측 PER 2026E 6.7배/2027E 4.6배(시장이 실적 폭증 전망 반영). 라벨은 코드가, 맥락 서술은 W09 LLM.

## forward_valuation — 예측 PER (KIS 리서치 컨센서스)
- `forward_valuation(estimate, valuation)` → `{forward_per:[{period,eps,forward_per,kis_per}], analyst, est_date, recommendation}`. **예측 PER = 현재가 ÷ 예측 EPS**(추정연도만, 실적연도 제외). EPS≤0(손실 예상)·현재가 결측 → forward_per None. 리서치 미대상 종목 → forward_per=[].
- 원천: KIS `estimate_perform`(HHKST668300C0, 리서치본부 월간, ~160종목). **공식 스펙 역설계 확정**(collectors 참조): output4=열 기간라벨('E'=추정), output3 r1=EPS·r3=PER(÷10). 실적컬럼(2023~2025)은 재무제표와 정확 일치.
- **판단 교훈**: 반도체(삼성·SK) 추정 매출이 실적 대비 2~6배로 튀어 처음엔 "데이터 오류"로 판단했으나, 실제로는 **AI/메모리 슈퍼사이클의 정당한 고성장 컨센서스**였다(사용자 시장지식으로 정정). 지식 컷오프 밖 시장을 "비현실적"이라 단정하지 말 것 — 그래서 magnitude 가드(예 est/actual 상한)를 걸지 않고 컨센서스 숫자를 출처와 함께 그대로 전달한다(판정은 코드가 아니라 사용자·LLM).

## CAGR 함정 (검증 반영)
- 정렬: income/ratio 는 KIS 가 최신연도 우선(내림차순)으로 줄 수 있어 **연도 오름차순 정렬 후** first/last. 안 하면 부호가 뒤집힌다.
- 연율화 지수 = **양끝 연도의 실제 연도차**(list 길이 아님) — 결측 연도가 있어도 왜곡 안 됨.
- 기초/기말 ≤ 0(적자 시작·부호전환) → **None + 사유**(음수 밑 거듭제곱 미정의, 억지 계산 금지). 표본 < `MIN_HISTORY_YEARS`(3) → None.
- **연간 필터·창**: `_recent_annual_periods`(avg_per 와 공유)로 최빈 결산월 연간만(분기 interim 제외) 최근 `FINANCIALS_LOOKBACK_YEARS`(5)년. 라이브에서 삼성 op_cagr 이 23년 혼합 +7.5% → 최근 5년 −4.1%(실적 감소 반영)로 의미가 달라짐.

## 3중 일관성 (constants.py 단일 출처)
- `VALUATION_BAND_PCT=10`(±10% 라벨, 경계 포함=적정), `MA_PERIOD=20`, `RSI_PERIOD=14`, `MIN_HISTORY_YEARS=3`, `MIN_CHART_CANDLES_*`, `STOCK_META_TTL_SECONDS`. `INDICATOR_CONFIG`={ma_period, rsi_period, **grand_cycle**{periods, stages}} 를 번들이 프론트(klinecharts)로 내려 **차트 지표 기간·대순환 3MA 오버레이 기간·6단계 라벨이 이 상수 단일 출처**(klinecharts·프론트가 4번째 진실이 되지 않게). grand_cycle 추가로 `indicator_config` 는 더 이상 정확 dict 비교 대상 아님(키 단위 검증).
- **REGIME_PARAMS 는 재정의 금지** — `macro.engine` 에서 import 만. 역발상 현금비중(`cash`)의 SSOT 는 매크로 엔진. 국면은 **현금비중만** 관리한다(항목3 — `single_cap`/`per_max`/`pbr_max` 폐기).

## 국면 진입게이트(regime_gate)는 폐기 — 항목3
- `regime_gate`·`regime_entry_blocked`·`_gate_note` 는 "너무 보수적"(진입 차단·밸류에이션 부담 판정 과함)이라 **삭제**됐다. 종목 번들·워치리스트·리포트 어디도 국면 커트로 신규진입을 판정하지 않는다.
- 국면은 현금비중(역발상)만 남는다(매크로 대시보드가 표시). 종목의 raw PER/PBR·`valuation_label`(자기과거 avg_per 기준)은 **정량 데이터로 그대로 유지**(국면 커트가 아니라 종목 자기 이력 기준).
- 구조화 리포트의 `국면정합성` 필드는 **LLM 이 국면명 + 권장 현금비중을 제시받아 '최종 적합성'을 서술**(chat/report.py::_regime_block) — 게이트 상한 판정이 아니다.

## 기술적 지표
- RSI = **Wilder 평활**(period=14) — 차트(klinecharts)의 RSI 와 같은 기법으로 마지막 값 일치. 캔들 < period+1 → None. 전량 상승→100 / 전량 하락→0.
- ma20_gap 현재가는 **라이브 valuation.price**(캔들 종가 아님). 52주 위치는 valuation(inquire_price) w52 를 권위로, chart 는 결측 시 폴백만.

## 고지로 이동평균선 대순환 (`_ma_grand_cycle`)
- 3 SMA(단기5/중기20/장기40 = `GRAND_CYCLE_MA_PERIODS`, 일봉 표준)의 **상→하 배열 순서**로 6단계 국면을 판정하는 결정적 지표(3! = 6 순열). 사이클 1→2→3→4→5→6→1. `_stage_of(s,m,l)`가 순수 분류(동률·결측 → None, 억지 판정 금지). 라벨(name/arrangement/phase)은 `constants.GRAND_CYCLE_STAGES` **SSOT**.
- `_ma_grand_cycle(closes)` 입력은 `_sorted_closes`(date 오름차순 종가). **`len < 40`(장기) → None**(graceful; build_stock_summary 가 `closes` 있을 때만 사유 note, 빈 차트는 침묵). 반환: stage/stage_name/arrangement/phase·ma{short,medium,long}·periods·`band_width_pct`((단기−장기)/장기×100)·`band_direction`(전환창 `GRAND_CYCLE_TRANSITION_WINDOW`=20봉 전 **절대폭** 대비 확대/축소/유지)·`bars_in_stage`(현재 단계 연속 봉수, 장기계산 가능 전 구간 기준)·`prev_stage`(직전 전환 단계).
- **band_width_pct 는 상대(%) 측정** — 단순 선형·2차 가속 상승은 상대격차가 오히려 좁아질 수 있다(테스트가 이 함정을 반영: 확대 검증은 평탄→급등 국면으로). 100봉이면 40+20=60봉으로 충분해 페이지네이션 불요.
- **판정은 코드, 서술은 프론트/LLM**: 엔진은 구조화 필드만 반환(산문 없음). 6단계 서술 문장은 `frontend/src/lib/grandCycle.js`가 조립하고 면책은 컴포넌트 고정. 라이브 검증(005930): stage 4(역배열)·band −14.7%·전환 3→4 정합.
- **스테이지 시계열 세그먼트(`stage_segments`) — 차트 하단 리본용**: `_ma_grand_cycle(closes, dates=None)` 이 `dates` 를 받으면 `_grand_cycle_segments(dated_closes, periods)`(순수)로 **연속 동일 단계 구간**을 `[{stage, start_date, end_date}]`(날짜 키·시간 오름차순)로 낸다. 각 봉을 `_stage_at` 로 분류해 같은 단계 런을 묶고, None(봉<40·동률)은 런을 끊는다(구간 미포함). **날짜 키**라 프론트 캔들 정렬/결측 차이에 안전(klinecharts timestamp 로 위치). `dates` 없으면 `stage_segments=[]`(하위호환). `build_stock_summary` 가 `_sorted_dated_closes`(신규, `_sorted_closes` 를 이걸로 파생)로 (date,close)를 뽑아 dates 를 넘긴다 → **`ma_grand_cycle` 하위 키로만 추가**(build 최상위 10키 계약 불변). 마지막 세그먼트 stage == 현재 stage(리본 '현재' 표시 근거). 판정=코드, 노출·그룹핑만(LLM 0).
- **`stage_segments_for_chart(chart)`**(public): 임의 차트(candles)에서 스테이지 구간+현재단계만 계산 → `{stage_segments, current_stage}`. `_sorted_dated_closes`+`_grand_cycle_segments` 재사용(동일 SSOT·순수·결정적). **선택형 차트 라우트**(`GET /api/detail/{ticker}/chart` 일봉/주봉·기간)가 **표시 시계열로 리본을 재계산**할 때 쓴다 — 대순환은 timeframe 무관 유효(주봉=주봉 대순환·10년=10년 단계 이력). 봉<40·빈 차트 graceful. **정량 요약(build_stock_summary)은 번들[일봉]에 pin** — 차트 탐색이 판정을 바꾸지 않는다.

## 테스트
- `tests/unit/stock/test_summary.py` (콜로케이트 아님 — 프로젝트 규약 `tests/unit/{module}/`). 경계 전량 Red-first. `_valuation_label`/`_cagr`/`_rsi` 는 private 이지만 경계 검증 위해 직접 import 테스트.
