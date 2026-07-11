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
