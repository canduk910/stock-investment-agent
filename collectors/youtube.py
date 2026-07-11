"""YouTube 자막 수집 — 챗봇 '콘텐츠 툴'(summarize_youtube)용.

조회 전용(외부 공개 자막). LLM 이 이 자막을 소비·요약한다(설명만·판정은 코드 원칙 유지 —
영상은 3자 의견이므로 요약은 '출처 귀속'으로, 매매 판정으로 제시하지 않는다: build_prompt 규칙).
URL 파싱은 youtu.be / youtube.com/watch?v= / m.youtube.com / embed / shorts 를 방어적으로 처리.
자막 부재·불량 URL·API 실패는 예외 대신 None(파이프라인·챗 안 죽임 — 상위가 graceful 안내).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi

# 자막 우선순위 언어(한국어 → 영어). 종목·시황 영상 대응.
DEFAULT_LANGS = ("ko", "en")
# 자막이 매우 길 수 있어 요약 컨텍스트 보호용 상한(문자). 초과분은 잘라 요약에 넘긴다.
MAX_TRANSCRIPT_CHARS = 12000
# ★외부 호출 타임아웃(초) — youtube_transcript_api 는 자체 타임아웃이 없어, YouTube 가
#   차단/지연(데이터센터·로컬 IP 흔함)하면 챗 요청이 무한 hang 된다. 스레드 + result(timeout)
#   로 상한을 걸어 초과 시 graceful None(챗은 "자막 못 가져옴" 안내).
FETCH_TIMEOUT_SECONDS = 12


def parse_video_id(url: str) -> str | None:
    """YouTube URL → video id. 실패(불량/미지원 형식) 시 None."""
    if not url or not isinstance(url, str):
        return None
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if host == "youtu.be":
        vid = parsed.path.lstrip("/").split("/")[0]
        return vid or None
    if host in ("www.youtube.com", "youtube.com", "m.youtube.com"):
        qs = parse_qs(parsed.query)
        if qs.get("v"):
            return qs["v"][0]
        # /embed/ID · /shorts/ID · /v/ID
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in ("embed", "shorts", "v"):
            return parts[1]
    return None


def fetch_transcript(
    url: str,
    languages=DEFAULT_LANGS,
    max_chars: int = MAX_TRANSCRIPT_CHARS,
    timeout: int = FETCH_TIMEOUT_SECONDS,
) -> str | None:
    """YouTube URL → 자막 전문(문자열). 실패·부재·타임아웃은 None(graceful).

    max_chars 초과 시 앞부분만 반환(요약 컨텍스트 보호). 조회 전용(다운로드/저장 없음).
    외부 호출은 timeout 초로 상한(무한 hang 방지) — 초과·차단·자막 없음은 모두 None.
    """
    vid = parse_video_id(url)
    if not vid:
        return None

    def _do() -> str:
        fetched = YouTubeTranscriptApi().fetch(vid, languages=list(languages))
        return " ".join(snippet.text for snippet in fetched).strip()

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            text = ex.submit(_do).result(timeout=timeout)
    except Exception:
        # 자막 없음·비공개·API 차단·타임아웃 등 — 예외 대신 graceful None
        return None
    if not text:
        return None
    return text[:max_chars]
