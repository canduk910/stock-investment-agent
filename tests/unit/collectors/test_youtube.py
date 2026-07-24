"""YouTube 자막 collector 테스트 — URL 파싱 + graceful 조회(외부 API mock)."""
from __future__ import annotations

import pytest

from collectors import youtube
from collectors.youtube import fetch_transcript, parse_video_id


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=wAHyhMinFAs", "wAHyhMinFAs"),
        ("https://youtube.com/watch?v=abc123&t=10s", "abc123"),
        ("https://m.youtube.com/watch?v=xyz789", "xyz789"),
        ("https://youtu.be/shortID01", "shortID01"),
        ("https://www.youtube.com/embed/embedID9", "embedID9"),
        ("https://www.youtube.com/shorts/shortsID", "shortsID"),
    ],
)
def test_parse_video_id_valid(url, expected):
    assert parse_video_id(url) == expected


@pytest.mark.parametrize(
    "url",
    ["", None, "https://example.com/watch?v=x", "https://www.youtube.com/", "그냥 텍스트"],
)
def test_parse_video_id_invalid(url):
    assert parse_video_id(url) is None


class _Snippet:
    def __init__(self, text):
        self.text = text


def _fake_api(snippets=None, raises=None):
    """YouTubeTranscriptApi 대체 — .fetch() 가 snippet 리스트를 주거나 예외."""

    class _Fake:
        def fetch(self, video_id, languages=None):
            if raises is not None:
                raise raises
            return snippets or []

    return _Fake


def test_fetch_transcript_joins_snippets(monkeypatch):
    monkeypatch.setattr(
        youtube, "YouTubeTranscriptApi",
        _fake_api([_Snippet("안녕"), _Snippet("하세요"), _Snippet("시장 이야기")]),
    )
    out = fetch_transcript("https://youtu.be/vid123")
    assert out == "안녕 하세요 시장 이야기"


def test_fetch_transcript_invalid_url_is_none(monkeypatch):
    # 불량 URL 은 API 호출 전에 None (parse 실패).
    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", _fake_api([_Snippet("x")]))
    assert fetch_transcript("https://example.com/x") is None


def test_fetch_transcript_api_failure_is_none(monkeypatch):
    """자막 없음·비공개·차단 등 API 예외 → 예외 전파 아니라 graceful None."""
    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", _fake_api(raises=Exception("no transcript")))
    assert fetch_transcript("https://youtu.be/vid123") is None


def test_fetch_transcript_empty_is_none(monkeypatch):
    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", _fake_api([]))
    assert fetch_transcript("https://youtu.be/vid123") is None


def test_fetch_transcript_truncates(monkeypatch):
    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", _fake_api([_Snippet("가" * 100)]))
    out = fetch_transcript("https://youtu.be/vid123", max_chars=20)
    assert len(out) == 20


def test_fetch_transcript_timeout_is_none(monkeypatch):
    """외부 호출이 지연(YouTube 차단·hang)되면 timeout 상한으로 graceful None(챗 hang 방지)."""
    import time

    class _SlowFake:
        def fetch(self, video_id, languages=None):
            time.sleep(0.5)  # timeout 보다 김
            return [_Snippet("느림")]

    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", lambda: _SlowFake())
    assert fetch_transcript("https://youtu.be/vid123", timeout=0.1) is None


# ── 실패 사유 분류(fetch_transcript_detailed) — IP 차단 vs 자막 없음 vs 접근불가 구분 ──────────


def test_failure_reason_classifies():
    from youtube_transcript_api import (
        IpBlocked,
        RequestBlocked,
        TranscriptsDisabled,
        VideoUnavailable,
    )

    assert youtube._failure_reason(RequestBlocked("v")) == youtube.REASON_BLOCKED
    assert youtube._failure_reason(IpBlocked("v")) == youtube.REASON_BLOCKED
    assert youtube._failure_reason(TranscriptsDisabled("v")) == youtube.REASON_NO_CAPTION
    assert youtube._failure_reason(VideoUnavailable("v")) == youtube.REASON_UNAVAILABLE
    assert youtube._failure_reason(RuntimeError("x")) == youtube.REASON_GENERIC


def test_detailed_success(monkeypatch):
    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", _fake_api([_Snippet("안녕"), _Snippet("시장")]))
    text, reason = youtube.fetch_transcript_detailed("https://youtu.be/vid123")
    assert text == "안녕 시장" and reason is None


def test_detailed_bad_url():
    text, reason = youtube.fetch_transcript_detailed("https://example.com/x")
    assert text is None and reason == youtube.REASON_BAD_URL


def test_detailed_ip_block_reason(monkeypatch):
    # ★핵심: YouTube 가 서버 IP 를 차단(RequestBlocked)하면 '자막 없음' 이 아니라 'IP 차단' 으로 안내.
    from youtube_transcript_api import RequestBlocked

    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", _fake_api(raises=RequestBlocked("vid123")))
    text, reason = youtube.fetch_transcript_detailed("https://youtu.be/vid123")
    assert text is None and reason == youtube.REASON_BLOCKED
    assert "차단" in reason and "로컬" in reason  # 사용자에게 원인·회피 정보 전달


def test_detailed_no_caption_reason(monkeypatch):
    from youtube_transcript_api import TranscriptsDisabled

    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", _fake_api(raises=TranscriptsDisabled("vid123")))
    text, reason = youtube.fetch_transcript_detailed("https://youtu.be/vid123")
    assert text is None and reason == youtube.REASON_NO_CAPTION


def test_detailed_empty_reason(monkeypatch):
    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", _fake_api([]))
    text, reason = youtube.fetch_transcript_detailed("https://youtu.be/vid123")
    assert text is None and reason == youtube.REASON_NO_TEXT
