# -*- coding: utf-8 -*-
"""OPS-4 r3 재검증(qa-engineer, 지시서 2026-09-27-76) — 결과는 `reports/2026-09-27-ops4-qa-r3.md`.

① 표 ↔ 결재함 일치 행렬(양방향). 임시 루트에서 **매시 실제 `scan()`** 을 49번(0~48시간) 돌리고, 같은 시각·같은 루트를
   대시보드 경로 그대로(`attach_verdict` → `attach_silence` → 실제 HTML `schedState`) 읽어 맞댄다.
   상태: 꺼짐 · 꺼짐+실패 · 다음 실행 없음 · 실패 · 실행된 적 없음 · 아직 때가 안 됨 → 첫 실행 없음 · 조용히 안 돎 ·
   실행 중 · 정상 · 판정 불가(트리거 못 읽음) · 회복 · 열린 티켓 뒤 고장(터널).
   - 결재함이 경보하는 순간(`task_eval` action 이 `order`) 표는 초록·대기가 아니고, 칩 + 사유 = 그 지시서의 라벨.
   - 표가 초록·대기·확인 불가면 그 시각 순환계는 그 작업을 경보 후보로도 보지 않는다(`task_eval` 결과에 없다).
   - 빨강 ⟺ 순환계 고장, 주황 ⟺ 순환계 조용한 누락(같은 시각). 타일 '볼 것'(sched_alarm) = 순환계 경보 후보 수.
   - 판정 불가(행에 verdict·silence 를 못 실음) 세 모양에서 표는 초록·대기로 칠하지 않는다(실행 중만 예외 — 아래).
   - 관찰(결함 아님, 계약 §3 '대가'): 작업이 회복하면 표는 초록인데 지시서는 열린 채 남는다 — 그 모양을 따로 못 박는다.
② 결재함 목적 줄(`task_purpose` → `clip_line`) — 네 모양 × 이름 길이 × 결과 값 격자에서 1999 없음 · '다음 실행 없음'
   한 번 · 140자 경계는 ' · ' 또는 낱말 경계 + '…' · 숫자·시각 중간을 자르지 않음. alert·routine·인계 사유 목록도.
③ 옛 칩 규칙 사본이 테스트에 다시 생기지 않는다(`_dashboard_pill`·`_dashboard_class` 는 실제 `schedState` 로 바뀌었다).

운영 orders/·data/ 에 쓰지 않는다(전부 tmp_path). 블록은 앵커 문자열로 자른다(CLAUDE.md 운영 규칙 8).
"""
from __future__ import annotations

import ast
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
import _schedstate_js as sj  # noqa: E402
import agent_dashboard as ad  # noqa: E402
import org_runtime as rt  # noqa: E402
import test_ops4_qa_adversarial as q1  # noqa: E402

DAY = 86400
NEVER = "1999-11-30 00:00"
T0 = datetime(2026, 10, 28, 0, 5)            # 매시 :05 스캔
HOURS = range(0, 49)


def _f(d: datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M")


def _r(name, **kw):
    t = {"name": name, "status": "Ready", "running": False, "last_run": "", "last_result": "0", "next_run": "",
         "enabled": True, "never_ran": False, "ok": True, "period_s": DAY, "first_start": _f(T0 - timedelta(days=30)),
         "registered": "", "trigger_error": ""}
    t.update(kw)
    return t


def _normal(name, now, **kw):
    return _r(name, last_run=_f(now - timedelta(hours=2)), next_run=_f(now + timedelta(hours=22)), **kw)


def _recover(now):
    """조용히 안 돎(h6 경보) → h10 에 따라잡아 성공 — 표는 초록, 지시서는 열린 채(계약 §3 '대가')."""
    if now < T0 + timedelta(hours=10):
        return _r("q-recover", last_run=_f(T0 - timedelta(hours=30)), next_run=_f(T0 + timedelta(hours=100)))
    return _normal("q-recover", now)


# 행 = 시각의 함수(돌아가는 작업은 시간이 가면 마지막 실행이 따라온다). 이름은 §3.1 에 없는 것 → steward · 티켓 없음.
SCEN = {
    "q-disabled": lambda now: _r("q-disabled", status="Disabled", enabled=False, last_run=_f(T0 - timedelta(days=3))),
    "q-disabled-failed": lambda now: _r("q-disabled-failed", status="Disabled", enabled=False, ok=False,
                                        last_result="1", last_run=_f(T0 - timedelta(days=3))),
    "q-no-next": lambda now: _r("q-no-next", last_run=_f(T0 - timedelta(hours=10))),
    "q-failed": lambda now: _r("q-failed", ok=False, last_result="1", last_run=_f(T0 - timedelta(hours=2)),
                               next_run=_f(T0 + timedelta(hours=22))),
    "q-never-no-next": lambda now: _r("q-never-no-next", never_ran=True, ok=False, last_result="267011",
                                      last_run=NEVER),
    "q-pending": lambda now: _r("q-pending", never_ran=True, ok=False, last_result="267011", last_run=NEVER,
                                next_run=_f(T0 + timedelta(hours=100)), registered=_f(T0 - timedelta(hours=1)),
                                first_start=_f(T0 - timedelta(hours=1))),
    "q-quiet": lambda now: _r("q-quiet", last_run=_f(T0 - timedelta(hours=20)),
                              next_run=_f(T0 + timedelta(hours=100))),
    "q-running": lambda now: _r("q-running", period_s=60, status="Running", running=True, last_result="267009",
                                last_run=_f(now - timedelta(minutes=1)), next_run=_f(now + timedelta(minutes=1))),
    "q-normal": lambda now: _normal("q-normal", now),
    "q-unknown": lambda now: _normal("q-unknown", now, period_s=None, first_start="",
                                     trigger_error="QA 픽스처 — 트리거를 못 읽음"),
    "q-recover": _recover,
}
REAL = [n for n, r in rt.Org(ROOT).alert_routes().items() if r["source"] == "예약 작업"]
# 결재함에 지시서가 서는 첫 시각(T0 뒤 시간) — 규칙 함수가 아니라 계약 §1·§3 문장으로 따로 계산했다
# (예약 작업 실패 지속 24시간 · 매일 작업 성공 없음 한도 36시간 — 조용한 누락은 한도가 곧 지속이라 더 기다리지 않는다).
EXPECT_ORDER_AT = {
    "q-disabled": 24, "q-disabled-failed": 24,       # 처음 본 T0 + 24
    "q-no-next": 14, "q-failed": 22,                 # 마지막 실행(T0-10h · T0-2h) + 24
    "q-never-no-next": 24,                           # 처음 본 T0 + 24
    "q-pending": 35,                                 # 등록 T0-1h + 36
    "q-quiet": 16, "q-recover": 6,                   # 마지막 성공(T0-20h · T0-30h) + 36
}
EXPECT_LABEL = {
    "q-disabled": "꺼짐(Disabled)", "q-disabled-failed": "꺼짐(Disabled)", "q-no-next": "다음 실행 없음",
    "q-failed": "실패 · 결과 1(0x00000001)", "q-never-no-next": "실행된 적 없음 · 예정도 없음",
}


def _rows(now):
    tunnel = _r("naechaget-home-tunnel", period_s=None, first_start="", last_run="2026-09-16 05:24",
                last_result="3221225477", ok=False)
    real = [tunnel if n == "naechaget-home-tunnel" else _normal(n, now) for n in REAL]
    return [f(now) for f in SCEN.values()] + real


def _root(base: Path) -> Path:
    root = base / "matrix"
    (root / "docs" / "daily-reports").mkdir(parents=True)
    (root / "reports").mkdir()
    (root / "data").mkdir()
    shutil.copy(ROOT / "docs" / "org-contracts.md", root / "docs" / "org-contracts.md")
    (root / "docs" / "backlog.md").write_text(q1.BACKLOG, encoding="utf-8")      # AUD-05(터널) 열림
    return root


def _chip_words(x: dict) -> str:
    return x["text"] + (" · " + x["sub"] if x["sub"] else "")


def run_matrix(pg, root: Path, hours=HOURS, rows_of=_rows) -> list[dict]:
    """매시 scan() → 같은 시각 대시보드 행 → 실제 schedState. 시각마다 한 줄 기록을 돌려준다(단언은 부르는 쪽)."""
    log = []
    old_root = ad.ROOT
    ad.ROOT = root
    try:
        for h in hours:
            now = T0 + timedelta(hours=h)
            rows = rows_of(now)
            o = rt.Org(root)
            o.rhythm_states = lambda: []
            o.schedule_states = lambda rows=rows: ([dict(r) for r in rows], None)
            r = o.scan(now=now)
            tasks = {t["name"]: t for t in r["tasks"]}
            inbox = {}
            for x in rt.Org(root).orders().values():
                m = x["meta"]
                if m["reason"] == "task" and m["status"] in rt.OPEN_STATES:
                    inbox[m["key"].split(":")[1]] = x["body"].split("## 목적", 1)[-1].strip().splitlines()[0]
            main = [dict(x) for x in rows]
            vw, ve = ad.attach_verdict(main)
            _, se = ad.attach_silence(main, now)
            assert ve is None and se is None and not vw
            v_null = [dict(x, verdict=None) for x in main]                     # 판정 불가 ⑴ 고장 판정 못 실음
            both_null = [dict(x, verdict=None, silence=None) for x in main]     # ⑵ 둘 다 못 실음
            s_null = [dict(x, silence=None) for x in main]                      # ⑶ 조용한 누락만 못 실음
            n = len(main)
            names = [x["name"] for x in main]
            st = sj.states(pg, main + v_null + both_null + s_null)
            log.append({"h": h, "now": now, "tasks": tasks, "inbox": inbox, "rows": main,
                        "kpi": ad.schedule_counts(main),
                        "main": dict(zip(names, st[:n])), "v_null": dict(zip(names, st[n:2 * n])),
                        "both_null": dict(zip(names, st[2 * n:3 * n])), "s_null": dict(zip(names, st[3 * n:]))})
    finally:
        ad.ROOT = old_root
    return log


@pytest.fixture(scope="module")
def pg():
    with sj.page() as p:
        yield p


@pytest.fixture(scope="module")
def matrix(pg, tmp_path_factory):
    return run_matrix(pg, _root(tmp_path_factory.mktemp("ops4r3qa")))


def test_matrix_is_not_vacuous(matrix):
    """공허 통과 방지 — 경보 여덟이 계산한 시각에 **처음** 서고, 각 상태의 칩이 실제로 그려졌다."""
    first = {}
    for e in matrix:
        for n, t in e["tasks"].items():
            if t["action"] == "order":
                first.setdefault(n, e["h"])
    assert first == EXPECT_ORDER_AT
    seen = {(n, x["pill"]) for e in matrix for n, x in e["main"].items() if n.startswith("q-")}
    for want in [("q-disabled", "bad"), ("q-disabled-failed", "bad"), ("q-no-next", "bad"), ("q-failed", "bad"),
                 ("q-never-no-next", "bad"), ("q-pending", "idle"), ("q-pending", "warn"), ("q-quiet", "ok"),
                 ("q-quiet", "warn"), ("q-running", "ok"), ("q-normal", "ok"), ("q-unknown", "mute"),
                 ("q-recover", "warn"), ("q-recover", "ok")]:
        assert want in seen, want
    assert all(e["tasks"]["naechaget-home-tunnel"]["action"] == "ticket-open" for e in matrix)


def test_when_the_inbox_alarms_the_table_is_not_green_and_says_the_same_words(matrix):
    """결재함 → 표: 지시서가 서는 순간 칩은 빨강·주황이고, 칩 + 사유 = 그 지시서 목적 줄의 라벨(글자까지)."""
    hits = 0
    for e in matrix:
        for n, t in e["tasks"].items():
            if t["action"] != "order":
                continue
            hits += 1
            x = e["main"][n]
            assert x["pill"] == ("warn" if t["quiet"] else "bad"), (e["h"], n, x)
            assert _chip_words(x) == t["label"], (e["h"], n, x, t["label"])
            assert e["inbox"][n].startswith(f"예약 작업 `{n}` — {t['label']}"), (e["h"], n)
            if n in EXPECT_LABEL:
                assert t["label"] == EXPECT_LABEL[n]
    assert hits == len(EXPECT_ORDER_AT)


def test_when_the_table_is_green_or_waiting_the_runtime_sees_no_alarm(matrix):
    """표 → 결재함: 초록(ok)·대기(idle)·확인 불가(mute)인 작업은 같은 시각 순환계의 경보 후보(`task_eval` 결과)에 없다."""
    n_calm = 0
    for e in matrix:
        for n, x in e["main"].items():
            if x["pill"] in ("ok", "idle", "mute"):
                n_calm += 1
                assert n not in e["tasks"], (e["h"], n, x, e["tasks"].get(n))
    assert n_calm > 300


def test_red_is_runtime_broken_and_orange_is_runtime_quiet_at_every_hour(matrix):
    """같은 시각 빨강 ⟺ 순환계 고장, 주황 ⟺ 순환계 조용한 누락. 타일 '볼 것' = 순환계 경보 후보 수(미등록 없음)."""
    for e in matrix:
        red = {n for n, x in e["main"].items() if x["pill"] == "bad"}
        orange = {n for n, x in e["main"].items() if x["pill"] == "warn"}
        assert red == {n for n, t in e["tasks"].items() if not t["quiet"]}, e["h"]
        assert orange == {n for n, t in e["tasks"].items() if t["quiet"]}, e["h"]
        assert {n for n, x in e["main"].items() if x["alarm"]} == orange, e["h"]
        assert {n for n, x in e["main"].items() if x["row"] == "bad"} == red, e["h"]
        assert {n for n, x in e["main"].items() if x["row"] == "late"} == orange, e["h"]
        assert e["kpi"]["sched_alarm"] == len(e["tasks"]), e["h"]
        assert e["kpi"]["sched_stopped"] == len({"q-disabled", "q-no-next"}), e["h"]   # 꺼짐+실패는 sched_bad


def test_unknown_verdict_or_silence_is_never_painted_green_or_waiting(matrix):
    """판정 불가 세 모양 — ⑴ verdict 없음 ⑵ 둘 다 없음 ⑶ silence 없음. 초록·대기는 ⑶ 의 '실행 중' 하나뿐이다
    (순환계 판정이 '실행 중'이고 조용한 누락은 실행 중인 작업을 보지 않는다 — frontend r3 §2 ⓐ③)."""
    for e in matrix:
        for var in ("v_null", "both_null", "s_null"):
            for n, x in e[var].items():
                if x["pill"] in ("ok", "idle"):
                    assert (var, x["pill"], x["text"]) == ("s_null", "ok", "실행 중"), (e["h"], var, n, x)
                    assert n not in e["tasks"]
                t = e["tasks"].get(n)
                if t and t["action"] == "order":
                    assert x["pill"] in ("bad", "warn", "mute"), (e["h"], var, n, x)
        # ⑴ 에서 silence 가 경보면 주황 그대로(frontend r3 §2 '다르게 읽은 곳 1') — 결재함 경보가 표에서 사라지지 않는다
        for n, t in e["tasks"].items():
            if t["quiet"]:
                assert e["v_null"][n]["pill"] == "warn", (e["h"], n)


def test_recovered_task_is_green_while_its_order_stays_open_by_design(matrix):
    """관찰(결함 아님) — 계약 §3 '대가': 회복 뒤 지시서는 자동으로 닫히지 않는다. 표는 초록, 결재함에는 열린 한 장.
    이 모양이 바뀌면(자동으로 닫게 되면) 이 테스트가 알려 준다 — 그때 계약 문단과 함께 고친다."""
    after = [e for e in matrix if e["h"] >= 10]
    assert all(e["main"]["q-recover"]["pill"] == "ok" for e in after)
    assert all("q-recover" in e["inbox"] and "q-recover" not in e["tasks"] for e in after)
    assert [e["h"] for e in matrix if e["main"]["q-recover"]["pill"] == "warn"] == [6, 7, 8, 9]


# ════════════════════════════════════════════════════════════════════════
# ② 결재함 목적 줄 — 네 모양 격자
# ════════════════════════════════════════════════════════════════════════
NOW = datetime(2026, 10, 28, 10, 5)
_TS = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}|\d{2}-\d{2} \d{2}:\d{2}")
NAMES = ["x", "naechaget-weekly-report", "NaechaGet-PhotoClassify-" + "long" * 8,
         "naechaget-" + "a" * 60, "작업 이름에 공백이 있는 아주 긴 예약 작업 하나 둘 셋 넷 다섯"]
RESULTS = ["1", "3221225477", "-2147024894", "267014"]


def _shapes(name: str, res: str) -> dict[str, dict]:
    """네 모양(조용히 안 돎·첫 실행 없음·실패/다음 실행 없음·꺼짐) + 실패(다음 실행 있음)·실행된 적 없음 — task_eval 한 줄 모양."""
    s = rt.Org(ROOT).contracts()[0]
    seen = (NOW - timedelta(hours=40)).isoformat()                               # task_seen — 등록 날짜 없는 첫 실행 기준
    rows = {
        "quiet": _r(name, last_run=_f(NOW - timedelta(hours=50)), next_run=_f(NOW + timedelta(hours=10))),
        "first": _r(name, period_s=31 * DAY, never_ran=True, ok=False, last_result="267011", last_run=NEVER,
                    next_run=_f(NOW + timedelta(days=4)), registered=_f(NOW - timedelta(days=40)),
                    first_start=_f(NOW - timedelta(days=45))),
        "first-seen-only": _r(name, never_ran=True, ok=False, last_result="267011", last_run=NEVER,
                              next_run=_f(NOW + timedelta(hours=10)), first_start=_f(NOW - timedelta(days=3))),
        "fail-no-next": _r(name, ok=False, last_result=res, last_run="2026-10-16 05:24"),
        "fail-next": _r(name, ok=False, last_result=res, last_run=_f(NOW - timedelta(hours=1)),
                        next_run=_f(NOW + timedelta(hours=1))),
        "no-next": _r(name, last_run=_f(NOW - timedelta(hours=30))),
        "disabled": _r(name, status="Disabled", enabled=False, last_run=_f(NOW - timedelta(days=3))),
        "disabled-never": _r(name, status="Disabled", enabled=False, never_ran=True, ok=False,
                             last_result="267011", last_run=NEVER),
        "never-no-next": _r(name, never_ran=True, ok=False, last_result="267011", last_run=NEVER,
                            registered=_f(NOW - timedelta(days=5))),
    }
    out = {}
    for k, t in rows.items():
        v, sv = rt.judge_task(t, NOW, s, seen)
        assert v["broken"] or sv["bad"], k
        label = sv["label"] if sv["bad"] else v["label"]
        out[k] = dict(t, label=label, quiet=bool(sv["bad"]), since=seen)
    return out


def _clip_ok(line: str, clipped: str) -> None:
    lim = rt.PURPOSE_CLIP
    assert len(clipped) <= lim
    if len(line) <= lim:
        assert clipped == line
        return
    assert clipped.endswith("…"), clipped
    body = clipped[:-1].rstrip()
    body = body[:-2] if body.endswith(" ·") else body
    kept = body
    while kept and not line.startswith(kept):                  # clip_line 이 닫아 준 ** · ` 는 원문에 없다
        assert kept[-1] in "*`", (line, clipped)
        kept = kept[:-1]
    assert kept and line.startswith(kept), (line, clipped)
    j = len(kept)
    # 자른 자리 — 숫자 사이가 아니고, 시각 안이 아니다
    assert not (kept[-1:].isdigit() and line[j:j + 1].isdigit()), (line, clipped)
    for m in _TS.finditer(line):
        assert not (m.start() < j < m.end()), (m.group(), clipped)
    # ' · ' 가 뒤쪽 절반(자른 뒤에도 한도 안에 들 자리)에 있으면 그 경계에서 잘린다('단위 · …')
    if line.rfind(" · ", lim // 2, lim - 4) >= 0:
        assert clipped.endswith(" · …"), clipped


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("res", RESULTS)
def test_purpose_line_grid_no_1999_no_repeat_and_clean_clip(name, res):
    for k, t in _shapes(name, res).items():
        line = rt.task_purpose(t, NOW)
        assert "1999" not in line, (k, line)
        assert line.count("다음 실행 없음") <= 1, (k, line)
        assert line.count("다음 실행") <= 1, (k, line)
        assert "시간째" not in line and "(마지막 실행" not in line, (k, line)
        assert line.startswith(f"예약 작업 `{name}` — {t['label']}"), (k, line)
        if not t["quiet"]:
            assert re.search(r" · (마지막 실행|등록|순환계가 처음 본) \d{4}-\d{2}-\d{2} \d{2}:\d{2} 뒤 \d+시간", line), (k, line)
        _clip_ok(line, rt.clip_line(line))


def test_board_lists_every_reason_clipped_at_a_boundary(tmp_path):
    """결재함 목록(`Org.board` open·inbox) — task·alert·routine·handoff·manual 사유의 긴 목적 줄이 경계에서 '…'.
    manual 은 시각이 한도에 걸친 줄이다(시각 안 공백이 한도 안 마지막 공백) — 시각을 가르지 않고 그 앞 공백에서 자른다."""
    root = tmp_path / "b"
    (root / "docs").mkdir(parents=True)
    (root / "data").mkdir()
    shutil.copy(ROOT / "docs" / "org-contracts.md", root / "docs" / "org-contracts.md")
    o = rt.Org(root)
    orders: dict = {}
    long_task = rt.task_purpose(_shapes("naechaget-" + "a" * 60, "3221225477")["fail-next"], NOW)
    purposes = {
        "task": long_task,
        "alert": ("경보 `케이카 교차검증`(일일 리포트 공급 신호) — ⚠ **3개 리포트 연속**(2026-10-25~2026-10-27): "
                  "케이카 표본 0 · 마지막 성공 2026-10-24 12:00 · 표본 1234건 중 0건 일치 · 원인 미상 · 다음 리포트 "
                  "2026-10-28 12:00"),
        "routine": ("정기 점검(7일 주기) — 주간 성과 보고서가 나오면 지표 변화의 원인을 찾아 확인된 사실과 추정을 나누고 "
                    "다음 주 우선순위 세 가지를 근거와 함께 적는다 · 필요하면 실험안을 낸다 · 분량을 채우지 않는다 · "
                    "볼 것이 없으면 한 줄로 닫는다 · 지난 2026-10-21 09:05 점검과 같은 표본 1234건을 쓴다"),
        "handoff": ("`frontend-engineer` 가 넘김: 예약 작업 표의 사유 줄이 320px 에서 갈리는 문제를 app-design-expert·"
                    "design-critic 교차검수로 넘긴다 2026-10-28 09:05 캡처 기준 12345678 커밋 위에서 확인 요망 "
                    "사유 줄과 칩 글자가 결재함 라벨과 같은지 320 360 390 430 네 폭에서 함께 본다"),
    }
    # 시각이 한도에 걸친 줄(' · ' 없음) — 시각 안 공백(127+10)이 한도 안 마지막 공백이다. 시각 보호가 없으면 거기서 자른다
    pre = ("수동 지시 — 캡처를 다시 찍고 표와 결재함 글자를 맞댄다 " + "가나다 " * 40)[:125].rstrip()
    pre = pre + "라" * (126 - len(pre))                                            # 126자, 공백으로 끝나지 않는다
    purposes["manual"] = pre + " 2026-10-28 09:05 캡처 기준으로 다시 본다"
    assert purposes["manual"].index("2026-10-28 09:05") == 127 and " · " not in purposes["manual"]
    for reason, p in purposes.items():
        o.create_order(orders, to=rt.STEWARD, frm="org-runtime", purpose=p, reason=reason, key=f"{reason}:x")
    got = {x["reason"]: x["purpose"] for x in o.board(now=NOW)["inbox"]}
    assert set(got) == set(purposes)
    for reason, p in purposes.items():
        assert len(p) > rt.PURPOSE_CLIP, reason                                   # 공허 방지 — 전부 한도를 넘는다
        _clip_ok(p, got[reason])


# ════════════════════════════════════════════════════════════════════════
# ③ 옛 칩 규칙 사본이 테스트에 없다
# ════════════════════════════════════════════════════════════════════════
def test_no_copied_chip_rule_left_in_tests():
    """`s.ok` 만 보는 칩 규칙 사본(r1)이 테스트 파일에 다시 생기지 않는다 — 칩은 `_schedstate_js`(실제 JS)로 판정한다.
    찾는 것: 이름(`_dashboard_pill`·`_dashboard_class`)의 **정의**, 그리고 행의 `ok` 칸으로 'bad' 를 고르는 조건식."""
    bad = []
    for f in sorted((ROOT / "tests").glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in ("_dashboard_pill", "_dashboard_class"):
                bad.append(f"{f.name}: def {node.name}")
            if isinstance(node, ast.IfExp):
                src = ast.unparse(node)
                if re.search(r"\[['\"]ok['\"]\]", src) and re.search(r"['\"]bad['\"]", src):
                    bad.append(f"{f.name}: {src[:80]}")
    assert bad == []


# ════════════════════════════════════════════════════════════════════════
# ④ QA-OPS4-5(재현된 결함 · 낮음 · r2 부터 있던 라벨) — '첫 실행 없음' 라벨이 기준 시각을 늘 '등록'이라 부른다
# ════════════════════════════════════════════════════════════════════════
@pytest.mark.xfail(strict=True, reason=(
    "QA-OPS4-5: silence_verdict 의 '첫 실행 없음 · 등록 {기준} 뒤 …' 은 기준이 등록 날짜가 아니어도(등록 날짜가 비어 "
    "순환계가 처음 본 때 · 첫 트리거 시작이 더 늦을 때) '등록'이라 쓴다. 같은 기준을 task_purpose 는 '순환계가 처음 본'으로 "
    "쓴다 — 같은 시각이 결재함 두 모양에서 다른 말이 된다. 라벨이 기준을 제대로 부르면 XPASS — 그때 표식만 뗀다."))
@pytest.mark.parametrize("case", ["seen-only", "first-trigger-later"])
def test_first_run_missing_label_names_its_real_anchor(case):
    s = rt.Org(ROOT).contracts()[0]
    seen = NOW - timedelta(hours=40)
    if case == "seen-only":           # 등록 날짜 빈 값(실제 db-backup-pull 이 그렇다) → 기준 = 순환계가 처음 본 때
        t = _r("x-first", never_ran=True, ok=False, last_result="267011", last_run=NEVER,
               next_run=_f(NOW + timedelta(hours=10)), first_start=_f(NOW - timedelta(days=3)))
        anchor = seen
    else:                             # 등록 뒤 한참 지나 첫 트리거가 시작 → 기준 = 첫 트리거 시작
        t = _r("x-first", period_s=31 * DAY, never_ran=True, ok=False, last_result="267011", last_run=NEVER,
               next_run=_f(NOW + timedelta(days=4)), registered=_f(NOW - timedelta(days=60)),
               first_start=_f(NOW - timedelta(days=40)))
        anchor = NOW - timedelta(days=40)
    sv = rt.silence_verdict(t, NOW, s, seen.isoformat())
    assert sv["bad"] and sv["label"].startswith("첫 실행 없음 · ")                    # 공허 방지 — 경보는 선다
    assert f"{anchor:%m-%d %H:%M}" in sv["label"]                                    # 기준 시각은 맞다
    assert "등록" not in sv["label"], sv["label"]                                     # 그 시각을 '등록'이라 부르지 않는다
