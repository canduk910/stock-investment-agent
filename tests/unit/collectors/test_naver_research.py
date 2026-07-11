"""네이버 리서치 수집기 테스트 — 목록 파싱 + cp949 디코딩 + graceful(외부 요청 mock)."""
from __future__ import annotations

from collectors import naver_research
from collectors.naver_research import _parse_list_html, download_pdf, fetch_company_reports

# 실제 구조 반영 fixture: 헤더 행 + 유효 행(첨부 O) + 첨부 없는 행(skip 대상).
_HTML = """
<table class="type_1">
  <tr><th>종목명</th><th>제목</th><th>증권사</th><th>첨부</th><th>작성일</th><th>조회수</th></tr>
  <tr>
    <td><a href="/item/main.naver?code=006360">GS건설</a></td>
    <td><a href="company_read.naver?nid=94082&page=1">확실한 투자포인트가 붙었다</a></td>
    <td>한화투자증권</td>
    <td class="file"><a href="https://stock.pstatic.net/stock-research/company/16/20260710_company_149419000.pdf"><img></a></td>
    <td class="date">26.07.10</td>
    <td class="date">1234</td>
  </tr>
  <tr>
    <td><a href="/item/main.naver?code=000660">SK하이닉스</a></td>
    <td><a href="company_read.naver?nid=94000">첨부 없는 리포트</a></td>
    <td>미래증권</td>
    <td class="file"></td>
    <td class="date">26.07.09</td>
    <td class="date">99</td>
  </tr>
</table>
"""


class _FakeResp:
    def __init__(self, content=b"", status_ok=True):
        self.content = content
        self._ok = status_ok

    def raise_for_status(self):
        if not self._ok:
            raise Exception("HTTP error")


def test_parse_list_html_extracts_and_skips_no_attachment():
    rows = _parse_list_html(_HTML)
    assert len(rows) == 1  # 첨부 없는 행은 제외
    r = rows[0]
    assert r["stock_name"] == "GS건설"
    assert r["stock_code"] == "006360"
    assert r["title"] == "확실한 투자포인트가 붙었다"
    assert r["nid"] == "94082"
    assert r["broker"] == "한화투자증권"
    assert r["pdf_url"].endswith("20260710_company_149419000.pdf")
    assert r["date"] == "26.07.10"


def test_parse_empty_when_no_table():
    assert _parse_list_html("<html><body>no table</body></html>") == []


def test_fetch_decodes_cp949_and_limits(monkeypatch):
    # 네이버는 euc-kr — content 를 euc-kr 바이트로 주고 한글이 깨지지 않는지 + limit.
    encoded = _HTML.encode("euc-kr")
    monkeypatch.setattr(
        naver_research.requests, "get", lambda *a, **k: _FakeResp(encoded)
    )
    out = fetch_company_reports(limit=5, pages=1)
    assert len(out) == 1
    assert out[0]["stock_name"] == "GS건설"  # cp949 디코딩 정상
    assert out[0]["broker"] == "한화투자증권"


def test_fetch_graceful_on_network_error(monkeypatch):
    def _boom(*a, **k):
        raise Exception("network down")

    monkeypatch.setattr(naver_research.requests, "get", _boom)
    assert fetch_company_reports(limit=5) == []  # 예외 대신 빈 리스트


def test_download_pdf_rejects_non_pdf():
    assert download_pdf("https://example.com/not-a-pdf") is None
    assert download_pdf("") is None


def test_download_pdf_saves(monkeypatch, tmp_path):
    monkeypatch.setattr(
        naver_research.requests, "get", lambda *a, **k: _FakeResp(b"%PDF-1.4 fake")
    )
    path = download_pdf(
        "https://stock.pstatic.net/stock-research/company/16/x_company_1.pdf",
        dest_dir=str(tmp_path),
    )
    assert path and path.endswith("x_company_1.pdf")
    with open(path, "rb") as f:
        assert f.read().startswith(b"%PDF")


def test_download_pdf_graceful_on_error(monkeypatch, tmp_path):
    monkeypatch.setattr(
        naver_research.requests, "get", lambda *a, **k: _FakeResp(b"", status_ok=False)
    )
    assert download_pdf("https://x/a.pdf", dest_dir=str(tmp_path)) is None
