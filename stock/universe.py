"""보통주 유니버스 필터 — 종목 마스터(코스피+코스닥)에서 보통주만 남긴다(순수·결정적).

전체 유니버스 대순환 스캔의 대상 종목을 확정한다. 마스터(`collectors.stock_master`)는
`{ticker, name, market, sec_group}` 를 준다. 우선 순위:

1. **우선주 제외 (코드 규칙, 전 경로 공통)** — KRX 보통주 코드는 관용적으로 **끝자리 0**
   (우선주/신형우선주는 5/7/9/K 등). `ticker[-1] != "0"` 이면 제외. 우선주도 법적으로
   증권그룹은 ST(주권)라 그룹코드로는 안 걸리므로 이 코드 규칙이 여전히 필요하다.
2. **증권그룹구분코드(sec_group) 결정적 필터 (있으면 우선)** — `sec_group == "ST"`(주권)만
   통과하고 ETF(EF)·ETN(EN)·리츠(RT)·ELW(EW)·수익증권(BC)·외국주권(FS)·예탁증서(DR)·
   투자회사(MF)·인프라(IF) 등은 전부 제외한다. 이름 브랜드 휴리스틱의 누수(신생 브랜드
   ETF)와 오탐('메리츠'의 '리츠' 부분일치)을 **결정적으로** 해소한다. **스팩(SPAC)은 법적
   주권이라 sec_group=ST → 그룹코드로 안 잡히므로 이름 '스팩' backstop 을 유지**한다.
3. **폴백 (sec_group 부재 → 이름/코드 휴리스틱)** — 구 캐시·파싱실패로 sec_group 이 None 이면
   기존 이름 브랜드/키워드 휴리스틱으로 판정(하위호환·캐시 미갱신 환경에서도 안전).

판정은 순수 문자열/코드 규칙(LLM·랜덤 0). 필터 상수는 SSOT 로 두어 조정 가능하게 하고,
**과필터보다 명확한 제외 위주(보수적)** — 애매하면 남긴다. 라이브 실측: master 3,927 →
common 2,532(sec_group 결정적: ETF/DR/FS/IF 등 48건 누수 제거 + '리츠' 오탐 2건 복구).
"""
from __future__ import annotations

# 보통주 코드 끝자리(KRX 관용). 우선주/신형우선주/기타 클래스는 5·7·9·K 등으로 끝난다.
COMMON_STOCK_LAST_DIGIT = "0"

# 증권그룹구분코드: 주권(=보통주+우선주, 우선주는 코드 규칙으로 별도 제외). 이 값만 통과.
SECURITY_GROUP_COMMON = "ST"

# ST(주권)이지만 유니버스에서 제외할 이름 backstop — 스팩(SPAC)은 법적 주권이라 그룹코드로
# 안 걸린다. 이름에 이 키워드가 있으면 제외(그룹코드 필터를 보완).
SPAC_NAME_KEYWORDS: tuple[str, ...] = ("스팩",)

# ETF/ETN 운용사 브랜드(프리픽스). 마스터의 ETF/ETN 이름은 브랜드로 시작한다(예 "KODEX 200",
# "TIGER차이나전기차"). 대문자 정규화 후 **startswith** 로 매칭 — 이 브랜드들은 ETF 전용이라
# 보통주(한글명)와 충돌하지 않는다(정식 종목 접두로 안 쓰임). 조정 가능(추가 브랜드는 여기 한 곳).
ETF_BRANDS: frozenset[str] = frozenset(
    {
        "KODEX", "TIGER", "PLUS", "ACE", "SOL", "RISE", "KBSTAR", "ARIRANG",
        "HANARO", "TIMEFOLIO", "KOSEF", "KINDEX", "TREX", "FOCUS", "KIWOOM",
        "TRUSTON", "히어로즈", "마이다스", "마이티", "에셋플러스",
    }
)

# 접두가 **실제 종목명과 겹칠 수 있는** 브랜드는 '브랜드 + 공백'으로만 매칭한다 —
# 예: "BNK 스마트카"(ETF)는 제외하되 "BNK금융지주"(정식 종목)는 보존, "TIME 미국S&P500"(ETF)
# 제외하되 가상의 "TIME..." 종목 오발 방지. 짧고 흔한 접두(BNK/TIME/WON)는 여기.
ETF_BRANDS_SPACED: frozenset[str] = frozenset({"BNK", "TIME", "WON"})

# 이름에 포함되면 제외하는 키워드(부분일치). 스팩/파생형 ETN·ETF·리츠·액티브ETF.
# 리츠는 애매(부동산 상장리츠도 보통주적 성격)하나 스크리너 유니버스에선 일단 제외(조정 가능).
# ⚠ 오탐 주의: "합성"(동남합성 등 화학사)은 단독 금지어로 쓰지 않고 "(합성)"(ETF 합성복제 표기)로만.
NAME_EXCLUDE_KEYWORDS: tuple[str, ...] = (
    "스팩",       # SPAC(기업인수목적회사)
    "ETN",        # 상장지수증권
    "선물",       # 선물 기초 ETN/ETF
    "레버리지",   # 레버리지 ETF/ETN
    "인버스",     # 인버스 ETF/ETN
    "채권",       # 채권 ETF/ETN
    "리츠",       # REIT
    "액티브",     # 액티브 ETF(신생 운용사 브랜드 누수 방어 — 정식 종목명엔 안 쓰임)
    "(합성)",     # 합성복제 ETF(파생형) — 화학사 '합성' 오탐 방지 위해 괄호 포함형만
    "(H)",        # 환헤지 ETF
)


def _passes_name_heuristic(name: str) -> bool:
    """이름 브랜드/키워드 휴리스틱(sec_group 부재 시 폴백). 순수·결정적."""
    upper = name.upper()
    if any(upper.startswith(brand) for brand in ETF_BRANDS):
        return False  # ETF/ETN 브랜드로 시작 → 제외
    if any(upper.startswith(brand + " ") for brand in ETF_BRANDS_SPACED):
        return False  # 접두 애매 브랜드(BNK/TIME/WON)는 공백 뒤에만 → 정식 종목(BNK금융지주) 보존
    if any(kw in upper for kw in NAME_EXCLUDE_KEYWORDS):
        return False  # 스팩/파생형/리츠/액티브 키워드 포함 → 제외
    return True


def is_common_stock(stock: dict) -> bool:
    """단일 종목이 보통주인지(순수). 코드 규칙 → 그룹코드 결정적 → (부재 시)이름 휴리스틱 폴백."""
    ticker = (stock.get("ticker") or "").strip()
    name = (stock.get("name") or "").strip()
    # 1) 코드 규칙(전 경로 공통): 6자리 + 끝자리 0 → 우선주·비정상 코드 제외.
    if len(ticker) != 6 or ticker[-1] != COMMON_STOCK_LAST_DIGIT:
        return False
    if not name:
        return False
    # 2) 증권그룹구분코드가 있으면 결정적 필터(이름 휴리스틱보다 우선).
    sec_group = (stock.get("sec_group") or "").strip().upper()
    if sec_group:
        if sec_group != SECURITY_GROUP_COMMON:
            return False  # ETF/ETN/리츠/ELW/수익증권/외국주권/DR/투자회사/… → 결정적 제외
        # ST(주권)이라도 스팩은 이름 backstop 으로 제외(스팩=법적 주권).
        if any(kw in name for kw in SPAC_NAME_KEYWORDS):
            return False
        return True
    # 3) sec_group 부재(구 캐시·파싱실패) → 이름 브랜드/키워드 휴리스틱 폴백(하위호환).
    return _passes_name_heuristic(name)


def common_stocks(master: list[dict]) -> list[dict]:
    """마스터 → 보통주만(입력 순서 보존·`{ticker,name,market}` 그대로). 순수·결정적."""
    return [s for s in (master or []) if is_common_stock(s)]
