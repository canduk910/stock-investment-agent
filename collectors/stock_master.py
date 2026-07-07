"""종목 마스터(코스피·코스닥) 로딩·검색 — 종목명 자동완성용.

KIS 는 종목명 검색 API 를 주지 않는다. 대신 공개 마스터 파일(kospi_code.mst /
kosdaq_code.mst)을 내려받아 파싱해 전 종목(코드·이름·시장) 목록을 만든다.

## .mst 포맷 (라이브 검증: 005930→삼성전자, 247540→에코프로비엠)
고정폭 EUC-KR(cp949). 한 행:
- `row[0:9].strip()` = 단축코드(6자리 종목코드)
- `row[9:21]`        = 표준코드(ISIN)
- `row[21:len-TAIL].strip()` = 한글 종목명 (뒤 TAIL 바이트는 고정 필드 묶음)
  - **KOSPI TAIL=228, KOSDAQ TAIL=222** (시장별로 다름 — 라이브 검증값).

시세·현재가가 아니므로 캐시 금지 원칙과 무관(정적 참조 데이터). 로컬 JSON 으로 하루 캐시.
"""
from __future__ import annotations

import io
import json
import os
import time
import zipfile

import requests

_BASE = "https://new.real.download.dws.co.kr/common/master"
KOSPI = {"url": f"{_BASE}/kospi_code.mst.zip", "tail": 228, "market": "KOSPI"}
KOSDAQ = {"url": f"{_BASE}/kosdaq_code.mst.zip", "tail": 222, "market": "KOSDAQ"}

DEFAULT_CACHE_PATH = ".cache/stock_master.json"
DEFAULT_TTL_SECONDS = 24 * 3600  # 마스터는 신규상장 때만 바뀜 → 하루 캐시


def parse_master(text: str, tail: int, market: str) -> list[dict]:
    """.mst 텍스트 → [{ticker, name, market}]. 6자리 종목코드 + 이름 있는 행만(선물 등 제외)."""
    out = []
    for row in text.splitlines():
        if len(row) < 21 + tail:
            continue
        ticker = row[0:9].strip()
        name = row[21 : len(row) - tail].strip()
        if len(ticker) == 6 and ticker.isalnum() and name:
            out.append({"ticker": ticker, "name": name, "market": market})
    return out


def _fetch_market(spec: dict, timeout: int = 30) -> list[dict]:
    """마스터 zip 다운로드 → 압축 해제 → cp949 디코드 → 파싱."""
    resp = requests.get(spec["url"], timeout=timeout)
    resp.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    raw = zf.read(zf.namelist()[0]).decode("cp949", errors="replace")
    return parse_master(raw, spec["tail"], spec["market"])


def _fetch_all() -> list[dict]:
    """코스피 + 코스닥 전 종목."""
    return _fetch_market(KOSPI) + _fetch_market(KOSDAQ)


def load_stock_master(
    cache_path: str = DEFAULT_CACHE_PATH,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    fetcher=_fetch_all,
    now=time.time,
) -> list[dict]:
    """캐시가 신선하면 로컬 JSON, 아니면 마스터를 내려받아 파싱 후 캐시.

    fetcher/now 주입으로 테스트에서 네트워크·시계를 대체한다.
    """
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                cached = json.load(f)
            if now() - cached.get("as_of", 0) < ttl_seconds and cached.get("stocks"):
                return cached["stocks"]
        except (json.JSONDecodeError, OSError):
            pass  # 손상 캐시 → 재수집

    stocks = fetcher()
    try:
        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"as_of": now(), "stocks": stocks}, f, ensure_ascii=False)
    except OSError:
        pass  # 캐시 실패는 치명적 아님(다음 요청에 재수집)
    return stocks


def search_stocks(master: list[dict], query: str, limit: int = 10) -> list[dict]:
    """종목명/코드 검색(순수). 숫자면 코드 prefix, 아니면 이름 prefix 우선 + 부분일치.

    정렬: prefix 먼저 → 부분일치. 각 그룹은 (코스피 먼저, 이름 오름차순). 최대 limit 개.
    """
    q = (query or "").strip()
    if not q:
        return []

    def _rank(items):
        # 짧은 이름 우선 → 정식 종목(예 "SK하이닉스")이 파생상품("KODEX SK하이닉스레버리지")보다 먼저.
        # 그다음 코스피 먼저, 이름 오름차순.
        return sorted(items, key=lambda s: (len(s["name"]), s["market"] != "KOSPI", s["name"]))

    if q.isdigit():
        hits = [s for s in master if s["ticker"].startswith(q)]
        return _rank(hits)[:limit]

    ql = q.lower()
    prefix = [s for s in master if s["name"].lower().startswith(ql)]
    contains = [
        s for s in master if ql in s["name"].lower() and not s["name"].lower().startswith(ql)
    ]
    return (_rank(prefix) + _rank(contains))[:limit]
