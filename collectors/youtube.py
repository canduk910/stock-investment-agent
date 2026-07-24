"""YouTube 자막 수집 — 챗봇 '콘텐츠 툴'(summarize_youtube)용.

조회 전용(외부 공개 자막). LLM 이 이 자막을 소비·요약한다(설명만·판정은 코드 원칙 유지 —
영상은 3자 의견이므로 요약은 '출처 귀속'으로, 매매 판정으로 제시하지 않는다: build_prompt 규칙).
URL 파싱은 youtu.be / youtube.com/watch?v= / m.youtube.com / embed / shorts 를 방어적으로 처리.

**실패 사유 표면화(진단 가능)**: 예전엔 모든 실패를 `None` 으로 뭉개 "자막 못 가져옴"만 안내했다.
이제 `fetch_transcript_detailed` 가 예외를 분류해 **사용자 안내 문구(reason)** 를 함께 돌려준다 —
특히 **YouTube 가 데이터센터 IP 를 차단**(RequestBlocked/IpBlocked/PoTokenRequired)하는 경우와
**영상에 자막이 없는** 경우(TranscriptsDisabled/NoTranscriptFound)를 구분한다. ★배포(Cloud Run 등
데이터센터 IP)에서는 YouTube 차단으로 실패하고 로컬(가정/사무실 IP)에서는 정상인 게 대표 패턴이라,
그 차이를 사용자에게 정확히 안내해야 혼선이 없다. 로깅(WARNING)에 예외 타입을 남겨 프로덕션 진단도 돕는다.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from urllib.parse import parse_qs, urlparse

import youtube_transcript_api as _yt
from youtube_transcript_api import YouTubeTranscriptApi

_log = logging.getLogger(__name__)

# 자막 우선순위 언어(한국어 → 영어). 종목·시황 영상 대응.
DEFAULT_LANGS = ("ko", "en")
# 자막이 매우 길 수 있어 요약 컨텍스트 보호용 상한(문자). 초과분은 잘라 요약에 넘긴다.
MAX_TRANSCRIPT_CHARS = 12000
# ★외부 호출 타임아웃(초) — youtube_transcript_api 는 자체 타임아웃이 없어, YouTube 가
#   차단/지연(데이터센터·로컬 IP 흔함)하면 챗 요청이 무한 hang 된다. 스레드 + result(timeout)
#   로 상한을 걸어 초과 시 graceful 안내(챗은 "자막 못 가져옴" 사유 표시).
FETCH_TIMEOUT_SECONDS = 12

# ── 실패 사유(사용자 안내 문구) — 콘텐츠 툴이 LLM 에 그대로 되먹여 사용자에게 전달 ──────────────
REASON_BAD_URL = "유효한 YouTube 링크가 아닙니다. URL 을 다시 확인해 주세요."
REASON_BLOCKED = (
    "YouTube 가 서버(클라우드) IP 를 차단해 이 영상의 자막을 가져올 수 없습니다. "
    "배포 환경(데이터센터 IP)의 제약이며 영상 자체 문제가 아닙니다 — 로컬 실행에서는 정상 동작합니다."
)
REASON_NO_CAPTION = (
    "이 영상은 자막(자동 생성 자막 포함)이 제공되지 않아 요약할 수 없습니다. "
    "자막이 있는 다른 영상을 시도해 주세요."
)
REASON_UNAVAILABLE = (
    "이 영상은 비공개·삭제·연령제한 등으로 접근할 수 없어 자막을 가져올 수 없습니다."
)
REASON_TIMEOUT = "자막 조회가 시간 내에 끝나지 않았습니다. 잠시 후 다시 시도해 주세요."
REASON_NO_TEXT = "이 영상에서 자막 텍스트를 찾지 못했습니다."
REASON_GENERIC = "자막을 가져오지 못했습니다. 잠시 후 다시 시도하거나 다른 영상을 확인해 주세요."


def _exc(*names: str) -> tuple[type, ...]:
    """youtube_transcript_api 에서 실제 존재하는 예외 클래스만 튜플로(버전 차이 방어)."""
    out = []
    for n in names:
        cls = getattr(_yt, n, None)
        if isinstance(cls, type):
            out.append(cls)
    return tuple(out)


# YouTube 봇/IP 차단(데이터센터 IP 대표 실패) · 자막 부재 · 영상 접근 불가 그룹.
_BLOCK_EXC = _exc("RequestBlocked", "IpBlocked", "PoTokenRequired")
_NO_CAPTION_EXC = _exc("TranscriptsDisabled", "NoTranscriptFound", "NotTranslatable")
_UNAVAILABLE_EXC = _exc("VideoUnavailable", "VideoUnplayable", "AgeRestricted", "InvalidVideoId")


def _failure_reason(exc: Exception) -> str:
    """예외 → 사용자 안내 사유(isinstance 기반, 서브클래스 견고)."""
    if _BLOCK_EXC and isinstance(exc, _BLOCK_EXC):
        return REASON_BLOCKED
    if _NO_CAPTION_EXC and isinstance(exc, _NO_CAPTION_EXC):
        return REASON_NO_CAPTION
    if _UNAVAILABLE_EXC and isinstance(exc, _UNAVAILABLE_EXC):
        return REASON_UNAVAILABLE
    return REASON_GENERIC


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


def fetch_transcript_detailed(
    url: str,
    languages=DEFAULT_LANGS,
    max_chars: int = MAX_TRANSCRIPT_CHARS,
    timeout: int = FETCH_TIMEOUT_SECONDS,
) -> tuple[str | None, str | None]:
    """YouTube URL → (자막 전문, None) 성공 / (None, 사유) 실패.

    실패 사유를 분류해 사용자 안내 문구로 돌려준다(IP 차단 / 자막 없음 / 접근 불가 / 타임아웃 구분).
    조회 전용(다운로드/저장 없음). 외부 호출은 timeout 초 상한(무한 hang 방지). 예외를 밖으로 던지지 않는다.
    """
    vid = parse_video_id(url)
    if not vid:
        return None, REASON_BAD_URL

    def _do() -> str:
        fetched = YouTubeTranscriptApi().fetch(vid, languages=list(languages))
        return " ".join(snippet.text for snippet in fetched).strip()

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            text = ex.submit(_do).result(timeout=timeout)
    except FuturesTimeout:
        _log.warning("youtube transcript timeout: vid=%s (>%ss)", vid, timeout)
        return None, REASON_TIMEOUT
    except Exception as exc:  # 차단·자막 없음·접근 불가 등 — 예외 대신 분류된 사유
        _log.warning("youtube transcript failed (%s): vid=%s", type(exc).__name__, vid)
        return None, _failure_reason(exc)
    if not text:
        return None, REASON_NO_TEXT
    return text[:max_chars], None


def fetch_transcript(
    url: str,
    languages=DEFAULT_LANGS,
    max_chars: int = MAX_TRANSCRIPT_CHARS,
    timeout: int = FETCH_TIMEOUT_SECONDS,
) -> str | None:
    """자막 전문(문자열) 또는 None(실패). 하위호환 — 사유가 필요하면 fetch_transcript_detailed."""
    text, _reason = fetch_transcript_detailed(url, languages, max_chars, timeout)
    return text
