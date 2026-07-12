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


# KIS 자격증명 암호화 마스터키의 dev 전용 비보안 기본값(auth._DEV_SECRET 패턴).
# 프로덕션은 반드시 KIS_ENC_KEY(Secret Manager)로 오버라이드한다 — 이 값은 공개 저장소에 있어 비보안.
_DEV_ENC_KEY = "noiNyahceRH8zjRWO72a_nB9vbtgKcHyzFCsKI7Hsx0="


def kis_encryption_key() -> str:
    """유저별 KIS 자격증명 암호화(Fernet)용 마스터키(base64 44자).

    KIS_ENC_KEY(Secret Manager) 우선, 미설정 시 dev 기본값(비보안). 생성:
    `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
    """
    return _optional("KIS_ENC_KEY") or _DEV_ENC_KEY


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


def kis_account() -> tuple[str, str]:
    """잔고조회(inquire_balance)용 (CANO, ACNT_PRDT_CD) — 단일 로컬 사용자.

    - CANO: KIS_ACNT_NO 우선, 없으면 기존 KIS_ACCOUNT_NO 폴백(하위호환). 계좌번호가
      "12345678-01" 처럼 하이픈으로 상품코드를 포함하면 앞 8자리(CANO)만 취한다.
    - ACNT_PRDT_CD: KIS_ACNT_PRDT_CD_STK, 미설정 시 "01"(국내주식 종합계좌).
    - 미설정 허용(_optional) — 예외 없이 빈 CANO 반환(잔고 라우트가 graceful 처리).

    조회 전용 — 이 값들은 KIS 조회 API 파라미터일 뿐, 주문/매매엔 쓰지 않는다.
    """
    cano = _optional("KIS_ACNT_NO") or _optional("KIS_ACCOUNT_NO")
    cano = cano.split("-", 1)[0]  # "12345678-01" → "12345678"(CANO 8자리)
    prdt = _optional("KIS_ACNT_PRDT_CD_STK") or "01"
    return cano, prdt


def fred_api_key() -> str:
    return _require("FRED_API_KEY")


def dart_api_key() -> str:
    return _require("DART_API_KEY")


def openai_api_key() -> str:
    """W09 LLM 챗봇용. 미설정 시 ConfigError(LLM 계층에서만 호출 — 조회/엔진 계층은 무관)."""
    return _require("OPENAI_API_KEY")
