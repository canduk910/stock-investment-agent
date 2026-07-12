# collectors/ — 외부 데이터 수집 계층

> 코드에서 자명하지 않은 것만 기록. 구조·구현은 소스를 볼 것.

## KIS 어댑터 (kis/)
- **조회 전용.** 매매 주문(order/buy/sell) 계열은 절대 만들지 않는다(플랜 원칙 1).
- **KIS 코드는 기억으로 쓰지 않는다.** TR_ID·파라미터·응답 필드명은 재현 불가 → `kis-code-assistant` MCP로 검증 코드를 받아 어댑터화한다(`kis-data-pipeline` 스킬).
- **오류 표면화**: KIS 실패는 두 형태 — (a) HTTP 200 + `rt_cd != "0"`, (b) **HTTP 5xx**(게이트웨이/유량/토큰 무효). `client.get`이 **두 경우 모두** body의 `msg_cd/msg1/status`를 `KisApiError`로 표면화한다(`errors.py`) + WARNING 로깅(토큰/appkey 미출력). ⚠ `raise_for_status()`로 5xx 본문을 버리면 "왜 500인지"(예: `EGW00123` 만료토큰)를 못 봐 진단이 막힌다 — **본문을 먼저 읽는다**(비-JSON 5xx는 status+스냅샷). `rt_cd`는 문자열 비교, 부재(None)는 통과.
- **재시도(client.get)**: 전이성 5xx·유량(`EGW00201`)은 짧은 지수 backoff로 최대 3회 재시도(자가치유). 인증/파라미터는 비재시도(즉시 표면화). `_SLEEP`은 테스트 patch용 간접참조.
- **토큰 자가치유(★근본원인 회귀 방지)**: 캐시 토큰이 **외부 재발급 등으로 KIS에서 무효화**되면(우리 `expires_at`이 미래여도) 데이터 호출이 `EGW00123`(만료)/`EGW00121`(무효)로 거절된다. 같은 죽은 토큰 재시도는 무의미 → `client.get`이 이 코드를 감지해 **`provider(stale_token=죽은토큰)`로 강제 재발급** 후 재시도. `auth.get_token`은 stale_token이 오면 재사용 검사를 건너뛰고 재발급하되 **캐시에 이미 다른(새) 토큰이 있으면 그걸 사용**(동시 재발급 방지), 강제 재발급 실패는 죽은 토큰 폴백 없이 전파. (같은 appkey를 여러 프로젝트가 공유하면 서로 토큰을 무효화하니 **앱키 분리 권장**.)
- **토큰 캐시는 app_key 별 격리**(유저별 KIS 키): `cache.keys.kis_token_key(env, app_key)` = `kis:token:{env}:{sha256(app_key)[:12]}`(원문 미노출·`kis:token:` 프리픽스 유지로 정책 통과). `auth.get_token`/`_REFRESH_LOCKS`/`_LAST_REFRESH_FAILURE` 모두 이 캐시 키 단위 — 유저 A·B 키가 서로 토큰을 밟지 않는다. 클라이언트 조립은 env 가 아니라 `api.detail.resolve_kis_client(user, db)`(본인 등록키→공유→env)로 해석된 자격증명을 받는다(`_build_kis_client`=env 하위호환). 자가치유·backoff·single-flight 로직은 키 세분화만 하고 불변.
- **토큰(auth.py)**: 24h 유효. KIS가 재발급을 분당 1회 수준으로 제한(EGW00133) → 만료 <1h일 때만 재발급. single-flight 락 + double-checked locking(동시 스탬피드 차단) + 거절 시 유효 토큰 폴백 + **60s backoff**(순차 재시도 폭주 차단). **한계**: threading.Lock은 in-process 전용 — 다중 프로세스/Lambda는 각자 1회 발급 가능(배포 시 분산 락 필요).
- **라이브 확정 필드명**(추측 아님): `intstock_multprice` → `inter_shrn_iscd`/`inter2_prpr`/`prdy_ctrt`. `quote` 등락률 → `antc_cntg_prdy_ctrt`(예상체결 전일대비율).
- **W08 종목 어댑터 3종**(MCP 검증): `inquire_price`(FHKST01010100, `/quotations/inquire-price`, 단일 output — 현재가·`per`·`w52_hgpr`/`w52_lwpr`·`hts_avls`), `finance_income_statement`(FHKST66430200, `/finance/income-statement`), `finance_financial_ratio`(FHKST66430300, `/finance/financial-ratio`). 재무 2종 output은 **리스트(행 1개면 단일 dict로 오는 변형** → `normalize._output_rows`가 리스트화). ROE는 `roe_val`.
  - **⚠ 재무 API params 키 대소문자 혼합**(MCP 확정, 추측 통일 금지): `FID_DIV_CLS_CODE`만 대문자, `fid_cond_mrkt_div_code`·`fid_input_iscd`는 소문자. 통일하면 KIS가 파라미터 오류를 낸다.
  - **inquire_price는 캐시 금지**(현재가·PER·52주 라이브 → cache 인자 없음, 원칙1). 재무·basic메타만 캐시 대상.
  - **[2026-07-07 라이브 검증 통과]** `tests/live/test_live_stock_bundle.py` 4게이트(real 키, 삼성전자 005930): 재무 히스토리 **23년**, EPS/주가 조정기준 일치(PER_year 자릿수 튐 없음), 재무 API **real 정상**, 일봉 **100/회**(6개월 창은 ~100 상한 → 더 길면 페이지네이션 P2). 결과: `constants.AVG_PER_VERIFIED=True`(엔진이 avg_per/valuation_label 산출). 어댑터 조정기준/소스 변경 시 재검증.
  - **재무 응답에 분기 interim 혼입**(예 `202603`이 연간 12월과 섞임) → 엔진 `_recent_annual_periods`가 최빈 결산월 연간만 최근 5년으로 필터(CAGR/avg_per 왜곡 방지).
- **W08 예측실적 어댑터** `estimate_perform`(HHKST668300C0, `/quotations/estimate-perform`, 리서치본부 월간 ~160종목·real전용): 예측 PER/EPS 원천. **응답 구조는 "행=지표, 열 data1~5=연도"**(흔한 "행=연도" 아님). `output4[i].dt`가 열 라벨('E'=추정) → **하드코딩 금지, output4로 동적 매핑**. `output2`=손익 6행(r0 매출·r2 영업이익·r4 순이익, 억원), `output3`=투자지표 ≤8행(r1 EPS·r3 PER, **÷10 스케일**; PBR 없음). ⚠ `output1` 한글 라벨과 kis-code-assistant MCP `COLUMN_MAPPING`은 ELW 템플릿 복붙 오류라 **사용 금지** — 실제 필드명(name1=애널리스트·estdate·rcmd_name)으로 읽는다. output3 행수는 종목마다 다름(은행 0행 등) → 부재 graceful. `normalize_estimate_perform`이 이 전부를 흡수. SHT_CD는 'A' 없이 6자리.

## 종목 마스터 (stock_master.py) — 자동완성용
- KIS 는 **종목명 검색 API 가 없다**(확인). 대신 공개 마스터 파일을 파싱해 전 종목 목록을 만든다: `https://new.real.download.dws.co.kr/common/master/{kospi,kosdaq}_code.mst.zip`.
- **고정폭 EUC-KR(cp949) 포맷**(라이브 검증): `row[0:9].strip()`=6자리 종목코드, `row[9:21]`=ISIN, `row[21:len-TAIL].strip()`=한글명. **TAIL: KOSPI=228 / KOSDAQ=222**(시장별 다름). 6자리 코드 + 이름 있는 행만(선물 등 제외).
- 시세 아님(정적 참조) → `.cache/stock_master.json`로 **하루 캐시**(신규상장 때만 변동). 캐시 정책(현재가 금지)과 무관.
- `search_stocks`: 숫자=코드 prefix, 문자=이름 prefix 우선+부분일치. **랭킹은 이름 길이순** — 정식 종목("SK하이닉스")이 파생상품("KODEX SK하이닉스레버리지")보다 먼저. 소비: `GET /api/stocks/search?q=&limit=`(api/stocks.py, 프로세스 메모리 1회 로드).

## 네이버 애널리스트 리포트 (naver_research.py)
- 소스 `finance.naver.com/research/company_list.naver` = **SSR HTML**(JS 불필요)·**robots `/research/` 허용**·**EUC-KR(cp949)**(응답 `meta`는 utf-8이라 속으므로 `resp.content.decode("euc-kr")` — stock_master 와 동일 패턴, `resp.text` 금지). 파싱은 bs4 `table.type_1` → 각 `tr`에서 `len(tds)>=6` + 종목링크(`?code=`) + 제목링크(`?nid=`) + 첨부(`.pdf`)를 모두 갖춘 행만. 첨부 없는 행·비종목 행은 제외.
- 반환 dict: `{stock_name, stock_code, title, nid, broker, pdf_url, date}`. **목록만으로 전 필드 확보**(상세페이지 조회 불필요) — 라이브 검증됨(nid·broker·code·pdf_url 실제 채워짐).
- `download_pdf(url, dest_dir="reports/naver")`: `stock.pstatic.net`에서 **직접 다운로드**. 비-`.pdf` URL 거부, UA+timeout, 실패 graceful `None`. PDF는 각 증권사 **저작물** → `reports/` gitignore(원문 재배포 금지, 요약만 제공).
- **예의 크롤링**: UA 지정·페이지 간 지연·top-N 소량. `fetch_company_reports(limit, pages)`는 개별 오류에 graceful(빈 리스트/부분).
- **종목별 수집은 itemCode 필터 필수**(라이브 확인): `company_list.naver`를 파라미터 없이 부르면 **전체 최신 피드**(모든 종목 섞임)라 특정 종목 상세엔 그 종목 리포트가 없기 일쑤 → `fetch_stock_reports(ticker, limit)`가 `?searchType=itemCode&itemName=&itemCode=<ticker>`로 **그 종목만** 받는다(6칸 company 레이아웃 재사용). ticker 빈값·네트워크 실패는 graceful `[]`. `fetch_reports`/`fetch_stock_reports` 모두 공용 `_fetch_list`(page 순회·cp949·graceful) 위임.

## 지표 수집기 (fred/vix/fear_greed)
- 공통 반환 계약 **`IndicatorPoint = {key, value, as_of, source, prev_value}`**(`base.py`). 소비자(quant·api)가 이 shape에 의존.
- **VIX**: 야후 `^VIX` 1차 → 실패 시 FRED `VIXCLS` 폴백. `source`에 성공 소스 기록.
- **fear_greed**: 실패 시 예외 대신 `None` 반환(파이프라인 안 죽임). `fear_and_greed`를 **지연 import** — import 시 `requests_cache`를 전역 설치해 다른 테스트의 HTTP mock을 오염시키기 때문.
- **`fetch_gdp`는 미국 GDP** — 버핏지수는 KRX 시총 ÷ 한국 GDP라 이대로면 무의미. 한국 GDP 소스 교체가 남은 과제(W07 지표 확장 시).

## 집계
- `macro_snapshot.collect_macro_indicators` = ThreadPool 병렬 + `partial_failure`(§5.1 번들 패턴). 한 소스가 죽어도 나머지는 채운다.
