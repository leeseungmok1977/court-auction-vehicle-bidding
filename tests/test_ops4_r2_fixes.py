# -*- coding: utf-8 -*-
"""OPS-4 수정 회차(r2, 지시서 2026-09-27-69) — qa 결함 QA-OPS4-1·2·3 과 Steward 결정의 **가장자리**를 지킨다.

① `workflow: -   # 주석` 도 '워크플로 없음'(QA-OPS4-3) — 값이 더 붙은 `- x` 는 여전히 깨짐
② 반복의 끝나는 `Duration` 은 바깥 트리거 주기를 쓴다(QA-OPS4-1) — 창이 이어지면(Duration ≥ 바깥 주기) 반복 간격
③ 끝난 트리거(`EndBoundary` 지남)는 주기·첫 시작에서 뺀다(QA-OPS4-2)
④ 대시보드 예약 작업 행·KPI 는 순환계 `silence_verdict` 결과를 **그대로** 싣는다(규칙은 org_runtime 한 곳)
⑤ §3.1 네 행의 티켓 칸 `-`(Steward 결정) · 따라잡기 적용 사실 · '정기 작업'↔'예약 작업' 어휘

모두 tmp_path·가짜 스케줄 목록으로 돈다 — 작업 스케줄러·서버·외부 요청을 건드리지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import agent_dashboard as ad  # noqa: E402
import org_runtime as rt  # noqa: E402

DAY = 86400
NS = 'xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"'
NOW = datetime(2026, 9, 27, 17, 5)
STEWARD_MARK = "2026-09-27 Steward: 조용한 누락은 지시서로(열린 티켓이 다른 주제)"
FOUR = ("naechaget-db-backup-pull", "naechaget-weekly-report", "naechaget-monthly-report", "NaechaGet-PhotoClassify")
BACKLOG = """# 백로그

| ID | 제목 | 담당 | 상태 | 완료 기준(DoD) |
|---|---|---|---|---|
| AUD-05 | 터널 | Steward | todo · Steward 재현 확인 | x |
| AUD-08 | 백업·헬스체크 | backend | **백업 완료(2026-09-27) · 헬스체크 남음** | x |
| AUD-15 | 운영 위생 묶음 | 각 담당 | todo(낮음) | x |
"""


def _T(body: str) -> str:
    return f"<Triggers {NS}>{body}</Triggers>"


def _weekly(extra: str = "", start: str = "2026-09-05T13:00:00", end: str = "") -> str:
    eb = f"<EndBoundary>{end}</EndBoundary>" if end else ""
    return (f"<CalendarTrigger><StartBoundary>{start}</StartBoundary>{eb}{extra}<ScheduleByWeek><WeeksInterval>1"
            "</WeeksInterval><DaysOfWeek><Saturday /></DaysOfWeek></ScheduleByWeek></CalendarTrigger>")


def _daily(extra: str = "", start: str = "2026-08-01T09:00:00", end: str = "") -> str:
    eb = f"<EndBoundary>{end}</EndBoundary>" if end else ""
    return (f"<CalendarTrigger><StartBoundary>{start}</StartBoundary>{eb}{extra}<ScheduleByDay><DaysInterval>1"
            "</DaysInterval></ScheduleByDay></CalendarTrigger>")


def _rep(interval: str, duration: str | None = None) -> str:
    d = "" if duration is None else f"<Duration>{duration}</Duration>"
    return f"<Repetition><Interval>{interval}</Interval>{d}<StopAtDurationEnd>false</StopAtDurationEnd></Repetition>"


def _loc(s: str) -> datetime:
    return datetime.fromisoformat(s).astimezone().replace(tzinfo=None)


def task(name="naechaget-daily-report", **kw) -> dict:
    t = {"name": name, "status": "Ready", "running": False, "last_run": "2026-09-27 12:00",
         "last_result": "0", "next_run": "2026-09-28 12:00", "enabled": True, "never_ran": False, "ok": True,
         "period_s": DAY, "first_start": "", "registered": "", "trigger_error": ""}
    t.update(kw)
    return t


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


def _report(org, workflow_line, name="be.md"):
    lines = ["---", "from: backend-engineer", "ticket: OPS-4", "result: done", "verified: 재현", workflow_line,
             "handoff:", "  - to: qa-engineer", "    why: 반증", "---", "본문", ""]
    (org.root / "reports" / name).write_text("\n".join(lines), encoding="utf-8")


def _handoffs(org):
    return sorted(o["meta"]["to"] for o in org.orders().values() if o["meta"]["reason"] == "handoff")


# ════════════════════════════════════════════════════════════════════════
# ① workflow: - 뒤 주석(QA-OPS4-3)
# ════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("line", ["workflow: -   # 워크플로 밖", "workflow: -\t# 탭 뒤 주석",
                                  "workflow: - #", "workflow:-  # 콜론 뒤 공백 없음"])
def test_bare_dash_with_any_trailing_comment_is_no_workflow(org, line):
    _report(org, line)
    r = org.scan(now=NOW)
    assert _handoffs(org) == ["qa-engineer"], line
    assert not [w for w in r["warnings"] if "머리말" in w], line
    assert not [e for e in org.events() if str(e.get("kind", "")).endswith(".skipped")], line


def test_dash_glued_to_hash_is_a_yaml_value_and_leaves_a_skip_record(org):
    """한계(확인된 사실): YAML 주석은 `#` 앞에 공백이 있어야 한다. `workflow: -#x` 는 문법 오류가 아니라 **값 '-#x'** 라
    정규식까지 오지 않고 워크플로로 취급된다. 조용히 사라지지는 않는다 — 버스에 `handoff.skipped` 가 남는다."""
    assert rt.split_front("---\nworkflow: -#x\n---\n")[0] == {"workflow": "-#x"}
    _report(org, "workflow: -# 붙은 주석")
    org.scan(now=NOW)
    assert _handoffs(org) == []
    assert [e for e in org.events() if e.get("kind") == "handoff.skipped"]


@pytest.mark.parametrize("line", ["workflow: - x", "workflow: - x  # 주석", "workflow: -- # 주석"])
def test_dash_followed_by_a_value_is_not_rescued(line):
    """주석이 아닌 값이 더 붙으면 '없음'이 아니다 — 그 줄만 비우지 않는다(깨짐은 경고로 드러난다)."""
    m, _ = rt.split_front("\n".join(["---", "from: x", line, "handoff: []", "---", ""]))
    if m != {"__broken__": True}:                       # YAML 이 값으로 읽었다면 워크플로로 취급된다(비우지 않았다)
        assert rt.workflow_of(m) != "", line


def test_the_rescue_touches_only_the_workflow_line():
    """다른 줄의 `-  # 주석`(예: ticket)은 고치지 않는다 — 그 머리말은 여전히 깨짐이다."""
    m, _ = rt.split_front("\n".join(["---", "from: x", "workflow: -  # 밖", "ticket: -  # 없음", "---", ""]))
    assert m == {"__broken__": True}
    assert rt._BARE_DASH_WORKFLOW.sub("workflow: ''", "workflow: -  # a\nticket: -  # b") == \
        "workflow: ''\nticket: -  # b"


# ════════════════════════════════════════════════════════════════════════
# ② 반복의 Duration(QA-OPS4-1)
# ════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("trig,period", [
    (_weekly(_rep("PT1H", "PT3H")), 7 * DAY),            # 토 13:00 부터 3시간 매시 — 매주 작업
    (_weekly(_rep("PT1H", "P6D")), 7 * DAY),             # 창(6일) < 바깥 주기(7일) — 하루 넘게 비는 날이 있다
    (_weekly(_rep("PT1H", "P7D")), 3600),                # 창이 다음 회차까지 이어진다 — 매시
    (_weekly(_rep("PT1H")), 3600),                       # Duration 없음 = 무기한
    (_weekly(_rep("PT1H", "P0D")), 3600),                # 0 도 무기한으로 읽는다
    (_weekly(_rep("PT1H", "")), 3600),                   # 빈 요소 = 무기한
    (_weekly(_rep("PT1H", "P1W")), 7 * DAY),             # 못 읽는 글자 — 무기한으로 치지 않는다(바깥 주기)
    (_daily(_rep("PT1H", "P1D")), 3600),                 # 흔한 GUI 설정 '매일, 1시간마다 1일 동안' — 매시
    (_daily(_rep("PT10M", "PT2H")), DAY),                # 매일 2시간 창 — 매일 작업
])
def test_repetition_duration_uses_the_outer_period_unless_the_window_is_continuous(trig, period):
    assert ad.trigger_period(_T(trig), now=NOW)["period_s"] == period


def test_one_shot_trigger_with_a_finite_repetition_dies_at_start_plus_duration():
    x = _T("<TimeTrigger><StartBoundary>2026-09-27T00:00:00</StartBoundary>" + _rep("PT1H", "P1D") + "</TimeTrigger>")
    live = ad.trigger_period(x, now=datetime(2026, 9, 27, 12, 0))
    assert (live["period_s"], live["first_start"]) == (3600, "2026-09-27 00:00")
    dead = ad.trigger_period(x, now=datetime(2026, 9, 28, 0, 0))
    assert (dead["period_s"], dead["first_start"], dead["error"]) == (None, "", "")     # 규칙 밖 — 오류 아님
    # 무기한 반복인 한 번 트리거(이 PC 의 ops-snapshot·heartbeat 모양)는 언제나 살아 있다
    y = _T("<TimeTrigger><StartBoundary>2026-09-23T08:36:41</StartBoundary>" + _rep("PT1M") + "</TimeTrigger>")
    assert ad.trigger_period(y, now=datetime(2027, 1, 1))["period_s"] == 60


def test_finite_duration_weekly_task_is_not_flagged_on_monday_but_is_after_eight_days():
    """QA-OPS4-1 의 결과 쪽 — 매주 한도(8일)로 판정된다."""
    p = ad.trigger_period(_T(_weekly(_rep("PT1H", "PT3H"))), now=NOW)["period_s"]
    s = rt.Org(ROOT).contracts()[0]
    t = task("x", period_s=p, last_run="2026-09-26 15:00", next_run="2026-10-03 13:00")
    assert not rt.silence_verdict(t, datetime(2026, 9, 28, 3, 0), s)["bad"]
    assert not rt.silence_verdict(t, datetime(2026, 10, 4, 14, 59), s)["bad"]
    v = rt.silence_verdict(t, datetime(2026, 10, 4, 15, 0), s)
    assert v["bad"] and v["cls"] == "매주" and v["limit_h"] == 8 * 24


# ════════════════════════════════════════════════════════════════════════
# ③ 끝난 트리거(QA-OPS4-2)
# ════════════════════════════════════════════════════════════════════════
def test_expired_trigger_is_dropped_from_period_and_first_start():
    x = _T(_daily(end="2026-08-31T09:00:00") + _weekly())
    tp = ad.trigger_period(x, now=NOW)
    assert tp["period_s"] == 7 * DAY and tp["first_start"] == "2026-09-05 13:00"
    # 끝나기 전에는 매일 트리거가 살아 있다 — 첫 시작도 그것
    tp = ad.trigger_period(x, now=datetime(2026, 8, 20))
    assert tp["period_s"] == DAY and tp["first_start"] == "2026-08-01 09:00"


def test_end_boundary_is_compared_in_local_time_and_is_exclusive_at_the_instant():
    end = "2026-09-27T12:00:00+09:00"
    x = _T(_daily(end=end))
    at = _loc(end)
    assert ad.trigger_period(x, now=at - timedelta(minutes=1))["period_s"] == DAY
    assert ad.trigger_period(x, now=at)["period_s"] is None                        # 끝난 순간부터 죽었다


def test_all_triggers_expired_is_out_of_rule_not_an_error():
    tp = ad.trigger_period(_T(_daily(end="2026-08-31T09:00:00") + _weekly(end="2026-09-01T00:00:00")), now=NOW)
    assert (tp["period_s"], tp["first_start"], tp["error"]) == (None, "", "")


def test_default_now_is_the_reading_moment():
    """`now` 를 안 주면 읽는 순간 — read_schedule 이 그렇게 부른다."""
    assert ad.trigger_period(_T(_daily(end="2000-01-01T00:00:00")))["period_s"] is None
    assert ad.trigger_period(_T(_daily(end="2099-01-01T00:00:00")))["period_s"] == DAY


# ════════════════════════════════════════════════════════════════════════
# ④ 대시보드는 순환계 판정을 그대로 싣는다
# ════════════════════════════════════════════════════════════════════════
def test_silence_verdict_carries_class_and_limit_even_when_fine():
    s = rt.Org(ROOT).contracts()[0]
    keys = {"bad", "label", "since", "limit_h", "cls", "warn"}
    ok = rt.silence_verdict(task(), NOW, s)
    assert set(ok) == keys and not ok["bad"] and (ok["cls"], ok["limit_h"]) == ("매일", 36)
    wk = rt.silence_verdict(task(period_s=7 * DAY, last_run="2026-09-26 13:00"), NOW, s)
    assert (wk["cls"], wk["limit_h"], wk["bad"]) == ("매주", 192, False)
    boot = rt.silence_verdict(task(period_s=None), NOW, s)
    assert set(boot) == keys and (boot["cls"], boot["limit_h"]) == ("", 0)
    nokey = rt.silence_verdict(task(), NOW, {})
    assert nokey["cls"] == "매일" and nokey["limit_h"] == 0 and nokey["warn"] and not nokey["bad"]


def _rows():
    """조용한 매일 1 · 첫 실행 없음 1 · 정상 매일 1 · 대기 1 · 실패 1 · 부팅 1."""
    return [task("naechaget-daily-report", last_run="2026-09-25 12:00"),
            task("naechaget-db-backup-pull", never_ran=True, ok=False, last_result="267011",
                 last_run="1999-11-30 00:00", first_start="2026-09-20 09:10", next_run="2026-09-28 09:10"),
            task("naechaget-org-standup", last_run="2026-09-27 08:45"),
            task("naechaget-monthly-report", never_ran=True, ok=False, last_result="267011",
                 last_run="1999-11-30 00:00", period_s=31 * DAY, registered="2026-09-22 20:47",
                 next_run="2026-10-01 13:30"),
            task("naechaget-ops-snapshot", ok=False, last_result="1", period_s=60),
            task("naechaget-home-tunnel", period_s=None, ok=False, last_result="3221225477", next_run="")]


def test_silence_rows_is_read_only_and_uses_task_seen_else_now(org):
    org.state_file.parent.mkdir(parents=True, exist_ok=True)
    org.state_file.write_text(json.dumps({"reports": {}, "task_seen": {"naechaget-db-backup-pull": "2026-09-20T09:00:00"}}),
                              encoding="utf-8")
    before = hashlib.md5(org.state_file.read_bytes()).hexdigest()
    v = org.silence_rows(_rows(), NOW)
    assert hashlib.md5(org.state_file.read_bytes()).hexdigest() == before and not org.bus.exists()
    assert v["naechaget-daily-report"]["label"].startswith("조용히 안 돎 · 마지막 성공 09-25 12:00")
    assert v["naechaget-db-backup-pull"]["label"].startswith("첫 실행 없음 · 등록 09-20 09:10")   # 첫 트리거 시작이 더 늦다
    assert not v["naechaget-monthly-report"]["bad"] and not v["naechaget-org-standup"]["bad"]
    # 처음 보는 작업은 '지금' — 첫 실행 없음을 당장 울리지 않는다(task_eval 과 같은 기준)
    org.state_file.write_text(json.dumps({"reports": {}}), encoding="utf-8")
    assert not org.silence_rows(_rows(), NOW)["naechaget-db-backup-pull"]["bad"]


def test_dashboard_and_runtime_give_the_same_verdict_on_the_same_rows(org, monkeypatch):
    """같은 행·같은 시각 → 순환계 스캔이 '조용히 안 돎/첫 실행 없음'으로 본 작업 = 대시보드 행의 silence.bad."""
    rows = _rows()
    monkeypatch.setattr(org, "schedule_states", lambda: ([dict(r) for r in rows], None))
    org.scan(now=NOW - timedelta(days=10))                                   # task_seen 을 남긴다(10일 전에 처음 봄)
    r = org.scan(now=NOW)
    runtime = {t["name"]: t["label"] for t in r["tasks"]
               if t["label"].startswith(("조용히 안 돎", "첫 실행 없음"))}
    monkeypatch.setattr(ad, "ROOT", org.root)
    sched = [dict(x) for x in rows]
    warns, err = ad.attach_silence(sched, NOW)
    assert err is None and warns == []
    board = {s["name"]: s["silence"]["label"] for s in sched if s["silence"]["bad"]}
    assert board == runtime and set(board) == {"naechaget-daily-report", "naechaget-db-backup-pull"}


def test_attach_silence_passes_the_runtime_result_through_untouched(org, monkeypatch):
    sentinel = {"bad": True, "label": "순환계가 정한 글자", "since": "x", "limit_h": 7, "cls": "매주", "warn": ""}
    monkeypatch.setattr(ad, "ROOT", org.root)
    monkeypatch.setattr(rt.Org, "silence_rows", lambda self, sched, now=None, settings=None:
                        {t["name"]: dict(sentinel) for t in sched})
    sched = [task()]
    ad.attach_silence(sched, NOW)
    assert sched[0]["silence"] == sentinel


def test_attach_silence_failure_is_unknown_not_fine(org, monkeypatch):
    monkeypatch.setattr(ad, "ROOT", org.root)

    def boom(self, *a, **kw):
        raise RuntimeError("계약을 못 읽음")
    monkeypatch.setattr(rt.Org, "silence_rows", boom)
    sched = [task(last_run="2026-09-01 00:00")]
    warns, err = ad.attach_silence(sched, NOW)
    assert sched[0]["silence"] is None and "판정하지 못했다" in err and warns == []
    k = ad.schedule_counts(sched)
    assert k["sched_silent"] is None                                        # 0(=이상 없음)이 아니다


def test_attach_silence_surfaces_judgement_warnings_once(org, monkeypatch):
    monkeypatch.setattr(ad, "ROOT", org.root)
    sched = [task("a", trigger_error="거부"), task("b", trigger_error="거부"), task("c")]
    warns, err = ad.attach_silence(sched, NOW)
    assert err is None and len(warns) == 2 and all("트리거를 읽지 못했다" in w for w in warns)
    assert sched[2]["silence"]["cls"] == "매일"


def test_schedule_counts_include_the_silence_verdict(org, monkeypatch):
    monkeypatch.setattr(ad, "ROOT", org.root)
    org.state_file.parent.mkdir(parents=True, exist_ok=True)
    org.state_file.write_text(json.dumps({"task_seen": {r["name"]: "2026-09-01T00:00:00" for r in _rows()}}),
                              encoding="utf-8")
    sched = _rows()
    ad.attach_verdict(sched)                                                # OPS-4 r3 — 꺼짐·다음 실행 없음 수(여기선 0)
    ad.attach_silence(sched, NOW)
    k = ad.schedule_counts(sched)
    assert k == {"sched_total": 6, "sched_never": 0, "sched_pending": 1, "sched_bad": 2,
                 "sched_silent": 2, "sched_stopped": 0, "sched_alarm": 4}
    # 첫 실행 없음으로 판정된 작업은 '대기'에서 빠진다 — 대기이면서 경보일 수 없다
    assert k["sched_pending"] == sum(1 for s in sched if s["never_ran"] and not s["silence"]["bad"])


def test_build_state_carries_silence_on_rows_and_in_kpi(org, monkeypatch):
    monkeypatch.setattr(ad, "ROOT", org.root)
    monkeypatch.setattr(ad, "SUPPLY", org.root / "없음.json")
    rows = _rows()
    for fn, val in (("read_schedule", ([dict(r) for r in rows], None)), ("read_git", ([], None)),
                    ("read_product", ({}, None)), ("read_delegation", ([], None))):
        monkeypatch.setattr(ad, fn, lambda *a, _v=val, **kw: _v)
    monkeypatch.setattr(ad, "read_artifacts", lambda: [])
    monkeypatch.setattr(ad, "scan_sessions", lambda rescan=False: (ad._empty_stats(), None))
    monkeypatch.setattr(ad, "read_agent_events", lambda: {"enabled": False, "running": [], "recent": [],
                                                          "durations": {}, "count": 0})
    org.state_file.parent.mkdir(parents=True, exist_ok=True)
    org.state_file.write_text(json.dumps({"task_seen": {r["name"]: "2026-09-01T00:00:00" for r in rows}}),
                              encoding="utf-8")
    s = ad.build_state()
    by = {x["name"]: x for x in s["schedule"]}
    assert all("silence" in x for x in s["schedule"])
    assert by["naechaget-daily-report"]["silence"]["bad"]
    assert by["naechaget-home-tunnel"]["silence"]["cls"] == ""
    assert s["kpi"]["sched_silent"] >= 1 and s["kpi"]["sched_alarm"] == (
        s["kpi"]["sched_never"] + s["kpi"]["sched_bad"] + s["kpi"]["sched_silent"])
    json.dumps(s, ensure_ascii=False)                                        # /api/state 로 나갈 수 있다


def test_the_rule_lives_only_in_org_runtime():
    """대시보드 소스에 §1 한도 이름·분류 표가 없다 — 판정을 다시 짜지 않았다."""
    src = (ROOT / "tools" / "agent_dashboard.py").read_text(encoding="utf-8")
    assert "성공 없음 한도" not in src and "SILENCE_CLASSES" not in src
    body = src[src.index("def attach_silence"):src.index("def schedule_counts")]
    assert "silence_rows(" in body and "timedelta" not in body


# ════════════════════════════════════════════════════════════════════════
# ⑤ Steward 결정 · 문서의 현재 상태 · 어휘
# ════════════════════════════════════════════════════════════════════════
def test_the_four_quiet_prone_tasks_have_no_ticket_to_hide_behind():
    """§3.1: 이 넷은 '조용히 안 돎' 규칙의 계기다. 다른 주제의 열린 티켓(AUD-08 헬스체크 · AUD-15 묶음)을 달면
    조용히 빠져도 지시서가 0장이다(ops4-qa §1.4). 다시 달려면 조용한 누락을 맡는 티켓이어야 한다."""
    routes = rt.Org(ROOT).alert_routes()
    for n in FOUR:
        r = routes[n]
        assert (r["source"], r["seat"], r["watch"], r["ticket"]) == ("예약 작업", "steward", True, ""), n
        assert STEWARD_MARK in r["note"], n


def test_the_four_tasks_now_raise_an_order_when_quiet(org, monkeypatch):
    """실제 §3.1 로 — 네 작업이 조용히 빠지면 지시서가 생긴다(전에는 ticket-open → 0장)."""
    rows = [task("naechaget-db-backup-pull", last_run="2026-09-20 09:10"),
            task("naechaget-weekly-report", period_s=7 * DAY, last_run="2026-09-12 13:00"),
            task("NaechaGet-PhotoClassify", period_s=7 * DAY, last_run="2026-09-13 08:17"),
            task("naechaget-monthly-report", period_s=31 * DAY, last_run="2026-08-01 13:30")]
    monkeypatch.setattr(org, "schedule_states", lambda: ([dict(r) for r in rows], None))
    r = org.scan(now=NOW)
    got = {t["name"]: t["action"] for t in r["tasks"] if t["name"] in FOUR}
    assert got == {n: "order" for n in FOUR}
    made = [o["meta"]["key"].split(":")[1] for o in org.orders().values() if o["meta"]["reason"] == "task"]
    assert sorted(n for n in made if n in FOUR) == sorted(FOUR)                  # 작업당 한 장


def test_documents_state_the_catch_up_as_applied():
    c = (ROOT / "docs" / "org-contracts.md").read_text(encoding="utf-8")
    src = (ROOT / "tools" / "org_runtime.py").read_text(encoding="utf-8")
    for old in ("따라잡기가 없어(AUD-15)", "노트북 조건에서 건너뛰고 따라잡지 않는다"):
        assert old not in c and old not in src, old
    s3 = c[c.index("## 3."):c.index("### 3.1")]
    assert "StartWhenAvailable=True" in s3 and "DisallowStartIfOnBatteries=False" in s3 and "2026-09-27 16:5x" in s3
    sv = src[src.index("def silence_verdict"):src.index("def workflow_of")]
    assert "StartWhenAvailable=True" in sv and "2026-09-27 16:5x" in sv


def test_scheduler_list_is_called_yeyak_not_jeonggi_in_contract_and_code():
    """§3.1 정의: '예약 작업' = 작업 스케줄러, '정기 작업' = 일일 리포트 `## 정기 작업` 표.
    대시보드의 스케줄러 목록을 '정기 작업 표'라고 부르던 곳(design #2)이 계약·코드에 남지 않는다."""
    c = (ROOT / "docs" / "org-contracts.md").read_text(encoding="utf-8")
    rt_src = (ROOT / "tools" / "org_runtime.py").read_text(encoding="utf-8")
    ad_src = (ROOT / "tools" / "agent_dashboard.py").read_text(encoding="utf-8")
    for text in (c, rt_src, ad_src):
        assert "대시보드 정기 작업 표" not in text
    assert "정기작업" not in ad_src and "| 정기 작업 | `schtasks" not in ad_src
    assert "사내 대시보드 예약 작업 표" in c
    # 스탠드업 '경보 → 티켓' 머리 문구는 조용히 안 돎도 포함한다
    assert "예약 작업 경보(고장·조용히 안 돎)" in rt_src
    # '정기 작업'은 일일 리포트 뜻으로는 그대로 쓴다(지우면 안 된다)
    assert '_section_lines(text, "정기 작업")' in rt_src
