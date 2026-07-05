# cache/ — 캐시 레이어 (3원칙을 구조로 강제)

> 규칙이 아니라 코드 구조로 3원칙을 강제하는 게 핵심.

- **원칙1 (현재가 캐시 금지)**: 현재가는 **캐시 네임스페이스 자체가 없다.** `is_cacheable`가 화이트리스트(`macro:` / `stock:meta:` / `kis:token:`) 밖의 키(`stock:price:` 등)를 `CachePolicyError`로 거부한다. 현재가 어댑터에는 애초에 cache 인자를 주지 않는다(시그니처로 강제).
- **원칙2 (실패 응답 캐시 금지)**: `cache_if_clean`이 `value["partial_failure"]`가 비어있지 않으면 `set`을 생략한다. **fetch 결과의 유일한 저장 게이트**가 이 함수다.
- **원칙3 (프리웜)**: P2, 인터페이스만.

## 계약/전환
- `base.py`의 `Cache` Protocol은 **ElastiCache/DynamoDB 호환 시그니처**(문자열 키 + TTL)로 설계 — 로컬(`LocalCache`/`FileCache`) → Redis/Dynamo 전환은 **구현체 교체만**, 로직은 안 건드린다.
- 예외: `auth.py`의 토큰 저장은 `cache_if_clean`을 우회한 직접 `cache.set`(단 `is_cacheable` 가드 통과 후). 토큰엔 `partial_failure` 개념이 없어 허용되는 유일한 예외.
- `LocalCache`/`FileCache`는 `clock` 주입으로 TTL을 결정적으로 테스트한다.
