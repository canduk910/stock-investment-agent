"""네이버 금융 리서치 — 종목분석 리포트 목록 수집 + PDF 다운로드(조회/색인 전용).

finance.naver.com/research/company_list.naver 는 SSR HTML(`table.type_1`)·**EUC-KR**(meta는
utf-8이라 속음)이다. 목록만으로 {종목·코드·제목·증권사·PDF URL·작성일·nid} 전부 추출(상세 불필요).
robots.txt /research/ 허용. **예의 크롤링**(UA·페이지 간 지연·top-N 소량). 리포트는 각 증권사
**저작물** → 개인·교육용 요약에만 쓰고 원문 전체 재배포·커밋 금지(PDF 는 gitignore).
인코딩 처리는 collectors/stock_master.py(cp949 decode) 패턴 재사용.
"""
from __future__ import annotations

import os
import time
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

_RESEARCH_BASE = "https://finance.naver.com/research"
_UA = "Mozilla/5.0 (compatible; dk-invest-agent/edu)"
_PAGE_DELAY = 0.5  # 페이지 간 지연(예의 크롤링)

# 카테고리 → (목록 URL 파일, 종목 컬럼 유무). 종목분석은 종목(코드) 컬럼이 있고, 시황/투자정보/
# 경제분석은 시장 전체 리포트라 종목 컬럼이 없다(라이브 확인: market_info/invest/economy = 5칸).
_CATEGORIES = {
    "company": ("company_list.naver", True),   # 종목분석
    "market": ("market_info_list.naver", False),  # 시황정보(마켓 아웃룩)
    "invest": ("invest_list.naver", False),    # 투자정보
    "economy": ("economy_list.naver", False),  # 경제분석
}


def _qs_param(href: str | None, key: str) -> str | None:
    if not href:
        return None
    return parse_qs(urlparse(href).query).get(key, [None])[0]


def _parse_list_html(html: str, *, has_stock: bool = True) -> list[dict]:
    """리서치 목록 HTML → 리포트 dict 리스트. 첨부(PDF) 없는 행·헤더 행은 제외.

    has_stock=True(종목분석): [종목(a,code)·제목(a,nid)·증권사·첨부(pdf)·작성일·조회수](6칸).
    has_stock=False(시황/투자/경제): [제목(a,nid)·증권사·첨부(pdf,class=file)·작성일·조회수](5칸),
      종목 없음(시장 전체) → stock_name/stock_code=None.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="type_1")
    if not table:
        return []
    # 컬럼 인덱스(종목 유무로 오프셋 결정).
    if has_stock:
        min_cols, i_title, i_broker, i_pdf, i_date = 6, 1, 2, 3, 4
    else:
        min_cols, i_title, i_broker, i_pdf, i_date = 4, 0, 1, 2, 3
    out: list[dict] = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < min_cols:
            continue  # 헤더/구분 행
        a_title = tds[i_title].find("a")
        a_pdf = tds[i_pdf].find("a")
        if not (a_title and a_pdf):
            continue  # 제목/첨부 중 하나라도 없으면 skip
        pdf_url = a_pdf.get("href")
        if not (pdf_url and pdf_url.lower().endswith(".pdf")):
            continue
        if has_stock:
            a_stock = tds[0].find("a")
            if not a_stock:
                continue
            stock_name = a_stock.get_text(strip=True)
            stock_code = _qs_param(a_stock.get("href"), "code")
        else:
            stock_name = None
            stock_code = None
        out.append(
            {
                "stock_name": stock_name,
                "stock_code": stock_code,
                "title": a_title.get_text(strip=True),
                "nid": _qs_param(a_title.get("href"), "nid"),
                "broker": tds[i_broker].get_text(strip=True),
                "pdf_url": pdf_url,
                "date": tds[i_date].get_text(strip=True),
            }
        )
    return out


def fetch_reports(
    category: str = "company", limit: int = 20, pages: int = 1, *, timeout: int = 15
) -> list[dict]:
    """카테고리 리서치 목록(최신순) → 최대 limit 개. 미지원 카테고리·네트워크 실패는 graceful.

    category: company(종목분석)·market(시황)·invest(투자정보)·economy(경제분석).
    시황/투자/경제 리포트는 종목이 없어 stock_code=None 이다(다운스트림 graceful 처리 필요).
    """
    cfg = _CATEGORIES.get(category)
    if cfg is None:
        return []
    url_file, has_stock = cfg
    url = f"{_RESEARCH_BASE}/{url_file}"
    reports: list[dict] = []
    for page in range(1, max(1, pages) + 1):
        try:
            resp = requests.get(
                url, params={"page": page}, headers={"User-Agent": _UA}, timeout=timeout
            )
            resp.raise_for_status()
            html = resp.content.decode("euc-kr", errors="replace")  # cp949(stock_master 패턴)
        except Exception:
            break
        rows = _parse_list_html(html, has_stock=has_stock)
        if not rows:
            break
        reports.extend(rows)
        if len(reports) >= limit:
            break
        time.sleep(_PAGE_DELAY)  # 예의 크롤링
    return reports[:limit]


def fetch_company_reports(limit: int = 20, pages: int = 1, *, timeout: int = 15) -> list[dict]:
    """종목분석 리포트 목록(하위호환 wrapper) → fetch_reports('company', ...)."""
    return fetch_reports("company", limit=limit, pages=pages, timeout=timeout)


def download_pdf(url: str, dest_dir: str = "reports/naver", *, timeout: int = 20) -> str | None:
    """PDF 다운로드 → dest_dir/파일명(경로 반환). 실패는 graceful None. 조회 전용(저작물 개인용)."""
    if not (url and url.lower().endswith(".pdf")):
        return None
    try:
        os.makedirs(dest_dir, exist_ok=True)
        name = os.path.basename(urlparse(url).path) or "report.pdf"
        path = os.path.join(dest_dir, name)
        resp = requests.get(url, headers={"User-Agent": _UA}, timeout=timeout)
        resp.raise_for_status()
        with open(path, "wb") as f:
            f.write(resp.content)
        return path
    except Exception:
        return None
