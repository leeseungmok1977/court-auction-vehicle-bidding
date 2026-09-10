"""엔카 수집 차단 감지 — 침묵의 장애 재발 방지.

2026-09 실장애: 엔카가 서버 IP를 407로 차단해 시세 수집이 3일간 조용히 멈췄고,
그 사이 신규 물건이 전부 '신뢰도 낮음'으로 적체돼 '지금 입찰 추천'이 30→21로 줄었다.
상태 판정(encar_health_status)은 **외부요청 없이** 저장된 상태만 읽어야 한다(화면 렌더용).
"""
from datetime import date, timedelta

import pytest


@pytest.fixture
def dbmod(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    return db


def _iso(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat() + " 06:30:00"


def test_unknown_when_never_checked(dbmod):
    from web import service
    s = service.encar_health_status()
    assert s["state"] == "unknown"
    assert s["degraded"] is False          # 이력 없음을 장애로 단정하지 않는다


def test_ok_recent_is_not_degraded(dbmod):
    from web import service
    dbmod.set_setting("encar_health_state", "ok")
    dbmod.set_setting("encar_health_ok_at", _iso(0))
    s = service.encar_health_status()
    assert s["state"] == "ok" and s["stale_days"] == 0
    assert s["degraded"] is False


def test_blocked_is_degraded(dbmod):
    from web import service
    dbmod.set_setting("encar_health_state", "blocked")
    dbmod.set_setting("encar_health_code", "407")
    dbmod.set_setting("encar_health_ok_at", _iso(0))
    s = service.encar_health_status()
    assert s["degraded"] is True           # 차단은 최근 정상 이력과 무관하게 즉시 고지
    assert s["code"] == "407"


def test_stale_ok_is_degraded(dbmod):
    """마지막 정상이 2일 이상 지났으면(수집이 조용히 멈춘 상태) 고지한다."""
    from web import service
    dbmod.set_setting("encar_health_state", "ok")
    dbmod.set_setting("encar_health_ok_at", _iso(3))
    s = service.encar_health_status()
    assert s["stale_days"] == 3
    assert s["degraded"] is True


def test_status_makes_no_external_request(dbmod, monkeypatch):
    """화면 렌더 경로이므로 외부요청이 있어선 안 된다."""
    from web import service
    from src.collect import encar

    def _boom(*a, **k):
        raise AssertionError("encar_health_status가 외부요청을 했다")

    monkeypatch.setattr(encar, "new_session", _boom)
    monkeypatch.setattr(encar, "search", _boom)
    service.encar_health_status()
