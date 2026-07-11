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

_BASE = "https://finance.naver.com/research/company_list.naver"
_UA = "Mozilla/5.0 (compatible; dk-invest-agent/edu)"
_PAGE_DELAY = 0.5  # 페이지 간 지연(예의 크롤링)


def _qs_param(href: str | None, key: str) -> str | None:
    if not href:
        return None
    return parse_qs(urlparse(href).query).get(key, [None])[0]


def _parse_list_html(html: str) -> list[dict]:
    """리서치 목록 HTML → 리포트 dict 리스트. 첨부(PDF) 없는 행·헤더 행은 제외."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="type_1")
    if not table:
        return []
    out: list[dict] = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 6:
            continue  # 헤더/구분 행
        a_stock = tds[0].find("a")
        a_title = tds[1].find("a")
        a_pdf = tds[3].find("a")
        if not (a_stock and a_title and a_pdf):
            continue  # 종목/제목/첨부 중 하나라도 없으면 skip
        pdf_url = a_pdf.get("href")
        if not (pdf_url and pdf_url.lower().endswith(".pdf")):
            continue
        out.append(
            {
                "stock_name": a_stock.get_text(strip=True),
                "stock_code": _qs_param(a_stock.get("href"), "code"),
                "title": a_title.get_text(strip=True),
                "nid": _qs_param(a_title.get("href"), "nid"),
                "broker": tds[2].get_text(strip=True),
                "pdf_url": pdf_url,
                "date": tds[4].get_text(strip=True),
            }
        )
    return out


def fetch_company_reports(limit: int = 20, pages: int = 1, *, timeout: int = 15) -> list[dict]:
    """종목분석 리포트 목록(최신순) → 최대 limit 개. 네트워크 실패는 graceful(수집분까지)."""
    reports: list[dict] = []
    for page in range(1, max(1, pages) + 1):
        try:
            resp = requests.get(
                _BASE, params={"page": page}, headers={"User-Agent": _UA}, timeout=timeout
            )
            resp.raise_for_status()
            html = resp.content.decode("euc-kr", errors="replace")  # cp949(stock_master 패턴)
        except Exception:
            break
        rows = _parse_list_html(html)
        if not rows:
            break
        reports.extend(rows)
        if len(reports) >= limit:
            break
        time.sleep(_PAGE_DELAY)  # 예의 크롤링
    return reports[:limit]


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
