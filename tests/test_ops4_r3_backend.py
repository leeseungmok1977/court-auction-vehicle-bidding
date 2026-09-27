# -*- coding: utf-8 -*-
"""OPS-4 r3 backend(지시서 2026-09-27-74) — 결과는 `reports/2026-09-27-ops4-backend-r3.md`.

① QA-OPS4-4 ⓐ(Steward 결정): 대시보드 예약 작업 행마다 순환계 `schedule_verdict` 결과를 `verdict` = {broken, label}로
   **그대로** 싣는다(`agent_dashboard.attach_verdict`). 판정을 못 붙이면 None(모름) — 정상으로 채우지 않는다.
② 필드 동일성: 순환계(`Org.schedule_states`)와 대시보드는 **같은 함수**(`agent_dashboard.read_schedule`)의 같은 행을 읽고,
   그 행에는 `schedule_verdict` 가 읽는 칸(`SCHEDULE_FIELDS`)이 같은 뜻으로 들어 있다 — 가짜 PowerShell 출력에서 끝까지.
③ 겹침 없음 · 같은 순서: 고장 먼저, 고장이 아닐 때만 조용한 누락(`judge_task`) — `task_eval` 과 `silence_rows` 가 같다.
④ KPI `sched_stopped`(꺼짐·다음 실행 없음) · `sched_alarm` 에 합침 · 기존 키의 뜻은 그대로.
⑤ 결재함 목적 줄(design-critic r2 #1): 라벨 그대로 + 라벨에 없는 것만 · 1999 없음 · '다음 실행 없음' 되풀이 없음 ·
   주어 없는 'N시간째' 없음 · 140자 한도는 ` · `(없으면 공백) 경계에서 자르고 '…'.
⑥ 변이 검사: 각 검사 함수에 **옛 동작**(r2 코드)을 넣으면 빨개진다 — 옛 동작을 되살리면 이 파일이 빨간불이다.

모두 tmp_path·가짜 스케줄 목록으로 돈다 — 작업 스케줄러·운영 orders/·data/·서버·외부 요청을 건드리지 않는다.
블록은 줄 번호가 아니라 함수 이름·앵커 문자열로 가리킨다(CLAUDE.md 운영 규칙 8).
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import agent_dashboard as ad  # noqa: E402
import org_runtime as rt  # noqa: E402

DAY = 86400
NOW = datetime(2026, 10, 28, 10, 5)
NEVER = "1999-11-30 00:00"
SEEN = (NOW - timedelta(hours=37)).isoformat()
BAD_SINCE = (NOW - timedelta(hours=30)).isoformat()
BACKLOG = """# 백로그

| ID | 제목 | 담당 | 상태 | 완료 기준(DoD) |
|---|---|---|---|---|
| AUD-99 | 테스트 | x | 완료 | x |
"""
_TS = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?|\d{2}-\d{2} \d{2}:\d{2}")


def _f(d: datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M")


def _r(name, **kw) -> dict:
    """`read_schedule` 한 행과 같은 모양(칸 전부)."""
    t = {"name": name, "status": "Ready", "running": False, "last_run": _f(NOW - timedelta(hours=2)),
         "last_result": "0", "next_run": _f(NOW + timedelta(hours=22)), "enabled": True, "never_ran": False,
         "ok": True, "period_s": DAY, "first_start": "", "registered": "", "trigger_error": ""}
    t.update(kw)
    return t


REAL = sorted(n for n, r in rt.Org(ROOT).alert_routes().items() if r["source"] == "예약 작업")
MISSING = "naechaget-org-standup"                     # 표(§3.1)에는 있는데 목록에 없다 → '미등록'
X = [
    _r("x-quiet", last_run=_f(NOW - timedelta(hours=50)), next_run=_f(NOW + timedelta(hours=14))),
    _r("x-first", never_ran=True, ok=False, last_result="267011", last_run=NEVER, period_s=31 * DAY,
       registered=_f(NOW - timedelta(days=40)), first_start=_f(NOW - timedelta(days=45)),
       next_run=_f(NOW + timedelta(days=4))),
    _r("x-disabled", status="Disabled", enabled=False, last_run=_f(NOW - timedelta(hours=72)), next_run=""),
    _r("x-no-next", last_run=_f(NOW - timedelta(hours=30)), next_run=""),
    _r("x-dead", last_run="2026-10-16 05:24", last_result="3221225477", ok=False, next_run="", period_s=None),
    _r("x-hourly", last_run=_f(NOW - timedelta(hours=1)), last_result="1", ok=False,
       next_run=_f(NOW + timedelta(hours=1)), period_s=3600),
    _r("x-never-reg", never_ran=True, ok=False, last_result="267011", last_run=NEVER, next_run="",
       registered=_f(NOW - timedelta(hours=120))),
    _r("x-never-noreg", never_ran=True, ok=False, last_result="267011", last_run=NEVER, next_run=""),
    _r("x-normal"),
    _r("x-running", status="Running", running=True, last_result="267009", ok=True, period_s=60),
    _r("x-waiting", never_ran=True, ok=False, last_result="267011", last_run=NEVER,
       registered=_f(NOW - timedelta(hours=3)), next_run=_f(NOW + timedelta(hours=5))),
]
ROWS = [_r(n) for n in REAL if n != MISSING] + X

# 순환계 라벨(글자 그대로) — 표의 칩과 결재함이 같은 글자를 쓴다
LABEL = {
    "x-quiet": "조용히 안 돎 · 마지막 성공 10-26 08:05 · 매일 작업 한도 36시간 넘김",
    "x-first": "첫 실행 없음 · 등록 09-18 10:05 뒤 매월 작업 한도 35일 넘김",
    "x-disabled": "꺼짐(Disabled)",
    "x-no-next": "다음 실행 없음",
    "x-dead": "실패 · 결과 3221225477(0xC0000005) · 다음 실행 없음",
    "x-hourly": "실패 · 결과 1(0x00000001)",
    "x-never-reg": "실행된 적 없음 · 예정도 없음",
    "x-never-noreg": "실행된 적 없음 · 예정도 없음",
    MISSING: "미등록",
}
# 결재함 목적 첫 줄 — 기대값(설계 r2 #1 의 네 모양)
PURPOSE = {
    "x-quiet": f"예약 작업 `x-quiet` — {LABEL['x-quiet']} · 다음 실행 2026-10-29 00:05",
    "x-first": f"예약 작업 `x-first` — {LABEL['x-first']} · 다음 실행 2026-11-01 10:05",
    "x-disabled": "예약 작업 `x-disabled` — 꺼짐(Disabled) · 마지막 실행 2026-10-25 10:05 뒤 72시간",
    "x-no-next": "예약 작업 `x-no-next` — 다음 실행 없음 · 마지막 실행 2026-10-27 04:05 뒤 30시간",
    "x-dead": f"예약 작업 `x-dead` — {LABEL['x-dead']} · 마지막 실행 2026-10-16 05:24 뒤 292시간",
    "x-hourly": ("예약 작업 `x-hourly` — 실패 · 결과 1(0x00000001) · 마지막 실행 2026-10-28 09:05 뒤 1시간"
                 " · 다음 실행 2026-10-28 11:05"),
    "x-never-reg": "예약 작업 `x-never-reg` — 실행된 적 없음 · 예정도 없음 · 등록 2026-10-23 10:05 뒤 120시간",
    "x-never-noreg": "예약 작업 `x-never-noreg` — 실행된 적 없음 · 예정도 없음 · 순환계가 처음 본 2026-10-27 04:05 뒤 30시간",
    MISSING: f"예약 작업 `{MISSING}` — 미등록 · 순환계가 처음 본 2026-10-27 04:05 뒤 30시간",
}
QUIET = {"x-quiet", "x-first"}
STOPPED = {"x-disabled", "x-no-next"}


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / "docs" / "daily-reports").mkdir(parents=True)
    (root / "reports").mkdir()
    (root / "data").mkdir()
    shutil.copy(ROOT / "docs" / "org-contracts.md", root / "docs" / "org-contracts.md")
    (root / "docs" / "backlog.md").write_text(BACKLOG, encoding="utf-8")
    return root


def _org(root: Path, monkeypatch, rows: list[dict] | None = None) -> rt.Org:
    o = rt.Org(root)
    monkeypatch.setattr(o, "rhythm_states", lambda: [])
    if rows is not None:
        monkeypatch.setattr(o, "schedule_states", lambda: ([dict(r) for r in rows], None))
    return o


def _seed(root: Path) -> None:
    bad = {n: BAD_SINCE for n in ("x-disabled", "x-hourly", "x-never-reg", "x-never-noreg", MISSING)}
    (root / "data" / "org-state.json").write_text(json.dumps({
        "reports": {}, "task_seen": {r["name"]: SEEN for r in ROWS} | {MISSING: SEEN},
        "task_bad": bad}), encoding="utf-8")


def _first_line(body: str) -> str:
    return body.split("## 목적", 1)[-1].strip().splitlines()[0]


@pytest.fixture()
def scene(tmp_path, monkeypatch):
    """임시 루트: 실제 §3.1 · 스캔 한 번(결재함 지시서) · 같은 루트를 대시보드가 읽는다(verdict·silence)."""
    root = _root(tmp_path)
    _seed(root)
    o = _org(root, monkeypatch, ROWS)
    res = o.scan(now=NOW)
    inbox = {}
    for x in rt.Org(root).orders().values():
        m = x["meta"]
        if m["reason"] == "task":
            inbox[m["key"].split(":")[1]] = _first_line(x["body"])
    monkeypatch.setattr(ad, "ROOT", root)
    rows = [dict(r) for r in ROWS]
    vw, ve = ad.attach_verdict(rows)
    sw, se = ad.attach_silence(rows, NOW)
    assert (ve, se) == (None, None)
    return SimpleNamespace(root=root, org=o, tasks={t["name"]: t for t in res["tasks"]}, inbox=inbox,
                           rows={r["name"]: r for r in rows}, rowlist=rows, vwarns=vw, swarns=sw,
                           warnings=res["warnings"])


# ════════════════════════════════════════════════════════════════════════
# 검사 함수 — 본 테스트와 변이 테스트(⑥)가 같은 것을 쓴다
# ════════════════════════════════════════════════════════════════════════
EXPECTED_VERDICT = {
    "x-disabled": (True, "꺼짐(Disabled)"), "x-no-next": (True, "다음 실행 없음"),
    "x-dead": (True, LABEL["x-dead"]), "x-hourly": (True, LABEL["x-hourly"]),
    "x-never-reg": (True, "실행된 적 없음 · 예정도 없음"), "x-never-noreg": (True, "실행된 적 없음 · 예정도 없음"),
    "x-quiet": (False, "정상"), "x-first": (False, "아직 때가 안 됨"), "x-normal": (False, "정상"),
    "x-running": (False, "실행 중"), "x-waiting": (False, "아직 때가 안 됨"),
}


def check_verdicts(rows: dict[str, dict]) -> None:
    for n, (broken, label) in EXPECTED_VERDICT.items():
        v = rows[n].get("verdict")
        assert v == {"broken": broken, "label": label}, (n, v)
    for n in STOPPED:                                          # QA-OPS4-4 — 결과 0 인데 고장
        assert rows[n]["verdict"]["broken"] is True, n


def check_order(silence: dict[str, dict], rows: list[dict]) -> None:
    """고장 행의 silence 는 '판정 없음'(SILENCE_NONE) — task_eval 과 같은 순서. 한 행이 두 경보가 아니다."""
    for r in rows:
        broken, _ = rt.schedule_verdict(r)
        sv = silence[r["name"]]
        assert not (broken and sv["bad"]), r["name"]
        if broken:
            assert sv == rt.SILENCE_NONE, (r["name"], sv)


def check_counts(k: dict, rows: list[dict]) -> None:
    never = sum(1 for s in rows if s["never_ran"] and not s.get("next_run"))
    bad = sum(1 for s in rows if not s["ok"] and not s["never_ran"])
    quiet = sum(1 for s in rows if (s.get("silence") or {}).get("bad"))
    # 기존 키의 뜻은 그대로(r2 정의)
    assert (k["sched_never"], k["sched_bad"], k["sched_silent"]) == (never, bad, quiet)
    assert k["sched_pending"] == sum(1 for s in rows if s["never_ran"] and s.get("next_run")
                                     and not (s.get("silence") or {}).get("bad"))
    stopped = {s["name"] for s in rows if (s.get("verdict") or {}).get("broken")
               and not (s["never_ran"] and not s.get("next_run")) and not (not s["ok"] and not s["never_ran"])}
    assert k["sched_stopped"] == len(stopped)
    assert k["sched_alarm"] == never + bad + quiet + len(stopped)
    # 볼 것 = 순환계가 경보로 보는 작업(고장 또는 조용한 누락) — 같은 집합의 수
    assert k["sched_alarm"] == sum(1 for s in rows if s["verdict"]["broken"] or s["silence"]["bad"])


def check_purpose(p: str, label: str, quiet: bool) -> None:
    head = f"예약 작업 `"
    assert p.startswith(head) and f" — {label} · " in p, p           # 라벨을 그대로 앞에
    tail = p.split(f" — {label} · ", 1)[1]
    assert "1999" not in p, p                                          # 스케줄러의 '안 돎' 표시
    assert "시간째" not in p and "**" not in p, p                      # 주어 없는 수 · 굵은 글씨
    assert "(마지막 실행" not in p and "(다음 실행" not in p, p        # 괄호로 되풀이하지 않는다
    assert p.count("다음 실행 없음") <= 1, p                           # 라벨의 '다음 실행 없음'을 되풀이하지 않는다
    for m in re.finditer(r"\d+시간", tail):
        assert tail[:m.start()].endswith("뒤 "), p                     # 수에는 늘 '… 뒤'
    if quiet:
        assert re.fullmatch(r"다음 실행 (\d{4}-\d{2}-\d{2} \d{2}:\d{2}|없음)", tail), p
    else:
        assert re.fullmatch(r"(마지막 실행|등록|순환계가 처음 본) \d{4}-\d{2}-\d{2} \d{2}:\d{2} 뒤 \d+시간"
                            r"( · 다음 실행 \d{4}-\d{2}-\d{2} \d{2}:\d{2})?", tail), p


def _kept(out: str, s: str) -> str:
    k = out[:-1]
    for suf in (" · ", " "):
        if k.endswith(suf):
            k = k[:-len(suf)]
            break
    while not s.startswith(k) and k.endswith(("`", "**")):         # 짝 맞추려 닫은 표식
        k = k[:-2] if k.endswith("**") else k[:-1]
    return k


CLIP_CASES = [
    # r2 의 실제 모양(design-critic r2 #1 — 140자에서 '17:5' 로 끊겼다)
    ("예약 작업 `naechaget-weekly-report` — 조용히 안 돎 · 마지막 성공 09-25 15:53 · 매주 작업 한도 8일 넘김 · "
     "**226시간째**(마지막 실행 2026-09-25 15:53 · 다음 실행 2026-10-02 17:50)"),
    # 이름이 긴 조용한 누락
    ("예약 작업 `naechaget-a-very-long-scheduled-task-name-for-the-r3-test-case` — 조용히 안 돎 · 마지막 성공 09-25 15:53 · "
     "매주 작업 한도 8일 넘김 · 다음 실행 2026-10-02 17:50"),
    # 경보(⑥) 모양 — detail 이 길다
    ("경보 `케이카 교차검증`(공급) — 🛑 **2개 리포트 연속**(2026-10-26~2026-10-27): 교차검증 멈춤 · "
     "마지막 성공 2026-10-24 06:10 · 원인 후보 세 가지를 로그에서 확인할 것 · 서버 journald 기록 2026-10-27 06:10 부터 없음"),
    # ` · ` 없는 인계 사유(실제 지시서 모양) — 시각이 경계 근처
    ("§5 티켓 초안 15건과 OPS-3 범위 확장 3항을 백로그에 등록한다(무티켓 high·medium 전부). A-03 터널 감시 작업을 "
     "재기동한다. A-19 는 입찰 시각 2026-09-28 10:00 뒤 벨과 홈을 1회 대조한다. §6 오너 결정 7건을 상정한다"),
    # 앞쪽에 ` · ` 하나뿐인 긴 문장 — 거기서 자르면 읽을 게 없다(공백 경계로)
    ("정기 점검 · 7일 주기로 결재함·리듬·산출물을 훑고 볼 것이 없으면 한 줄로 닫는다. 볼 것이 있으면 무엇을 왜 봐야 "
     "하는지 근거 파일과 함께 적고 담당을 제안한다. 분량을 채우지 않는다(_handoff-protocol §3) 다음 회차에 같은 항목을 다시 본다"),
    # 시각이 한도(140) 바로 앞에 걸친 문장 — 시각 안의 공백에서 자르면 '2026-09-28' 만 남는다
    ("대조한다 " * 30)[:120] + "시각 2026-09-28 10:00 뒤 벨과 홈을 대조한다",
    # 백틱 안에서 잘릴 문장
    ("계약에 없는 인계: `frontend-engineer` → `" + "a-very-long-seat-name " * 8 + "` — 사유"),
    # 짧은 줄 — 손대지 않는다
    "예약 작업 `x` — 정상",
]


def check_clip(clip) -> None:
    for s in CLIP_CASES:
        out = clip(s)
        assert len(out) <= 140, (len(out), out)
        if len(s) <= 140:
            assert out == s
            continue
        assert out.endswith("…"), out
        k = _kept(out, s)
        assert s.startswith(k) and len(k) >= 20, (k, s)
        rest = s[len(k):]
        assert rest[:1].isspace() or rest.startswith(" · "), (k, rest[:10])    # 경계에서 잘렸다
        for m in _TS.finditer(s):
            assert m.end() <= len(k) or m.start() >= len(k), (m.group(), out)   # 시각을 가르지 않는다
        assert out.count("`") % 2 == 0 and out.count("**") % 2 == 0, out       # 마크다운 짝


def _old_purpose(t: dict) -> str:
    """r2 까지의 모양(`Org.scan` ⑦) — 변이 검사용."""
    return (f"예약 작업 `{t['name']}` — {t['label']} · **{t['hours']}시간째**"
            f"(마지막 실행 {t['last_run'] or '없음'} · 다음 실행 {t['next_run'] or '없음'})")


def _r2_counts(sched: list[dict]) -> dict:
    """r2 의 `schedule_counts` — 꺼짐·다음 실행 없음을 세지 않았다(변이 검사용)."""
    judged = all(s.get("silence") is not None for s in sched)
    quiet = {s["name"] for s in sched if (s.get("silence") or {}).get("bad")}
    never = sum(1 for s in sched if s["never_ran"] and not s.get("next_run"))
    bad = sum(1 for s in sched if not s["ok"] and not s["never_ran"])
    return {"sched_total": len(sched), "sched_never": never,
            "sched_pending": sum(1 for s in sched if s["never_ran"] and s.get("next_run") and s["name"] not in quiet),
            "sched_bad": bad, "sched_silent": len(quiet) if judged else None,
            "sched_alarm": never + bad + len(quiet)}


# ════════════════════════════════════════════════════════════════════════
# ① verdict 싣기
# ════════════════════════════════════════════════════════════════════════
def test_scene_really_hits_every_branch(scene):
    """공허 통과 방지 — 네 모양의 지시서가 모두 섰고, 대시보드 행이 각 분기에 떨어진다."""
    assert set(scene.inbox) == set(PURPOSE)
    assert {n for n, r in scene.rows.items() if r["silence"]["bad"]} == QUIET
    assert {n for n, r in scene.rows.items() if r["verdict"]["broken"]} == set(EXPECTED_VERDICT) - {
        n for n, (b, _) in EXPECTED_VERDICT.items() if not b}
    assert all(scene.rows[n]["verdict"] == {"broken": False, "label": "정상"} for n in REAL if n != MISSING)


def test_attach_verdict_carries_the_runtime_verdict_on_every_row(scene):
    check_verdicts(scene.rows)
    for r in scene.rowlist:
        assert set(r["verdict"]) == {"broken", "label"}
        assert (r["verdict"]["broken"], r["verdict"]["label"]) == rt.schedule_verdict(r)   # 순환계 결과 그대로
    assert scene.vwarns == []


def test_verdict_label_is_the_inbox_label(scene):
    """표가 칠할 글자(verdict.label · silence.label) = 결재함 목적 줄의 라벨 — 결재함에 선 모든 작업(미등록 제외)."""
    for n, p in scene.inbox.items():
        if n == MISSING:
            continue                                          # 목록에 없는 작업은 대시보드 행이 없다(§ 보고서)
        r = scene.rows[n]
        label = r["silence"]["label"] if r["silence"]["bad"] else r["verdict"]["label"]
        assert label == LABEL[n] and p.startswith(f"예약 작업 `{n}` — {label} · "), n


def test_attach_verdict_passes_the_runtime_result_through_untouched(monkeypatch):
    monkeypatch.setattr(rt, "schedule_verdict", lambda t: (True, "순환계가 정한 글자"))
    rows = [_r("a")]
    assert ad.attach_verdict(rows) == ([], None)
    assert rows[0]["verdict"] == {"broken": True, "label": "순환계가 정한 글자"}


def test_attach_verdict_unknown_is_none_not_fine(monkeypatch):
    # ⑴ 순환계를 못 불러온다 → 전부 None + 오류(화면 '못 읽은 것')
    rows = [_r("a"), _r("b", enabled=False)]
    monkeypatch.setitem(sys.modules, "org_runtime", None)
    warns, err = ad.attach_verdict(rows)
    assert err and "고장 판정을 싣지 못했다" in err and warns == []
    assert [r["verdict"] for r in rows] == [None, None]
    monkeypatch.undo()
    # ⑵ 판정 칸이 빠진 행 — `enabled` 없이 판정하면 꺼진 작업이 '정상'이 된다 → None + 경고
    partial = {k: v for k, v in _r("c", enabled=False, next_run="").items() if k != "enabled"}
    rows = [partial, _r("d")]
    warns, err = ad.attach_verdict(rows)
    assert err is None and rows[0]["verdict"] is None and rows[1]["verdict"] == {"broken": False, "label": "정상"}
    assert len(warns) == 1 and "`c`" in warns[0] and "enabled" in warns[0]
    # ⑶ 판정 함수가 한 행에서 터진다 → 그 행만 None
    def boom(t):
        if t["name"] == "e":
            raise ValueError("x")
        return (False, "정상")
    monkeypatch.setattr(rt, "schedule_verdict", boom)
    rows = [_r("e"), _r("f")]
    warns, err = ad.attach_verdict(rows)
    assert err is None and rows[0]["verdict"] is None and rows[1]["verdict"]["label"] == "정상" and len(warns) == 1
    for r in rows:
        r["silence"] = dict(rt.SILENCE_NONE)
    assert ad.schedule_counts(rows)["sched_stopped"] is None           # 모름은 0 이 아니다
    # ⑷ 빈 목록
    assert ad.attach_verdict([]) == ([], None)


def test_dashboard_has_no_copy_of_the_verdict_rule():
    """`attach_verdict`·`schedule_counts` 본문(설명 문자열 제외)에 판정 글자가 없다 — 규칙은 org_runtime 한 곳."""
    tree = ast.parse((ROOT / "tools" / "agent_dashboard.py").read_text(encoding="utf-8"))
    fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    for name in ("attach_verdict", "schedule_counts"):
        fn = fns[name]
        body = fn.body[1:] if isinstance(fn.body[0], ast.Expr) and isinstance(fn.body[0].value, ast.Constant) \
            else fn.body
        code = "\n".join(ast.unparse(b) for b in body)
        consts = [c.value for b in body for c in ast.walk(b) if isinstance(c, ast.Constant) and isinstance(c.value, str)]
        for label in ("꺼짐", "다음 실행 없음", "실패 · 결과", "실행된 적 없음", "아직 때가 안 됨"):
            assert not any(label in c for c in consts), (name, label)
        assert "enabled" not in code and "Disabled" not in code, name   # 꺼짐을 대시보드가 다시 가르지 않는다
    assert "schedule_verdict" in ast.unparse(fns["attach_verdict"])
    assert "SCHEDULE_FIELDS" in ast.unparse(fns["attach_verdict"])


def test_build_state_carries_verdict_on_rows_and_sched_stopped_in_kpi(tmp_path, monkeypatch):
    root = _root(tmp_path)
    _seed(root)
    monkeypatch.setattr(ad, "ROOT", root)
    monkeypatch.setattr(ad, "SUPPLY", root / "없음.json")
    for fn, val in (("read_schedule", ([dict(r) for r in ROWS], None)), ("read_git", ([], None)),
                    ("read_product", ({}, None)), ("read_delegation", ([], None))):
        monkeypatch.setattr(ad, fn, lambda *a, _v=val, **kw: _v)
    monkeypatch.setattr(ad, "read_artifacts", lambda: [])
    monkeypatch.setattr(ad, "scan_sessions", lambda rescan=False: (ad._empty_stats(), None))
    monkeypatch.setattr(ad, "read_agent_events", lambda: {"enabled": False, "running": [], "recent": [],
                                                          "durations": {}, "count": 0})
    s = ad.build_state()
    by = {x["name"]: x for x in s["schedule"]}
    assert by["x-disabled"]["verdict"] == {"broken": True, "label": "꺼짐(Disabled)"}
    assert by["x-no-next"]["verdict"] == {"broken": True, "label": "다음 실행 없음"}
    assert all(x["verdict"] is not None and x["silence"] is not None for x in s["schedule"])
    assert s["kpi"]["sched_stopped"] == len(STOPPED)
    json.dumps(s, ensure_ascii=False)                                 # /api/state · 스냅샷으로 나갈 수 있다


# ════════════════════════════════════════════════════════════════════════
# ② 필드 동일성 — 같은 함수 · 같은 칸 · 같은 뜻(가짜 PowerShell 출력에서 끝까지)
# ════════════════════════════════════════════════════════════════════════
def test_runtime_reads_the_same_function_as_the_dashboard(tmp_path, monkeypatch):
    sentinel = [_r("same-object")]
    monkeypatch.setattr(ad, "read_schedule", lambda: (sentinel, None))
    got, err = rt.Org(tmp_path).schedule_states()
    assert got is sentinel and err is None


def test_schedule_verdict_reads_exactly_the_schedule_fields():
    """`schedule_verdict` 가 읽는 칸 = `SCHEDULE_FIELDS`. 새 칸을 읽게 되면 목록에 더해야 이 테스트가 통과한다."""
    seen: set[str] = set()

    class Rec(dict):
        def get(self, k, d=None):
            seen.add(k)
            return super().get(k, d)

        def __getitem__(self, k):
            seen.add(k)
            return super().__getitem__(k)

    grid = [dict(never_ran=nr, running=ru, enabled=en, ok=ok, next_run=nx, last_result=lr)
            for nr in (True, False) for ru in (True, False) for en in (True, False) for ok in (True, False)
            for nx in ("", "2026-10-29 00:05") for lr in ("0", "1")]
    for g in grid:
        rt.schedule_verdict(Rec(g))
    assert seen == set(rt.SCHEDULE_FIELDS)


def _ps_ms(d: datetime) -> str:
    return f"/Date({int(d.timestamp() * 1000)})/"


def test_powershell_rows_carry_the_verdict_fields_with_the_same_meaning_end_to_end(tmp_path, monkeypatch):
    """PowerShell 출력 → `read_schedule` → (대시보드 `attach_verdict` · 순환계 `task_eval`) 두 읽기가 같은 판정.
    꺼진 작업은 `enabled` False 로, 다음 실행이 없으면 `next_run` '' 로 와야 한다 — 아니면 꺼진 작업이 '정상'이다."""
    daily = ('<Triggers xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><CalendarTrigger>'
             '<StartBoundary>2026-08-01T09:00:00</StartBoundary><ScheduleByDay><DaysInterval>1</DaysInterval>'
             '</ScheduleByDay></CalendarTrigger></Triggers>')
    base = {"Registered": "2026-08-01T09:00:00", "Triggers": daily, "TriggerError": None}
    data = [
        dict(base, TaskName="ps-disabled", State="Disabled", LastRunTime=_ps_ms(NOW - timedelta(hours=72)),
             LastTaskResult=0, NextRunTime=None),
        dict(base, TaskName="ps-no-next", State="Ready", LastRunTime=_ps_ms(NOW - timedelta(hours=30)),
             LastTaskResult=0, NextRunTime=None),
        dict(base, TaskName="ps-failed", State="Ready", LastRunTime=_ps_ms(NOW - timedelta(hours=3)),
             LastTaskResult=1, NextRunTime=_ps_ms(NOW + timedelta(hours=21))),
        dict(base, TaskName="ps-running", State="Running", LastRunTime=_ps_ms(NOW - timedelta(minutes=1)),
             LastTaskResult=267009, NextRunTime=_ps_ms(NOW + timedelta(hours=23))),
        dict(base, TaskName="ps-never", State="Ready", LastRunTime=_ps_ms(datetime(1999, 11, 30)),
             LastTaskResult=267011, NextRunTime=None),
        dict(base, TaskName="ps-fine", State="Ready", LastRunTime=_ps_ms(NOW - timedelta(hours=2)),
             LastTaskResult=0, NextRunTime=_ps_ms(NOW + timedelta(hours=22))),
    ]
    out = json.dumps(data).encode("utf-8")
    monkeypatch.setattr(ad.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=out))
    rows, err = ad.read_schedule()
    assert err is None and len(rows) == len(data)
    for r in rows:
        assert set(rt.SCHEDULE_FIELDS) <= set(r), r["name"]
    by = {r["name"]: r for r in rows}
    assert by["ps-disabled"]["enabled"] is False and by["ps-disabled"]["ok"] is True
    assert by["ps-no-next"]["next_run"] == "" and by["ps-never"]["never_ran"] is True
    assert by["ps-running"]["running"] is True and by["ps-failed"]["last_result"] == "1"
    ad.attach_verdict(rows)
    dash = {r["name"]: r["verdict"] for r in rows}
    assert dash["ps-disabled"] == {"broken": True, "label": "꺼짐(Disabled)"}
    assert dash["ps-no-next"] == {"broken": True, "label": "다음 실행 없음"}
    assert dash["ps-never"] == {"broken": True, "label": "실행된 적 없음 · 예정도 없음"}
    assert dash["ps-failed"]["broken"] and dash["ps-running"] == {"broken": False, "label": "실행 중"}
    assert dash["ps-fine"] == {"broken": False, "label": "정상"}
    # 같은 PowerShell 출력을 순환계가 읽는다(`schedule_states` → `read_schedule` — 가로채지 않는다)
    root = _root(tmp_path)
    (root / "data" / "org-state.json").write_text(json.dumps({"reports": {}, "task_bad": {
        n: BAD_SINCE for n in dash}}), encoding="utf-8")
    o = _org(root, monkeypatch)
    res = o.scan(now=NOW)
    runtime = {t["name"]: t["label"] for t in res["tasks"] if t["name"] in dash}   # 표(§3.1) 이름은 '미등록'으로 따로 선다
    assert runtime == {n: v["label"] for n, v in dash.items() if v["broken"]}


# ════════════════════════════════════════════════════════════════════════
# ③ 겹침 없음 · 같은 순서
# ════════════════════════════════════════════════════════════════════════
def _grid() -> list[dict]:
    out = []
    for nr in (True, False):
        for ru in (True, False):
            for en in (True, False):
                for ok in (True, False):
                    for nx in ("", _f(NOW + timedelta(hours=3))):
                        for old in (True, False):
                            for te in ("", "트리거를 못 읽음"):
                                out.append(_r(f"g-{len(out)}", never_ran=nr, running=ru, enabled=en, ok=ok,
                                              next_run=nx, last_result="0" if ok else "1",
                                              last_run=NEVER if nr else _f(NOW - timedelta(hours=60 if old else 2)),
                                              registered=_f(NOW - timedelta(days=5)), trigger_error=te))
    return out


def test_verdict_and_silence_never_both_alarm_and_silence_rows_follow_task_eval_order(tmp_path):
    root = _root(tmp_path)
    rows = _grid()
    sil = rt.Org(root).silence_rows(rows, NOW)
    check_order(sil, rows)
    settings = rt.Org(root).contracts()[0]
    for r in rows:
        v, sv = rt.judge_task(r, NOW, settings, NOW.isoformat())
        assert sv == sil[r["name"]] and (v["broken"], v["label"]) == rt.schedule_verdict(r)


def test_trigger_warning_comes_from_the_same_rows_on_both_sides(tmp_path, monkeypatch):
    """고장 행의 트리거 경고는 어디서도 안 나오고, 정상 행의 경고는 스탠드업과 대시보드에 같은 글자로 나온다."""
    rows = [_r("t-failed", ok=False, last_result="1", trigger_error="거부"),
            _r("t-disabled", enabled=False, status="Disabled", next_run="", trigger_error="거부"),
            _r("t-fine", trigger_error="거부")]
    root = _root(tmp_path)
    o = _org(root, monkeypatch, rows)
    res = o.scan(now=NOW)
    runtime = [w for w in res["warnings"] if "트리거를 읽지 못했다" in w]
    monkeypatch.setattr(ad, "ROOT", root)
    sched = [dict(r) for r in rows]
    dash, err = ad.attach_silence(sched, NOW)
    assert err is None and dash == runtime and len(dash) == 1 and "`t-fine`" in dash[0]


# ════════════════════════════════════════════════════════════════════════
# ④ KPI
# ════════════════════════════════════════════════════════════════════════
def test_counts_add_sched_stopped_and_fold_it_into_alarm(scene):
    k = ad.schedule_counts(scene.rowlist)
    check_counts(k, scene.rowlist)
    assert k["sched_stopped"] == len(STOPPED) == 2
    # 대시보드 '볼 것' = 결재함 예약 작업 경보 지시서(목록에 없는 '미등록'만 빼고)
    assert k["sched_alarm"] == len(set(scene.inbox) - {MISSING}) == 8


def test_disabled_and_failed_row_is_counted_once_as_failed():
    rows = [_r("df", status="Disabled", enabled=False, ok=False, last_result="1", next_run="")]
    ad.attach_verdict(rows)
    rows[0]["silence"] = dict(rt.SILENCE_NONE)
    k = ad.schedule_counts(rows)
    assert rows[0]["verdict"]["label"] == "꺼짐(Disabled)"
    assert (k["sched_bad"], k["sched_stopped"], k["sched_alarm"]) == (1, 0, 1)


# ════════════════════════════════════════════════════════════════════════
# ⑤ 결재함 목적 줄 · 경계 자르기
# ════════════════════════════════════════════════════════════════════════
def test_purpose_lines_have_the_four_shapes(scene):
    for n, want in PURPOSE.items():
        assert scene.inbox[n] == want, (n, scene.inbox[n])
        check_purpose(scene.inbox[n], LABEL[n], n in QUIET)


def test_purpose_lines_fit_in_the_inbox_without_cutting(scene):
    """이 이름 길이에서는 목적 줄이 결재함 목록 한도 안이다(자를 일이 없다) — 목록에 온전히 선다."""
    b = rt.Org(scene.root).board(now=NOW)
    listed = {o["id"]: o["purpose"] for o in b["inbox"] if o["reason"] == "task"}
    assert sorted(listed.values()) == sorted(scene.inbox.values())


def test_clip_line_cuts_at_a_boundary_and_marks_it():
    check_clip(rt.clip_line)
    first = rt.clip_line(CLIP_CASES[0])
    assert first.endswith(" · …") and "17:5" not in first            # r2 에서 '17:5' 로 끊기던 줄
    assert rt.clip_line(CLIP_CASES[3]).endswith(" …")                # ` · ` 없는 문장 → 공백 경계
    blob = "x" * 60 + "1234567890" * 10
    out = rt.clip_line(blob)
    assert len(out) <= 140 and out.endswith("…") and not out[-2].isdigit()   # 숫자 사이에서 자르지 않는다


def test_board_clips_every_reason_and_never_rewrites_an_open_order(tmp_path, monkeypatch):
    """결재함 목록의 자르기는 사유와 무관하다. 이미 열린 지시서 파일은 다시 쓰지 않는다(목록에서만 자른다)."""
    root = _root(tmp_path)
    o = _org(root, monkeypatch, [])
    orders = o.orders()
    for reason, text in zip(("task", "alert", "handoff", "routine", "owner", "manual"), CLIP_CASES):
        o.create_order(orders, to=rt.STEWARD, frm="org-runtime", reason=reason, purpose=text, now=NOW)
    before = {p.name: hashlib.md5(p.read_bytes()).hexdigest() for p in (root / "orders").glob("*.md")}
    b = rt.Org(root).board(now=NOW)
    got = {x["reason"]: x["purpose"] for x in b["inbox"]}
    for reason, text in zip(("task", "alert", "handoff", "routine", "owner", "manual"), CLIP_CASES):
        assert got[reason] == rt.clip_line(text), reason
    # r2 의 열린 task 지시서(옛 모양)도 목록에선 경계에서 잘린다 — 파일은 그대로
    assert got["task"].endswith(" · …") and "17:5" not in got["task"]
    o2 = _org(root, monkeypatch, [])
    o2.scan(now=NOW + timedelta(hours=1))
    after = {p.name: hashlib.md5(p.read_bytes()).hexdigest() for p in (root / "orders").glob("*.md")}
    assert {k: after[k] for k in before} == before


def test_documents_say_the_dashboard_now_carries_the_same_verdict():
    c = (ROOT / "docs" / "org-contracts.md").read_text(encoding="utf-8")
    s3 = c[c.index("## 3."):c.index("### 3.1")]
    doc = rt.schedule_verdict.__doc__
    for text in (s3, doc):
        assert "결과가 0 이면 정상으로 칠한다" not in text              # r3 전의 괄호
        assert "대시보드에 없는 규칙" not in text and "대시보드에 **없는**" not in text
    assert "`verdict`" in s3 and "sched_stopped" in s3 and "attach_verdict" in s3 and "2026-09-27-75" in s3
    assert "attach_verdict" in doc and "sched_stopped" in doc and "그대로 칠한다" in doc


# ════════════════════════════════════════════════════════════════════════
# ⑥ 변이 검사 — 옛 동작을 넣으면 위 검사 함수가 빨개진다
# ════════════════════════════════════════════════════════════════════════
def test_mutation_old_purpose_shape_is_caught(scene):
    caught = 0
    for n, t in scene.tasks.items():
        if n not in PURPOSE:
            continue
        with pytest.raises(AssertionError):
            check_purpose(_old_purpose(t), LABEL[n], n in QUIET)
        caught += 1
    assert caught == len(PURPOSE)


def test_1999_never_appears_even_without_the_never_ran_flag(scene):
    """두 겹: `never_ran` 을 보고, 그 칸이 빠져도 2000년 전 시각(스케줄러의 '안 돎' 표시)은 실행으로 치지 않는다."""
    t = dict(scene.tasks["x-never-reg"], never_ran=False)
    p = rt.task_purpose(t, NOW)
    assert p == PURPOSE["x-never-reg"]
    check_purpose(p, LABEL["x-never-reg"], False)
    old = _old_purpose(scene.tasks["x-never-reg"])                    # r2 모양에는 1999 가 그대로 섰다
    assert "1999-11-30" in old
    with pytest.raises(AssertionError):
        check_purpose(old, LABEL["x-never-reg"], False)


def test_mutation_repeated_no_next_run_is_caught(scene):
    t = scene.tasks["x-dead"]
    with pytest.raises(AssertionError):
        check_purpose(rt.task_purpose(t, NOW) + " · 다음 실행 없음", LABEL["x-dead"], False)


def test_mutation_raw_slice_is_caught():
    with pytest.raises(AssertionError):
        check_clip(lambda s: s[:140])


def test_mutation_verdict_missing_or_filled_as_fine_is_caught(scene):
    none = {n: {k: v for k, v in r.items() if k != "verdict"} for n, r in scene.rows.items()}
    with pytest.raises(AssertionError):
        check_verdicts(none)
    fine = {n: dict(r, verdict={"broken": False, "label": "정상"}) for n, r in scene.rows.items()}
    with pytest.raises(AssertionError):
        check_verdicts(fine)
    ok_only = {n: dict(r, verdict={"broken": not r["ok"] and not r["never_ran"],
                                   "label": "정상" if r["ok"] else "실패"}) for n, r in scene.rows.items()}
    with pytest.raises(AssertionError):                               # 대시보드 옛 칩 규칙(`ok` 만 본다)
        check_verdicts(ok_only)


def test_mutation_r2_counts_are_caught(scene):
    with pytest.raises((AssertionError, KeyError)):
        check_counts(_r2_counts(scene.rowlist), scene.rowlist)


def test_mutation_old_silence_order_is_caught(tmp_path):
    root = _root(tmp_path)
    rows = _grid()
    settings = rt.Org(root).contracts()[0]
    old = {r["name"]: rt.silence_verdict(r, NOW, settings, NOW.isoformat()) for r in rows}   # r2 `silence_rows`
    with pytest.raises(AssertionError):
        check_order(old, rows)
