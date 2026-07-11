"""PDF 리포트 인입 — pdfplumber 텍스트 추출 + 표 보존 청킹(강의 W09 아이디어 재구현).

- 텍스트 PDF 대상(pdfplumber, system 패키지 불필요). 스캔/이미지 PDF vision-OCR 폴백은 Phase 2b.
- 청킹은 표(| 포함)를 한 덩어리로 보존(스케일·의미 왜곡 방지), 그 외는 단어 예산으로 분할.
- 추출 실패·빈 PDF 는 예외 대신 빈 결과(파이프라인 안 죽임 — 상위가 graceful).
"""
from __future__ import annotations

import glob
import os

import pdfplumber

# 청크당 최대 단어 수(임베딩 입력·검색 정밀도 균형).
CHUNK_MAX_TOKENS = 400


def chunk_text(text: str, max_tokens: int = CHUNK_MAX_TOKENS) -> list[str]:
    """텍스트를 ~max_tokens 단어 청크로 분할. 표(| 포함 라인)는 빈 줄까지 한 덩어리로 보존."""
    lines = (text or "").split("\n")
    chunks: list[str] = []
    buf: list[str] = []
    count = 0
    in_table = False

    def flush() -> None:
        nonlocal buf, count
        joined = "\n".join(buf).strip()
        if joined:
            chunks.append(joined)
        buf, count = [], 0

    for line in lines:
        if "|" in line:
            in_table = True
        if in_table:
            buf.append(line)
            if not line.strip():  # 빈 줄 = 표 끝
                flush()
                in_table = False
            continue
        n = len(line.split())
        if count + n > max_tokens and buf:
            flush()
        buf.append(line)
        count += n
    flush()
    return chunks


def extract_text(pdf_path: str) -> str:
    """pdfplumber 로 PDF 전 페이지 텍스트 추출(연결). 실패·빈 페이지는 graceful(빈 문자열)."""
    parts: list[str] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    parts.append(extracted)
    except Exception:
        return ""  # 손상·암호화·비텍스트 PDF 등 — 상위가 partial 처리
    return "\n".join(parts)


def ingest_pdf(pdf_path: str) -> list[dict]:
    """단일 PDF → [{text, source}] 청크 리스트(source=파일명). 텍스트 없으면 빈 리스트."""
    source = os.path.basename(pdf_path)
    text = extract_text(pdf_path)
    return [{"text": c, "source": source} for c in chunk_text(text)]


def ingest_folder(folder: str) -> list[dict]:
    """폴더 내 모든 *.pdf → 청크 리스트(파일명순). 폴더 부재/빈 폴더는 빈 리스트."""
    if not folder or not os.path.isdir(folder):
        return []
    out: list[dict] = []
    for path in sorted(glob.glob(os.path.join(folder, "*.pdf"))):
        out.extend(ingest_pdf(path))
    return out
