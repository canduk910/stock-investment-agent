"""KIS 계좌 config 계약 — UX2. infra.config.kis_account() → (cano, acnt_prdt_cd).

단일 로컬 사용자. 잔고 조회 어댑터 inquire_balance(client, cano, prdt)가 요구하는
계좌 앞 8자리(CANO)·상품코드 2자리를 환경변수에서 읽는다(_optional — 미설정 허용).
KIS_ACNT_NO 우선, 없으면 기존 KIS_ACCOUNT_NO 폴백(하위호환). 상품코드 기본 "01"(주식종합).

격리: kis_account()는 os.environ 을 그때그때 읽으므로(모듈 재로딩 불필요) monkeypatch
setenv/delenv 만으로 결정적이다. importlib.reload 를 쓰면 모듈 상단 load_dotenv() 가
.env 실값을 재주입해 테스트를 오염시킨다 — 그래서 여기선 reload 를 쓰지 않는다.
"""
from __future__ import annotations

import pytest

import infra.config as config

_ACCOUNT_ENV_KEYS = ("KIS_ACNT_NO", "KIS_ACCOUNT_NO", "KIS_ACNT_PRDT_CD_STK")


@pytest.fixture
def clean_account_env(monkeypatch):
    """계좌 관련 env 를 전부 지운 상태에서 시작(결정적) — 테스트가 필요한 것만 setenv."""
    for key in _ACCOUNT_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_reads_acnt_no_and_prdt(clean_account_env):
    clean_account_env.setenv("KIS_ACNT_NO", "12345678")
    clean_account_env.setenv("KIS_ACNT_PRDT_CD_STK", "01")
    cano, prdt = config.kis_account()
    assert cano == "12345678"
    assert prdt == "01"


def test_prdt_defaults_to_01(clean_account_env):
    # 상품코드 미설정 → 국내주식 종합계좌 기본 "01".
    clean_account_env.setenv("KIS_ACNT_NO", "12345678")
    cano, prdt = config.kis_account()
    assert cano == "12345678"
    assert prdt == "01"


def test_falls_back_to_legacy_account_no(clean_account_env):
    # KIS_ACNT_NO 없으면 기존 KIS_ACCOUNT_NO 로 폴백(하위호환).
    clean_account_env.setenv("KIS_ACCOUNT_NO", "87654321")
    cano, prdt = config.kis_account()
    assert cano == "87654321"


def test_legacy_account_no_strips_product_suffix(clean_account_env):
    # 기존 KIS_ACCOUNT_NO 가 "계좌-상품" 형태면 CANO(앞 8자리)만 취한다.
    clean_account_env.setenv("KIS_ACCOUNT_NO", "12345678-01")
    cano, _ = config.kis_account()
    assert cano == "12345678"


def test_acnt_no_takes_priority_over_legacy(clean_account_env):
    # 둘 다 있으면 신규 KIS_ACNT_NO 우선.
    clean_account_env.setenv("KIS_ACNT_NO", "11112222")
    clean_account_env.setenv("KIS_ACCOUNT_NO", "99998888")
    cano, _ = config.kis_account()
    assert cano == "11112222"


def test_missing_is_empty(clean_account_env):
    # 단일 로컬 사용자·미설정 허용(_optional) — 예외 없이 빈 CANO, prdt 는 기본 "01".
    cano, prdt = config.kis_account()
    assert cano == ""
    assert prdt == "01"


def test_no_order_api_reference():
    # 안전: config 어디에도 주문/매매 관련 키가 없다(조회 전용).
    import inspect

    src = inspect.getsource(config)
    for banned in ("order", "buy", "sell", "cash_order"):
        assert banned not in src.lower()
