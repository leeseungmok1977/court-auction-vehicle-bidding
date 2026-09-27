# -*- coding: utf-8 -*-
"""OPS-4 수정 회차 재검증(qa-engineer, 지시서 2026-09-27-71) — 결과는 `reports/2026-09-27-ops4-qa-r2.md`.

① §3.1 네 칸(db-backup-pull·weekly·monthly·PhotoClassify)을 `-` 로 비운 뒤, 네 작업의 조용한 누락이
   **경계 시각 그 순간** 지시서가 되는지 dry-run 으로 밟는다(1초 전 0 · 그 순간 1 · 파일은 하나도 안 씀).
   대조군: 같은 입력에서 네 칸만 옛 티켓(AUD-08·AUD-15)으로 되돌리면 ticket-open(0장) — 이 테스트가
   공허 통과가 아니라 §3.1 변경을 보고 있다는 증거다.
② 사내 대시보드 표(실제 HTML `schedState` 를 브라우저에서 돌린다)가 결재함과 같은 판정을 보이는가.
   임시 루트에서 실제 `scan()` 이 만든 task 지시서와, 같은 루트를 읽는 `attach_silence` → `schedState` 칩을 맞댄다.
③ QA-OPS4-4: '꺼짐(Disabled)'·'다음 실행 없음'은 결재함에 '예약 작업 경보'가 서는데 표는 초록 '정상'이었다(r2).
   r3 에서 서버가 행마다 `verdict`(= `schedule_verdict`)를 싣고 표가 그것을 칠해 닫혔다. strict xfail 은 XPASS 가 됐고
   (qa r3, 지시서 2026-09-27-76) 표식을 뗐다 — 단언은 남기고 더 세게(빨강 · 결재함과 같은 글자) 했다.
   ⚠ XPASS 는 처음에 **다른 이유**로 났다: 이 파일의 `board` 가 `attach_verdict` 를 부르지 않아 두 작업이 '확인 불가'가
   되어 '초록이 아님'을 통과했다. 이제 `board` 는 대시보드 `build_state` 순서(`attach_verdict` → `attach_silence`)를 따른다.
④ 규칙 사본 도우미(`_dashboard_pill`·`_dashboard_class`)는 r1 칩 규칙(결과 `ok` 만 본다)의 사본이라 r3 표와 어긋났다 —
   qa r3 에서 지우고 두 파일이 실제 `schedState`(`_schedstate_js`)를 쓰게 바꿨다. 여기서는 표의 빨강이 **순환계 판정**
   (verdict 가 있으면 `verdict.broken`, 없으면 원자료로 확실한 것)과 같은지를 본다.

블록은 줄 번호가 아니라 앵커 문자열로 자른다(CLAUDE.md 운영 규칙 8). 운영 orders/·data/ 에 쓰지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "tools"), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import agent_dashboard as ad  # noqa: E402
import org_runtime as rt  # noqa: E402
import test_ops3_qa_adversarial as q3  # noqa: E402
import test_ops4_qa_adversarial as q1  # noqa: E402

DAY = 86400
FOUR_OLD = {"naechaget-db-backup-pull": "AUD-08", "naechaget-weekly-report": "AUD-15",
            "naechaget-monthly-report": "AUD-15", "NaechaGet-PhotoClassify": "AUD-15"}


def _root(tmp_path: Path, sub: str, *, old_tickets: bool = False, backlog: str = q1.BACKLOG) -> Path:
    root = tmp_path / sub
    (root / "docs" / "daily-reports").mkdir(parents=True)
    (root / "reports").mkdir()
    (root / "data").mkdir()
    c = (ROOT / "docs" / "org-contracts.md").read_text(encoding="utf-8")
    if old_tickets:
        for n, t in FOUR_OLD.items():
            c, k = re.subn(r"(\| `%s` \| `예약 작업` \| `steward` \| )`-`" % re.escape(n), r"\1`%s`" % t, c)
            assert k == 1, f"§3.1 `{n}` 행을 찾지 못했다 — 표 모양이 바뀌었으면 이 대조군을 고칠 것"
    (root / "docs" / "org-contracts.md").write_text(c, encoding="utf-8")
    (root / "docs" / "backlog.md").write_text(backlog, encoding="utf-8")
    return root


def _org(root: Path, rows: list[dict], monkeypatch, *, dry: bool) -> rt.Org:
    o = rt.Org(root)
    o.dry_run = dry
    monkeypatch.setattr(o, "rhythm_states", lambda: [])
    monkeypatch.setattr(o, "schedule_states", lambda: ([dict(r) for r in rows], None))
    return o


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


# ════════════════════════════════════════════════════════════════════════
# ① §3.1 변경 뒤 — 네 작업의 조용한 누락이 경계 시각에 지시서가 된다(dry-run)
# ════════════════════════════════════════════════════════════════════════
# 2026-09-27 16:14 캡처 9행(test_ops4_qa_adversarial.real_rows — 이 PC 실측)에서, 그 뒤로 아무것도 안 돈다고 둘 때
# 한도가 차는 순간(계약 §3 문장으로 계산: 등록 날짜 → 없으면 task_seen, 첫 트리거가 더 늦으면 그때 / 돈 적이 있으면
# 마지막 성공)과 멱등 키의 시각.
BOUNDARY = {
    "naechaget-db-backup-pull": (datetime(2026, 9, 29, 4, 5, 2), "2026-09-27T16:05"),   # task_seen 16:05:02 + 36h
    "naechaget-weekly-report": (datetime(2026, 10, 4, 13, 0), "2026-09-26T13:00"),       # 마지막 성공 + 8일
    "NaechaGet-PhotoClassify": (datetime(2026, 10, 5, 8, 17), "2026-09-27T08:17"),       # 마지막 성공 + 8일
    "naechaget-monthly-report": (datetime(2026, 10, 27, 20, 47), "2026-09-22T20:47"),    # 등록 날짜 + 35일
}


def _seed_state(root: Path, rows: list[dict]) -> Path:
    p = root / "data" / "org-state.json"
    p.write_text(json.dumps({"reports": {}, "task_seen": {r["name"]: q1.SEEN for r in rows},
                             "task_bad": {"naechaget-home-tunnel": "2026-09-16T05:24:00"}}), encoding="utf-8")
    return p


@pytest.mark.parametrize("name", sorted(BOUNDARY))
def test_quiet_task_becomes_an_order_exactly_at_the_limit_after_the_31_change(tmp_path, monkeypatch, name):
    rows = q1.real_rows()
    T, since = BOUNDARY[name]
    key = f"task:{name}:{since}"
    seen: dict[str, tuple] = {}
    for sub, old in (("after", False), ("before", True)):
        for label, when in (("-1s", T - timedelta(seconds=1)), ("T", T)):
            root = _root(tmp_path, f"{sub}{label}", old_tickets=old)
            st = _seed_state(root, rows)
            h0 = _md5(st)
            o = _org(root, rows, monkeypatch, dry=True)
            r = o.scan(now=when)
            t = next((x for x in r["tasks"] if x["name"] == name), None)
            would = [d["key"] for d in o.dry_orders_summary() if d["reason"] == "task" and d["key"].startswith(
                f"task:{name}:")]
            # dry-run 은 아무것도 쓰지 않는다
            assert _md5(st) == h0 and not o.bus.exists()
            assert not (o.orders_dir.exists() and list(o.orders_dir.glob("*.md")))
            seen[(sub, label)] = (t and t["action"], would)
    assert seen[("after", "-1s")] == (None, [])                                   # 1초 전 — 판정도 지시서도 없다
    assert seen[("after", "T")] == ("order", [key])                               # 그 순간 — 지시서 한 장
    assert seen[("before", "T")] == ("ticket-open", [])                           # 대조군: 옛 티켓 뒤에선 0장


def test_the_four_quiet_orders_carry_the_inbox_label_and_no_ticket(tmp_path, monkeypatch):
    """실제 스캔(임시 루트)으로 네 장을 만들면 받는 자리 steward · 티켓 칸이 비어 '티켓 없음' 문구 · 목적 줄 라벨."""
    rows = q1.real_rows()
    root = _root(tmp_path, "real")
    _seed_state(root, rows)
    o = _org(root, rows, monkeypatch, dry=False)
    o.scan(now=datetime(2026, 10, 27, 21, 5))                                     # 넷 다 경계를 넘은 첫 매시 스캔
    got = {}
    for x in o.orders().values():
        m = x["meta"]
        if m["reason"] == "task" and m["key"].split(":")[1] in BOUNDARY:
            got[m["key"].split(":")[1]] = (m["to"], m["key"], x["body"])
    assert set(got) == set(BOUNDARY)
    for n, (to, key, body) in got.items():
        assert to == rt.STEWARD and key == f"task:{n}:{BOUNDARY[n][1]}", n
        assert "**티켓 없음**" in body, n                                            # §3.1 티켓 칸 '-'
        assert re.search(rf"예약 작업 `{re.escape(n)}` — (조용히 안 돎|첫 실행 없음) · ", body), n


# ════════════════════════════════════════════════════════════════════════
# ② 대시보드 표 = 결재함 — 임시 루트의 실제 scan() 지시서 ↔ 실제 HTML schedState
# ════════════════════════════════════════════════════════════════════════
HTML = (ROOT / "tools" / "agent_dashboard.html").read_text(encoding="utf-8")


def _cut(start: str, end: str) -> str:
    i = HTML.index(start)
    return HTML[i:HTML.index(end, i) + len(end)]


@pytest.fixture(scope="module")
def page():
    pw = pytest.importorskip("playwright.sync_api")
    js = "\n".join([_cut("const esc = ", "\n"), _cut("  {'&':'&amp;'", "\n"), _cut("const RSN = {", "};"),
                    _cut("const schedState = s => {", "\n};")])
    with pw.sync_playwright() as p:
        b = None
        for kw in ({}, {"channel": "chrome"}):
            try:
                b = p.chromium.launch(**kw)
                break
            except Exception:                                            # noqa: BLE001
                continue
        if b is None:
            pytest.skip("chromium·chrome 둘 다 없음")
        pg = b.new_page()
        pg.set_content("<!doctype html><meta charset='utf-8'><body></body>")
        pg.add_script_tag(content=js)
        yield pg
        b.close()


NOW = datetime(2026, 10, 28, 10, 5)
NEVER = "1999-11-30 00:00"


def _f(d: datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M")


def _r(name, **kw):
    t = {"name": name, "status": "Ready", "running": False, "last_run": "", "last_result": "0", "next_run": "",
         "enabled": True, "never_ran": False, "ok": True, "period_s": DAY, "first_start": _f(NOW - timedelta(days=10)),
         "registered": "", "trigger_error": ""}
    t.update(kw)
    return t


# 실제 이름 9개(§3.1 경로를 그대로 탄다) + 표에 없는 이름 3개(표에 없으면 steward · 티켓 없음)
SCENARIO = [
    _r("naechaget-org-standup", last_run=_f(NOW - timedelta(hours=50)), next_run=_f(NOW + timedelta(hours=10))),
    _r("naechaget-weekly-report", period_s=7 * DAY, last_run=_f(NOW - timedelta(days=9)),
       next_run=_f(NOW + timedelta(days=2)), registered=_f(NOW - timedelta(days=20))),
    _r("naechaget-monthly-report", period_s=31 * DAY, never_ran=True, ok=False, last_result="267011", last_run=NEVER,
       next_run=_f(NOW + timedelta(days=4)), registered=_f(NOW - timedelta(days=40)),
       first_start=_f(NOW - timedelta(days=45))),
    _r("naechaget-db-backup-pull", never_ran=True, ok=False, last_result="267011", last_run=NEVER,   # task_seen 경로
       next_run=_f(NOW + timedelta(hours=10)), first_start=_f(NOW - timedelta(days=3))),
    _r("NaechaGet-PhotoClassify", period_s=7 * DAY, last_run=_f(NOW - timedelta(days=2)),
       next_run=_f(NOW + timedelta(days=5))),
    _r("naechaget-daily-report", last_run=_f(NOW - timedelta(hours=5)), next_run=_f(NOW + timedelta(hours=19))),
    _r("naechaget-org-heartbeat", period_s=3600, never_ran=True, ok=False, last_result="267011", last_run=NEVER,
       next_run=_f(NOW + timedelta(minutes=50)), registered=_f(NOW - timedelta(minutes=10))),
    _r("naechaget-ops-snapshot", period_s=60, status="Running", running=True, last_result="267009",
       last_run=_f(NOW - timedelta(minutes=1)), next_run=_f(NOW + timedelta(minutes=1))),
    _r("naechaget-home-tunnel", period_s=None, first_start="", last_run="2026-09-16 05:24", last_result="3221225477",
       next_run="", ok=False),
    _r("x-disabled", status="Disabled", enabled=False, last_run=_f(NOW - timedelta(days=3)), next_run=""),
    _r("x-no-next", last_run=_f(NOW - timedelta(hours=30)), next_run=""),
    _r("x-trigger-unreadable", period_s=None, first_start="", last_run=_f(NOW - timedelta(days=2)),
       next_run=_f(NOW + timedelta(days=5)), trigger_error="QA 픽스처 — 트리거를 못 읽음"),
]
QUIET = {"naechaget-org-standup", "naechaget-weekly-report", "naechaget-monthly-report", "naechaget-db-backup-pull"}
GAP = {"x-disabled", "x-no-next"}                                                  # QA-OPS4-4


@pytest.fixture()
def board(tmp_path, monkeypatch):
    """임시 루트: 실제 §3.1 · 실제 백로그 모양(AUD-05 열림) → scan() 이 결재함 지시서를 만든다.
    같은 루트를 대시보드가 읽는다(`ad.ROOT` → `attach_silence` → `Org.silence_rows`)."""
    root = _root(tmp_path, "dash")
    (root / "data" / "org-state.json").write_text(json.dumps({
        "reports": {}, "task_seen": {r["name"]: (NOW - timedelta(hours=37)).isoformat() for r in SCENARIO},
        "task_bad": {"x-disabled": (NOW - timedelta(hours=30)).isoformat()}}), encoding="utf-8")
    o = _org(root, SCENARIO, monkeypatch, dry=False)
    r = o.scan(now=NOW)
    inbox = {}
    for x in rt.Org(root).orders().values():
        m = x["meta"]
        if m["reason"] == "task" and m["status"] in rt.OPEN_STATES:
            purpose = x["body"].split("## 목적", 1)[-1].strip().splitlines()[0]
            inbox[m["key"].split(":")[1]] = (m["to"], purpose)
    monkeypatch.setattr(ad, "ROOT", root)
    rows = [dict(s) for s in SCENARIO]
    vwarns, verr = ad.attach_verdict(rows)                  # 대시보드 build_state 순서 — 고장 판정 먼저(OPS-4 r3)
    assert verr is None and not vwarns
    warns, err = ad.attach_silence(rows, NOW)
    assert err is None
    return {"tasks": {t["name"]: t for t in r["tasks"]}, "inbox": inbox, "rows": rows, "warns": warns}


def _chips(page, rows):
    return {r["name"]: s for r, s in zip(rows, page.evaluate("rows => rows.map(schedState)", rows))}


def test_scenario_really_hits_every_branch(board):
    """공허 통과 방지 — 넷은 조용한 누락 지시서, 둘은 기존 고장 지시서, 터널은 열린 티켓 뒤(0장)."""
    assert set(board["inbox"]) == QUIET | GAP
    assert board["tasks"]["naechaget-home-tunnel"]["action"] == "ticket-open"
    assert {n: board["tasks"][n]["label"] for n in GAP} == {"x-disabled": "꺼짐(Disabled)", "x-no-next": "다음 실행 없음"}
    assert board["warns"] and "x-trigger-unreadable" in board["warns"][0]
    assert all(to == rt.STEWARD for to, _ in board["inbox"].values())


def test_dashboard_json_silence_equals_the_inbox_label(board):
    """JSON(`schedule[].silence`)의 라벨 = 결재함 목적 줄의 라벨 — 조용한 누락 넷, 글자까지."""
    by = {r["name"]: r for r in board["rows"]}
    for n in QUIET:
        sv = by[n]["silence"]
        assert sv["bad"], n
        # OPS-4 r3(backend): 라벨 뒤는 ' · **N시간째**(…)' 가 아니라 ' · 다음 실행 …' — 라벨에 없는 것만 붙는다
        assert board["inbox"][n][1].startswith(f"예약 작업 `{n}` — {sv['label']} · 다음 실행 "), n
    assert {n for n, r in by.items() if (r["silence"] or {}).get("bad")} == QUIET
    k = ad.schedule_counts(board["rows"])
    assert k["sched_silent"] == len(QUIET)


def test_table_chip_reads_like_the_inbox_for_quiet_tasks_and_is_never_green_for_them(page, board):
    ch = _chips(page, board["rows"])
    for n in QUIET:
        x = ch[n]
        assert (x["pill"], x["row"], x["alarm"]) == ("warn", "late", True), n
        assert board["inbox"][n][1].startswith(f"예약 작업 `{n}` — {x['text']} · {x['sub']} · 다음 실행 "), n  # r3 모양
    # 반대 방향 — 표가 조용한 누락(주황 경보)으로 그린 작업은 모두 결재함에 있다
    assert {n for n, x in ch.items() if x["alarm"]} == QUIET
    # 결재함에 없는 빨강은 열린 티켓 뒤의 고장(터널)뿐 — 표가 더 엄격한 쪽으로만 어긋난다
    assert {n for n, x in ch.items() if x["pill"] == "bad" and n not in board["inbox"]} == {"naechaget-home-tunnel"}
    assert ch["x-trigger-unreadable"]["pill"] == "mute"                         # 모름은 초록이 아니다


def test_qa_ops4_4_disabled_and_no_next_run_are_red_in_the_table_like_the_inbox(page, board):
    """QA-OPS4-4(r2 strict xfail → r3 해소, qa r3 에서 표식 뗌). 옛 이름
    `test_known_gap_disabled_and_no_next_run_are_green_in_the_table_while_the_inbox_alarms` — 옛 단언(초록이 아님)은
    그대로 두고, 빨강 칩 · 빨강 행 · 칩 + 사유 = 결재함 목적 줄의 라벨(글자까지)을 더했다."""
    ch = _chips(page, board["rows"])
    for n in GAP:
        assert n in board["inbox"]
        assert ch[n]["pill"] != "ok", (n, ch[n])
        assert (ch[n]["pill"], ch[n]["row"], ch[n]["alarm"]) == ("bad", "bad", False), (n, ch[n])
        words = ch[n]["text"] + (" · " + ch[n]["sub"] if ch[n]["sub"] else "")
        assert words == board["tasks"][n]["label"], (n, ch[n])
        assert board["inbox"][n][1].startswith(f"예약 작업 `{n}` — {words} · "), n


def test_qa_ops4_4_tile_counts_the_inbox_and_unknown_verdict_is_not_green(page, board):
    """옛 이름 `test_known_gap_is_what_it_is_today`(r2 의 초록을 못 박았다 — r3 에서 뜻을 잃어 지금 모습으로 바꿨다).
    - 타일 '볼 것'(sched_alarm) = 결재함 task 지시서 + 터널(열린 티켓 뒤 — 표 빨강 · 결재함 0). r2 에는 이 둘만큼 적었다.
    - 서버가 verdict 를 못 실으면(판정 불가) 두 작업은 '확인 불가'다 — 초록으로 돌아가지 않는다. sched_stopped 는 None."""
    ch = _chips(page, board["rows"])
    assert {n: (ch[n]["pill"], ch[n]["text"]) for n in GAP} == {
        "x-disabled": ("bad", "꺼짐(Disabled)"), "x-no-next": ("bad", "다음 실행 없음")}
    k = ad.schedule_counts(board["rows"])
    assert k["sched_stopped"] == len(GAP)
    assert k["sched_alarm"] == len(board["inbox"]) + 1                             # +1 = 터널
    unknown = [dict(r, verdict=None) for r in board["rows"]]
    cu = _chips(page, unknown)
    assert {n: (cu[n]["pill"], cu[n]["text"]) for n in GAP} == {n: ("mute", "확인 불가") for n in GAP}
    assert ad.schedule_counts(unknown)["sched_stopped"] is None


# ════════════════════════════════════════════════════════════════════════
# ④ 표의 빨강 = 순환계 판정(규칙 사본이 아니다) — qa r3 에서 사본 도우미를 지우고 이 뜻으로 바꿨다
# ════════════════════════════════════════════════════════════════════════
def test_red_in_the_table_is_the_runtime_verdict_not_a_copied_rule(page, board):
    """옛 이름 `test_copied_rule_helpers_still_agree_with_schedstate_on_red`. 사본 도우미(`_dashboard_pill`·
    `_dashboard_class`)는 r1 규칙이라 r3 에서 x-disabled·x-no-next 를 '정상'이라 했다 — 지웠다(qa r3).
    48행(verdict 있음/없음 × silence 그대로/없음/가짜 경보)에서 빨강 ⟺ verdict 가 있으면 `verdict.broken`,
    없으면 원자료로 확실한 것(실행된 적 없음 · 예정도 없음 / 돈 적 있고 결과 ≠ 0). 빨강 ⟺ 빨강 행."""
    fake = {"bad": True, "label": "조용히 안 돎 · x", "since": "", "limit_h": 36, "cls": "매일", "warn": ""}
    base = board["rows"]
    rows = []
    for v in (True, False):
        for sv in ("keep", None, fake):
            rows += [dict(r, **({} if v else {"verdict": None}), **({} if sv == "keep" else {"silence": sv}))
                     for r in base]
    ch = page.evaluate("rows => rows.map(schedState)", rows)
    assert sum(1 for r in rows if r["verdict"] is None) == len(base) * 3            # 공허 방지 — 두 갈래 다 돈다
    for r, x in zip(rows, ch):
        red = x["pill"] == "bad"
        assert red == (x["row"] == "bad"), r["name"]
        if r["verdict"] is not None:
            assert red == r["verdict"]["broken"], (r["name"], x)
            assert red == rt.schedule_verdict(r)[0], (r["name"], x)
        else:
            raw = (r["never_ran"] and not r["next_run"]) or (not r["never_ran"] and not r["ok"])
            assert red == raw, (r["name"], x)
    assert not hasattr(q1, "_dashboard_pill") and not hasattr(q3, "_dashboard_class")
