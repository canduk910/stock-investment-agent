"""보통주 유니버스 필터 — 종목 마스터(코스피+코스닥)에서 보통주만 남긴다(순수·결정적).

전체 유니버스 대순환 스캔의 대상 종목을 확정한다. 마스터(`collectors.stock_master`)는
`{ticker, name, market}` 3필드뿐(시총/증권종류 없음)이라 **코드 규칙 + 이름 휴리스틱**으로
보통주를 가려낸다:

1. 우선주 제외 — KRX 보통주 코드는 관용적으로 **끝자리 0**(우선주/신형우선주는 5/7/9/K 등).
   `ticker[-1] != "0"` 이면 우선주로 보고 제외(코드 규칙 1차 필터).
2. ETF/ETN/스팩/리츠 제외 — 이름이 ETF/ETN 운용사 브랜드로 **시작**하거나(예 "KODEX 200"),
   이름에 스팩/ETN/선물/레버리지/인버스/채권/리츠 키워드를 **포함**하면 제외.

판정은 순수 문자열/코드 규칙(LLM·랜덤 0). 필터 상수는 SSOT 로 두어 조정 가능하게 하고,
**과필터보다 명확한 제외 위주(보수적)** — 애매하면 남긴다. 결과 대략 1,800~2,200종목 예상.
"""
from __future__ import annotations

# 보통주 코드 끝자리(KRX 관용). 우선주/신형우선주/기타 클래스는 5·7·9·K 등으로 끝난다.
COMMON_STOCK_LAST_DIGIT = "0"

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


def is_common_stock(stock: dict) -> bool:
    """단일 종목이 보통주인지(순수). 코드 끝자리 + 이름 휴리스틱으로 판정."""
    ticker = (stock.get("ticker") or "").strip()
    name = (stock.get("name") or "").strip()
    if len(ticker) != 6 or ticker[-1] != COMMON_STOCK_LAST_DIGIT:
        return False  # 우선주·비정상 코드 제외(코드 규칙)
    if not name:
        return False
    upper = name.upper()
    if any(upper.startswith(brand) for brand in ETF_BRANDS):
        return False  # ETF/ETN 브랜드로 시작 → 제외
    if any(upper.startswith(brand + " ") for brand in ETF_BRANDS_SPACED):
        return False  # 접두 애매 브랜드(BNK/TIME/WON)는 공백 뒤에만 → 정식 종목(BNK금융지주) 보존
    if any(kw in upper for kw in NAME_EXCLUDE_KEYWORDS):
        return False  # 스팩/파생형/리츠/액티브 키워드 포함 → 제외
    return True


def common_stocks(master: list[dict]) -> list[dict]:
    """마스터 → 보통주만(입력 순서 보존·`{ticker,name,market}` 그대로). 순수·결정적."""
    return [s for s in (master or []) if is_common_stock(s)]
