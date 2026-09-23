"""기동 백필 가드 — 앱을 켜는 것만으로 운영 DB에 쓰지 않는다.

배경(실제로 일어난 일, 2026-09-23):
  `@app.on_event("startup")`이 백필 데몬 스레드 4종을 띄운다. 그중 `backfill_sale_results`는
  확정 낙찰 전량을 `record_sale_result`(ON CONFLICT DO UPDATE)로 재upsert한다. 그래서 검증용으로
  서버를 켠 작업자가 매번 `sale_results` 138행 중 134행의 `recorded_at`을 덮어썼다(15:10 → 15:27).
  테스트 5개 파일을 `yield TestClient(app)`로 고쳐 막아 뒀지만, 누가 `with`를 되돌리면 재발한다.
  그래서 **환경변수 가드**로 구조를 막는다 — 이름·방식은 기존 `NC_NO_SCHEDULER` 관례를 따른다.

⚠ 운영에서는 백필이 계속 돌아야 한다. 기본값은 '켜짐'이고 가드를 켠 경우에만 건너뛴다 —
  아래 두 테스트가 그 양쪽(막힘/돎)을 모두 고정한다.
"""

import threading

import pytest


@pytest.fixture
def started(monkeypatch):
    """`_startup()`이 띄우려 한 스레드 target 이름을 모은다(실제로는 띄우지 않는다)."""
    names = []

    class _Noop:
        def start(self):
            pass

    def _fake_thread(*a, **kw):
        t = kw.get("target")
        names.append(getattr(t, "__name__", repr(t)))
        return _Noop()

    # app._startup()은 함수 안에서 `import threading` 하므로 모듈 속성을 직접 갈아끼운다.
    monkeypatch.setattr(threading, "Thread", _fake_thread)
    return names


def test_guard_blocks_startup_backfills(started, monkeypatch):
    """NC_NO_BACKGROUND=1 이면 백필 스레드를 하나도 띄우지 않는다."""
    from web import app as webapp

    monkeypatch.setenv("NC_NO_BACKGROUND", "1")
    webapp._startup()
    assert started == [], f"가드가 켜졌는데도 백필이 떴다: {started}"


def test_backfills_run_without_the_guard(started, monkeypatch):
    """가드가 없으면 운영처럼 4종이 모두 뜬다 — 가드가 운영 백필을 막아선 안 된다."""
    from web import app as webapp

    monkeypatch.delenv("NC_NO_BACKGROUND", raising=False)
    monkeypatch.setenv("NC_NO_SCHEDULER", "1")   # 스케줄러(외부 수집)는 계속 막아 둔다
    webapp._startup()
    assert started == ["backfill_mileage_from_files", "backfill_sale_results",
                       "backfill_appraisal_signals", "backfill_photo_count"], started


def test_conftest_sets_the_guard_for_every_test():
    """테스트 프로세스에서는 항상 켜져 있어야 한다(누가 `with TestClient(app)`을 되돌려도 안전)."""
    import os
    assert os.environ.get("NC_NO_BACKGROUND") == "1"


# ── 예외 래퍼 ──────────────────────────────────────────────────────────

def test_background_task_logs_instead_of_swallowing(caplog):
    """백필이 죽으면 흔적이 남아야 한다 — 이름과 트레이스백 둘 다."""
    from web import service

    def backfill_boom():
        raise RuntimeError("no such table: sale_results")

    with caplog.at_level("ERROR", logger="naechaget.background"):
        assert service.background_task(backfill_boom)() is None   # 스레드를 죽이지 않는다
    assert "backfill_boom" in caplog.text
    assert "no such table: sale_results" in caplog.text
    assert "Traceback" in caplog.text
    # 핸들러가 없으면 파이썬 기본(lastResort)은 **메시지만** 찍는다(실측). 로거 이름이
    # 메시지 안에 없으면 운영 로그에서 이 줄의 출처를 못 가린다 — 태그를 고정한다.
    assert "[naechaget.background]" in caplog.records[0].getMessage()


def test_background_task_returns_the_value_on_success():
    from web import service
    assert service.background_task(lambda: 7)() == 7
