"""T0 스캐폴딩 부트 테스트 — 프로젝트 구조와 pytest 설정이 정상 기동하는지 확인."""
from __future__ import annotations

import importlib


def test_packages_importable():
    for mod in ("collectors", "collectors.kis", "cache", "infra", "infra.config"):
        assert importlib.import_module(mod) is not None


def test_config_raises_on_missing_key(monkeypatch):
    """키 미설정 시 하드코딩 fallback 없이 ConfigError를 던진다 (안전 요건)."""
    from infra.config import ConfigError, KisConfig

    monkeypatch.delenv("KIS_APP_KEY", raising=False)
    monkeypatch.setenv("KIS_ENV", "real")
    import pytest

    with pytest.raises(ConfigError):
        KisConfig.load()
