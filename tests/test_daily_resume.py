"""매일 갱신: 재시작으로 끊긴 런 자동 재개 + 개발 기동용 스케줄러 가드.

배경(둘 다 실제로 일어난 일):
  · OS 자동 보안 업데이트가 패키지를 올리며 naechaget.service 를 재시작해 매일 갱신이
    한가운데서 끊겼다(2026-09-14 06:32, 2026-09-17 06:42). 09-17에는 낙찰결과 반영에서
    멈춰 무결성 검토와 출시가 수집이 통째로 누락됐고, 아무도 다시 돌리지 않았다.
  · 성능 측정용으로 띄운 로컬 개발 서버가 스케줄러를 켜 **승인 없는 외부 수집**을 시작했다
    (실행 #61, 시세 분석 27/80 시도 — C.4-6 위반).

재개는 '이어하기'가 아니라 **다시 한 번 돌리기**다. daily_update 의 각 단계가 증분·멱등이라
다음 날 아침 다시 도는 것과 같아 안전하다. 대신 폭주 방지 장치를 검증한다.
"""
from datetime import date

import pytest

TODAY = date.today().isoformat()


@pytest.fixture
def svc(tmp_path, monkeypatch):
    from web import db, service
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "r.db")
    db.init_db()
    # 냉각 시간은 기본적으로 지난 것으로 둔다(각 테스트가 필요하면 되돌린다)
    monkeypatch.setattr(service, "_PROC_START", service.time.monotonic() - 10_000)
    monkeypatch.setattr(service, "_scheduler_started", False)
    return service


def _finish_run(db_mod, service_mod, *, mark: bool, status: str = "error"):
    """오늘 자 런을 하나 만들고 닫는다. mark=True 면 재시작 표식을 남긴다."""
    rid = db_mod.create_run(target=0)
    msg = "낙찰결과 조회 46/55 법원 (요청 46/300)"
    if mark:
        msg += " (" + service_mod.RESTART_MARK + ")"
    db_mod.update_run(rid, status=status, finished_at="2026-01-01 00:00:00", message=msg)
    return rid


def _settings(**kw):
    s = {"daily_enabled": "1", "daily_time": "06:00", "last_run_date": TODAY}
    s.update(kw)
    return s


# ── 재개 판정 ────────────────────────────────────────────────────

def test_resumes_when_restart_killed_todays_run(svc):
    from web import db
    _finish_run(db, svc, mark=True)
    assert svc._should_resume(_settings(), TODAY) is True


def test_does_not_resume_a_genuine_error(svc):
    """진짜 오류(코드 버그·차단 등)는 다시 돌린다고 낫지 않는다 — 표식이 있을 때만 재개."""
    from web import db
    _finish_run(db, svc, mark=False)
    assert svc._should_resume(_settings(), TODAY) is False


def test_does_not_resume_before_today_started(svc):
    """오늘 갱신 전이면 정상 트리거가 처리한다 — 재개가 끼어들면 두 번 돈다."""
    from web import db
    _finish_run(db, svc, mark=True)
    assert svc._should_resume(_settings(last_run_date="2026-01-01"), TODAY) is False


def test_stops_after_daily_limit(svc):
    """재시작이 반복돼도 하루 한도까지만 — 무한 재시도로 외부 요청이 폭주하면 안 된다."""
    from web import db
    _finish_run(db, svc, mark=True)
    s = _settings(daily_resume_date=TODAY, daily_resume_count=str(svc.RESUME_MAX_PER_DAY))
    assert svc._should_resume(s, TODAY) is False


def test_waits_out_the_cooldown(svc, monkeypatch):
    """업그레이드가 여러 패키지를 연달아 올리는 동안에는 재시도하지 않는다."""
    from web import db
    _finish_run(db, svc, mark=True)
    monkeypatch.setattr(svc, "_PROC_START", svc.time.monotonic())
    assert svc._should_resume(_settings(), TODAY) is False


def test_resume_count_resets_next_day(svc):
    assert svc._resume_count({"daily_resume_date": "2026-01-01",
                              "daily_resume_count": "9"}, TODAY) == 0
    assert svc._resume_count({"daily_resume_date": TODAY,
                              "daily_resume_count": "1"}, TODAY) == 1
    assert svc._resume_count({"daily_resume_date": TODAY,
                              "daily_resume_count": None}, TODAY) == 0


# ── 개발 기동 가드 ───────────────────────────────────────────────

def test_guard_blocks_scheduler(svc, monkeypatch):
    """NC_NO_SCHEDULER=1 이면 스레드를 아예 띄우지 않는다(개발 서버가 수집을 시작하지 못하게)."""
    started = []
    monkeypatch.setattr(svc.threading, "Thread",
                        lambda *a, **k: started.append(k.get("target")) or _Noop())
    monkeypatch.setenv("NC_NO_SCHEDULER", "1")
    svc.start_scheduler()
    assert started == [], "가드가 켜졌는데도 스케줄러가 떴다"
    assert svc._scheduler_started is False


def test_scheduler_starts_without_the_guard(svc, monkeypatch):
    started = []
    monkeypatch.setattr(svc.threading, "Thread",
                        lambda *a, **k: started.append(k.get("target")) or _Noop())
    monkeypatch.delenv("NC_NO_SCHEDULER", raising=False)
    svc.start_scheduler()
    assert started and started[0] is svc._scheduler_loop


class _Noop:
    def start(self):
        pass
