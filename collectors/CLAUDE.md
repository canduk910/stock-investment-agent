# collectors/ — 외부 데이터 수집 계층

> 코드에서 자명하지 않은 것만 기록. 구조·구현은 소스를 볼 것.

## KIS 어댑터 (kis/)
- **조회 전용.** 매매 주문(order/buy/sell) 계열은 절대 만들지 않는다(플랜 원칙 1).
- **KIS 코드는 기억으로 쓰지 않는다.** TR_ID·파라미터·응답 필드명은 재현 불가 → `kis-code-assistant` MCP로 검증 코드를 받아 어댑터화한다(`kis-data-pipeline` 스킬).
- **오류 표면화**: KIS는 실패해도 HTTP 200 + `rt_cd != "0"`(+`msg_cd`/`msg1`)로 응답한다. `client.get`이 이를 `KisApiError`로 던진다(`errors.py`). `rt_cd`는 문자열 비교, 부재(None)는 통과(토큰/웹소켓 응답 대비). 이 검사가 없으면 실패 body가 normalize에서 전 필드 조용한 None이 되어 잡히지 않는다.
- **토큰(auth.py)**: 24h 유효. KIS가 재발급을 분당 1회 수준으로 제한(EGW00133) → 만료 <1h일 때만 재발급. single-flight 락 + double-checked locking(동시 스탬피드 차단) + 거절 시 유효 토큰 폴백 + **60s backoff**(순차 재시도 폭주 차단). **한계**: threading.Lock은 in-process 전용 — 다중 프로세스/Lambda는 각자 1회 발급 가능(배포 시 분산 락 필요).
- **라이브 확정 필드명**(추측 아님): `intstock_multprice` → `inter_shrn_iscd`/`inter2_prpr`/`prdy_ctrt`. `quote` 등락률 → `antc_cntg_prdy_ctrt`(예상체결 전일대비율).

## 지표 수집기 (fred/vix/fear_greed)
- 공통 반환 계약 **`IndicatorPoint = {key, value, as_of, source, prev_value}`**(`base.py`). 소비자(quant·api)가 이 shape에 의존.
- **VIX**: 야후 `^VIX` 1차 → 실패 시 FRED `VIXCLS` 폴백. `source`에 성공 소스 기록.
- **fear_greed**: 실패 시 예외 대신 `None` 반환(파이프라인 안 죽임). `fear_and_greed`를 **지연 import** — import 시 `requests_cache`를 전역 설치해 다른 테스트의 HTTP mock을 오염시키기 때문.
- **`fetch_gdp`는 미국 GDP** — 버핏지수는 KRX 시총 ÷ 한국 GDP라 이대로면 무의미. 한국 GDP 소스 교체가 남은 과제(W07 지표 확장 시).

## 집계
- `macro_snapshot.collect_macro_indicators` = ThreadPool 병렬 + `partial_failure`(§5.1 번들 패턴). 한 소스가 죽어도 나머지는 채운다.
