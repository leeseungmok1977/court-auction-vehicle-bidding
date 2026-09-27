# -*- coding: utf-8 -*-
"""OPS-4 — OPS-3 후속 세 가지(2026-09-27).

① 예약 작업이 **고장 표시 없이 조용히 안 도는 것**도 잡는다(Steward 결정, QA-OPS3-4):
   매일 작업 마지막 성공 36시간 · 주간 8일 · 월간 35일 초과 → 다음 실행이 잡혀 있어도 task 지시서 대상.
   주기는 작업 **트리거**에서 읽는다(작업 이름별 주기를 코드에 박지 않는다). 한 번도 안 돈 작업은 등록 후 한도 전에는 보지 않는다.
② 머리말 `workflow:` 가 비었거나 '없음'·'none'·'-'·'no' 면 워크플로로 보지 않는다(인계 정상 처리).
③ 월간 보고에 주간과 **같은 함수**의 '운영·공급' 절.

모두 tmp_path·가짜 스케줄 목록으로 돈다 — 작업 스케줄러·서버·외부 요청을 건드리지 않는다.
"""
from __future__ import annotations

import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import agent_dashboard as ad  # noqa: E402
import org_runtime as rt  # noqa: E402

NOW = datetime(2026, 9, 27, 13, 5, 0)
DAY = 86400
BACKLOG = """# 백로그

| ID | 제목 | 담당 | 상태 | 완료 기준(DoD) |
|---|---|---|---|---|
| AUD-06 | 공급 신호 오탐 | backend | todo · 확인(qa) | x |
"""

# 2026-09-27 15:2x 이 PC 작업 스케줄러에서 `Export-ScheduledTask` 로 읽은 트리거 XML 원문(읽기만).
NS = 'xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"'
X_DAILY = (f'<Triggers {NS}><CalendarTrigger><StartBoundary>2026-09-27T09:10:00+09:00</StartBoundary>'
           '<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger></Triggers>')
X_BOOT = f'<Triggers {NS}><BootTrigger><Delay>PT1M</Delay></BootTrigger></Triggers>'
X_MONTHLY = (f'<Triggers {NS}><CalendarTrigger><StartBoundary>2026-09-22T13:30:00</StartBoundary><ScheduleByMonth>'
             '<Months><January /><February /><March /><April /><May /><June /><July /><August /><September />'
             '<October /><November /><December /></Months><DaysOfMonth><Day>1</Day></DaysOfMonth></ScheduleByMonth>'
             '</CalendarTrigger></Triggers>')
X_MINUTE = (f'<Triggers {NS}><TimeTrigger><StartBoundary>2026-09-23T08:36:41+09:00</StartBoundary><Repetition>'
            '<Interval>PT1M</Interval><StopAtDurationEnd>true</StopAtDurationEnd></Repetition></TimeTrigger></Triggers>')
X_HOURLY = (f'<Triggers {NS}><TimeTrigger><StartBoundary>2026-09-27T00:05:00+09:00</StartBoundary><Repetition>'
            '<Interval>PT1H</Interval><StopAtDurationEnd>true</StopAtDurationEnd></Repetition></TimeTrigger></Triggers>')
X_SUNDAY = (f'<Triggers {NS}><CalendarTrigger><StartBoundary>2026-09-06T08:17:00+09:00</StartBoundary><ScheduleByWeek>'
            '<WeeksInterval>1</WeeksInterval><DaysOfWeek><Sunday /></DaysOfWeek></ScheduleByWeek></CalendarTrigger></Triggers>')


def _loc(s: str) -> str:
    """오프셋이 붙은 시각을 이 PC 현지 시각으로 — 테스트가 어느 시간대 PC 에서 돌아도 같은 답을 기대하게."""
    dt = datetime.fromisoformat(s)
    return dt.astimezone().replace(tzinfo=None).isoformat(sep=" ", timespec="minutes")


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


def task(name="naechaget-daily-report", **kw) -> dict:
    """read_schedule 한 행(OPS-4 모양). 기본은 결과 0 · 다음 실행 있음 · 매일 작업."""
    t = {"name": name, "status": "Ready", "running": False, "last_run": "2026-09-27 12:00",
         "last_result": "0", "next_run": "2026-09-28 12:00", "enabled": True, "never_ran": False, "ok": True,
         "period_s": DAY, "first_start": "", "registered": "", "trigger_error": ""}
    t.update(kw)
    return t


def registered(*extra) -> list[dict]:
    """§3.1 예약 작업 행 전부를 정상(방금 성공)으로 — '미등록'이 섞이지 않게. extra 가 같은 이름을 덮는다."""
    names = [n for n, r in rt.Org(ROOT).alert_routes().items() if r["source"] == "예약 작업"]
    ex = {e["name"] for e in extra}
    return [task(n) for n in names if n not in ex] + list(extra)


def sched(org, monkeypatch, rows, err=None):
    monkeypatch.setattr(org, "schedule_states", lambda: ([dict(r) for r in rows], err))


def by_reason(org, reason):
    return [o for o in org.orders().values() if o["meta"]["reason"] == reason]


def task_orders(org, name):
    """이 작업의 task 지시서만 — 다른 작업(기본값 09-27 12:00 성공)도 시간이 흐르면 정당하게 조용해진다."""
    return [o for o in by_reason(org, "task") if str(o["meta"]["key"]).startswith(f"task:{name}:")]


def settings():
    return rt.Org(ROOT).contracts()[0]


# ════════════════════════════════════════════════════════════════════════
# ① 주기는 트리거에서 — agent_dashboard.trigger_period
# ════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("xml,period", [
    (X_DAILY, DAY), (X_SUNDAY, 7 * DAY), (X_MONTHLY, 31 * DAY), (X_MINUTE, 60), (X_HOURLY, 3600), (X_BOOT, None),
])
def test_trigger_period_reads_the_real_0927_triggers(xml, period):
    assert ad.trigger_period(xml)["period_s"] == period
    assert ad.trigger_period(xml)["error"] == ""


def test_trigger_period_first_start_is_local_time():
    assert ad.trigger_period(X_DAILY)["first_start"] == _loc("2026-09-27T09:10:00+09:00")
    assert ad.trigger_period(X_MONTHLY)["first_start"] == "2026-09-22 13:30"          # 오프셋 없음 = 현지 시각
    assert ad.trigger_period(X_BOOT)["first_start"] == ""


def test_trigger_period_edge_shapes():
    week = (f'<Triggers {NS}><CalendarTrigger><StartBoundary>2026-09-01T09:00:00</StartBoundary><ScheduleByWeek>'
            '<WeeksInterval>{n}</WeeksInterval><DaysOfWeek>{d}</DaysOfWeek></ScheduleByWeek></CalendarTrigger></Triggers>')
    assert ad.trigger_period(week.format(n=1, d="<Monday /><Thursday />"))["period_s"] == 4 * DAY   # 목→월 4일이 가장 길다
    assert ad.trigger_period(week.format(n=2, d="<Sunday />"))["period_s"] == 14 * DAY
    quarterly = X_MONTHLY.replace("<February /><March />", "").replace("<May /><June />", "") \
                         .replace("<August /><September />", "").replace("<November /><December />", "")
    assert ad.trigger_period(quarterly)["period_s"] == 3 * 31 * DAY
    both = X_DAILY.replace("</ScheduleByDay>", "</ScheduleByDay><Repetition><Interval>PT30M</Interval></Repetition>")
    assert ad.trigger_period(both)["period_s"] == 1800                                  # 짧은 쪽
    two = X_BOOT.replace("</Triggers>", X_SUNDAY.split(">", 1)[1].replace("</Triggers>", "") + "</Triggers>")
    assert ad.trigger_period(two)["period_s"] == 7 * DAY                                # 부팅 + 매주 → 매주
    off = X_DAILY.replace("<StartBoundary>", "<Enabled>false</Enabled><StartBoundary>")
    assert ad.trigger_period(off)["period_s"] is None                                   # 꺼진 트리거는 안 센다
    assert ad.trigger_period("")["period_s"] is None and ad.trigger_period("")["error"] == ""
    assert ad.trigger_period("<Triggers")["error"]                                      # 깨진 XML 은 사유를 싣는다


@pytest.mark.parametrize("s,v", [("PT1M", 60), ("PT1H", 3600), ("P1D", DAY), ("P1DT2H", DAY + 7200),
                                 ("PT0S", None), ("", None), ("junk", None)])
def test_iso_duration(s, v):
    assert ad._iso_duration(s) == v


def test_read_schedule_rows_carry_period_fields(monkeypatch):
    """PowerShell 이 준 JSON → 행에 주기·첫 시작·등록 날짜·트리거 오류가 실린다(실제 작업 스케줄러는 안 부른다)."""
    import json
    import subprocess

    payload = [{"TaskName": "naechaget-db-backup-pull", "State": "Ready", "LastRunTime": "/Date(943887600000)/",
                "LastTaskResult": 267011, "NextRunTime": "/Date(1790554200000)/", "Registered": "",
                "Triggers": X_DAILY, "TriggerError": None},
               {"TaskName": "naechaget-monthly-report", "State": "Ready", "LastRunTime": None,
                "LastTaskResult": 0, "NextRunTime": None, "Registered": "2026-09-22T20:47:31",
                "Triggers": None, "TriggerError": "액세스가 거부되었습니다."}]

    class P:
        returncode = 0
        stdout = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: P())
    rows, err = ad.read_schedule()
    assert err is None
    r = {x["name"]: x for x in rows}
    assert r["naechaget-db-backup-pull"]["period_s"] == DAY and r["naechaget-db-backup-pull"]["trigger_error"] == ""
    assert r["naechaget-monthly-report"]["registered"] == "2026-09-22 20:47"
    assert r["naechaget-monthly-report"]["period_s"] is None
    assert "거부" in r["naechaget-monthly-report"]["trigger_error"]                    # 못 읽은 것은 '없음'이 아니다
    assert "Export-ScheduledTask" in ad._PS_SCHED and "TriggerError" in ad._PS_SCHED


# ════════════════════════════════════════════════════════════════════════
# ① 판정 — org_runtime.silence_verdict
# ════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("period,limit_h,cls", [
    (DAY, 36, "매일"), (3600, 36, "매일"), (60, 36, "매일"), (7 * DAY, 8 * 24, "매주"), (31 * DAY, 35 * 24, "매월"),
])
def test_silence_limit_edges_follow_the_steward_decision(period, limit_h, cls):
    s = settings()
    last = NOW - timedelta(hours=limit_h)
    t = task(period_s=period, last_run=last.isoformat(sep=" ", timespec="minutes"))
    v = rt.silence_verdict(t, NOW, s)
    assert v["bad"] and v["limit_h"] == limit_h and f"{cls} 작업" in v["label"]
    assert v["label"].startswith("조용히 안 돎 · 마지막 성공") and v["since"] == last.isoformat()
    t2 = task(period_s=period, last_run=(last + timedelta(minutes=1)).isoformat(sep=" ", timespec="minutes"))
    assert not rt.silence_verdict(t2, NOW, s)["bad"]                                    # 한도 1분 전


def test_silence_is_not_applied_where_it_does_not_belong():
    s, old = settings(), "2026-08-01 00:00"
    assert not rt.silence_verdict(task(period_s=None, last_run=old), NOW, s)["bad"]    # 부팅 트리거 — 주기 없음
    assert not rt.silence_verdict(task(period_s=93 * DAY, last_run=old), NOW, s)["bad"]  # 31일 초과 — 규칙 밖
    assert not rt.silence_verdict(task(running=True, last_run=old), NOW, s)["bad"]     # 실행 중은 정상
    legacy = {k: v for k, v in task(last_run=old).items() if k != "period_s"}
    assert not rt.silence_verdict(legacy, NOW, s)["bad"]                               # 트리거를 안 읽은 목록
    assert not rt.silence_verdict(task(last_run=old, next_run=""), NOW, s)["bad"]      # schedule_verdict 몫
    assert not rt.silence_verdict(task(last_run=old, ok=False, last_result="1"), NOW, s)["bad"]


def test_silence_warns_instead_of_guessing():
    v = rt.silence_verdict(task(last_run="2026-08-01 00:00", trigger_error="거부"), NOW, settings())
    assert not v["bad"] and "트리거를 읽지 못했다" in v["warn"]
    v = rt.silence_verdict(task(last_run="2026-08-01 00:00"), NOW, {})
    assert not v["bad"] and "성공 없음 한도 · 매일(시간)" in v["warn"]                 # 한도를 코드가 지어내지 않는다


def test_never_ran_waits_for_period_plus_margin_after_registration():
    s = settings()
    nr = dict(never_ran=True, ok=False, last_result="267011", last_run="1999-11-30 00:00")
    # 등록 날짜가 있으면 그것부터(월간 보고: 09-22 20:47 등록 · 한도 35일)
    m = task("naechaget-monthly-report", period_s=31 * DAY, registered="2026-09-22 20:47",
             first_start="2026-09-22 13:30", next_run="2026-10-01 13:30", **nr)
    assert not rt.silence_verdict(m, datetime(2026, 10, 27, 20, 46), s)["bad"]
    v = rt.silence_verdict(m, datetime(2026, 10, 27, 20, 47), s)
    assert v["bad"] and v["label"].startswith("첫 실행 없음 · 등록 09-22 20:47 뒤 매월 작업 한도 35일")
    # 등록 날짜가 없으면 순환계가 처음 본 시각부터(DB 백업 내려받기: 첫 실행 09-28 09:10)
    b = task("naechaget-db-backup-pull", first_start="2026-09-27 09:10", next_run="2026-09-28 09:10", **nr)
    seen = "2026-09-27T16:05:00"
    assert not rt.silence_verdict(b, datetime(2026, 9, 29, 4, 4), s, seen)["bad"]
    assert rt.silence_verdict(b, datetime(2026, 9, 29, 4, 5), s, seen)["bad"]
    # 등록 날짜도 처음 본 시각도 없으면 첫 트리거 시작부터 — 그것도 없으면 보지 않는다
    assert rt.silence_verdict(b, datetime(2026, 9, 28, 21, 10), s, "")["bad"]
    assert not rt.silence_verdict(b, datetime(2026, 9, 28, 21, 9), s, "")["bad"]
    assert not rt.silence_verdict(dict(b, first_start=""), datetime(2026, 12, 1), s, "")["bad"]
    # 첫 트리거 시작이 등록보다 늦으면 그때부터
    late = task(first_start="2026-10-10 09:00", registered="2026-09-27 10:00", next_run="2026-10-10 09:00", **nr)
    assert not rt.silence_verdict(late, datetime(2026, 10, 11, 20, 59), s)["bad"]
    assert rt.silence_verdict(late, datetime(2026, 10, 11, 21, 0), s)["bad"]
    # 예정도 없으면 schedule_verdict 가 이미 고장으로 본다 — 여기서 두 번 세지 않는다
    assert not rt.silence_verdict(dict(b, next_run=""), datetime(2026, 12, 1), s, seen)["bad"]


# ════════════════════════════════════════════════════════════════════════
# ① 스캔 — 지시서·멱등·열린 티켓·상태 파일
# ════════════════════════════════════════════════════════════════════════
def test_daily_task_skipped_for_two_days_becomes_one_task_order(org, monkeypatch):
    stale = task("naechaget-daily-report", last_run="2026-09-25 12:00", next_run="2026-09-28 12:00")
    sched(org, monkeypatch, registered(stale))
    r = org.scan(now=NOW)
    t = by_reason(org, "task")
    assert len(t) == 1 and t[0]["meta"]["to"] == rt.STEWARD
    assert t[0]["meta"]["key"] == "task:naechaget-daily-report:2026-09-25T12:00"       # 고장 시작 = 마지막 성공
    assert "조용히 안 돎" in t[0]["body"] and "다음 실행 2026-09-28 12:00" in t[0]["body"]
    ev = next(x for x in r["tasks"] if x["name"] == "naechaget-daily-report")
    assert ev["hours"] == 49 and ev["need_hours"] == 36 and ev["action"] == "order"
    for h in (1, 2, 30):
        org.scan(now=NOW + timedelta(hours=h))
    assert len(by_reason(org, "task")) == 1                                             # 멱등


def test_closing_the_order_as_intended_does_not_reopen_the_same_silence(org, monkeypatch):
    stale = task("naechaget-daily-report", last_run="2026-09-25 12:00", next_run="2026-09-28 12:00")
    sched(org, monkeypatch, registered(stale))
    org.scan(now=NOW)
    o = task_orders(org, "naechaget-daily-report")[0]
    org.set_status(o, "done", note="PC 를 이틀 껐다 — 의도된 상태")
    r = org.scan(now=NOW + timedelta(hours=5))
    assert len(task_orders(org, "naechaget-daily-report")) == 1
    assert next(x for x in r["tasks"] if x["name"] == "naechaget-daily-report")["action"] == "done-before"
    # 다시 돌았다가 또 조용히 빠지면 새 구간 — 새 지시서
    again = task("naechaget-daily-report", last_run="2026-09-28 12:00", next_run="2026-09-29 12:00")
    sched(org, monkeypatch, registered(again))
    org.scan(now=datetime(2026, 9, 28, 13, 5))
    assert not org._state()["task_bad"].get("naechaget-daily-report")                   # 풀렸다
    org.scan(now=datetime(2026, 9, 30, 1, 5))
    keys = sorted(x["meta"]["key"] for x in task_orders(org, "naechaget-daily-report"))
    assert keys == ["task:naechaget-daily-report:2026-09-25T12:00", "task:naechaget-daily-report:2026-09-28T12:00"]


def test_open_ticket_keeps_the_existing_rule(org, monkeypatch):
    """열린 티켓이 맡고 있으면 지시서를 만들지 않는다 — 스탠드업 줄에는 나온다.

    r2(2026-09-27): 실제 §3.1 은 Steward 결정으로 주간 작업의 티켓 칸을 `-` 로 비웠다. 규칙 자체를 보려고
    임시 계약표의 그 한 칸만 `AUD-15` 로 되돌려 둔다 — 실제 표에 기대지 않는다.
    """
    c = org.contracts_md.read_text(encoding="utf-8")
    row = next(ln for ln in c.splitlines() if ln.startswith("| `naechaget-weekly-report` |"))
    cells = row.split("|")
    cells[4] = " `AUD-15` "
    org.contracts_md.write_text(c.replace(row, "|".join(cells)), encoding="utf-8")
    assert org.alert_routes()["naechaget-weekly-report"]["ticket"] == "AUD-15"
    org.backlog_md.write_text(BACKLOG + "| AUD-15 | 따라잡기 없음 | Steward | todo(낮음) | x |\n", encoding="utf-8")
    stale = task("naechaget-weekly-report", period_s=7 * DAY, last_run="2026-09-19 13:00", next_run="2026-10-03 13:00")
    sched(org, monkeypatch, registered(stale))
    r = org.scan(now=NOW)
    assert by_reason(org, "task") == []
    ev = next(x for x in r["tasks"] if x["name"] == "naechaget-weekly-report")
    assert ev["action"] == "ticket-open" and ev["ticket"] == "AUD-15" and "매주 작업 한도 8일" in ev["label"]
    text = org.standup(now=NOW + timedelta(minutes=1)).read_text(encoding="utf-8")
    assert "`naechaget-weekly-report` 조용히 안 돎" in text


def test_first_run_that_never_happens_is_seen_after_registration_plus_limit(org, monkeypatch):
    b = task("naechaget-db-backup-pull", never_ran=True, ok=False, last_result="267011", last_run="1999-11-30 00:00",
             first_start="2026-09-27 09:10", next_run="2026-09-28 09:10")
    sched(org, monkeypatch, registered(b))
    org.scan(now=NOW)                                                                   # 처음 봄 = 09-27 13:05
    assert org._state()["task_seen"]["naechaget-db-backup-pull"] == NOW.isoformat()
    org.scan(now=NOW + timedelta(hours=35, minutes=59))
    assert task_orders(org, "naechaget-db-backup-pull") == []
    org.scan(now=NOW + timedelta(hours=36))
    t = task_orders(org, "naechaget-db-backup-pull")
    assert len(t) == 1 and "첫 실행 없음 · 등록 09-27 13:05 뒤 매일 작업 한도 36시간 넘김" in t[0]["body"]
    assert t[0]["meta"]["key"] == "task:naechaget-db-backup-pull:2026-09-27T13:05"


def test_dry_run_does_not_record_first_seen(org, monkeypatch):
    sched(org, monkeypatch, registered())
    org.dry_run = True
    org.scan(now=NOW)
    assert not org.state_file.exists()


def test_removed_task_forgets_first_seen(org, monkeypatch):
    sched(org, monkeypatch, registered())
    org.scan(now=NOW)
    assert "naechaget-ops-snapshot" in org._state()["task_seen"]
    sched(org, monkeypatch, [t for t in registered() if t["name"] != "naechaget-ops-snapshot"])
    org.scan(now=NOW + timedelta(hours=1))
    assert "naechaget-ops-snapshot" not in org._state()["task_seen"]


def test_trigger_read_failure_is_a_warning_not_a_silent_pass(org, monkeypatch):
    t = task("naechaget-org-standup", last_run="2026-09-20 08:45", trigger_error="액세스가 거부되었습니다.")
    sched(org, monkeypatch, registered(t))
    r = org.scan(now=NOW)
    assert by_reason(org, "task") == []
    assert any("naechaget-org-standup" in w and "트리거를 읽지 못했다" in w for w in r["warnings"])


def test_breakdown_rules_still_win_and_keep_their_24h_wait(org, monkeypatch):
    """고장(실패)은 전과 같다 — 조용히 안 돎이 고장 판정을 덮지 않는다."""
    f = task("naechaget-org-standup", last_run="2026-09-27 08:45", last_result="1", ok=False)
    sched(org, monkeypatch, registered(f))
    r = org.scan(now=NOW)
    ev = next(x for x in r["tasks"] if x["name"] == "naechaget-org-standup")
    assert ev["label"] == "실패 · 결과 1(0x00000001)" and ev["need_hours"] == 24 and ev["action"] == "below"


# ════════════════════════════════════════════════════════════════════════
# ① 문서 ↔ 코드
# ════════════════════════════════════════════════════════════════════════
def _sec(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i:text.index(end, i)]


def test_contract_carries_the_limits_and_the_decision():
    c = (ROOT / "docs" / "org-contracts.md").read_text(encoding="utf-8")
    src = (ROOT / "tools" / "org_runtime.py").read_text(encoding="utf-8")
    s = settings()
    for cls, _, key, _ in rt.SILENCE_CLASSES:
        assert f"`{key}`" in _sec(c, "## 1.", "## 2.") and f'"{key}"' in src
    assert (s["성공 없음 한도 · 매일(시간)"], s["성공 없음 한도 · 매주(일)"], s["성공 없음 한도 · 매월(일)"]) == (36, 8, 35)
    s3 = _sec(c, "## 3.", "### 3.1")
    assert "결정 대기" not in s3 and "Steward 결정 2026-09-27(QA-OPS3-4)" in s3
    assert "트리거에서 읽는다" in s3 and "trigger_period" in s3 and "task_seen" in s3
    row = next(ln for ln in s3.splitlines() if ln.startswith("| **예약 작업**"))
    assert "'조용히 안 돎'" in row and "'첫 실행 없음'" in row
    # 문서에 적힌 판정 이름 = 코드가 내는 라벨의 머리
    v1 = rt.silence_verdict(task(last_run="2026-09-01 00:00"), NOW, s)["label"]
    v2 = rt.silence_verdict(task(never_ran=True, ok=False, registered="2026-09-01 00:00"), NOW, s)["label"]
    assert v1.startswith("조용히 안 돎") and v2.startswith("첫 실행 없음")


def test_no_task_name_carries_a_hardcoded_period():
    """주기는 트리거에서 — 작업 이름과 주기를 짝지은 표가 코드에 없다(Steward 지시)."""
    src = (ROOT / "tools" / "org_runtime.py").read_text(encoding="utf-8")
    body = src[src.index("def silence_verdict"):src.index("def workflow_of")]
    assert "naechaget-" not in body


# ════════════════════════════════════════════════════════════════════════
# ② workflow: 없음 · none · - · no 는 워크플로가 아니다
# ════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("v", [None, False, "", "  ", "없음", "none", "None", "NONE", "-", "—", "no", "No",
                               "null", "n/a", "false", []])
def test_workflow_of_empty_values(v):
    assert rt.workflow_of({"workflow": v}) == ""


def test_workflow_of_real_ids():
    assert rt.workflow_of({"workflow": "ops4-followups"}) == "ops4-followups"
    assert rt.workflow_of({"workflow": " audit-1-run-3 "}) == "audit-1-run-3"
    assert rt.workflow_of({}) == ""


def _raw_report(org, name: str, workflow_line: str, result="done", handoff=True) -> None:
    """머리말을 **손으로 쓴 그대로** 둔다 — dump_front 는 값을 따옴표로 감싸 YAML 해석 차이를 지운다."""
    lines = ["---", "from: backend-engineer", "ticket: OPS-4", f"result: {result}", "verified: 재현"]
    if workflow_line is not None:
        lines.append(workflow_line)
    lines += (["handoff:", "  - to: qa-engineer", "    why: 반증"] if handoff else ["handoff: []"])
    lines += ["---", "본문"]
    (org.root / "reports" / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.mark.parametrize("line", ["workflow: 없음", "workflow: none", "workflow: None", "workflow: -",
                                  "workflow: '-'", "workflow: no", "workflow: 'no'", "workflow:", "workflow: ''"])
def test_handoff_with_no_workflow_value_is_processed_normally(org, line):
    _raw_report(org, "be.md", line)
    org.scan(now=NOW)
    assert [o["meta"]["to"] for o in by_reason(org, "handoff")] == ["qa-engineer"], line
    assert not [e for e in org.events() if e.get("kind") == "handoff.skipped"], line


@pytest.mark.parametrize("line", ["workflow: 없음", "workflow: none"])
def test_fail_without_handoff_and_no_workflow_value_goes_to_pm(org, line):
    _raw_report(org, "be.md", line, result="fail", handoff=False)
    org.scan(now=NOW)
    assert [o["meta"]["to"] for o in by_reason(org, "result")] == ["pm-orchestrator"], line


def test_bare_dash_workflow_line_is_emptied_and_nothing_else():
    """`workflow: -` 는 YAML 문법 오류라 전에는 머리말 **전체**가 깨졌다(인계가 통째로 사라짐). 그 한 줄만 비운다."""
    m, _ = rt.split_front("\n".join(["---", "from: x", "workflow: -", "handoff: []", "---", ""]))
    assert m == {"from": "x", "workflow": "", "handoff": []}
    m, _ = rt.split_front("\n".join(["---", "from: x", "ticket: -", "handoff: []", "---", ""]))
    assert m == {"__broken__": True}                                                   # 다른 줄의 오류는 그대로


def test_real_workflow_id_still_skips(org):
    _raw_report(org, "be.md", "workflow: ops4-followups")
    org.scan(now=NOW)
    assert by_reason(org, "handoff") == []
    assert [e for e in org.events() if e.get("kind") == "handoff.skipped"]


def test_handoff_protocol_says_so():
    hp = (ROOT / ".claude" / "agents" / "_handoff-protocol.md").read_text(encoding="utf-8")
    w = _sec(hp, "### 워크플로가 부른 단계면", "## 3.")
    assert "`없음`·`none`·`-`·`no`" in w and "워크플로로 보지 않는다" in w
    for v in ("없음", "none", "-", "no"):
        assert v in rt.NO_WORKFLOW


# ════════════════════════════════════════════════════════════════════════
# ③ 월간 운영·공급 절 — 주간과 같은 함수
# ════════════════════════════════════════════════════════════════════════
def _monthly():
    import monthly_report as M                                                     # noqa: PLC0415
    return M


def _weekly():
    import weekly_report as W                                                      # noqa: PLC0415
    return W


def test_monthly_import_does_not_replace_stdout():
    before = sys.stdout
    _monthly()
    assert sys.stdout is before


def test_weekly_and_monthly_share_one_implementation():
    import ops_digest as OD                                                        # noqa: PLC0415
    M, W = _monthly(), _weekly()
    assert W.ops_stats is OD.ops_stats and M.ops_digest is OD
    for name in ("tools/weekly_report.py", "tools/monthly_report.py"):
        src = (ROOT / name).read_text(encoding="utf-8")
        assert "def ops_stats" not in src and "sup: dict[str, dict]" not in src, name   # 복붙 금지
        assert "| 신호 | 이상·멈춤 |" not in src, name


def _ops_fixture():
    def p(supply=None, jobs=None, ticket=None):
        return {"supply": {k: {"state": v, "ticket": ticket} for k, v in (supply or {}).items()},
                "jobs": {k: {"state": v} for k, v in (jobs or {}).items()}, "issues": []}
    reps = [("2026-09-15", p(jobs={"매일 시세·낙찰 갱신": "alert", "주간 전문가 패널": "na"})),
            ("2026-09-24", p({"케이카 교차검증": "alert", "물건 수집": "ok"}, {"매일 시세·낙찰 갱신": "ok"})),
            ("2026-09-25", p({"케이카 교차검증": "alert", "물건 수집": "alert"}, {"매일 시세·낙찰 갱신": "alert"})),
            ("2026-09-26", p({"케이카 교차검증": "alert", "물건 수집": "ok"},
                             {"매일 시세·낙찰 갱신": "ok", "주간 전문가 패널": "alert"}, ticket="**❗ 티켓 없음**"))]
    return {"reports": reps, "missing": [f"2026-09-{d:02d}" for d in range(1, 15)],
            "tickets": {"케이카 교차검증": {"ticket": "KCAR-1", "state": "닫힘", "status": "완료"}}}


def test_monthly_ops_section_counts_and_folds_long_day_runs():
    M = _monthly()
    since, until = M.month_range("2026-09")
    md = M.build_markdown("2026-09", since, until, {"error": "x"}, {"commits": []}, ["2026-09-12.md"], _ops_fixture())
    assert md.index("## 운영·공급") < md.index("## 고객 유입")                     # 주간과 같이 맨 앞
    sec = md.split("## 운영·공급")[1].split("\n## ")[0]
    assert "이 달 일일 리포트 **4편**" in sec and "리포트 없는 날 09-01~09-14" in sec
    k = next(ln for ln in sec.splitlines() if ln.startswith("| 케이카 교차검증 |"))
    assert "**3일** (09-24~09-26)" in k and "`KCAR-1`" in k and "**1일** · 칸 생기기 전 2일" in k
    j = next(ln for ln in sec.splitlines() if ln.startswith("| 매일 시세·낙찰 갱신 |"))
    assert "| 4회 | 2회 | **2회** (09-15·09-25) |" in j
    q = md.split("## 품질")[1].split("\n## ")[0]
    assert "**실패 1회**(09-26)" in q and q.index("정기 실행") < q.index("2026-09-12.md")   # 파일 수로 가리지 않는다
    assert "전문가 패널 리포트 **" not in md


def test_monthly_ops_section_unknown_is_not_quiet():
    M = _monthly()
    since, until = M.month_range("2026-09")
    for ops in (None, {"error": "경보 표를 읽지 못함"}, {"reports": [], "missing": [], "tickets": {}}):
        md = M.build_markdown("2026-09", since, until, {"error": "x"}, {"commits": []}, [], ops)
        sec = md.split("## 운영·공급")[1].split("\n## ")[0]
        assert "확인 불가" in sec
    md = M.build_markdown("2026-09", since, until, {"error": "x"}, {"commits": []}, [],
                          {"reports": [], "missing": [], "tickets": {}})
    assert "이 달 일일 리포트가 한 편도 없다" in md and "이상이 없었다는 뜻이 아니다" in md


def test_weekly_wording_is_unchanged_by_the_move():
    W = _weekly()
    md = "\n".join(W.ops_section(_ops_fixture()))
    assert "이번 주 일일 리포트 **4편**" in md
    assert "리포트 없는 날 09-01·09-02·09-03" in md                                  # 주간은 접지 않는다(전과 같다)
    assert "**3일** (09-24·09-25·09-26)" in md


@pytest.mark.parametrize("ds,compact,out", [
    (["2026-09-24", "2026-09-25", "2026-09-26"], False, "09-24·09-25·09-26"),
    (["2026-09-24", "2026-09-25", "2026-09-26"], True, "09-24~09-26"),
    (["2026-09-24", "2026-09-25"], True, "09-24·09-25"),
    (["2026-09-15", "2026-09-19", "2026-09-20", "2026-09-21", "2026-09-27"], True, "09-15·09-19~09-21·09-27"),
    (["2026-09-30", "2026-10-01", "2026-10-02"], True, "09-30~10-02"),
    ([], True, ""),
])
def test_days_text(ds, compact, out):
    import ops_digest as OD                                                        # noqa: PLC0415
    assert OD.days_text(ds, compact) == out


def test_monthly_main_wires_the_ops_section(monkeypatch, capsys):
    """진입점이 운영 절을 실제로 채우는가 — 서버·git 은 부르지 않는다."""
    M = _monthly()
    monkeypatch.setattr(M, "collect_server", lambda: {"error": "테스트: 서버 안 읽음"})
    monkeypatch.setattr(M, "collect_git", lambda a, b: {"commits": []})
    seen = {}

    def fake_ops(a, b, today=None):
        seen["range"] = (a, b)
        return _ops_fixture()

    monkeypatch.setattr(M, "collect_ops", fake_ops)
    assert M.main(["2026-09", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert seen["range"] == (date(2026, 9, 1), date(2026, 9, 30))
    assert "## 운영·공급" in out and "**3일** (09-24~09-26)" in out


def test_monthly_september_counts_match_the_raw_daily_reports():
    """실제 9월 일일 리포트로 — 공용 파서가 아니라 원문 표를 직접 잘라 센 값과 대조한다."""
    M = _monthly()
    since, until = M.month_range("2026-09")
    ops = M.collect_ops(since, until, today=date(2026, 9, 27))
    if len(ops.get("reports") or []) < 7:
        pytest.skip("9월 일일 리포트가 이 작업 트리에 충분하지 않다")
    bs = chr(92)
    raw_sup: dict[str, list] = {}
    raw_job: dict[str, list] = {}
    for d, _ in ops["reports"]:
        text = (ROOT / "docs" / "daily-reports" / f"{d}.md").read_text(encoding="utf-8")
        for head, store, col, marks in (("## 공급 상태", raw_sup, 1, ("🛑", "⚠")),
                                        ("## 정기 작업", raw_job, 5, ("❌", "⚠", "⏭"))):
            if head not in text:
                continue
            for ln in text.split(head, 1)[1].split("\n## ", 1)[0].splitlines():
                if not ln.startswith("|") or ln.startswith("|---") or ln.startswith(("| 신호", "| 작업")):
                    continue
                c = [x.strip() for x in ln.replace(bs + "|", "").strip().strip("|").split("|")]
                if len(c) > col and any(m in c[col] for m in marks):
                    store.setdefault(c[0], []).append(d)
    import ops_digest as OD                                                        # noqa: PLC0415
    st = OD.ops_stats(ops)
    assert {n: s["alert"] for n, s in st["supply"].items() if s["alert"]} == raw_sup
    assert {n: j["bad"] for n, j in st["jobs"].items() if j["bad"]} == raw_job
    md = M.build_markdown("2026-09", since, until, {"error": "x"}, {"commits": []}, [], ops)
    for n, ds in raw_sup.items():
        row = next(ln for ln in md.splitlines() if ln.startswith(f"| {n} |"))
        assert f"**{len(ds)}일**" in row, row
