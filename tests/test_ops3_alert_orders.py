# -*- coding: utf-8 -*-
"""OPS-3 — 경보가 티켓이 되는 장치(2026-09-27, 오너 승인).

케이카 교차검증 경보가 일일 리포트 맨 위에 **사흘** 떴는데 백로그 티켓은 0 이었다(KCAR-1).
경보는 '보이게'까지만 만들어졌고, 순환계는 보고서·리듬·백로그만 읽었다. 이 테스트가 지키는 것:

  ① 같은 신호가 연속 N편(§1, 지금 2) 이상·멈춤 → 결재함에 지시서 **한 건**. 사흘째도 한 건(멱등).
  ② 그 신호를 맡은 **열린 티켓**이 있으면 만들지 않는다. 티켓이 닫혔는데 경보가 계속되면 만든다.
  ③ '중지(의도)'(✅ 정상)와 하루짜리 경보는 지시서가 아니다. 경보 사이의 모르는 날(❔)은 세지도 끊지도 않는다
     — 끊는 것은 ✅ 정상뿐이다(r2, QA-OPS3-3).
  ④ 예약 작업이 실패·다음 실행 없음·미등록인 채 24시간 → 결재함. 대시보드와 같은 판정 규칙.
  ⑤ 일일 리포트는 경보 줄마다 티켓을 적고, 없으면 **❗ 티켓 없음**. 주간 보고는 운영 절에서 센다.
  ⑥ 경보·예약 작업 지시서는 당직이 부르지 않는다(코드·서버 권한이 필요하다).

계약표(`docs/org-contracts.md` §3.1)는 **실물을 그대로** 쓴다 — 표가 규약을 어기면 여기서 깨진다.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)
import org_runtime as rt  # noqa: E402
from web import ops_health as oh  # noqa: E402

_spec = importlib.util.spec_from_file_location("daily_ops_report_ops3", ROOT / "tools" / "daily_ops_report.py")
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

NOW = datetime(2026, 9, 27, 13, 5, 0)
SUPPLY = ["물건 수집", "시세 분석", "엔카 시세", "케이카 교차검증", "낙찰결과", "시세 0표본", "실행 기록"]
MARK = {"ok": "✅ 정상", "warn": "⚠️ 이상", "down": "🛑 멈춤", "unknown": "❔ 확인 불가"}

BACKLOG = """# 백로그

| ID | 제목 | 담당 | 상태 | 완료 기준(DoD) |
|---|---|---|---|---|
| AUD-06 | 공급 신호 오탐 | backend | todo · 확인(qa) | x |
| KCAR-1 | 케이카 중단 | backend | **완료 — 배포 2026-09-27 11:26** | x |
| AUD-10 | 사진 점검 | backend | todo | x |
| AUD-15 | 운영 위생 | 각 담당 | todo(낮음) | x |

| ID | 제목 | 분류 | 상태 | 비고 |
|---|---|---|---|---|
| PANEL-01 | 배포 대기 | x | **완료(배포 대기)** | x |
"""


# ── 픽스처 ────────────────────────────────────────────────────────────────
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


def daily(org, day: str, supply: dict | None = None, jobs: dict | None = None, *,
          no_supply: bool = False, ticket_col: bool = False) -> Path:
    """일일 리포트 형식(tools/daily_ops_report.build_markdown)을 따라 한 편 쓴다. 기본은 전부 정상."""
    sup = {n: "ok" for n in SUPPLY}
    sup.update(supply or {})
    L = [f"# 작업 결과 리포트 · {day}", "", "- **요약** x", ""]
    if no_supply:
        L += ["## 공급 상태", "", "> ❔ **확인 불가** — 운영 서버 스냅샷을 읽지 못했다. 정상이라는 뜻이 아니다.", ""]
    else:
        L += ["## 공급 상태", "", "> x", "",
              "| 신호 | 상태 | 값 | 근거 |" + (" 티켓 |" if ticket_col else ""),
              "|---|---|---|---|" + ("---|" if ticket_col else "")]
        for n, st in sup.items():
            head = "중지(의도)" if st == "paused" else "값"
            cell = MARK["ok" if st == "paused" else st]
            tk = (" **❗ 티켓 없음** |" if st in ("warn", "down") else " — |") if ticket_col else ""
            L.append(f"| {n} | {cell} | {head} | 근거 \\| 칸 안의 막대 |{tk}")
        L += ["", "> 임계는 `config.yaml: ops_alert`", ""]
    L += ["## 정기 작업", "", "| 작업 | 실행 위치 | 예정 | 실제 실행 | 건수 | 결과 |", "|---|---|---|---|---|---|"]
    j = {"매일 시세·낙찰 갱신": "✅ 성공", "SSL 인증서 갱신 확인": "✅ 성공",
         "주간 전문가 패널": "— 없음", "사진 미분류 점검": "— 없음", "집 회선 터널": "✅ 성공"}
    j.update(jobs or {})
    L += [f"| {n} | 이 PC | x | x | — | {st} |" for n, st in j.items()]
    L += ["", "## 매일 시세·낙찰 갱신 · 단계별", "", "| 단계 | 건수 | 결과 |", "|---|---|---|", "| x | 1 | ✅ 성공 |"]
    p = org.daily_dir / f"{day}.md"
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    return p


def by_reason(org, reason):
    return [o for o in org.orders().values() if o["meta"]["reason"] == reason]


def at(day: str, hh: int = 13) -> datetime:
    return datetime.fromisoformat(f"{day}T{hh:02d}:05:00")


# ── 계약표 §3.1 — 실물 ────────────────────────────────────────────────────
def test_contract_alert_table_covers_every_ops_health_signal_by_exact_name():
    """신호 이름이 한 글자라도 다르면 경보가 표를 못 찾아 '티켓 없음'으로 떨어진다 — 이름으로 고정한다."""
    routes = rt.Org(ROOT).alert_routes()
    labels = [s["label"] for s in oh.evaluate({}, now=NOW)["signals"]]
    assert labels == SUPPLY
    for lb in labels:
        assert lb in routes and routes[lb]["source"] == "공급", lb


def test_contract_alert_table_covers_every_daily_job_and_its_tickets_exist():
    routes = rt.Org(ROOT).alert_routes()
    md = R.build_markdown({"since": datetime(2026, 9, 26, 12), "until": datetime(2026, 9, 27, 12),
                           "generated": datetime(2026, 9, 27, 12, 0, 5), "server": {"error": "x"},
                           "tasks": {"error": "x"}, "panel": {"error": "x"}, "photo_log": {},
                           "tunnel_log": {}, "routes": {}})
    jobs = rt.parse_daily_report(md)["jobs"]
    assert len(jobs) == 5
    for name in jobs:
        assert name in routes and routes[name]["source"] == "정기 작업", name
    # 표에 적힌 티켓은 백로그에 실제로 있어야 한다 — 오타면 '백로그에 없음'으로 매일 지시서가 생긴다
    tickets = rt.Org(ROOT).backlog_tickets()
    for r in routes.values():
        if r["ticket"]:
            assert r["ticket"] in tickets, f"§3.1 `{r['name']}` 의 티켓 {r['ticket']} 가 백로그에 없다"


def test_contract_settings_for_alerts_are_numbers():
    settings, _ = rt.Org(ROOT).contracts()
    assert settings["경보 연속 기준(리포트)"] == 2
    assert settings["예약 작업 실패 지속(시간)"] == 24


def test_ticket_open_reads_status_cells():
    assert rt.ticket_is_open("todo · 확인(qa)")
    assert rt.ticket_is_open("**완료(배포 대기)**")           # 라이브에 아직 없다 — 경보가 계속되는 게 당연하다
    assert rt.ticket_is_open("고지만 완료 · 분모는 PANEL-09")
    assert not rt.ticket_is_open("**완료 — 배포 2026-09-27 11:26**")
    assert not rt.ticket_is_open("✅ 완료")
    assert not rt.ticket_is_open("판정: 통일하지 않음")


# ── ① 연속 2편 → 한 건, 멱등 ──────────────────────────────────────────────
def test_two_consecutive_alert_reports_make_one_order_for_steward(org):
    daily(org, "2026-09-26", {"물건 수집": "down"})
    daily(org, "2026-09-27", {"물건 수집": "down"})
    r = org.scan(now=NOW)
    a = by_reason(org, "alert")
    assert len(a) == 1
    m = a[0]["meta"]
    assert m["to"] == rt.STEWARD and m["key"] == "alert:물건 수집:2026-09-26"
    assert m["due"] == "2026-09-27"                                    # 당일
    assert m["inputs"][:2] == ["docs/daily-reports/2026-09-26.md", "docs/daily-reports/2026-09-27.md"]
    assert "2개 리포트 연속" in a[0]["body"] and "티켓 없음" in a[0]["body"]
    ev = next(x for x in r["alerts"] if x["name"] == "물건 수집")
    assert ev["action"] == "order" and ev["order"] == m["id"]


def test_third_day_rerun_adds_nothing_even_after_the_order_was_cancelled(org):
    daily(org, "2026-09-26", {"물건 수집": "down"})
    daily(org, "2026-09-27", {"물건 수집": "down"})
    org.scan(now=NOW)
    org.scan(now=NOW + timedelta(hours=1))
    daily(org, "2026-09-28", {"물건 수집": "down"})
    org.scan(now=at("2026-09-28"))
    assert len(by_reason(org, "alert")) == 1
    o = by_reason(org, "alert")[0]
    org.set_status(o, "cancelled", note="의도된 상태")
    daily(org, "2026-09-29", {"물건 수집": "down"})
    r = org.scan(now=at("2026-09-29"))
    assert len(by_reason(org, "alert")) == 1                           # 같은 연속 구간 — 닫혀도 다시 안 만든다
    assert next(x for x in r["alerts"] if x["name"] == "물건 수집")["action"] == "done-before"


def test_a_new_streak_after_recovery_makes_a_new_order_once_the_old_is_closed(org):
    for d, st in (("2026-09-23", "down"), ("2026-09-24", "down"), ("2026-09-25", "ok")):
        daily(org, d, {"물건 수집": st})
    org.scan(now=at("2026-09-24"))
    first = by_reason(org, "alert")
    assert len(first) == 1
    daily(org, "2026-09-26", {"물건 수집": "down"})
    daily(org, "2026-09-27", {"물건 수집": "down"})
    r = org.scan(now=NOW)
    assert len(by_reason(org, "alert")) == 1                           # 앞 지시서가 열려 있다 — 한 장만
    assert next(x for x in r["alerts"] if x["name"] == "물건 수집")["action"] == "open-order"
    org.set_status(first[0], "done", note="해결")
    org.scan(now=NOW + timedelta(minutes=5))
    keys = sorted(o["meta"]["key"] for o in by_reason(org, "alert"))
    assert keys == ["alert:물건 수집:2026-09-23", "alert:물건 수집:2026-09-26"]


# ── ② 티켓 ────────────────────────────────────────────────────────────────
def test_open_ticket_owns_the_alert_so_no_order(org):
    daily(org, "2026-09-26", {"시세 분석": "warn"})                     # §3.1 → AUD-06(todo)
    daily(org, "2026-09-27", {"시세 분석": "warn"})
    r = org.scan(now=NOW)
    assert by_reason(org, "alert") == []
    ev = next(x for x in r["alerts"] if x["name"] == "시세 분석")
    assert (ev["ticket"], ev["ticket_state"], ev["action"]) == ("AUD-06", "열림", "ticket-open")


def test_closed_ticket_with_continuing_alert_makes_an_order_on_that_ticket(org):
    daily(org, "2026-09-26", {"케이카 교차검증": "warn"})               # §3.1 → KCAR-1(완료)
    daily(org, "2026-09-27", {"케이카 교차검증": "warn"})
    org.scan(now=NOW)
    a = by_reason(org, "alert")
    assert len(a) == 1 and a[0]["meta"]["ticket"] == "KCAR-1"
    assert "닫혔는데 경보가 계속된다" in a[0]["body"]


def test_ticket_missing_from_backlog_is_not_treated_as_owned(org):
    # §3.1 주간 전문가 패널 → AUD-09. 이 백로그에는 없다. 주간 작업이라 '— 없음' 날은 세지도 끊지도 않는다.
    daily(org, "2026-09-19", jobs={"주간 전문가 패널": "❌ 실패"})
    for d in ("2026-09-20", "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25"):
        daily(org, d)
    daily(org, "2026-09-26", jobs={"주간 전문가 패널": "❌ 실패"})
    daily(org, "2026-09-27")
    r = org.scan(now=NOW)
    a = by_reason(org, "alert")
    assert len(a) == 1 and a[0]["meta"]["key"] == "alert:주간 전문가 패널:2026-09-19"
    assert "백로그에 없다" in a[0]["body"]
    ev = next(x for x in r["alerts"] if x["name"] == "주간 전문가 패널")
    assert ev["n"] == 2 and ev["source"] == "정기 작업"


# ── ③ 경보가 아닌 것 ──────────────────────────────────────────────────────
def test_paused_signal_is_not_an_alert(org):
    daily(org, "2026-09-26", {"케이카 교차검증": "paused"})             # ✅ 정상 · 중지(의도)
    daily(org, "2026-09-27", {"케이카 교차검증": "paused"})
    r = org.scan(now=NOW)
    assert by_reason(org, "alert") == [] and r["alerts"] == []


def test_single_alert_report_is_below_threshold(org):
    daily(org, "2026-09-26")
    daily(org, "2026-09-27", {"시세 0표본": "warn"})
    r = org.scan(now=NOW)
    assert by_reason(org, "alert") == []
    ev = next(x for x in r["alerts"] if x["name"] == "시세 0표본")
    assert (ev["n"], ev["action"]) == (1, "below")


def test_unknown_day_between_alerts_is_skipped_not_a_break(org):
    """r2(QA-OPS3-3): 전에는 모름이 연속을 끊었다(이 테스트의 옛 이름 test_unknown_day_breaks_the_streak).
    늦은 리포트·서버 못 읽은 날이 하루걸러 끼면 멈춤이 끝없이 지시서가 되지 않았다."""
    daily(org, "2026-09-25", {"물건 수집": "down"})
    daily(org, "2026-09-26", no_supply=True)                            # 서버를 못 읽은 날 = 모름
    daily(org, "2026-09-27", {"물건 수집": "down"})
    r = org.scan(now=NOW)
    a = by_reason(org, "alert")
    assert len(a) == 1 and a[0]["meta"]["key"] == "alert:물건 수집:2026-09-25"
    assert "사이의 ❔ 모름 1편은 세지 않음" in a[0]["body"]
    ev = next(x for x in r["alerts"] if x["name"] == "물건 수집")
    assert (ev["n"], ev["gaps"], ev["tail"]) == (2, ["2026-09-26"], [])


def test_ok_day_between_alerts_breaks_the_streak(org):
    daily(org, "2026-09-25", {"물건 수집": "down"})
    daily(org, "2026-09-26")                                            # ✅ 정상
    daily(org, "2026-09-27", {"물건 수집": "down"})
    r = org.scan(now=NOW)
    assert by_reason(org, "alert") == []
    ev = next(x for x in r["alerts"] if x["name"] == "물건 수집")
    assert (ev["n"], ev["start"], ev["action"]) == (1, "2026-09-27", "below")


def test_not_watched_signal_never_orders(org):
    # 매일 시세·낙찰 갱신 은 §3.1 받는 자리 '-' — 같은 원인을 '실행 기록'이 본다
    daily(org, "2026-09-26", jobs={"매일 시세·낙찰 갱신": "❌ 실패"})
    daily(org, "2026-09-27", jobs={"매일 시세·낙찰 갱신": "❌ 실패"})
    r = org.scan(now=NOW)
    assert by_reason(org, "alert") == []
    assert next(x for x in r["alerts"] if x["name"] == "매일 시세·낙찰 갱신")["action"] == "not-watched"


def test_real_reports_parse_pipes_inside_cells():
    """리포트는 칸 안의 `|` 를 `\\|` 로 적는다 — 칸 수가 어긋나 행을 버리면 그 신호는 '모름'이 된다."""
    p = rt.parse_daily_report("## 공급 상태\n\n| 신호 | 상태 | 값 | 근거 |\n|---|---|---|---|\n"
                              "| 실행 기록 | 🛑 멈춤 | error | a \\| b |\n")
    assert p["supply"]["실행 기록"]["state"] == "alert"


# ── ④ 예약 작업 ───────────────────────────────────────────────────────────
TUNNEL_DEAD = {"name": "naechaget-home-tunnel", "status": "Ready", "running": False,
               "last_run": "2026-09-16 05:24", "last_result": "3221225477", "next_run": "",
               "enabled": True, "never_ran": False, "ok": False}


def _sched(org, monkeypatch, rows, err=None):
    monkeypatch.setattr(org, "schedule_states", lambda: ([dict(r) for r in rows], err))


def _registered(extra=()):
    """§3.1 예약 작업 행 전부를 정상으로 — '미등록'이 섞이지 않게."""
    names = [n for n, r in rt.Org(ROOT).alert_routes().items() if r["source"] == "예약 작업"]
    rows = [{"name": n, "status": "Ready", "running": False, "last_run": "2026-09-27 12:00",
             "last_result": "0", "next_run": "2026-09-28 12:00", "enabled": True, "never_ran": False,
             "ok": True} for n in names]
    return [r for r in rows if r["name"] not in {e["name"] for e in extra}] + list(extra)


def test_dead_task_without_next_run_goes_to_inbox_when_ticket_not_open(org, monkeypatch):
    _sched(org, monkeypatch, _registered([TUNNEL_DEAD]))                # AUD-05 가 이 백로그에는 없다
    r = org.scan(now=NOW)
    t = by_reason(org, "task")
    assert len(t) == 1 and t[0]["meta"]["to"] == rt.STEWARD
    assert "0xC0000005" in t[0]["body"] and "다음 실행 없음" in t[0]["body"]
    ev = r["tasks"][0]
    assert ev["hours"] >= 24 * 11 and ev["since"].startswith("2026-09-16T05:24")
    org.scan(now=NOW + timedelta(hours=1))
    assert len(by_reason(org, "task")) == 1                            # 멱등


def test_dead_task_with_open_ticket_makes_no_order(org, monkeypatch):
    bl = org.backlog_md
    bl.write_text(bl.read_text(encoding="utf-8").replace(
        "| AUD-10 |", "| AUD-05 | 터널 | Steward | todo · 재현 | x |\n| AUD-10 |"), encoding="utf-8")
    _sched(org, monkeypatch, _registered([TUNNEL_DEAD]))
    r = org.scan(now=NOW)
    assert by_reason(org, "task") == []
    assert r["tasks"][0]["action"] == "ticket-open"


def test_hourly_failing_task_counts_from_first_sighting(org, monkeypatch):
    """매시 실패하는 작업은 마지막 실행이 늘 최근이다 — 처음 본 시각을 상태 파일에 남겨 24시간을 센다."""
    def row(t):
        return {"name": "naechaget-org-heartbeat", "status": "Ready", "running": False,
                "last_run": (t - timedelta(minutes=5)).isoformat(sep=" ", timespec="minutes"),
                "last_result": "1", "next_run": (t + timedelta(minutes=55)).isoformat(sep=" ", timespec="minutes"),
                "enabled": True, "never_ran": False, "ok": False}
    _sched(org, monkeypatch, _registered([row(NOW)]))
    r = org.scan(now=NOW)
    assert by_reason(org, "task") == [] and r["tasks"][0]["action"] == "below"
    later = NOW + timedelta(hours=25)
    _sched(org, monkeypatch, _registered([row(later)]))
    org.scan(now=later)
    t = by_reason(org, "task")
    assert len(t) == 1 and "실패 · 결과 1" in t[0]["body"]


def test_task_recovery_clears_the_first_sighting(org, monkeypatch):
    bad = dict(TUNNEL_DEAD, last_run="2026-09-27 12:00")
    _sched(org, monkeypatch, _registered([bad]))
    org.scan(now=NOW)
    assert "naechaget-home-tunnel" in org._state()["task_bad"]
    _sched(org, monkeypatch, _registered([dict(TUNNEL_DEAD, status="Running", running=True, ok=True)]))
    org.scan(now=NOW + timedelta(hours=1))
    assert "naechaget-home-tunnel" not in org._state()["task_bad"]


def test_first_run_pending_is_not_a_failure_and_unregistered_is(org, monkeypatch):
    monthly = {"name": "naechaget-monthly-report", "status": "Ready", "running": False,
               "last_run": "1999-11-30 00:00", "last_result": "267011", "next_run": "2026-10-01 13:30",
               "enabled": True, "never_ran": True, "ok": False}
    rows = [r for r in _registered([monthly]) if r["name"] != "naechaget-org-standup"]
    _sched(org, monkeypatch, rows)
    r = org.scan(now=NOW)
    names = {t["name"]: t for t in r["tasks"]}
    assert "naechaget-monthly-report" not in names                    # '아직 때가 안 됨'(대시보드와 같다)
    assert names["naechaget-org-standup"]["label"] == "미등록"
    assert names["naechaget-org-standup"]["action"] == "below"        # 처음 본 순간 — 24시간을 기다린다
    org.scan(now=NOW + timedelta(hours=25))
    t = by_reason(org, "task")
    assert len(t) == 1 and "미등록" in t[0]["body"]


def test_unreadable_schedule_is_a_warning_not_an_order(org, monkeypatch):
    _sched(org, monkeypatch, [], "예약 작업을 읽지 못했다(powershell 종료코드 1)")
    r = org.scan(now=NOW)
    assert by_reason(org, "task") == [] and r["tasks"] == []
    assert any("읽지 못했다" in w for w in r["warnings"])


def test_schedule_verdict_matches_dashboard_rules():
    v = rt.schedule_verdict
    assert v({"never_ran": True, "next_run": "2026-10-01 13:30"}) == (False, "아직 때가 안 됨")
    assert v({"never_ran": True, "next_run": ""})[0] is True
    assert v({"running": True, "ok": True, "last_result": "267009"}) == (False, "실행 중")
    assert v({"ok": True, "next_run": "2026-09-28 12:00"}) == (False, "정상")
    assert v(TUNNEL_DEAD) == (True, "실패 · 결과 3221225477(0xC0000005) · 다음 실행 없음")
    assert v({"ok": True, "next_run": "", "enabled": True})[1] == "다음 실행 없음"
    assert v({"ok": True, "next_run": "x", "enabled": False})[1] == "꺼짐(Disabled)"


# ── ⑥ 당직은 부르지 않는다 ────────────────────────────────────────────────
def test_alert_and_task_orders_are_never_dispatched(org, monkeypatch):
    orders = org.orders()
    a = org.create_order(orders, to="insight", frm="org-runtime", purpose="x", reason="alert", now=NOW)
    b = org.create_order(orders, to="insight", frm="org-runtime", purpose="y", reason="task", now=NOW)
    board = org.board(now=NOW)
    plan = org.dispatch_plan(board, limit=5)
    assert a["meta"]["id"] not in {o["id"] for o in plan} and b["meta"]["id"] not in {o["id"] for o in plan}
    monkeypatch.setattr(org, "_claude_cmd", lambda: ["claude"])
    r = org.dispatch(a["meta"]["id"])
    assert r["ok"] is False and "부르지 않는다" in r["why"]
    assert org.orders()[a["meta"]["id"]]["meta"]["status"] == "open"


def test_standup_shows_alert_to_ticket_section(org):
    daily(org, "2026-09-26", {"물건 수집": "down", "시세 분석": "warn"})
    daily(org, "2026-09-27", {"물건 수집": "down", "시세 분석": "warn"})
    text = org.standup(now=NOW).read_text(encoding="utf-8")
    sec = text.split("## 경보 → 티켓")[1].split("## ")[0]
    assert "`물건 수집`" in sec and "**❗ 티켓 없음**" in sec and "지시서 `" in sec
    assert "`시세 분석`" in sec and "티켓 `AUD-06`" in sec and "열린 티켓이 맡고 있다" in sec
    assert "## 결재함" in text                                          # 경보 지시서는 steward 결재함에 있다


# ── dry-run ───────────────────────────────────────────────────────────────
def test_dry_run_writes_nothing_but_reports_what_it_would_make(org, capsys):
    daily(org, "2026-09-26", {"물건 수집": "down"})
    daily(org, "2026-09-27", {"물건 수집": "down"})
    org.dry_run = True
    r = org.scan(now=NOW)
    assert not org.orders_dir.exists() or not list(org.orders_dir.glob("*.md"))
    assert not org.bus.exists() and not org.state_file.exists()
    made = org.dry_orders_summary()
    assert [m["reason"] for m in made if m["reason"] == "alert"] == ["alert"]
    assert next(x for x in r["alerts"] if x["name"] == "물건 수집")["action"] == "order"


def test_cli_scan_dry_run_prints_would_create(org, capsys, monkeypatch):
    daily(org, "2026-09-26", {"물건 수집": "down"})
    daily(org, "2026-09-27", {"물건 수집": "down"})
    monkeypatch.setattr(rt.Org, "rhythm_states", lambda self: [])
    monkeypatch.setattr(rt.Org, "schedule_states", lambda self: ([], "테스트"))
    assert rt.main(["--root", str(org.root), "scan", "--dry-run"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] is True and any(m["reason"] == "alert" for m in out["would_create"])
    assert not list((org.root / "orders").glob("*.md")) if (org.root / "orders").exists() else True


# ── ⑤ 일일 리포트 티켓 칸 ─────────────────────────────────────────────────
def _verdict(**states):
    sig = []
    for key, label in (("collect", "물건 수집"), ("analyze", "시세 분석"), ("kcar", "케이카 교차검증"),
                       ("zero_sample", "시세 0표본")):
        st = states.get(key, "ok")
        sig.append({"key": key, "label": label, "state": st, "head": "537/1,492 (36%)" if key == "zero_sample"
                    else "값", "detail": "근거"})
    alerts = [s for s in sig if s["state"] in ("warn", "down")]
    return {"state": "warn" if alerts else "ok", "headline": "h", "checked_at": "2026-09-27 12:00:00",
            "source": "운영 서버", "signals": sig, "alerts": alerts}


ROUTES = {"물건 수집": {"ticket": "", "state": ""}, "시세 분석": {"ticket": "AUD-06", "state": "열림"},
          "케이카 교차검증": {"ticket": "KCAR-1", "state": "닫힘"}, "시세 0표본": {"ticket": "", "state": ""}}


def test_daily_alert_lines_carry_ticket_or_a_loud_no_ticket():
    md = "\n".join(R.supply_block(_verdict(collect="down", analyze="warn", kcar="warn", zero_sample="warn"),
                                  True, ROUTES, {"zero_sample": "537건 시세 없음"}))
    first = md.split("**먼저 볼 것**")[1].split("| 신호 |")[0]
    line = {ln.split("**")[1]: ln for ln in first.splitlines() if ln.startswith("- ")}
    assert line["물건 수집"].endswith("티켓 **❗ 티켓 없음**")
    assert line["시세 분석"].endswith("티켓 `AUD-06`") and "❗" not in line["시세 분석"]
    assert "`KCAR-1`(닫힘) · **❗ 열린 티켓 없음**" in line["케이카 교차검증"]
    assert "피해: **537건 시세 없음**" in line["시세 0표본"]
    assert "| 신호 | 상태 | 값 | 근거 | 티켓 |" in md
    row = next(ln for ln in md.splitlines() if ln.startswith("| 물건 수집 |"))
    assert row.endswith("| **❗ 티켓 없음** |")


def test_daily_ok_rows_do_not_shout_and_unreadable_table_is_not_green():
    md = "\n".join(R.supply_block(_verdict(), True, ROUTES))
    assert "❗" not in md
    assert next(ln for ln in md.splitlines() if ln.startswith("| 시세 분석 |")).endswith("| `AUD-06` |")
    md2 = "\n".join(R.supply_block(_verdict(collect="down"), True, None))
    assert "❔ 표를 읽지 못함" in md2


def test_daily_damage_only_from_values_we_already_have():
    data = {"server": {"supply": {"zero_sample": {"zero": 537, "total": 1492}}}}
    assert R.alert_damage({"key": "zero_sample"}, data) == "537건 시세 없음"
    for k in ("collect", "analyze", "results", "encar", "kcar", "runs"):
        assert R.alert_damage({"key": k}, data) == ""                 # 모르는 수를 지어내지 않는다


def _report_data(**over):
    since, until = R.report_window(date(2026, 9, 26))
    d = {"since": since, "until": until, "generated": datetime(2026, 9, 26, 12, 0, 5),
         "server": {"runs": [], "settings": {"daily_time": "06:30", "daily_enabled": "1",
                                              "encar_health_state": "ok", "encar_health_ok_at": "2026-09-26 06:31:00"},
                    "certbot": {"started": 2, "finished": 2, "failed": 0}, "service": {"active": "active"}},
         "tasks": {R.PHOTO_TASK: {"state": "Ready", "last": "", "next": "", "result": 0},
                   R.TUNNEL_TASK: {"state": "Running", "last": "", "next": "", "result": 267009}},
         "panel": {"commits": []}, "photo_log": {}, "tunnel_log": {},
         "supply": _verdict(collect="down"),
         "routes": {"물건 수집": {"ticket": "", "state": ""}, "주간 전문가 패널": {"ticket": "AUD-09", "state": "열림"}}}
    d.update(over)
    return d


def test_daily_failed_job_rows_get_a_ticket_line_without_changing_the_table():
    md = R.build_markdown(_report_data())
    # 표 형식은 그대로다(다른 테스트·도구가 이 행 형식을 읽는다)
    assert "| 주간 전문가 패널 | 클라우드 루틴 | 매주 토 09:20 | 리포트 커밋 없음 | — | ❌ 실패 |" in md
    tl = next(ln for ln in md.splitlines() if ln.startswith("- 실패·경고 줄 티켓:"))
    assert "**주간 전문가 패널** `AUD-09`" in tl
    assert "**매일 시세·낙찰 갱신** **❗ 티켓 없음**" in tl             # 실행 기록 없음 → 실패, 표에 티켓 없음


def test_daily_report_round_trips_into_the_alert_parser():
    """리포트가 쓴 것을 순환계가 그대로 읽는가 — 쓰는 쪽과 읽는 쪽이 갈라지면 경보가 조용히 사라진다."""
    p = rt.parse_daily_report(R.build_markdown(_report_data()))
    assert p["ticket_column"] is True
    assert p["supply"]["물건 수집"]["state"] == "alert" and "티켓 없음" in p["supply"]["물건 수집"]["ticket"]
    assert p["supply"]["시세 분석"]["state"] == "ok"
    assert p["jobs"]["주간 전문가 패널"]["state"] == "alert"
    assert p["jobs"]["사진 미분류 점검"]["state"] == "na"


# ── ⑤ 주간 보고 운영 절 ───────────────────────────────────────────────────
def _weekly():
    import weekly_report as W                                        # noqa: PLC0415
    return W


def test_weekly_import_does_not_replace_stdout():
    before = sys.stdout
    _weekly()
    assert sys.stdout is before                                        # 전에는 import 만으로 콘솔을 갈아치웠다


def test_weekly_ops_section_counts_alert_days_ticketless_days_and_job_failures(org):
    W = _weekly()
    reps = []
    reps.append(("2026-09-21", rt.parse_daily_report(daily(org, "2026-09-21", no_supply=True).read_text(encoding="utf-8"))))
    for d in ("2026-09-24", "2026-09-25"):                          # 티켓 칸이 생기기 전 리포트
        reps.append((d, rt.parse_daily_report(daily(org, d, {"케이카 교차검증": "warn"}).read_text(encoding="utf-8"))))
    reps.append(("2026-09-26", rt.parse_daily_report(daily(
        org, "2026-09-26", {"케이카 교차검증": "warn"}, {"주간 전문가 패널": "❌ 실패"},
        ticket_col=True).read_text(encoding="utf-8"))))
    reps.append(("2026-09-27", rt.parse_daily_report(daily(
        org, "2026-09-27", {"시세 분석": "warn"}, ticket_col=True).read_text(encoding="utf-8"))))
    ops = {"reports": reps, "missing": ["2026-09-22", "2026-09-23"],
           "tickets": {"케이카 교차검증": {"ticket": "KCAR-1", "state": "닫힘", "status": "완료 — 배포"},
                       "주간 전문가 패널": {"ticket": "AUD-09", "state": "열림", "status": "todo"}}}
    st = W.ops_stats(ops)
    k = st["supply"]["케이카 교차검증"]
    assert (len(k["alert"]), len(k["no_ticket"]), len(k["unmarked"]), len(k["unknown"])) == (3, 1, 2, 1)
    assert st["jobs"]["주간 전문가 패널"] == {"due": ["2026-09-26"], "ok": [], "bad": ["2026-09-26"], "unknown": []}
    md = "\n".join(W.ops_section(ops))
    row = next(ln for ln in md.splitlines() if ln.startswith("| 케이카 교차검증 |"))
    assert "**3일** (09-24·09-25·09-26)" in row and "`KCAR-1`" in row and "닫힘" in row
    assert "**1일** · 칸 생기기 전 2일" in row
    assert "리포트 없는 날 09-22·09-23" in md
    prow = next(ln for ln in md.splitlines() if ln.startswith("| 주간 전문가 패널 |"))
    assert "**1회** (09-26)" in prow and "`AUD-09`" in prow
    # 품질 절은 실패를 파일 수로 가리지 않는다(A-05)
    full = W.build_markdown(date(2026, 9, 21), date(2026, 9, 27), {"error": "x"}, {"commits": []},
                            {"files": ["2026-09-22.md", "2026-09-23.md"]}, ops)
    q = full.split("## 품질 — 전문가 패널")[1].split("## ")[0]
    assert "**실패 1회**(09-26)" in q
    assert q.index("정기 실행") < q.index("2026-09-22.md")
    assert "패널 리포트 2건" not in full
    assert full.index("## 운영·공급") < full.index("## 성장")


def test_weekly_ops_section_without_reports_is_unknown_not_quiet():
    W = _weekly()
    md = "\n".join(W.ops_section({"reports": [], "missing": [], "tickets": {}}))
    assert "확인 불가" in md and "이상이 없었다는 뜻이 아니다" in md
    assert "확인 불가" in "\n".join(W.ops_section({"error": "경보 표를 읽지 못함"}))
