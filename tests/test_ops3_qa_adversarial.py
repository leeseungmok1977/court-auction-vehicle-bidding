# -*- coding: utf-8 -*-
"""OPS-3 적대적 반증 — qa-engineer, 2026-09-27, 지시서 2026-09-27-60.

구현 테스트(`test_ops3_alert_orders.py`·`test_org_runtime.py`)가 **구현자가 떠올린 경우**를 지킨다면,
이 파일은 **구현자가 떠올리지 않은 경우**를 지킨다. 보고서: `reports/2026-09-27-ops3-qa.md`.

  ① 멱등 — 매시·자정·같은 날 재생성·dry-run 뒤 실제 실행 · **연속 구간이 조회 창(21일)보다 길 때**
  ② 오탐·조용한 0 — 전부 정상·중지(의도) 장기·열린 티켓 장기 · **형식이 조금 달라진 리포트** · **늦게 쓴 리포트**
  ③ 예약 작업 — 미등록·다음 실행 없음·마지막 실패를 구분하는가 · 이 PC 실측 스냅숏 · **성공 결과로 멈춘 작업**
  ④ 워크플로 인계 중복 방지가 정당한 인계를 막지 않는가 · 09-27 11:05 사고 모양
  ⑤ 일일·주간 표기 — 실제 계약표·실제 일일 리포트로
  ⑥ 문서와 코드가 같은 말을 하는가

★ `xfail(strict=True)` 는 **찾은 결함**이다. 고치면 XPASS 로 빨개지니 그때 표시를 지운다.
  (전례: test_feat1·feat2_qa_adversarial 의 strict xfail 3건.) 초록을 만들려고 기대값을 낮추지 않았다.
"""
from __future__ import annotations

import importlib.util
import re
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import org_runtime as rt  # noqa: E402

_spec = importlib.util.spec_from_file_location("daily_ops_report_ops3_qa", ROOT / "tools" / "daily_ops_report.py")
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

NOW = datetime(2026, 9, 27, 13, 5, 0)
SUPPLY = ["물건 수집", "시세 분석", "엔카 시세", "케이카 교차검증", "낙찰결과", "시세 0표본", "실행 기록"]
MARK = {"ok": "✅ 정상", "warn": "⚠️ 이상", "down": "🛑 멈춤", "unknown": "❔ 확인 불가"}
JOBS = {"매일 시세·낙찰 갱신": "✅ 성공", "SSL 인증서 갱신 확인": "✅ 성공",
        "주간 전문가 패널": "— 없음", "사진 미분류 점검": "— 없음", "집 회선 터널": "✅ 성공"}

BACKLOG = """# 백로그

| ID | 제목 | 담당 | 상태 | 완료 기준(DoD) |
|---|---|---|---|---|
| AUD-06 | 공급 신호 오탐 | backend | todo · 확인(qa) | x |
| KCAR-1 | 케이카 중단 | backend | **완료 — 배포 2026-09-27 11:26** | x |
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


def daily(org, day: str, supply: dict | None = None, jobs: dict | None = None, *, marks: dict | None = None,
          heading: str | None = "## 공급 상태", status_col: str = "상태", late: bool = False,
          newline: str = "\n") -> Path:
    """일일 리포트 한 편. 기본은 새 형식(5열 · 티켓 칸) · 전부 정상. `late` = 14:00 넘어 쓴 리포트(지난 기간)."""
    sup = {n: "ok" for n in SUPPLY}
    sup.update(supply or {})
    mk = marks or MARK
    L = [f"# 작업 결과 리포트 · {day}", "", "- **요약** x", ""]
    if late:
        L += ["## 공급 상태", "",
              "> ❔ **지난 기간** — 공급 판정은 지금 값이라 지난 날짜 리포트에는 적지 않는다.", ""]
    else:
        L += ([heading, ""] if heading else [])
        L += [f"| 신호 | {status_col} | 값 | 근거 | 티켓 |", "|---|---|---|---|---|"]
        for n, st in sup.items():
            head = "중지(의도)" if st == "paused" else "값"
            L.append(f"| {n} | {mk['ok' if st == 'paused' else st]} | {head} | 근거 | — |")
        L += [""]
    j = dict(JOBS)
    j.update(jobs or {})
    L += ["## 정기 작업", "", "| 작업 | 실행 위치 | 예정 | 실제 실행 | 건수 | 결과 |", "|---|---|---|---|---|---|"]
    L += [f"| {n} | 이 PC | x | x | — | {st} |" for n, st in j.items()]
    p = org.daily_dir / f"{day}.md"
    p.write_text(newline.join(L) + newline, encoding="utf-8", newline="")
    return p


def by_reason(org, reason):
    return [o for o in org.orders().values() if o["meta"]["reason"] == reason]


def at(d: date, hh: int = 13, mm: int = 5) -> datetime:
    return datetime.combine(d, datetime.min.time()) + timedelta(hours=hh, minutes=mm)


def report(org, name, meta: dict, body="본문"):
    p = org.root / "reports" / name
    p.write_text(rt.dump_front(meta, body), encoding="utf-8")
    return p


# ════════════════════════════════════════════════════════════════════════
# ① 멱등
# ════════════════════════════════════════════════════════════════════════
def test_hourly_scans_across_midnight_and_same_day_regeneration_make_one_order(org):
    """13:05 부터 25시간 매시 스캔 · 16:05 에 같은 날 리포트 재생성(내용 바뀜) · 다음 날 12:00 새 리포트."""
    daily(org, "2026-09-26", {"물건 수집": "down"})
    daily(org, "2026-09-27", {"물건 수집": "down"})
    for h in range(26):
        if h == 3:
            daily(org, "2026-09-27", {"물건 수집": "down", "시세 0표본": "warn"})     # 재생성 — mtime·내용 변경
        if h == 23:
            daily(org, "2026-09-28", {"물건 수집": "down"})
        org.scan(now=NOW + timedelta(hours=h))
    assert [o["meta"]["key"] for o in by_reason(org, "alert")] == ["alert:물건 수집:2026-09-26"]


def test_dry_run_first_does_not_consume_the_key_and_real_run_stays_single(org):
    daily(org, "2026-09-26", {"물건 수집": "down"})
    daily(org, "2026-09-27", {"물건 수집": "down"})
    org.dry_run = True
    org.scan(now=NOW)
    assert [m["reason"] for m in org.dry_orders_summary() if m["reason"] == "alert"] == ["alert"]
    org.dry_run = False
    org.scan(now=NOW + timedelta(minutes=1))
    org.scan(now=NOW + timedelta(minutes=2))
    assert len(by_reason(org, "alert")) == 1


def test_two_signals_alerting_together_make_one_order_each_with_distinct_ids(org):
    daily(org, "2026-09-26", {"물건 수집": "down", "시세 0표본": "warn"})
    daily(org, "2026-09-27", {"물건 수집": "down", "시세 0표본": "warn"})
    org.scan(now=NOW)
    org.scan(now=NOW + timedelta(hours=1))
    a = by_reason(org, "alert")
    assert sorted(o["meta"]["key"] for o in a) == ["alert:물건 수집:2026-09-26", "alert:시세 0표본:2026-09-26"]
    assert len({o["meta"]["id"] for o in a}) == 2


# 결함 QA-OPS3-1(고침 — backend r2): 구간 시작일을 조회 창(21일) 안에서만 찾아 30일 연속 🛑 에서 지시서 9건이었다.
# 이제 구간의 정체(시작일·지시서 id)를 상태 파일 `alert_runs` 에 고정한다. strict xfail 이 XPASS 로 빨개져 표식을 지웠다.
def test_streak_longer_than_lookback_window_does_not_reorder_after_close(org):
    d0 = date(2026, 9, 1)
    for i in range(30):
        d = d0 + timedelta(days=i)
        daily(org, d.isoformat(), {"물건 수집": "down"})
        org.scan(now=at(d))
        for o in by_reason(org, "alert"):
            if o["meta"]["status"] == "open":
                org.set_status(o, "done", note="의도된 상태 — 근거 기록")   # 계약 §3 의 '의도된 상태로 닫는다'
    assert [o["meta"]["key"] for o in by_reason(org, "alert")] == ["alert:물건 수집:2026-09-01"]


# 결함 QA-OPS3-1(같은 뿌리, 고침 — backend r2): 지난 리포트를 다시 만들면 첫 날짜가 밀려 두 번째 지시서가 생겼다.
def test_regenerating_a_past_report_does_not_mint_a_second_order_for_the_same_outage(org):
    daily(org, "2026-09-25", {"물건 수집": "down"})
    daily(org, "2026-09-26", {"물건 수집": "down"})
    org.scan(now=at(date(2026, 9, 26)))
    first = by_reason(org, "alert")
    assert len(first) == 1
    org.set_status(first[0], "done", note="의도된 상태")
    daily(org, "2026-09-27", {"물건 수집": "down"})
    daily(org, "2026-09-25", late=True)                  # 09-25 를 --date 로 다시 만든 모양(지난 기간)
    org.scan(now=NOW)
    assert len(by_reason(org, "alert")) == 1


def test_streak_within_lookback_window_stays_single_after_close(org):
    """대조군 — 21일 안에서는 닫아도 같은 구간 지시서를 다시 만들지 않는다(구현 주장 재현)."""
    d0 = date(2026, 9, 1)
    for i in range(20):
        d = d0 + timedelta(days=i)
        daily(org, d.isoformat(), {"물건 수집": "down"})
        org.scan(now=at(d))
        for o in by_reason(org, "alert"):
            if o["meta"]["status"] == "open":
                org.set_status(o, "done", note="의도된 상태")
    assert len(by_reason(org, "alert")) == 1


# ════════════════════════════════════════════════════════════════════════
# ② 오탐 0건 · 조용한 0 은 경고로
# ════════════════════════════════════════════════════════════════════════
def test_all_green_week_yields_no_alert_entries_and_no_orders(org):
    for i in range(7):
        daily(org, (date(2026, 9, 21) + timedelta(days=i)).isoformat())
    r = org.scan(now=NOW)
    assert r["alerts"] == [] and by_reason(org, "alert") == []


def test_paused_kcar_for_ten_days_with_closed_ticket_never_orders(org):
    for i in range(10):
        daily(org, (date(2026, 9, 18) + timedelta(days=i)).isoformat(), {"케이카 교차검증": "paused"})
    r = org.scan(now=NOW)
    assert r["alerts"] == [] and by_reason(org, "alert") == []


def test_open_ticket_holds_a_ten_day_streak(org):
    for i in range(10):
        daily(org, (date(2026, 9, 18) + timedelta(days=i)).isoformat(), {"시세 분석": "warn"})
    r = org.scan(now=NOW)
    assert by_reason(org, "alert") == []
    ev = next(x for x in r["alerts"] if x["name"] == "시세 분석")
    assert (ev["n"], ev["action"]) == (10, "ticket-open")


def test_parser_tolerates_crlf_and_warning_sign_without_variation_selector(org):
    """형식이 조금 달라도 읽히는 쪽 — CRLF · '⚠'(VS16 없음)."""
    for d in ("2026-09-26", "2026-09-27"):
        daily(org, d, {"물건 수집": "warn"}, marks=dict(MARK, warn="⚠ 이상"), newline="\r\n")
    org.scan(now=NOW)
    assert len(by_reason(org, "alert")) == 1


_DRIFT = {
    "이모지 없음": dict(marks={"ok": "정상", "warn": "이상", "down": "멈춤", "unknown": "확인 불가"}),
    "머리글 없이 표만": dict(heading=None),
    "머리글이 ###": dict(heading="### 공급 상태"),
    "상태 열 이름 바뀜": dict(status_col="판정"),
}


# 결함 QA-OPS3-2(고침 — backend r2): 형식이 조금 달라지면 경보 0건·경고 0건이었다. 이제 parse_daily_report 가
# 어긋난 곳을 `issues` 로 돌려주고 순환계가 파일명을 붙여 경고한다.
@pytest.mark.parametrize("variant", list(_DRIFT))
def test_format_drift_is_not_a_silent_zero(org, variant):
    for d in ("2026-09-26", "2026-09-27"):
        daily(org, d, {"물건 수집": "down"}, **_DRIFT[variant])
    r = org.scan(now=NOW)
    made = by_reason(org, "alert")
    warned = [w for w in r["warnings"] if "2026-09-2" in w and "테스트" not in w]
    assert made or warned, f"{variant}: 경보 0건 · 경고 0건 — 조용한 0"


# 결함 QA-OPS3-3(고침 — backend r2, 지시서의 방법 (a)): 늦은 리포트의 '모름'이 연속을 끊어 🛑 8일이 지시서 0건이었다.
# 이제 모름은 세지도 끊지도 않고(리포트 없는 날과 같다), 건너뛴 편수를 지시서·스탠드업에 적는다.
def test_late_reports_every_other_day_do_not_silently_hide_an_eight_day_outage(org):
    for i in range(8):
        d = date(2026, 9, 20) + timedelta(days=i)
        daily(org, d.isoformat(), {"물건 수집": "down"}, late=(i % 2 == 1))
    r = org.scan(now=at(date(2026, 9, 27), 18))
    warned = [w for w in r["warnings"] if "테스트" not in w]
    assert by_reason(org, "alert") or warned


def test_late_report_between_alerts_is_skipped_but_an_ok_report_breaks(org):
    """대조군 — 계약 §3 개정(backend r2, QA-OPS3-3 방법 (a)). 원래 이 대조군은 옛 문언('❔ 인 날은 연속을
    끊는다')을 고정했다: 🛑·❔·🛑 → (1, below). 문언이 바뀌어 기대값을 바꿨다. **끊는 것은 ✅ 정상뿐이다** —
    그 절반은 아래 두 번째 경우가 지킨다(모름을 건너뛰는 규칙이 ✅ 까지 건너뛰면 여기서 빨개진다)."""
    daily(org, "2026-09-25", {"물건 수집": "down"})
    daily(org, "2026-09-26", late=True)
    daily(org, "2026-09-27", {"물건 수집": "down"})
    r = org.scan(now=NOW)
    ev = next(x for x in r["alerts"] if x["name"] == "물건 수집")
    assert (ev["n"], ev["action"], ev["gaps"]) == (2, "order", ["2026-09-26"])
    assert "사이의 ❔ 모름 1편은 세지 않음" in by_reason(org, "alert")[0]["body"]
    daily(org, "2026-09-26")                                                 # ✅ 정상으로 다시 만든다
    org2 = rt.Org(org.root)
    org2.rhythm_states = lambda: []
    org2.schedule_states = lambda: ([], "테스트")
    ev2 = next(x for x in org2.alert_eval(NOW, *org2.contracts(), {}) if x["name"] == "물건 수집")
    assert (ev2["n"], ev2["action"], ev2["start"]) == (1, "below", "2026-09-27")


# ════════════════════════════════════════════════════════════════════════
# ③ 예약 작업
# ════════════════════════════════════════════════════════════════════════
def _task(name, **kw):
    t = {"name": name, "status": "Ready", "running": False, "last_run": "2026-09-27 12:00",
         "last_result": "0", "next_run": "2026-09-28 12:00", "enabled": True, "never_ran": False, "ok": True}
    t.update(kw)
    return t


def _all_registered(*extra):
    names = [n for n, r in rt.Org(ROOT).alert_routes().items() if r["source"] == "예약 작업"]
    ex = {e["name"] for e in extra}
    return [_task(n) for n in names if n not in ex] + list(extra)


# 2026-09-27 13:3x 이 PC 작업 스케줄러 실측(agent_dashboard.read_schedule, 읽기만). 보고서 §3 표와 같다.
REAL_0927 = [
    _task("NaechaGet-PhotoClassify", last_run="2026-09-27 08:17", next_run="2026-10-04 08:17"),
    _task("naechaget-daily-report", last_run="2026-09-27 12:00", next_run="2026-09-28 12:00"),
    _task("naechaget-db-backup-pull", last_run="1999-11-30 00:00", last_result="267011",
          next_run="2026-09-28 09:10", never_ran=True, ok=False),
    _task("naechaget-home-tunnel", last_run="2026-09-16 05:24", last_result="3221225477", next_run="", ok=False),
    _task("naechaget-monthly-report", last_run="1999-11-30 00:00", last_result="267011",
          next_run="2026-10-01 13:30", never_ran=True, ok=False),
    _task("naechaget-ops-snapshot", last_run="2026-09-27 13:31", next_run="2026-09-27 13:32"),
    _task("naechaget-org-heartbeat", last_run="2026-09-27 13:05", next_run="2026-09-27 14:05"),
    _task("naechaget-org-standup", last_run="2026-09-27 08:45", next_run="2026-09-28 08:45"),
    _task("naechaget-weekly-report", last_run="2026-09-26 13:00", next_run="2026-10-03 13:00"),
]


def _dashboard_class(s: dict) -> str:
    """tools/agent_dashboard.html 의 `d.schedule.map` 행 클래스 규칙을 그대로 옮긴 것(defaccc)."""
    return ("late" if s["next_run"] else "bad") if s["never_ran"] else ("" if s["ok"] else "bad")


def test_real_0927_scheduler_snapshot_matches_dashboard_classes_and_only_tunnel_is_bad():
    for t in REAL_0927:
        bad, _ = rt.schedule_verdict(t)
        assert bad == (_dashboard_class(t) == "bad"), t["name"]
    assert [t["name"] for t in REAL_0927 if rt.schedule_verdict(t)[0]] == ["naechaget-home-tunnel"]


def test_real_0927_snapshot_through_scan_makes_no_task_order_because_aud05_is_open(org, monkeypatch):
    bl = org.backlog_md
    bl.write_text(bl.read_text(encoding="utf-8") + "| AUD-05 | 터널 | Steward | todo · Steward 재현 확인 | x |\n",
                  encoding="utf-8")
    monkeypatch.setattr(org, "schedule_states", lambda: ([dict(t) for t in REAL_0927], None))
    r = org.scan(now=NOW)
    assert by_reason(org, "task") == []
    assert [(t["name"], t["action"]) for t in r["tasks"]] == [("naechaget-home-tunnel", "ticket-open")]
    assert r["tasks"][0]["hours"] >= 24 * 11


def test_task_labels_distinguish_missing_no_next_and_last_failure(org, monkeypatch):
    rows = [t for t in _all_registered(
        _task("naechaget-ops-snapshot", last_result="1", ok=False),                     # 마지막 실패 · 다음 있음
        _task("naechaget-org-standup", next_run=""),                                   # 성공 · 다음 실행 없음
        _task("naechaget-home-tunnel", last_run="2026-09-16 05:24", last_result="3221225477",
              next_run="", ok=False),                                                  # 실패 · 다음 없음
    ) if t["name"] != "naechaget-weekly-report"]                                       # 미등록
    monkeypatch.setattr(org, "schedule_states", lambda: ([dict(t) for t in rows], None))
    r = org.scan(now=NOW)
    lab = {t["name"]: t["label"] for t in r["tasks"]}
    assert lab["naechaget-weekly-report"] == "미등록"
    assert lab["naechaget-org-standup"] == "다음 실행 없음"
    assert lab["naechaget-ops-snapshot"] == "실패 · 결과 1(0x00000001)"
    assert lab["naechaget-home-tunnel"] == "실패 · 결과 3221225477(0xC0000005) · 다음 실행 없음"
    assert len(set(lab.values())) == 4


@pytest.mark.xfail(strict=True, reason=(
    "지시서 문언과 구현 해석의 차이 QA-OPS3-4(Steward 결정 필요): 지시서 ②의 셋째 조건 '24시간 넘게 성공이 "
    "없으면'을 구현은 '고장 상태가 24시간 지속'으로 읽었다(구현 보고 §2-1). 그래서 **결과 0 으로 멈춘 작업**"
    "(PC 가 꺼져 매일 작업이 이틀 안 돌았고 다음 실행은 잡혀 있음 — AUD-15 의 '건너뛰고 따라잡지 않는다')은 "
    "영원히 '정상'이다. 해석을 받아들이면 이 테스트를 지운다"))
def test_daily_task_that_silently_missed_two_runs_is_seen(org, monkeypatch):
    stale = _task("naechaget-db-backup-pull", last_run="2026-09-25 09:10", next_run="2026-09-28 09:10")
    monkeypatch.setattr(org, "schedule_states", lambda: ([dict(t) for t in _all_registered(stale)], None))
    org.scan(now=NOW)
    org.scan(now=NOW + timedelta(hours=25))
    assert [o for o in by_reason(org, "task") if "db-backup-pull" in o["body"]]


# ════════════════════════════════════════════════════════════════════════
# ④ 워크플로 인계 중복 방지 — 정당한 인계는 막지 않는다
# ════════════════════════════════════════════════════════════════════════
def _parallel(org, ticket="OPS-3"):
    """Steward 가 한 워크플로로 backend·qa 를 한꺼번에 발행한 모양(09-27 의 실제 모양)."""
    orders = org.orders()
    b = org.create_order(orders, to="backend-engineer", frm=rt.STEWARD, purpose="구현", reason="manual",
                         ticket=ticket, now=NOW)
    q = org.create_order(orders, to="qa-engineer", frm=rt.STEWARD, purpose="반증", reason="manual",
                         ticket=ticket, now=NOW)
    return b, q


def test_0927_incident_shape_skips_parallel_duplicate(org):
    b, q = _parallel(org)
    report(org, "be.md", {"order": b["meta"]["id"], "from": "backend-engineer", "ticket": "OPS-3",
                          "result": "done", "handoff": [{"to": "qa-engineer", "why": "반증"}]})
    org.scan(now=NOW)
    assert by_reason(org, "handoff") == []


@pytest.mark.parametrize("case", ["다른 티켓", "다른 자리", "Steward 아닌 발행자", "같은 자리 지시서가 막힘",
                                  "같은 자리 지시서가 이미 닫힘", "order 없는 보고서", "workflow 값이 비어 있음"])
def test_legit_handoffs_are_not_blocked(org, case):
    b, q = _parallel(org)
    meta = {"order": b["meta"]["id"], "from": "backend-engineer", "ticket": "OPS-3", "result": "done",
            "handoff": [{"to": "qa-engineer", "why": "반증"}]}
    if case == "다른 티켓":
        meta["ticket"] = "OPS-4"
    elif case == "다른 자리":
        meta["handoff"] = [{"to": "frontend-engineer", "why": "화면 반영"}]
    elif case == "Steward 아닌 발행자":
        orders = org.orders()
        p = org.create_order(orders, to="backend-engineer", frm="pm-orchestrator", purpose="재작업",
                             reason="manual", ticket="OPS-3", now=NOW)
        meta["order"] = p["meta"]["id"]
    elif case == "같은 자리 지시서가 막힘":
        org.set_status(org.orders()[q["meta"]["id"]], "blocked", note="x")
    elif case == "같은 자리 지시서가 이미 닫힘":
        org.set_status(org.orders()[q["meta"]["id"]], "done", note="x")
    elif case == "order 없는 보고서":
        meta.pop("order")
    elif case == "workflow 값이 비어 있음":
        meta["workflow"] = ""                                          # 빈 값은 '워크플로 밖'이다
        org.set_status(org.orders()[q["meta"]["id"]], "done", note="x")  # Steward 중복 규칙과 섞이지 않게
    report(org, "be.md", meta)
    org.scan(now=NOW)
    to = meta["handoff"][0]["to"]
    assert [o["meta"]["to"] for o in by_reason(org, "handoff")] == [to], case
    assert not [e for e in org.events() if e.get("kind") == "handoff.skipped"], case


def test_needs_owner_with_workflow_still_reaches_inbox_and_skip_is_logged_once(org):
    b, _ = _parallel(org)
    report(org, "be.md", {"order": b["meta"]["id"], "from": "backend-engineer", "ticket": "OPS-3",
                          "result": "needs-owner", "workflow": "ops3-run",
                          "handoff": [{"to": "qa-engineer", "why": "반증"}]})
    org.scan(now=NOW)
    org.scan(now=NOW + timedelta(hours=1))
    assert [o["meta"]["to"] for o in by_reason(org, "owner")] == [rt.STEWARD]
    assert len([e for e in org.events() if e.get("kind") == "handoff.skipped"]) == 1


# ════════════════════════════════════════════════════════════════════════
# ⑤ 표기 — 실제 계약표·실제 일일 리포트
# ════════════════════════════════════════════════════════════════════════
def _oracle_rows(text: str, heading: str, name_col: int, state_col: int) -> dict:
    """구현과 **다른 방법**으로 표를 읽는 대조 파서 — 절을 정규식으로 자르고, 칸은 `\\|` 를 지운 뒤 나눈다."""
    m = re.search(rf"^## {re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m:
        return {}
    out = {}
    for ln in m.group(1).splitlines():
        if not ln.startswith("| ") or ln.startswith("|---"):
            continue
        cells = [c.strip() for c in ln.replace("\\|", "¦").strip().strip("|").split("|")]
        if cells[0] in ("신호", "작업"):
            continue
        out[cells[name_col]] = cells[state_col]
    return out


def test_parser_agrees_with_an_independent_oracle_on_every_real_daily_report():
    files = sorted((ROOT / "docs" / "daily-reports").glob("2026-*.md"))
    assert len(files) >= 7
    checked = 0
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        p = rt.parse_daily_report(text)
        sup = _oracle_rows(text, "공급 상태", 0, 1)
        assert set(p["supply"]) == set(sup), f.name
        for n, cell in sup.items():
            want = "alert" if ("⚠" in cell or "🛑" in cell) else ("ok" if "✅" in cell else "unknown")
            assert p["supply"][n]["state"] == want, (f.name, n, cell)
            checked += 1
        for n, cell in _oracle_rows(text, "정기 작업", 0, 5).items():
            want = ("alert" if any(x in cell for x in ("❌", "⚠", "⏭")) else "ok" if "✅" in cell
                    else "na" if "— 없음" in cell else "unknown")
            assert p["jobs"][n]["state"] == want, (f.name, n, cell)
            checked += 1
    assert checked > 50


def test_daily_supply_block_with_real_contract_marks_every_alert_row():
    """실제 §3.1 + 실제 백로그로, 모든 신호가 경보일 때 — 경보 줄의 티켓 칸은 열린 티켓이거나 ❗ 둘 중 하나."""
    routes = rt.Org(ROOT).signal_tickets()
    sig = [{"key": f"k{i}", "label": n, "state": "warn", "head": "h", "detail": "d"} for i, n in enumerate(SUPPLY)]
    md = "\n".join(R.supply_block({"state": "warn", "headline": "h", "checked_at": "2026-09-27 12:00:00",
                                   "source": "운영 서버", "signals": sig, "alerts": sig}, True, routes))
    rows = [ln for ln in md.splitlines() if ln.startswith("| ") and not ln.startswith("| 신호")]
    assert len(rows) == len(SUPPLY)
    for ln in rows:
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", ln.strip().strip("|"))]
        assert len(cells) == 5, ln
        name, tcell = cells[0], cells[4]
        r = routes[name]
        if r["ticket"] and r["state"] == "열림":
            assert tcell == f"`{r['ticket']}`", ln
        else:
            assert "❗" in tcell, ln                                       # 경보인데 맡은 티켓이 없으면 크게
    first = md.split("**먼저 볼 것**")[1].split("| 신호 |")[0]
    assert sum(1 for ln in first.splitlines() if ln.startswith("- ")) == len(SUPPLY)


def test_weekly_w39_ops_section_matches_oracle_counts_from_real_reports():
    import weekly_report as W                                              # noqa: PLC0415
    since, until = date(2026, 9, 21), date(2026, 9, 27)
    ops = W.collect_ops(since, until, today=until)
    if len(ops.get("reports") or []) < 7:
        pytest.skip("W39 일일 리포트 7편이 이 작업 트리에 없다")
    st = W.ops_stats(ops)
    # 대조: 원문에서 직접 센다
    alert_days: dict[str, list] = {}
    for d, _ in ops["reports"]:
        text = (ROOT / "docs" / "daily-reports" / f"{d}.md").read_text(encoding="utf-8")
        for n, cell in _oracle_rows(text, "공급 상태", 0, 1).items():
            if "⚠" in cell or "🛑" in cell:
                alert_days.setdefault(n, []).append(d)
    for n, s in st["supply"].items():
        assert s["alert"] == alert_days.get(n, []), n
    md = "\n".join(W.ops_section(ops))
    for n, days in alert_days.items():
        row = next(ln for ln in md.splitlines() if ln.startswith(f"| {n} |"))
        assert f"**{len(days)}일**" in row, row
    q = W.panel_line(ops)[0]
    pj = st["jobs"].get(W.PANEL_JOB) or {}
    if pj.get("bad"):
        assert f"**실패 {len(pj['bad'])}회**" in q                         # 실패를 파일 수로 가리지 않는다(A-05)


# ════════════════════════════════════════════════════════════════════════
# ⑥ 문서 ↔ 코드
# ════════════════════════════════════════════════════════════════════════
def _sec(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i:text.index(end, i)]


def test_contract_section3_names_what_the_code_does():
    c = (ROOT / "docs" / "org-contracts.md").read_text(encoding="utf-8")
    s3 = _sec(c, "## 3.", "## 4.")
    assert "reason: alert" in s3 and "reason: task" in s3
    assert set(rt.NO_DISPATCH_REASONS) == {"alert", "task"} and "NO_DISPATCH_REASONS" in s3
    assert "alert:<신호>:<구간 첫 날짜>" in s3 and "task:<작업>:<고장 시작>" in s3
    assert "workflow:" in s3 and "handoff.skipped" in s3 and "result.skipped" in s3
    s4 = _sec(c, "## 4.", "### 실측")
    assert "NO_DISPATCH_REASONS" in s4
    # 계약 §1 설정 이름은 코드가 읽는 글자와 같아야 한다
    src = (ROOT / "tools" / "org_runtime.py").read_text(encoding="utf-8")
    for key in ("경보 연속 기준(리포트)", "예약 작업 실패 지속(시간)"):
        assert f"`{key}`" in c and f'"{key}"' in src


def test_handoff_protocol_workflow_rules_match_contract():
    hp = (ROOT / ".claude" / "agents" / "_handoff-protocol.md").read_text(encoding="utf-8")
    w = _sec(hp, "### 워크플로가 부른 단계면", "## 3.")
    assert "needs-owner" in w and "결재함" in w
    assert "`open`·`doing`" in w                                            # 코드: status in ("open", "doing")


def test_steward_sops_put_supply_first_and_drop_visitor_checks():
    dc = (ROOT / ".claude" / "commands" / "daily-check.md").read_text(encoding="utf-8")
    first = _sec(dc, "## 1.", "## 2.")
    assert first.index("공급 상태") < first.index("결재함") < first.index("정기 작업 표")
    assert "## 방문자" not in dc and "방문자 급감" not in dc and "이탈 급증" not in dc
    wr = (ROOT / ".claude" / "commands" / "weekly-report.md").read_text(encoding="utf-8")
    w1 = _sec(wr, "## 1.", "## 2.")
    assert w1.index("운영·공급") < w1.index("결재함") < w1.index("품질")
    assert "방문자 집계에서" not in wr
