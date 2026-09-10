"""엔카 아웃바운드 경로 분리(ENCAR_PROXY) + 차단 코드 판정(407 포함)."""
import pytest


def test_session_uses_proxy_only_when_env_set(monkeypatch):
    from src.collect import encar
    monkeypatch.delenv("ENCAR_PROXY", raising=False)
    assert encar.new_session().proxies == {}
    monkeypatch.setenv("ENCAR_PROXY", "http://127.0.0.1:18080")
    s = encar.new_session()
    assert s.proxies["https"] == "http://127.0.0.1:18080"
    assert s.proxies["http"] == "http://127.0.0.1:18080"


class _Resp:
    def __init__(self, code):
        self.status_code = code


class _Err(Exception):
    def __init__(self, code):
        super().__init__(f"{code} Client Error")
        self.response = _Resp(code)


@pytest.mark.parametrize("code,expected", [(407, True), (403, True), (429, True), (500, False), (200, False)])
def test_is_block_by_status_code(code, expected):
    from web import service
    assert service._is_block(_Err(code)) is expected


def test_is_block_by_message_still_works():
    from web import service
    assert service._is_block(RuntimeError("법원 차단 감지")) is True
    assert service._is_block(RuntimeError("timeout")) is False
