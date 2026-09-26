# -*- coding: utf-8 -*-
"""조직 순환계(tools/org_runtime.py) — 인계·상한·리듬·정체·디스패치 가드.

실제 docs/org-contracts.md 를 그대로 쓴다. 계약 표를 고쳤는데 이 테스트가 깨지면
**표가 규약을 어겼거나 테스트가 낡은 것**이다 — 어느 쪽인지 보고 고친다.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import org_runtime as rt  # noqa: E402

NOW = datetime(2026, 9, 26, 9, 0, 0)


@pytest.fixture()
def org(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    (tmp_path / "reports").mkdir()
    shutil.copy(ROOT / "docs" / "org-contracts.md", tmp_path / "docs" / "org-contracts.md")
    (tmp_path / "docs" / "backlog.md").write_text(
        "# 백로그\n\n| ID | 제목 | 담당 | 상태 | 완료 기준(DoD) |\n|---|---|---|---|---|\n"
        "| T-1 | 첫 티켓 | backend | todo | x |\n"
        "| T-2 | 끝난 티켓 | frontend | ✅ 완료 | x |\n\n"
        "| ID | 제목 | 분류 | 상태 | 비고 |\n|---|---|---|---|---|\n"
        "| P-1 | 분류 표는 배분 대상 아님 | 유료 훅 | todo | x |\n", encoding="utf-8")
    o = rt.Org(tmp_path)
    monkeypatch.setattr(o, "rhythm_states", lambda: [])
    return o


def report(org, name, meta: dict, body="본문"):
    p = org.root / "reports" / name
    p.write_text(rt.dump_front(meta, body), encoding="utf-8")
    return p


def by_reason(org, reason):
    return [o for o in org.orders().values() if o["meta"]["reason"] == reason]


def test_contract_table_parses_all_seats():
    settings, seats = rt.Org(ROOT).contracts()
    assert settings["자동 디스패치"] in ("켜짐", "꺼짐")
    assert isinstance(settings["하루 디스패치 상한"], int)
    # ORG.md §1 부서표의 전원이 계약을 가져야 한다 — 계약 없는 자리는 일을 받을 길이 없다
    import agent_dashboard as ad
    depts, err = ad.read_departments()
    assert err is None
    members = {m for d in depts for m in d["members"]}
    assert members - set(seats) == set(), f"계약 없는 자리: {members - set(seats)}"
    assert set(seats) - members == set(), f"부서표에 없는 계약: {set(seats) - members}"
    for s in seats.values():
        assert all(r in seats for r in s["routes"]), f"{s['name']} 의 경로가 없는 자리를 가리킨다"


def test_code_editing_seats_are_never_auto():
    """코드를 고치는 자리는 오너가 있는 세션에서만 — 헤드리스 당직에 맡기지 않는다."""
    _, seats = rt.Org(ROOT).contracts()
    for n in ("backend-engineer", "frontend-engineer", "monetization-engineer"):
        assert seats[n]["auto"] is False


def test_unassigned_backlog_goes_to_pm_once_per_day(org):
    org.scan(now=NOW)
    u = by_reason(org, "unassigned")
    assert len(u) == 1 and u[0]["meta"]["to"] == "pm-orchestrator"
    assert "T-1" in u[0]["body"] and "T-2" not in u[0]["body"] and "P-1" not in u[0]["body"]
    org.scan(now=NOW + timedelta(hours=1))
    assert len(by_reason(org, "unassigned")) == 1          # 같은 날 두 번 만들지 않는다


def test_handoff_creates_next_order_and_closes_parent(org):
    org.scan(now=NOW)
    qa = next(o for o in org.orders().values() if o["meta"]["to"] == "qa-engineer")
    report(org, "2026-09-26-qa.md", {
        "order": qa["meta"]["id"], "from": "qa-engineer", "ticket": "FEAT-1", "result": "fail",
        "verified": "재현", "handoff": [{"to": "backend-engineer", "why": "반증 2건"}]})
    r = org.scan(now=NOW)
    orders = org.orders()
    assert orders[qa["meta"]["id"]]["meta"]["status"] == "done"
    assert orders[qa["meta"]["id"]]["meta"]["result"] == "fail"
    nxt = [o for o in orders.values() if o["meta"]["reason"] == "handoff"]
    assert len(nxt) == 1
    m = nxt[0]["meta"]
    assert (m["to"], m["from"], m["ticket"], m["round"]) == ("backend-engineer", "qa-engineer", "FEAT-1", 1)
    assert m["inputs"] == ["reports/2026-09-26-qa.md"]
    assert qa["meta"]["id"] in r["closed"]
    # 같은 보고서를 다시 읽어도(수정 없이) 인계가 두 번 생기지 않는다
    org.scan(now=NOW)
    assert len(by_reason(org, "handoff")) == 1


def test_route_outside_contract_goes_to_steward_not_agent(org):
    report(org, "x.md", {"from": "design-critic", "result": "done",
                         "handoff": [{"to": "backend-engineer", "why": "DB 고쳐라"}]})
    org.scan(now=NOW)
    assert not [o for o in org.orders().values() if o["meta"]["to"] == "backend-engineer"]
    r = by_reason(org, "route")
    assert len(r) == 1 and r[0]["meta"]["to"] == rt.STEWARD


def test_round_cap_escalates_instead_of_pingpong(org):
    # design-critic 왕복 상한 3 — 네 번째 인계는 결재함으로 간다
    for i in range(4):
        report(org, f"fe-{i}.md", {"from": "frontend-engineer", "ticket": "PANEL-9", "result": "done",
                                   "handoff": [{"to": "design-critic", "why": f"{i + 1}차 검수"}]})
        org.scan(now=NOW)
    to_critic = [o for o in org.orders().values() if o["meta"]["to"] == "design-critic"]
    assert [o["meta"]["round"] for o in sorted(to_critic, key=lambda o: o["meta"]["id"])] == [1, 2, 3]
    cap = by_reason(org, "cap")
    assert len(cap) == 1 and cap[0]["meta"]["to"] == rt.STEWARD and "PANEL-9" in cap[0]["body"]


def test_fail_without_handoff_goes_to_pm_and_needs_owner_to_inbox(org):
    report(org, "a.md", {"from": "insight", "result": "blocked", "handoff": []})
    report(org, "b.md", {"from": "compliance-officer", "result": "needs-owner", "handoff": []})
    org.scan(now=NOW)
    assert [o["meta"]["to"] for o in by_reason(org, "result")] == ["pm-orchestrator"]
    assert [o["meta"]["to"] for o in by_reason(org, "owner")] == [rt.STEWARD]


def test_unknown_result_is_not_read_as_done(org):
    org.scan(now=NOW)
    qa = next(o for o in org.orders().values() if o["meta"]["to"] == "qa-engineer")
    report(org, "q.md", {"order": qa["meta"]["id"], "from": "qa-engineer", "result": "끝남"})
    org.scan(now=NOW)
    assert org.orders()[qa["meta"]["id"]]["meta"]["status"] == "blocked"
    assert any("규약에 없다" in w for w in org.warnings)


def test_legacy_reports_without_front_matter_are_skipped_silently(org):
    (org.root / "reports" / "old.md").write_text("# 옛 보고서\n다음은 growth 로 넘긴다", encoding="utf-8")
    r = org.scan(now=NOW)
    assert r["legacy_reports"] == 1
    assert not by_reason(org, "handoff")


def test_rhythm_break_targets_auto_owner_or_inbox(org, monkeypatch):
    monkeypatch.setattr(org, "rhythm_states", lambda: [
        {"glob": "docs/reviews/*.md", "state": "끊김", "owner": "전문가 4인", "period": 7,
         "last": "2026-09-12", "age": 14, "impact": "점수 칸이 빈다"},
        {"glob": "docs/x/*.md", "state": "늦음", "owner": "`insight`", "period": 7,
         "last": "2026-09-17", "age": 9, "impact": "-"},
        {"glob": "docs/ok/*.md", "state": "정상", "owner": "`insight`", "period": 7}])
    org.scan(now=NOW)
    rh = {o["meta"]["key"]: o["meta"]["to"] for o in by_reason(org, "rhythm")}
    assert rh == {"rhythm:docs/reviews/*.md": rt.STEWARD, "rhythm:docs/x/*.md": "insight"}
    org.scan(now=NOW + timedelta(hours=1))
    assert len(by_reason(org, "rhythm")) == 2               # 열려 있는 동안 다시 만들지 않는다


def test_stale_orders_are_collected_for_pm(org):
    org.scan(now=NOW)
    later = NOW + timedelta(days=5)
    org.scan(now=later)
    st = by_reason(org, "stale")
    assert len(st) == 1 and st[0]["meta"]["to"] == "pm-orchestrator"


def test_dispatch_refuses_non_auto_and_blocks_when_no_report(org, monkeypatch):
    orders = org.orders()
    be = org.create_order(orders, to="backend-engineer", frm="steward", purpose="x", reason="manual", now=NOW)
    assert org.dispatch(be["meta"]["id"])["ok"] is False
    ins = org.create_order(orders, to="insight", frm="steward", purpose="x", reason="manual", now=NOW)

    class P:                                               # claude 가 0 으로 끝났지만 보고서는 안 썼다
        returncode, stdout, stderr = 0, b"{}", b""
    monkeypatch.setattr(org, "_claude_cmd", lambda: ["claude"])
    monkeypatch.setattr(rt.subprocess, "run", lambda *a, **k: P())
    r = org.dispatch(ins["meta"]["id"])
    m = org.orders()[ins["meta"]["id"]]["meta"]
    assert m["status"] == "blocked" and "보고서 없음" in m["note"]      # 종료코드 0 을 완료로 읽지 않는다
    assert r["exit"] == 0


def test_dispatch_guardrails_block_irreversible_tools():
    allowed = ",".join(rt.DISPATCH_ALLOWED)
    for bad in ("git commit", "git push", "ssh", "Edit(src", "Edit(web", "Bash(*"):
        assert bad not in allowed
    denied = ",".join(rt.DISPATCH_DENIED)
    for must in ("git commit", "git push", "ssh", "Edit(src/**)", "Edit(.claude/**)"):
        assert must in denied


def test_standup_respects_switch_and_daily_cap(org, monkeypatch):
    calls = []
    monkeypatch.setattr(org, "dispatch", lambda oid, dry_run=False: calls.append(oid) or {"ok": True})
    p = org.standup(dispatch=5, now=NOW)
    text = p.read_text(encoding="utf-8")
    assert "## 자리별 대기열" in text and "pm-orchestrator" in text
    assert 1 <= len(calls) <= 3                           # 하루 상한 3
    first = org.orders()[calls[0]]["meta"]["to"]
    assert first == "pm-orchestrator"                     # 배분이 먼저다
    assert len({org.orders()[c]["meta"]["to"] for c in calls}) == len(calls)   # 자리당 한 건

    md = org.contracts_md
    md.write_text(md.read_text(encoding="utf-8").replace("| `켜짐` |", "| `꺼짐` |"), encoding="utf-8")
    calls.clear()
    t2 = org.standup(dispatch=5, now=NOW + timedelta(days=1)).read_text(encoding="utf-8")
    assert calls == [] and "`꺼짐`" in t2


def test_board_counts_and_feed(org):
    org.scan(now=NOW)
    b = org.board(now=NOW)
    assert b["enabled"] and b["totals"]["open"] >= 3
    assert b["queue"]["pm-orchestrator"]["open"] == 1
    assert any(e["kind"] == "order.created" for e in b["feed"])
    json.dumps(b, ensure_ascii=False)                     # 대시보드가 그대로 직렬화한다


def test_close_done_requires_report(org, capsys):
    org.scan(now=NOW)
    oid = next(iter(org.orders()))
    assert rt.main(["--root", str(org.root), "close", oid, "--status", "done", "--note", "x"]) == 2
    assert rt.main(["--root", str(org.root), "close", oid, "--status", "cancelled", "--note", "중복"]) == 0


def test_dashboard_flow_counts_calls_via_orders():
    """대시보드 '지시서 경유 호출' — 라벨이 지시서 번호로 시작한 호출만 경유로 센다."""
    import agent_dashboard as ad
    # 날짜를 박지 않는다 — 7일 창이 지나면 테스트가 스스로 낡는다(CLAUDE.md 운영 규칙 8 과 같은 병)
    now = datetime.now().replace(microsecond=0)
    calls = [{"ts": now.isoformat(), "agent": "insight", "desc": "2026-09-26-04 주간 수치 검증"},
             {"ts": now.isoformat(), "agent": "frontend-engineer", "desc": "FEAT-1 디자인 지적 반영"},
             {"ts": "2026-09-20T10:00:00", "agent": "qa-engineer", "desc": "규칙 시행 전 호출"}]
    b, err = ad.read_flow(calls)
    assert err is None and b["enabled"]
    v = b["via_orders"]
    assert (v["total"], v["via"]) == (2, 1)                 # 시행일(09-26) 이전 호출은 분모에 넣지 않는다
    assert v["share"] == 50.0
