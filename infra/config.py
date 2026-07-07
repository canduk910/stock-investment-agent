"""환경변수 로딩 — API 키·시크릿은 오직 여기서만 읽는다 (하드코딩 금지).

PLAN §10: API 키는 환경변수/시크릿 매니저에서만 로드.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # 프로젝트 루트의 .env를 로드 (없으면 무시)


class ConfigError(RuntimeError):
    """필수 환경변수 누락 시 발생."""


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"환경변수 {name}가 설정되지 않았습니다. .env.example을 참고해 .env에 값을 채우세요."
        )
    return value


def _optional(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class KisConfig:
    app_key: str
    app_secret: str
    env: str  # "real" | "demo"
    account_no: str

    @staticmethod
    def load() -> "KisConfig":
        env = _optional("KIS_ENV", "real")
        if env not in ("real", "demo"):
            raise ConfigError("KIS_ENV must be 'real' or 'demo'")
        return KisConfig(
            app_key=_require("KIS_APP_KEY"),
            app_secret=_require("KIS_APP_SECRET"),
            env=env,
            account_no=_optional("KIS_ACCOUNT_NO"),
        )


def fred_api_key() -> str:
    return _require("FRED_API_KEY")


def dart_api_key() -> str:
    return _require("DART_API_KEY")


def openai_api_key() -> str:
    """W09 LLM 챗봇용. 미설정 시 ConfigError(LLM 계층에서만 호출 — 조회/엔진 계층은 무관)."""
    return _require("OPENAI_API_KEY")
