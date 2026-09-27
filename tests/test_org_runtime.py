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
    # 예약 작업은 이 PC 의 작업 스케줄러를 읽는다 — 테스트가 호스트 상태에 기대지 않게 비운다(OPS-3).
    # 빈 목록 + 사유 = '못 읽음'이라 지시서도 '미등록'도 만들지 않는다.
    monkeypatch.setattr(o, "schedule_states", lambda: ([], "테스트: 예약 작업을 읽지 않는다"))
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


# ── 워크플로 인계 중복 방지(OPS-3 ⑦, 2026-09-27) ───────────────────────────────
# 워크플로 보고서의 handoff 가 이미 돌고 있는 단계에 지시서 11건을 또 만들었다(Steward 취소).

def _bus(org, kind):
    return [e for e in org.events() if e.get("kind") == kind]


def test_workflow_report_does_not_spawn_handoff_orders(org):
    report(org, "wf.md", {"from": "qa-engineer", "ticket": "OPS-3", "result": "done", "workflow": "run-7",
                          "handoff": [{"to": "backend-engineer", "why": "반증 1건"}]})
    org.scan(now=NOW)
    assert by_reason(org, "handoff") == []
    sk = _bus(org, "handoff.skipped")
    assert len(sk) == 1 and sk[0]["to"] == "backend-engineer" and "run-7" in sk[0]["note"]
    org.scan(now=NOW + timedelta(hours=1))                      # 다시 읽어도 기록은 한 번
    assert len(_bus(org, "handoff.skipped")) == 1


def test_workflow_blocked_report_skips_pm_but_needs_owner_still_reaches_inbox(org):
    report(org, "wf-b.md", {"from": "insight", "result": "blocked", "workflow": "run-8", "handoff": []})
    report(org, "wf-o.md", {"from": "compliance-officer", "result": "needs-owner", "workflow": "run-8",
                            "handoff": []})
    org.scan(now=NOW)
    assert by_reason(org, "result") == [] and len(_bus(org, "result.skipped")) == 1
    assert [o["meta"]["to"] for o in by_reason(org, "owner")] == [rt.STEWARD]   # 오너 결정은 삼키지 않는다


def test_answer_to_steward_order_skips_duplicate_of_open_order_same_ticket_and_seat(org):
    orders = org.orders()
    parent = org.create_order(orders, to="qa-engineer", frm=rt.STEWARD, purpose="검증", reason="manual",
                              ticket="OPS-3", now=NOW)
    running = org.create_order(orders, to="backend-engineer", frm=rt.STEWARD, purpose="구현", reason="manual",
                               ticket="OPS-3", now=NOW)
    report(org, "qa.md", {"order": parent["meta"]["id"], "from": "qa-engineer", "ticket": "OPS-3",
                          "result": "fail", "handoff": [{"to": "backend-engineer", "why": "반증"}]})
    org.scan(now=NOW)
    assert org.orders()[parent["meta"]["id"]]["meta"]["status"] == "done"      # 부모는 그대로 닫힌다
    assert by_reason(org, "handoff") == []
    sk = _bus(org, "handoff.skipped")
    assert len(sk) == 1 and running["meta"]["id"] in sk[0]["note"]


def test_answer_to_non_steward_order_still_hands_off(org):
    """대조군 — 조건이 하나라도 빠지면 예전처럼 인계한다(막는 범위를 넓히지 않는다)."""
    orders = org.orders()
    parent = org.create_order(orders, to="qa-engineer", frm="frontend-engineer", purpose="검증",
                              reason="manual", ticket="OPS-3", now=NOW)
    org.create_order(orders, to="backend-engineer", frm=rt.STEWARD, purpose="구현", reason="manual",
                     ticket="OPS-3", now=NOW)
    report(org, "qa2.md", {"order": parent["meta"]["id"], "from": "qa-engineer", "ticket": "OPS-3",
                           "result": "fail", "handoff": [{"to": "backend-engineer", "why": "반증"}]})
    org.scan(now=NOW)
    assert [o["meta"]["to"] for o in by_reason(org, "handoff")] == ["backend-engineer"]


def test_contract_alert_table_parses():
    routes = rt.Org(ROOT).alert_routes()
    assert routes["시세 분석"]["ticket"] and routes["시세 분석"]["watch"]
    assert routes["매일 시세·낙찰 갱신"]["watch"] is False             # '-' = 이 신호로는 지시서를 만들지 않는다
    assert {r["source"] for r in routes.values()} == {"공급", "정기 작업", "예약 작업"}


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


def test_standup_briefing_only_does_not_claim_nothing_to_dispatch(org, monkeypatch):
    """--dispatch 0 은 '부를 것이 없다'가 아니라 '이번엔 안 불렀다'다 — 2026-09-27 첫 실제 실행에서 잡힌 문구."""
    calls = []
    monkeypatch.setattr(org, "dispatch", lambda oid, dry_run=False: calls.append(oid) or {"ok": True})
    text = org.standup(dispatch=0, now=NOW).read_text(encoding="utf-8")
    assert calls == []
    assert "브리핑만" in text and "없거나" not in text
    assert "pm-orchestrator" in text.split("## 오늘 당직이 부르는 것")[1]   # 부를 수 있었던 것을 보여 준다



# ── 당직의 claude 찾기(2026-09-27) ──────────────────────────────────────────────
# 이 PC 의 claude 는 VS Code 확장 안에만 있고 경로에 버전이 박혀 있다. 확장이 업데이트되면
# 등록 때 넘긴 --claude 경로가 사라진다 — 그때 가장 새 확장을 다시 찾는지 본다.

def _fake_ext(home, ver, with_exe=True):
    d = home / ".vscode" / "extensions" / f"anthropic.claude-code-{ver}-win32-x64" / "resources" / "native-binary"
    d.mkdir(parents=True)
    exe = d / ("claude.exe" if rt.os.name == "nt" else "claude")
    if with_exe:
        exe.write_bytes(b"")
    return exe


def test_vscode_claude_picks_highest_version_numerically(tmp_path):
    _fake_ext(tmp_path, "2.1.99")
    newest = _fake_ext(tmp_path, "2.1.282")                 # 문자열 정렬이면 2.1.99 가 이긴다
    _fake_ext(tmp_path, "2.1.300", with_exe=False)          # 업데이트 뒤 비어 남은 폴더는 세지 않는다
    assert rt._vscode_claude(tmp_path) == str(newest)


def test_vscode_claude_empty_when_no_extension(tmp_path):
    assert rt._vscode_claude(tmp_path) == ""


def test_claude_cmd_falls_back_when_registered_path_vanished(org, monkeypatch, tmp_path):
    org.claude_exe = str(tmp_path / "gone" / "claude.exe")  # 등록 때 넘긴 경로 — 확장 업데이트로 사라짐
    monkeypatch.setattr(rt.shutil, "which", lambda name: None)
    monkeypatch.setattr(rt, "_vscode_claude", lambda home=None: "C:/new/claude.exe")
    cmd = org._claude_cmd()
    assert cmd[0] == "C:/new/claude.exe" and "-p" in cmd


def test_claude_cmd_keeps_registered_path_when_it_exists(org, monkeypatch, tmp_path):
    exe = tmp_path / "claude.exe"
    exe.write_bytes(b"")
    org.claude_exe = str(exe)
    monkeypatch.setattr(rt, "_vscode_claude", lambda home=None: "C:/other/claude.exe")
    assert org._claude_cmd()[0] == str(exe)
