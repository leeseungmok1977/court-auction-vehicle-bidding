# -*- coding: utf-8 -*-
"""OPS-4 반증(qa-engineer, 지시서 2026-09-27-67) — ① 주기 읽기·조용히 안 돎 ② workflow 빈 값 ③ 월간 운영 절.

통과하는 테스트는 지금 동작을 못 박는다. `xfail(strict=True)` 는 **재현된 결함**이다 — 고치면 XPASS 로
빨개지니 그때 표식만 지운다(단언은 그대로). 결함 설명은 `reports/2026-09-27-ops4-qa.md`.

작업 스케줄러·서버·외부 요청을 건드리지 않는다. 트리거 XML 은 2026-09-27 16:1x 이 PC 에서
`Export-ScheduledTask` 로 **읽기만** 한 원문이다(작업 9개).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools"), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import _schedstate_js as sj  # noqa: E402
import agent_dashboard as ad  # noqa: E402
import org_runtime as rt  # noqa: E402

DAY = 86400
NS = 'xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"'


def _loc(s: str) -> str:
    """오프셋 붙은 시각 → 이 PC 현지 'YYYY-MM-DD HH:MM'(테스트가 어느 시간대에서 돌아도 같은 답)."""
    return datetime.fromisoformat(s).astimezone().replace(tzinfo=None).isoformat(sep=" ", timespec="minutes")


def _T(body: str) -> str:
    return f"<Triggers {NS}>{body}</Triggers>"


# ── 2026-09-27 16:1x 이 PC 의 작업 9개 트리거 원문(읽기만) ────────────────────────────────
MONTHLY_1ST = ("<CalendarTrigger><StartBoundary>2026-09-22T13:30:00</StartBoundary><ScheduleByMonth><Months><January />"
               "<February /><March /><April /><May /><June /><July /><August /><September /><October /><November />"
               "<December /></Months><DaysOfMonth><Day>1</Day></DaysOfMonth></ScheduleByMonth></CalendarTrigger>")
REAL_XML = {
    "naechaget-daily-report": _T("<CalendarTrigger><StartBoundary>2026-09-16T12:00:00+09:00</StartBoundary>"
                                 "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>"),
    "naechaget-db-backup-pull": _T("<CalendarTrigger><StartBoundary>2026-09-27T09:10:00+09:00</StartBoundary>"
                                   "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>"),
    "naechaget-home-tunnel": _T("<BootTrigger><Delay>PT1M</Delay></BootTrigger>"),
    "naechaget-monthly-report": _T(MONTHLY_1ST),
    "naechaget-ops-snapshot": _T("<TimeTrigger><StartBoundary>2026-09-23T08:36:41+09:00</StartBoundary><Repetition>"
                                 "<Interval>PT1M</Interval><StopAtDurationEnd>true</StopAtDurationEnd></Repetition>"
                                 "</TimeTrigger>"),
    "naechaget-org-heartbeat": _T("<TimeTrigger><StartBoundary>2026-09-27T00:05:00+09:00</StartBoundary><Repetition>"
                                  "<Interval>PT1H</Interval><StopAtDurationEnd>true</StopAtDurationEnd></Repetition>"
                                  "</TimeTrigger>"),
    "naechaget-org-standup": _T("<CalendarTrigger><StartBoundary>2026-09-27T08:45:00+09:00</StartBoundary>"
                                "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>"),
    "NaechaGet-PhotoClassify": _T("<CalendarTrigger><StartBoundary>2026-09-06T08:17:00+09:00</StartBoundary>"
                                  "<ScheduleByWeek><WeeksInterval>1</WeeksInterval><DaysOfWeek><Sunday /></DaysOfWeek>"
                                  "</ScheduleByWeek></CalendarTrigger>"),
    "naechaget-weekly-report": _T("<CalendarTrigger><StartBoundary>2026-09-22T13:00:00</StartBoundary><ScheduleByWeek>"
                                  "<WeeksInterval>1</WeeksInterval><DaysOfWeek><Saturday /></DaysOfWeek>"
                                  "</ScheduleByWeek></CalendarTrigger>"),
}
REAL_PERIOD = {
    "naechaget-daily-report": (DAY, _loc("2026-09-16T12:00:00+09:00")),
    "naechaget-db-backup-pull": (DAY, _loc("2026-09-27T09:10:00+09:00")),
    "naechaget-home-tunnel": (None, ""),
    "naechaget-monthly-report": (31 * DAY, "2026-09-22 13:30"),
    "naechaget-ops-snapshot": (60, _loc("2026-09-23T08:36:41+09:00")),
    "naechaget-org-heartbeat": (3600, _loc("2026-09-27T00:05:00+09:00")),
    "naechaget-org-standup": (DAY, _loc("2026-09-27T08:45:00+09:00")),
    "NaechaGet-PhotoClassify": (7 * DAY, _loc("2026-09-06T08:17:00+09:00")),
    "naechaget-weekly-report": (7 * DAY, "2026-09-22 13:00"),
}
# 같은 시각 read_schedule 행(결과·시각). 등록 날짜는 월간·주간 두 작업만 있다(나머지는 빈 값 — 실측).
REAL_ROWS_RAW = {
    "naechaget-daily-report": dict(last_run="2026-09-27 12:00", next_run="2026-09-28 12:00"),
    "naechaget-db-backup-pull": dict(last_run="1999-11-30 00:00", last_result="267011", next_run="2026-09-28 09:10",
                                     never_ran=True, ok=False),
    "naechaget-home-tunnel": dict(last_run="2026-09-16 05:24", last_result="3221225477", next_run="", ok=False),
    "naechaget-monthly-report": dict(last_run="1999-11-30 00:00", last_result="267011", next_run="2026-10-01 13:30",
                                     never_ran=True, ok=False, registered="2026-09-22 20:47"),
    "naechaget-ops-snapshot": dict(last_run="2026-09-27 16:14", next_run="2026-09-27 16:15"),
    "naechaget-org-heartbeat": dict(last_run="2026-09-27 16:05", next_run="2026-09-27 17:05"),
    "naechaget-org-standup": dict(last_run="2026-09-27 08:45", next_run="2026-09-28 08:45"),
    "NaechaGet-PhotoClassify": dict(last_run="2026-09-27 08:17", next_run="2026-10-04 08:17"),
    "naechaget-weekly-report": dict(last_run="2026-09-26 13:00", next_run="2026-10-03 13:00",
                                    registered="2026-09-22 20:47"),
}
CAPTURED = datetime(2026, 9, 27, 16, 14, 30)
SEEN = "2026-09-27T16:05:02"          # 순환계가 새 코드로 처음 본 시각(실제 data/org-state.json task_seen, 초까지)


def _row(name: str, **kw) -> dict:
    tp = ad.trigger_period(REAL_XML[name])
    t = {"name": name, "status": "Ready", "running": False, "last_run": "", "last_result": "0", "next_run": "",
         "enabled": True, "never_ran": False, "ok": True, "period_s": tp["period_s"],
         "first_start": tp["first_start"], "registered": "", "trigger_error": tp["error"]}
    t.update(REAL_ROWS_RAW[name])
    t.update(kw)
    return t


def real_rows() -> list[dict]:
    return [_row(n) for n in REAL_XML]


def settings() -> dict:
    return rt.Org(ROOT).contracts()[0]


# 백로그 — 2026-09-27 의 상태 칸 글자 그대로(순환계가 '열림'으로 읽는지가 요점이다)
BACKLOG = """# 백로그

| ID | 제목 | 담당 | 상태 | 완료 기준(DoD) |
|---|---|---|---|---|
| AUD-05 | 터널 | Steward | todo · Steward 재현 확인 | x |
| AUD-06 | 공급 신호 오탐 | backend | todo · 확인(qa) | x |
| AUD-08 | 백업·헬스체크 | backend | **백업 완료(2026-09-27) · 헬스체크 남음** | x |
| AUD-09 | 패널 | Steward | todo · 확인(qa) | x |
| AUD-10 | 사진 | Steward | todo · 확인(qa) | x |
| AUD-15 | 운영 위생 묶음 | 각 담당 | todo(낮음) | x |
| KCAR-1 | 케이카 | backend | 완료 | x |
"""


@pytest.fixture()
def org(tmp_path, monkeypatch):
    (tmp_path / "docs" / "daily-reports").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    shutil.copy(ROOT / "docs" / "org-contracts.md", tmp_path / "docs" / "org-contracts.md")
    (tmp_path / "docs" / "backlog.md").write_text(BACKLOG, encoding="utf-8")
    o = rt.Org(tmp_path)
    monkeypatch.setattr(o, "rhythm_states", lambda: [])
    monkeypatch.setattr(o, "schedule_states", lambda: ([], "테스트: 예약 작업을 읽지 않는다"))
    return o


def _sched(org, monkeypatch, rows):
    monkeypatch.setattr(org, "schedule_states", lambda: ([dict(r) for r in rows], None))


def _task_orders(org) -> list[dict]:
    return [o for o in org.orders().values() if o["meta"]["reason"] == "task"]


# ════════════════════════════════════════════════════════════════════════
# ① 주기 읽기 — 이 PC 의 실제 트리거 9개 · 여러 트리거 · 꺼진 트리거
# ════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("name", sorted(REAL_XML))
def test_real_0927_triggers_all_nine(name):
    tp = ad.trigger_period(REAL_XML[name])
    assert (tp["period_s"], tp["first_start"], tp["error"]) == (*REAL_PERIOD[name], ""), name


def test_real_0927_nine_tasks_fall_into_the_three_classes_as_decided():
    """매일 4(매분·매시 포함) · 매주 2 · 매월 1 · 규칙 밖 1(부팅 트리거 터널). 이름에 주기를 박지 않았다."""
    cls = {}
    for n, x in REAL_XML.items():
        p = ad.trigger_period(x)["period_s"]
        c = next((c for c, max_d, _, _ in rt.SILENCE_CLASSES if p and 0 < p <= max_d * DAY), "밖")
        cls.setdefault(c, []).append(n)
    assert sorted(cls["매일"]) == sorted(["naechaget-daily-report", "naechaget-db-backup-pull", "naechaget-ops-snapshot",
                                         "naechaget-org-heartbeat", "naechaget-org-standup"])
    assert sorted(cls["매주"]) == ["NaechaGet-PhotoClassify", "naechaget-weekly-report"]
    assert cls["매월"] == ["naechaget-monthly-report"] and cls["밖"] == ["naechaget-home-tunnel"]


def test_several_triggers_disabled_ones_and_first_start():
    daily_off = ("<CalendarTrigger><Enabled>false</Enabled><StartBoundary>2026-08-01T09:00:00</StartBoundary>"
                 "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>")
    weekly = ("<CalendarTrigger><StartBoundary>2026-09-05T13:00:00</StartBoundary><ScheduleByWeek><WeeksInterval>1"
              "</WeeksInterval><DaysOfWeek><Saturday /></DaysOfWeek></ScheduleByWeek></CalendarTrigger>")
    tp = ad.trigger_period(_T(daily_off + weekly))
    assert tp["period_s"] == 7 * DAY and tp["first_start"] == "2026-09-05 13:00"      # 꺼진 트리거는 시작도 안 센다
    # 부팅 + 매월 → 매월(부팅은 주기가 없다)
    tp = ad.trigger_period(_T("<BootTrigger />" + MONTHLY_1ST))
    assert tp["period_s"] == 31 * DAY
    # 요일을 트리거 두 개로 나눠 적으면(월·목) 트리거마다 7일 → 가장 짧은 것 7일. 합친 실제 간격(4일)보다 길게
    # 잡으므로 헛경보 쪽으로는 틀리지 않는다(분류도 둘 다 '매주').
    mon = weekly.replace("<Saturday />", "<Monday />")
    thu = weekly.replace("<Saturday />", "<Thursday />")
    assert ad.trigger_period(_T(mon + thu))["period_s"] == 7 * DAY
    # 전부 꺼지면 주기 없음(규칙 밖) — 오류가 아니다
    assert ad.trigger_period(_T(daily_off))["period_s"] is None and ad.trigger_period(_T(daily_off))["error"] == ""


# QA-OPS4-1(고침 — backend r2 2026-09-27): 유한 Duration 반복을 매일로 분류하던 결함. strict xfail 이 XPASS 로
# 빨개진 것을 확인하고 표식만 뗐다(단언은 그대로).
def test_repetition_with_a_finite_duration_does_not_make_a_weekly_task_daily():
    x = _T("<CalendarTrigger><StartBoundary>2026-09-05T13:00:00</StartBoundary><Repetition><Interval>PT1H</Interval>"
           "<Duration>PT3H</Duration><StopAtDurationEnd>false</StopAtDurationEnd></Repetition><ScheduleByWeek>"
           "<WeeksInterval>1</WeeksInterval><DaysOfWeek><Saturday /></DaysOfWeek></ScheduleByWeek></CalendarTrigger>")
    p = ad.trigger_period(x)["period_s"]
    t = {"name": "x", "running": False, "enabled": True, "never_ran": False, "ok": True, "last_result": "0",
         "last_run": "2026-09-26 15:00", "next_run": "2026-10-03 13:00", "period_s": p, "first_start": "",
         "registered": "", "trigger_error": ""}
    assert not rt.silence_verdict(t, datetime(2026, 9, 28, 3, 0), settings())["bad"]      # 월요일 새벽 — 아직 정상


# QA-OPS4-2(고침 — backend r2 2026-09-27): 끝난 트리거(EndBoundary 지남)를 주기에 넣던 결함. XPASS 확인 뒤 표식만 뗐다.
def test_expired_trigger_is_not_counted():
    x = _T("<CalendarTrigger><StartBoundary>2026-08-01T09:00:00</StartBoundary><EndBoundary>2026-08-31T09:00:00"
           "</EndBoundary><ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>"
           "<CalendarTrigger><StartBoundary>2026-09-05T13:00:00</StartBoundary><ScheduleByWeek><WeeksInterval>1"
           "</WeeksInterval><DaysOfWeek><Saturday /></DaysOfWeek></ScheduleByWeek></CalendarTrigger>")
    assert ad.trigger_period(x)["period_s"] != DAY


# ════════════════════════════════════════════════════════════════════════
# ① 첫 실행 전 오탐 · 36시간 경계(실제 초 단위 task_seen)
# ════════════════════════════════════════════════════════════════════════
def test_db_backup_pull_first_run_boundary_with_the_real_seen_seconds():
    """등록 날짜가 비어 있어 처음 본 시각(16:05:02 — 초까지)부터 36시간. 첫 예정(09-28 09:10) 전에는 절대 안 울린다."""
    s, b = settings(), _row("naechaget-db-backup-pull")
    assert b["registered"] == "" and b["first_start"] == _loc("2026-09-27T09:10:00+09:00")
    for t in (datetime(2026, 9, 28, 9, 9), datetime(2026, 9, 28, 23, 0), datetime(2026, 9, 29, 4, 5, 1)):
        assert not rt.silence_verdict(b, t, s, SEEN)["bad"], t
    v = rt.silence_verdict(b, datetime(2026, 9, 29, 4, 5, 2), s, SEEN)
    assert v["bad"] and v["label"] == "첫 실행 없음 · 등록 09-27 16:05 뒤 매일 작업 한도 36시간 넘김"
    assert v["since"] == SEEN                                                           # 키도 이 시각에서


def test_monthly_report_is_not_flagged_before_its_first_run_nor_until_registration_plus_35d():
    s, m = settings(), _row("naechaget-monthly-report")
    for t in (datetime(2026, 9, 30, 23, 0), datetime(2026, 10, 1, 13, 29), datetime(2026, 10, 15),
              datetime(2026, 10, 27, 20, 46)):
        assert not rt.silence_verdict(m, t, s, SEEN)["bad"], t
    assert rt.silence_verdict(m, datetime(2026, 10, 27, 20, 47), s, SEEN)["bad"]
    # 등록 날짜가 있으면 처음 본 시각(더 늦은 16:05)을 쓰지 않는다 — 등록 날짜 우선(계약 §3)
    assert rt.silence_verdict(m, datetime(2026, 10, 27, 20, 47), s, "2026-09-27T16:05:02")["since"] \
        == "2026-09-22T20:47:00"


def test_the_nine_captured_rows_raise_nothing_at_capture_time():
    """캡처 시각의 실제 9행 — 조용히 안 돎 0 · 경고 0(대시보드도 초록·주황·실패 1 그대로)."""
    s = settings()
    for r in real_rows():
        v = rt.silence_verdict(r, CAPTURED, s, SEEN)
        assert not v["bad"] and not v["warn"], (r["name"], v)


@pytest.fixture(scope="module")
def sched_page():
    """실제 `agent_dashboard.html` 의 `schedState` 가 올라간 Chromium 한 장(`_schedstate_js`)."""
    with sj.page() as pg:
        yield pg


def test_runtime_and_dashboard_do_not_contradict_on_the_captured_rows(sched_page):
    """캡처 9행을 대시보드 경로 그대로(`attach_verdict` → silence → **실제 HTML `schedState`**) 칠하면 빨강 ⟺ 순환계 고장,
    주황 ⟺ 순환계 조용히 안 돎, 그 밖(초록·대기·확인 불가)은 둘 다 아니다. 빨강은 터널 하나.
    qa r3(지시서 2026-09-27-76): 전에는 r1 칩 규칙 사본 `_dashboard_pill`(결과 `ok` 만 본다)로 셌다. 그 사본은 r3 표가
    빨강으로 칠하는 '꺼짐(Disabled)'·'다음 실행 없음'을 '정상'이라 했다 — 지우고 실제 JS 를 돌린다."""
    s = settings()
    rows = sj.judge(real_rows(), CAPTURED, s, SEEN)
    chips = sj.states(sched_page, rows)
    for r, x in zip(rows, chips):
        bad, _ = rt.schedule_verdict(r)
        quiet = rt.silence_verdict(r, CAPTURED, s, SEEN)["bad"]
        assert (x["pill"] == "bad") == bad, (r["name"], x)
        assert (x["pill"] == "warn") == (quiet and not bad), (r["name"], x)
    assert [r["name"] for r, x in zip(rows, chips) if x["pill"] == "bad"] == ["naechaget-home-tunnel"]


# ════════════════════════════════════════════════════════════════════════
# ① 실제 계약표(§3.1) + 실제 9행 — 열린 티켓이면 0 · 멱등 · dry-run 이 실제와 같은 것을 예고
# ════════════════════════════════════════════════════════════════════════
def _expected_actions(org) -> dict[str, str]:
    """§3.1 표(복사본)에서 기대 동작을 **계산**한다 — 표가 바뀌어도 이 테스트는 규칙을 본다."""
    routes, tickets = org.alert_routes(), org.backlog_tickets()
    out = {}
    for r in real_rows():
        if r["period_s"] is None:
            continue                                                                    # 터널 — 규칙 밖
        rt_ = routes.get(r["name"]) or {}
        _, topen = org._ticket_view(rt_.get("ticket", ""), tickets)
        out[r["name"]] = "not-watched" if not rt_.get("watch", True) else ("ticket-open" if topen else "order")
    return out


def test_every_periodic_real_task_goes_quiet_open_ticket_means_no_order(org, monkeypatch):
    """아무 작업도 다시 안 돈다고 두고 11-10 까지 하루마다 스캔(매시로 돌리면 2분 반 — 스위트가 느려진다).
    열린 티켓 뒤의 작업은 지시서 0 · 스탠드업 줄만."""
    rows = [dict(r, running=False) for r in real_rows()]                               # ops-snapshot 도 멈췄다고 본다
    _sched(org, monkeypatch, rows)
    org.state_file.parent.mkdir(parents=True, exist_ok=True)
    org.state_file.write_text(json.dumps({"reports": {}, "task_seen": {r["name"]: SEEN for r in rows}}),
                              encoding="utf-8")
    first: dict[str, tuple] = {}
    t = datetime(2026, 9, 27, 17, 5)
    while t < datetime(2026, 11, 10):
        for x in org.scan(now=t)["tasks"]:
            if x["action"] != "below":
                first.setdefault(x["name"], (t, x["action"], x["label"]))
        t += timedelta(hours=24)
    exp = _expected_actions(org)
    got = {n: v[1] for n, v in first.items() if n in exp}
    assert got == exp
    # 멱등 — 44일 동안 44번 스캔해도 작업당 한 장
    keys = [o["meta"]["key"] for o in _task_orders(org)]
    assert len(keys) == len(set(keys)) == sum(1 for a in exp.values() if a == "order")
    # 2026-09-27 계약표에서는 이 규칙을 만든 계기인 DB 백업 내려받기가 열린 AUD-08 뒤에 있다(지시서 0 — 보고서 §1)
    if exp.get("naechaget-db-backup-pull") == "ticket-open":
        assert not [k for k in keys if k.startswith("task:naechaget-db-backup-pull:")]
        assert first["naechaget-db-backup-pull"][2].startswith("첫 실행 없음 · 등록 09-27 16:05")
    # 스탠드업 '경보 → 티켓' 절에는 열린 티켓 뒤의 조용한 작업도 나온다
    text = org.standup(now=t).read_text(encoding="utf-8")
    for n, a in exp.items():
        if a == "ticket-open":
            assert f"예약 작업 `{n}`" in text, n


def test_dry_run_predicts_exactly_what_a_real_scan_writes(tmp_path, monkeypatch):
    """dry-run 이 '만들 것'으로 보인 키 = 같은 입력으로 실제 스캔이 만든 키. dry-run 은 파일을 하나도 안 쓴다."""
    def mk(sub):
        root = tmp_path / sub
        (root / "docs" / "daily-reports").mkdir(parents=True)
        (root / "reports").mkdir()
        shutil.copy(ROOT / "docs" / "org-contracts.md", root / "docs" / "org-contracts.md")
        (root / "docs" / "backlog.md").write_text(BACKLOG, encoding="utf-8")
        o = rt.Org(root)
        monkeypatch.setattr(o, "rhythm_states", lambda: [])
        stale = [dict(r, last_run="2026-09-20 12:00") if not r["never_ran"] and r["period_s"] else r
                 for r in real_rows()]
        monkeypatch.setattr(o, "schedule_states", lambda: ([dict(r) for r in stale], None))
        return o
    now = datetime(2026, 9, 27, 17, 5)
    dry, real = mk("dry"), mk("real")
    dry.dry_run = True
    dry.scan(now=now)
    real.scan(now=now)
    assert not dry.state_file.exists() and not dry.bus.exists()
    assert not (dry.orders_dir.exists() and list(dry.orders_dir.glob("*.md")))
    dk = sorted(o["key"] for o in dry.dry_orders_summary() if o["reason"] == "task")
    rk = sorted(o["meta"]["key"] for o in _task_orders(real))
    assert dk == rk and rk                                                              # 비어 있지 않은 채 같다


# ════════════════════════════════════════════════════════════════════════
# ② workflow 빈 값 변형
# ════════════════════════════════════════════════════════════════════════
def _report(org, workflow_line, *, result="done", handoff=("qa-engineer",), order="", crlf=False, name="be.md"):
    lines = ["---"] + ([f"order: {order}"] if order else []) + [
        "from: backend-engineer", "ticket: OPS-4", f"result: {result}", "verified: 재현"]
    if workflow_line is not None:
        lines.append(workflow_line)
    if handoff:
        lines.append("handoff:")
        for to in handoff:
            lines += [f"  - to: {to}", "    why: 반증"]
    else:
        lines.append("handoff: []")
    lines += ["---", "본문"]
    nl = "\r\n" if crlf else "\n"
    (org.root / "reports" / name).write_bytes((nl.join(lines) + nl).encode("utf-8"))


def _handoffs(org):
    return sorted(o["meta"]["to"] for o in org.orders().values() if o["meta"]["reason"] == "handoff")


def _skips(org):
    return [e for e in org.events() if str(e.get("kind", "")).endswith(".skipped")]


@pytest.mark.parametrize("line", ["workflow:-", "workflow: -\t", "workflow: ~", "workflow: Null", "workflow: NULL",
                                  "workflow: off", "workflow: 'none '", "workflow: N/A",
                                  "workflow: 없음  # 워크플로 밖", "workflow: none # 주석"])
def test_more_empty_workflow_spellings_are_processed_normally(org, line):
    _report(org, line)
    r = org.scan(now=datetime(2026, 9, 27, 13, 5))
    assert _handoffs(org) == ["qa-engineer"], line
    assert not _skips(org), line
    assert not [w for w in r["warnings"] if "머리말" in w], line


def test_bare_dash_in_a_crlf_file_is_processed_normally(org):
    """Windows 에서 CRLF 로 저장한 보고서 — 정규식의 `$` 가 `\\r` 앞에서 막히지 않는가."""
    _report(org, "workflow: -", crlf=True)
    org.scan(now=datetime(2026, 9, 27, 13, 5))
    assert _handoffs(org) == ["qa-engineer"] and not _skips(org)


def test_bare_dash_keeps_every_other_field_two_handoffs_and_closes_the_parent(org):
    """`workflow: -` 한 줄만 비운다 — 인계 두 건·티켓·부모 지시서 닫기가 모두 살아 있다."""
    orders = org.orders()
    parent = org.create_order(orders, to="backend-engineer", frm=rt.STEWARD, purpose="OPS-4 구현", reason="manual",
                              ticket="OPS-4", now=datetime(2026, 9, 27, 12, 0))
    pid = parent["meta"]["id"]
    _report(org, "workflow: -", handoff=("qa-engineer", "frontend-engineer"), order=pid)   # §2 backend 의 경로 둘
    r = org.scan(now=datetime(2026, 9, 27, 13, 5))
    assert pid in r["closed"] and org.orders()[pid]["meta"]["status"] == "done"
    hs = [o for o in org.orders().values() if o["meta"]["reason"] == "handoff"]
    assert sorted(o["meta"]["to"] for o in hs) == ["frontend-engineer", "qa-engineer"]
    assert {o["meta"]["ticket"] for o in hs} == {"OPS-4"}


@pytest.mark.parametrize("line", ["workflow: 없음", "workflow: -"])
def test_needs_owner_still_reaches_the_inbox_with_empty_workflow(org, line):
    _report(org, line, result="needs-owner", handoff=())
    org.scan(now=datetime(2026, 9, 27, 13, 5))
    assert [o["meta"]["to"] for o in org.orders().values() if o["meta"]["reason"] == "owner"] == [rt.STEWARD]


# QA-OPS4-3(고침 — backend r2 2026-09-27): `workflow: -   # 주석` 이 머리말 전체를 깨던 결함. XPASS 확인 뒤 표식만 뗐다.
def test_bare_dash_with_a_trailing_comment_is_processed_normally(org):
    _report(org, "workflow: -   # 워크플로 밖")
    r = org.scan(now=datetime(2026, 9, 27, 13, 5))
    assert _handoffs(org) == ["qa-engineer"]
    assert not [w for w in r["warnings"] if "머리말" in w]


def test_other_yaml_errors_still_break_the_header_even_with_a_bare_dash_workflow():
    m, _ = rt.split_front("\n".join(["---", "from: x", "workflow: -", "ticket: [", "handoff: []", "---", ""]))
    assert m == {"__broken__": True}


# ════════════════════════════════════════════════════════════════════════
# ③ 월간 운영 절 — 9월 실제 일일 리포트로 주간과 같은 수 · 같은 코드 · 예약 작업 진입점
# ════════════════════════════════════════════════════════════════════════
def test_monthly_september_equals_the_union_of_its_weekly_sections():
    """월간(09-01~30)의 신호·작업별 날짜 = 9월에 걸친 주간(월~일) 보고 각각의 날짜를 9월로 잘라 합친 것."""
    import monthly_report as M                                                     # noqa: PLC0415
    import ops_digest as OD                                                        # noqa: PLC0415
    import weekly_report as W                                                      # noqa: PLC0415
    today = date(2026, 9, 27)
    ms, mu = M.month_range("2026-09")
    mops = M.collect_ops(ms, mu, today=today)
    if len(mops.get("reports") or []) < 7:
        pytest.skip("9월 일일 리포트가 이 작업 트리에 충분하지 않다")
    mst = OD.ops_stats(mops)
    wsup: dict = {}
    wjob: dict = {}
    d = ms - timedelta(days=ms.weekday())
    while d <= mu:
        a, b = W.week_range(d)
        st = W.ops_stats(W.collect_ops(a, b, today=today))
        for store, part, ks in ((wsup, st["supply"], ("alert", "no_ticket", "unmarked")),
                                (wjob, st["jobs"], ("due", "ok", "bad", "unknown"))):
            for n, s in part.items():
                for k in ks:
                    store.setdefault(n, {}).setdefault(k, []).extend(x for x in s[k] if str(ms) <= x <= str(mu))
        d += timedelta(days=7)
    for n, s in mst["supply"].items():
        for k in ("alert", "no_ticket", "unmarked"):
            assert sorted(s[k]) == sorted(wsup.get(n, {}).get(k, [])), (n, k)
    for n, j in mst["jobs"].items():
        for k in ("due", "ok", "bad", "unknown"):
            assert sorted(j[k]) == sorted(wjob.get(n, {}).get(k, [])), (n, k)
    assert set(mst["jobs"]) == set(wjob)
    # 월간 표의 굵은 일수 = 같은 수
    md = M.build_markdown("2026-09", ms, mu, {"error": "x"}, {"commits": []}, [], mops)
    for n, s in mst["supply"].items():
        if s["alert"]:
            row = next(ln for ln in md.splitlines() if ln.startswith(f"| {n} |"))
            assert f"**{len(wsup[n]['alert'])}일**" in row, row


def test_weekly_and_monthly_render_through_the_same_functions(monkeypatch):
    """공용인지 — ops_digest 의 함수를 바꿔치면 주간·월간이 **둘 다** 바뀐다(한쪽에 복사본이 남았으면 안 바뀐다)."""
    import monthly_report as M                                                     # noqa: PLC0415
    import ops_digest as OD                                                        # noqa: PLC0415
    import weekly_report as W                                                      # noqa: PLC0415
    calls = []
    monkeypatch.setattr(OD, "ops_section", lambda ops, **kw: calls.append(("section", kw.get("period"))) or ["§"])
    monkeypatch.setattr(OD, "panel_line", lambda ops, **kw: calls.append(("panel", kw.get("period"))) or ["¶"])
    W.ops_section({"reports": []})
    W.panel_line({"reports": []})
    ms, mu = M.month_range("2026-09")
    M.build_markdown("2026-09", ms, mu, {"error": "x"}, {"commits": []}, [], {"reports": []})
    assert calls == [("section", "이번 주"), ("panel", "이번 주"), ("section", "이 달"), ("panel", "이 달")]


@pytest.mark.parametrize("script", ["monthly_report.py", "weekly_report.py"])
def test_scheduled_entrypoint_imports_the_shared_module_from_a_foreign_cwd(script, tmp_path):
    """예약 작업은 `python "<repo>\\tools\\monthly_report.py"` 로 돈다(작업 폴더 지정 없음 — 실측).
    다른 폴더에서 불러도 `import ops_digest` 가 되는가 — 10-01 13:30 첫 월간 실행이 import 로 죽지 않는가.
    `--help` 는 인자 해석에서 끝나 서버·git 을 부르지 않는다."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, str(ROOT / "tools" / script), "--help"], cwd=str(tmp_path),
                       capture_output=True, timeout=120, env=env)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")[-800:]
    assert "--dry-run" in p.stdout.decode("utf-8", "replace")
