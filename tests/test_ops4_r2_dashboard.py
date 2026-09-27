# -*- coding: utf-8 -*-
"""OPS-4 r2·r3(frontend) — 사내 대시보드 예약 작업 표·타일이 순환계 판정을 **그대로** 그린다.

r2(design-critic 2026-09-27 #1): 순환계가 '조용히 안 돎'·'첫 실행 없음'으로 결재함에 '예약 작업 경보'(주황)를 세운
작업이, 같은 화면 표에서는 칩 규칙이 `s.ok` 만 봐서 초록 '정상'으로 섰다. backend r2 가 행마다 `silence`
(= `org_runtime.silence_verdict`)를 실었고 화면이 그것을 따른다.
r3(QA-OPS4-4 ⓐ · design-critic r2 #2·#3): '꺼짐(Disabled)'·'다음 실행 없음'(결과 0)은 결재함이 경보하는데 표·타일은
초록이었다. backend r3 가 행마다 `verdict`(= `org_runtime.schedule_verdict` 결과 그대로)를 싣고, 화면이 그것을 따른다.

여기서는 **실제 JS**(`schedState`·`schedWhy`·`schedTile`)를 HTML 에서 앵커로 잘라 Chromium 에서 돌린다 — 문자열 대조가
아니라 동작이다. 입력 행은 대시보드가 받는 경로 그대로 판정을 붙인다(`ad.attach_verdict` → `Org.silence_rows`).

- 칩(순서): verdict 있음 — ① broken 빨강(머리 + 칩 아래 사유 = 결재함 라벨) ② silence.bad 주황(late 행 — 주황은 이것뿐)
  ③ 실행 중 초록(결재함 '진행'과 같은 ok) ④ silence null·warn 확인 불가 ⑤ 아직 때가 안 됨 무채색(결재함 '대기'와 같은
  idle, 행 클래스 없음) ⑥ 정상. verdict null — 원자료로 확실한 빨강(실행된 적 없음·예정도 없음 / 실패)과 silence.bad
  주황만, 나머지는 확인 불가(초록·대기로 칠하지 않는다).
- 사유 줄(schedWhy): 구분자 '·'는 앞 조각 안 끝 · 'MM-DD HH:MM'·조각 꼬리는 nowrap · 숫자 뒤 '(' 앞 <wbr> · 글자 불변.
- 타일: 부제는 칩 글자별 수(빨강 → 주황 → 확인 불가), 색은 서버 수 — sched_stopped(꺼짐·다음 실행 없음)도 빨강 몫.
- 어휘: 스케줄러 목록은 '예약 작업'(계약 §3.1). 피드 라벨 기본 색은 --soft.

블록은 줄 번호가 아니라 앵커 문자열로 자른다(CLAUDE.md 운영 규칙 8).
"""
from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
import agent_dashboard as ad  # noqa: E402
import org_runtime as rt  # noqa: E402

HTML_PATH = ROOT / "tools" / "agent_dashboard.html"
HTML = HTML_PATH.read_text(encoding="utf-8")


def _cut(start: str, end: str) -> str:
    """`start` 부터 그 뒤 첫 `end` 까지(끝 포함)."""
    i = HTML.index(start)
    return HTML[i:HTML.index(end, i) + len(end)]


def _js() -> str:
    """표·타일 판정에 필요한 최소 JS — esc · RSN · schedState · schedWhy · schedTile."""
    return "\n".join([
        _cut("const esc = ", "\n"),
        _cut("  {'&':'&amp;'", "\n"),
        _cut("const RSN = {", "};"),
        _cut("const schedState = s => {", "\n};"),
        _cut("const schedWhy = sub => {", "\n};"),
        _cut("function schedTile(k, rows){", "\n}\n"),
    ])


def _css() -> str:
    """실제 <style> 전부 — 사유 줄 줄바꿈을 실제 규칙으로 잰다."""
    return _cut("<style>", "</style>")


@pytest.fixture(scope="module")
def page():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:                                   # noqa: BLE001
            pytest.skip(f"chromium 없음: {e}")
        pg = b.new_page()
        pg.set_content("<!doctype html><meta charset='utf-8'>" + _css() + "<body></body>")
        pg.add_script_tag(content=_js())
        yield pg
        b.close()


def _states(page, rows):
    return page.evaluate("rows => rows.map(schedState)", rows)


def _tile(page, k, rows):
    return page.evaluate("([k, rows]) => schedTile(k, rows)", [k, rows])


# ── 행 — read_schedule 모양(가짜 값, 시각은 NOW 기준) ─────────────────────────
NOW = datetime(2026, 10, 28, 10, 0)
DAY = 86400


def _row(name, **kw):
    t = {"name": name, "status": "Ready", "running": False, "last_run": "", "last_result": "0", "next_run": "",
         "enabled": True, "never_ran": False, "ok": True, "period_s": DAY, "first_start": "2026-09-01 00:00",
         "registered": "", "trigger_error": ""}
    t.update(kw)
    return t


def _f(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


NEVER = "1999-11-30 00:00"
ROWS = [
    _row("a-normal", last_run=_f(NOW - timedelta(hours=5)), next_run=_f(NOW + timedelta(hours=19))),
    _row("b-quiet-daily", last_run=_f(NOW - timedelta(hours=50)), next_run=_f(NOW + timedelta(hours=10))),
    _row("c-quiet-weekly", period_s=7 * DAY, last_run=_f(NOW - timedelta(days=9)),
         next_run=_f(NOW + timedelta(days=2))),
    _row("d-first-run-missing", period_s=31 * DAY, never_ran=True, ok=False, last_result="267011", last_run=NEVER,
         next_run=_f(NOW + timedelta(days=4)), registered="2026-08-10 20:47", first_start="2026-08-01 13:30"),
    _row("e-waiting", never_ran=True, ok=False, last_result="267011", last_run=NEVER,
         next_run=_f(NOW + timedelta(hours=16)), registered=_f(NOW - timedelta(hours=2))),
    _row("f-running", period_s=60, status="Running", running=True, last_result="267009",
         last_run=_f(NOW - timedelta(minutes=1)), next_run=_f(NOW + timedelta(minutes=1))),
    _row("g-trigger-unreadable", period_s=None, first_start="", last_run=_f(NOW - timedelta(days=2)),
         next_run=_f(NOW + timedelta(days=5)), trigger_error="테스트 — 트리거를 못 읽음"),
    _row("h-failed", period_s=None, first_start="", last_run="2026-09-16 05:24", last_result="3221225477",
         next_run="", ok=False),
    _row("i-never-no-next", never_ran=True, ok=False, last_result="267011", last_run=NEVER, next_run=""),
    # r3 — QA-OPS4-4: 결과 0 인데 결재함은 경보(고장)
    _row("j-disabled", status="Disabled", enabled=False, last_run=_f(NOW - timedelta(days=3)), next_run=""),
    _row("k-no-next", last_run=_f(NOW - timedelta(hours=30)), next_run=""),
    # r3 — 꺼졌는데 마지막 결과 ≠ 0: 서버 수는 sched_bad, 글자는 결재함과 같은 '꺼짐(Disabled)'
    _row("l-disabled-failed", status="Disabled", enabled=False, ok=False, last_result="1",
         last_run=_f(NOW - timedelta(days=3)), next_run=""),
]
QUIET = {"b-quiet-daily", "c-quiet-weekly", "d-first-run-missing"}
BROKEN = {"h-failed", "i-never-no-next", "j-disabled", "k-no-next", "l-disabled-failed"}


@pytest.fixture()
def judged(tmp_path):
    """대시보드 `build_state` 가 싣는 순서 그대로 — `attach_verdict`(고장) → `Org.silence_rows`(조용한 누락, 계약은 실제 §1 사본)."""
    (tmp_path / "docs").mkdir()
    shutil.copy(ROOT / "docs" / "org-contracts.md", tmp_path / "docs" / "org-contracts.md")
    rows = [dict(r) for r in ROWS]
    warns, err = ad.attach_verdict(rows)
    assert err is None and warns == []
    verdicts = rt.Org(tmp_path).silence_rows(rows, NOW)
    for r in rows:
        r["silence"] = verdicts[r["name"]]
    return rows


def _by_name(page, rows):
    return {r["name"]: s for r, s in zip(rows, _states(page, rows))}


# ════════════════════════════════════════════════════════════════════════
# 칩 — 순환계 판정(verdict · silence)을 그대로 따른다
# ════════════════════════════════════════════════════════════════════════
def test_fixture_really_exercises_every_branch(judged):
    """공허 통과 방지 — 가짜 행이 정말로 각 분기에 떨어지는지 순환계 판정으로 먼저 확인한다."""
    sv = {r["name"]: r["silence"] for r in judged}
    vd = {r["name"]: r["verdict"] for r in judged}
    assert sv["b-quiet-daily"]["bad"] and sv["b-quiet-daily"]["label"].startswith("조용히 안 돎")
    assert sv["c-quiet-weekly"]["bad"] and "매주" in sv["c-quiet-weekly"]["label"]
    assert sv["d-first-run-missing"]["bad"] and sv["d-first-run-missing"]["label"].startswith("첫 실행 없음")
    assert {n for n, v in sv.items() if v["bad"]} == QUIET
    assert sv["g-trigger-unreadable"]["warn"] and not sv["g-trigger-unreadable"]["bad"]
    assert {n for n, v in vd.items() if v["broken"]} == BROKEN
    assert vd["j-disabled"] == {"broken": True, "label": "꺼짐(Disabled)"}
    assert vd["k-no-next"] == {"broken": True, "label": "다음 실행 없음"}
    assert vd["l-disabled-failed"] == {"broken": True, "label": "꺼짐(Disabled)"}
    assert vd["h-failed"]["label"] == "실패 · 결과 3221225477(0xC0000005) · 다음 실행 없음"
    assert vd["e-waiting"]["label"] == "아직 때가 안 됨" and vd["f-running"]["label"] == "실행 중"
    k = ad.schedule_counts(judged)
    assert (k["sched_never"], k["sched_bad"], k["sched_stopped"], k["sched_silent"]) == (1, 2, 2, 3)


def test_chips_follow_the_runtime_verdict(page, judged):
    st = _by_name(page, judged)
    got = {n: (x["pill"], x["text"], x["row"]) for n, x in st.items()}
    assert got == {
        "a-normal": ("ok", "정상", ""),
        "b-quiet-daily": ("warn", "조용히 안 돎", "late"),
        "c-quiet-weekly": ("warn", "조용히 안 돎", "late"),
        "d-first-run-missing": ("warn", "첫 실행 없음", "late"),
        "e-waiting": ("idle", "아직 때가 안 됨", ""),                        # r3: 주황·late → 결재함 '대기'와 같은 무채색
        "f-running": ("ok", "실행 중", ""),                                  # r3: 주황 → 결재함 '진행'과 같은 ok
        "g-trigger-unreadable": ("mute", "확인 불가", ""),
        "h-failed": ("bad", "실패", "bad"),                                  # 머리만 칩, 결과는 칩 아래
        "i-never-no-next": ("bad", "실행된 적 없음", "bad"),
        "j-disabled": ("bad", "꺼짐(Disabled)", "bad"),                     # r2: 초록 '정상'(QA-OPS4-4)
        "k-no-next": ("bad", "다음 실행 없음", "bad"),                       # r2: 초록 '정상'(QA-OPS4-4)
        "l-disabled-failed": ("bad", "꺼짐(Disabled)", "bad"),              # 결재함 글자를 따른다
    }
    assert [n for n, x in st.items() if x["alarm"]] == ["b-quiet-daily", "c-quiet-weekly", "d-first-run-missing"]
    assert st["h-failed"]["sub"] == "결과 3221225477(0xC0000005) · 다음 실행 없음"
    assert st["i-never-no-next"]["sub"] == "예정도 없음"


def test_chip_plus_reason_reads_exactly_like_the_inbox_label(page, judged):
    """칩 머리 + ' · ' + 칩 아래 사유 = 순환계 라벨(결재함 목적 줄의 그 글자). 고장은 verdict, 조용한 누락은 silence."""
    st = _by_name(page, judged)
    for r in judged:
        x = st[r["name"]]
        joined = x["text"] + (f" · {x['sub']}" if x["sub"] else "")
        if r["verdict"]["broken"]:
            assert joined == r["verdict"]["label"], r["name"]
        elif r["silence"]["bad"]:
            assert joined == r["silence"]["label"], r["name"]
        elif x["pill"] != "mute":
            assert x["text"] == r["verdict"]["label"] and x["sub"] == "", r["name"]


def test_table_and_runtime_never_disagree(page, judged):
    """QA-OPS4-4 의 양방향. 표 빨강 ⟺ 순환계 고장 · 표 주황 ⟺ 조용한 누락 · 표 초록/무채색이면 결재함 경보가 아니다.
    행 배경은 칩과 짝이다 — bad 행 ⟺ 빨강 칩, late 행 ⟺ 주황 칩(주황은 결재함 경보와 같은 판정 하나뿐)."""
    st = _by_name(page, judged)
    for r in judged:
        broken, _ = rt.schedule_verdict(r)
        quiet = r["silence"]["bad"]
        x = st[r["name"]]
        assert (x["pill"] == "bad") == broken, r["name"]
        assert (x["pill"] == "warn") == quiet, r["name"]
        if x["pill"] in ("ok", "idle"):
            assert not (broken or quiet), r["name"]
        assert (x["row"] == "bad") == (x["pill"] == "bad"), r["name"]
        assert (x["row"] == "late") == (x["pill"] == "warn"), r["name"]
        assert x["row"] in ("bad", "late", ""), r["name"]


def test_unknown_silence_is_never_drawn_calm(page, judged):
    """`silence` null(조용한 누락 판정을 못 붙임). 고장 판정은 있다 — 고장이면 빨강, 실행 중은 초록(silence 와 무관),
    나머지는 확인 불가. ★ '아직 때가 안 됨'도 확인 불가다 — 무채색(대기)으로 두면 한도를 넘긴 첫 실행일지 모르는 것을
    '괜찮다'로 칠한다."""
    rows = [dict(r, silence=None) for r in judged
            if r["name"] in ("a-normal", "b-quiet-daily", "e-waiting", "f-running", "h-failed", "j-disabled")]
    got = {r["name"]: (s["pill"], s["text"]) for r, s in zip(rows, _states(page, rows))}
    assert got == {"a-normal": ("mute", "확인 불가"), "b-quiet-daily": ("mute", "확인 불가"),
                   "e-waiting": ("mute", "확인 불가"), "f-running": ("ok", "실행 중"),
                   "h-failed": ("bad", "실패"), "j-disabled": ("bad", "꺼짐(Disabled)")}
    subs = {r["name"]: s["sub"] for r, s in zip(rows, _states(page, rows))}
    assert subs["e-waiting"].startswith("한 번도 안 돎 · 첫 실행이 늦었는지 판정 못함")
    assert subs["a-normal"].startswith("결과 0 · 조용히 안 도는지 판정 못함")


@pytest.mark.parametrize("missing", ["null", "absent"])
def test_unknown_verdict_only_raw_facts_are_red_and_nothing_is_green(page, judged, missing):
    """`verdict` null(또는 키 없음 — 옛 서버) = 고장인지 모른다. 원자료로 확실한 사실(실행된 적 없음 · 예정도 없음 /
    돈 적 있고 결과 ≠ 0)만 빨강, 순환계가 이미 경보로 본 silence.bad 는 주황, 나머지는 전부 확인 불가."""
    rows = []
    for r in judged:
        x = dict(r)
        if missing == "null":
            x["verdict"] = None
        else:
            x.pop("verdict")
        rows.append(x)
    got = {r["name"]: (s["pill"], s["text"], s["row"]) for r, s in zip(rows, _states(page, rows))}
    assert got["h-failed"] == ("bad", "실패", "bad")
    assert got["l-disabled-failed"] == ("bad", "실패", "bad")          # 판정 없이는 '꺼짐'을 모른다 — 확실한 건 실패
    assert got["i-never-no-next"] == ("bad", "실행된 적 없음", "bad")
    assert {n for n, g in got.items() if g[0] == "warn"} == QUIET
    for n in ("a-normal", "e-waiting", "f-running", "g-trigger-unreadable", "j-disabled", "k-no-next"):
        assert got[n] == ("mute", "확인 불가", ""), n
    assert not any(g[0] in ("ok", "idle") for g in got.values())


def test_failure_outranks_a_quiet_verdict_even_if_both_arrive(page, judged):
    """순환계는 고장 행에 silence.bad 를 싣지 않는다(`judge_task`). 그래도 둘이 함께 오면 고장이 이긴다 — 빨강을 주황으로 내리지 않는다."""
    quiet = {"bad": True, "label": "조용히 안 돎 · 마지막 성공 09-25 15:41 · 매일 작업 한도 36시간 넘김",
             "since": "", "limit_h": 36, "cls": "매일", "warn": ""}
    rows = [dict(r, silence=quiet) for r in judged if r["name"] in BROKEN]
    assert {(x["pill"], x["row"]) for x in _states(page, rows)} == {("bad", "bad")}


def test_empty_label_does_not_make_an_empty_chip(page, judged):
    quiet = next(r for r in judged if r["name"] == "b-quiet-daily")
    row = dict(quiet, silence={"bad": True, "label": "", "since": "", "limit_h": 36, "cls": "매일", "warn": ""})
    x = _states(page, [row])[0]
    assert x["pill"] == "warn" and x["text"] == "예약 작업 경보" and x["sub"] == ""
    broken = dict(quiet, verdict={"broken": True, "label": ""})
    y = _states(page, [broken])[0]
    assert y["pill"] == "bad" and y["text"] == "예약 작업 경보" and y["sub"] == ""


# ════════════════════════════════════════════════════════════════════════
# 사유 줄(schedWhy) — design-critic r2 #3: 구분자는 앞 조각 안, 시각·숫자는 갈리지 않는다
# ════════════════════════════════════════════════════════════════════════
SUBS = ["마지막 성공 09-25 15:59 · 매일 작업 한도 36시간 넘김",
        "등록 08-10 20:47 뒤 매월 작업 한도 35일 넘김",
        "결과 3221225477(0xC0000005) · 다음 실행 없음",
        "결과 0 · 조용히 안 도는지 판정 못함 · 사유는 맨 위 '읽지 못한 것'",
        "예정도 없음",
        "a<b & \"c\" · 10-01 13:30"]


def test_why_line_keeps_the_label_text_and_puts_the_separator_inside_the_segment(page):
    got = page.evaluate("""subs => subs.map(s => {
        const d = document.createElement('div'); d.innerHTML = schedWhy(s);
        return {text: d.textContent, segs: [...d.querySelectorAll('.seg')].map(x => x.textContent),
                between: [...d.childNodes].filter(n => n.nodeType === 3).map(n => n.data),
                nw: [...d.querySelectorAll('.nw')].map(x => x.textContent), html: d.innerHTML};
    })""", SUBS)
    for s, g in zip(SUBS, got):
        assert g["text"] == s, s                                            # 글자까지 같다(U+00A0 도 없다)
        parts = s.split(" · ")
        assert len(g["segs"]) == len(parts), s
        for i, seg in enumerate(g["segs"]):
            assert not seg.lstrip().startswith("·"), s
            assert seg.endswith(" ·") == (i < len(parts) - 1), (s, seg)
        assert all(b == " " for b in g["between"]), (s, g["between"])      # 조각 밖에는 공백 하나뿐 — '·'가 밖에 없다
        for tm in re.findall(r"\d{2}-\d{2} \d{2}:\d{2}", s):
            assert any(tm in n for n in g["nw"]), (s, tm)                     # 시각은 줄바꿈 금지 덩이 안
        for i, p in enumerate(parts[:-1]):
            assert any(n.endswith(" ·") and p.endswith(n[:-2]) for n in g["nw"]), (s, p)   # 꼬리 + ' ·' 한 덩이
    assert "3221225477<wbr>(0xC0000005" in got[2]["html"]                     # 숫자 중간이 아니라 괄호 앞에서 갈린다
    assert "a&lt;b &amp;" in got[5]["html"] and "<b" not in got[5]["html"]      # 사유 글자는 이스케이프된다


@pytest.mark.parametrize("width", [110, 120, 130, 150, 180, 240])
def test_why_line_never_orphans_the_dot_nor_splits_a_time_or_number(page, width):
    """실제 CSS(`td .sb.why`)로 좁은 상태 칸에 그려 글자마다 줄(top)을 잰다. 칸 폭(표 폭)은 r3 캡처의 실제 상태 칸
    (320·360·390·430px 화면에서 131·142·151·162px)보다 **좁은 것부터** 잰다 — 110px 표의 안쪽은 약 84px.
    '·' 는 앞 글자와 같은 줄, 'MM-DD HH:MM'·긴 숫자는 한 줄, 칸 밖으로 나가는 요소 0."""
    res = page.evaluate("""([subs, w]) => {
        const tbl = document.createElement('table'); tbl.style.width = w + 'px'; tbl.style.tableLayout = 'fixed';
        document.body.appendChild(tbl);
        const out = subs.map(s => {
            tbl.innerHTML = `<tr><td><span class="pill bad">x</span><i class="sb why">${schedWhy(s)}</i></td></tr>`;
            const i = tbl.querySelector('.why'); const cs = [];
            const tw = document.createTreeWalker(i, NodeFilter.SHOW_TEXT); let n;
            while ((n = tw.nextNode())) for (let k = 0; k < n.data.length; k++) cs.push([n, k, n.data[k]]);
            const top = ([n, k]) => { const r = document.createRange(); r.setStart(n, k); r.setEnd(n, k + 1);
                                      return Math.round(r.getClientRects()[0].top); };
            const vis = cs.filter(c => !/\\s/.test(c[2]));
            const lonely = vis.filter((c, k) => k > 0 && c[2] === '·' && top(c) !== top(vis[k - 1])).length;
            const txt = cs.map(c => c[2]).join('');
            const whole = re => { let m, bad = 0; while ((m = re.exec(txt)))
                if (top(cs[m.index]) !== top(cs[m.index + m[0].length - 1])) bad++; return bad; };
            const td = tbl.querySelector('td').getBoundingClientRect();
            const over = [...i.querySelectorAll('*')].filter(e => e.getBoundingClientRect().right > td.right + 0.5).length;
            return {lonely, time: whole(/\\d{2}-\\d{2} \\d{2}:\\d{2}/g), num: whole(/\\d{4,}|0x[0-9A-F]+/g), over,
                    lines: new Set(vis.map(top)).size};
        });
        tbl.remove(); return out;
    }""", [SUBS[:5], width])
    for s, r in zip(SUBS, res):
        assert (r["lonely"], r["time"], r["num"], r["over"]) == (0, 0, 0, 0), (width, s, r)
    if width <= 130:
        assert max(r["lines"] for r in res) >= 3                                # 공허 방지 — 실제로 여러 줄로 갈렸다


# ════════════════════════════════════════════════════════════════════════
# 타일 — 같은 행·같은 판정, 부제는 칩 글자, 색은 서버 schedule_counts
# ════════════════════════════════════════════════════════════════════════
def test_tile_mixed_is_red_and_lists_everything_in_chip_words(page, judged):
    k = ad.schedule_counts(judged)
    sub, lv, html = _tile(page, k, judged)
    assert lv == "alert"
    assert sub == ("1개 실패 · 1개 실행된 적 없음 · 2개 꺼짐(Disabled) · 1개 다음 실행 없음 · "
                   "2개 조용히 안 돎 · 1개 첫 실행 없음 · 1개 확인 불가")
    assert html.count('<span style="white-space:nowrap">') == 7             # 항목마다 줄바꿈 없음
    # 칩 글자로 센 수 = 서버 수(빨강 = never + bad + stopped, 주황 = silent)
    st = _states(page, judged)
    assert sum(x["pill"] == "bad" for x in st) == k["sched_never"] + k["sched_bad"] + k["sched_stopped"] == 5
    assert sum(x["alarm"] for x in st) == k["sched_silent"] == 3
    assert k["sched_alarm"] == 8


def test_tile_separator_sits_inside_the_preceding_chunk(page, judged):
    """design-critic OPS-4 r3 #1 — 부제 구분자가 덩이 밖에 있으면 430px 에서 둘째 줄이 '· 2개 …' 로 시작했다.
    ' ·' 는 앞 항목 nowrap 덩이 안 끝에 있고(마지막 항목 제외), 덩이 사이는 공백 하나뿐이다. 화면 글자는 부제와 같다."""
    k = ad.schedule_counts(judged)
    sub, _lv, html = _tile(page, k, judged)
    chunks = html.split('<span style="white-space:nowrap">')[1:]
    assert len(chunks) == 7
    for c in chunks[:-1]:
        assert c.endswith(" ·</span> "), c                                   # 구분자는 덩이 안, 사이는 공백
    assert chunks[-1].endswith("</span>") and "·" not in chunks[-1]
    assert page.evaluate("h => { const d = document.createElement('div'); d.innerHTML = h; return d.textContent; }",
                         html) == sub


@pytest.mark.parametrize("width", [150, 200, 250, 330, 400])
def test_tile_subtitle_never_starts_a_line_with_the_dot(page, judged, width):
    """실제 CSS 로 좁은 타일 부제를 그려 줄머리 '·' 가 0 인지 잰다(폭은 320~1440 화면에서 타일 부제가 받는 범위)."""
    k = ad.schedule_counts(judged)
    _sub, _lv, html = _tile(page, k, judged)
    lonely = page.evaluate(r"""([h, w]) => {
      const box = document.createElement('div'); box.className = 'kpi'; box.style.width = w + 'px';
      const s = document.createElement('div'); s.className = 's'; s.innerHTML = h; box.appendChild(s);
      document.body.appendChild(box);
      const cs = []; const tw = document.createTreeWalker(s, NodeFilter.SHOW_TEXT); let n;
      while ((n = tw.nextNode())) for (let i = 0; i < n.data.length; i++) if (!/\s/.test(n.data[i])) cs.push([n, i, n.data[i]]);
      const top = ([n, i]) => { const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + 1);
        return Math.round(r.getClientRects()[0].top); };
      let bad = 0;
      for (let j = 1; j < cs.length; j++) if (cs[j][2] === '·' && top(cs[j]) !== top(cs[j - 1])) bad++;
      box.remove(); return bad;
    }""", [html, width])
    assert lonely == 0


def test_tile_stopped_only_is_red(page, judged):
    """QA-OPS4-4 ⓐ — 실패·조용한 누락이 없고 꺼짐·다음 실행 없음만 있어도 타일은 빨강이다(서버 sched_stopped)."""
    rows = [r for r in judged if r["name"] in ("a-normal", "e-waiting", "f-running", "j-disabled", "k-no-next")]
    k = ad.schedule_counts(rows)
    assert (k["sched_never"], k["sched_bad"], k["sched_silent"], k["sched_stopped"]) == (0, 0, 0, 2)
    assert _tile(page, k, rows)[:2] == ["1개 꺼짐(Disabled) · 1개 다음 실행 없음", "alert"]


def test_tile_quiet_only_is_orange(page, judged):
    rows = [r for r in judged if r["name"] not in BROKEN | {"g-trigger-unreadable"}]
    sub, lv, _ = _tile(page, ad.schedule_counts(rows), rows)
    assert lv == "warn" and sub == "2개 조용히 안 돎 · 1개 첫 실행 없음"


def test_tile_unknown_is_mute_and_all_good_is_plain(page, judged):
    rows = [dict(r, silence=None) for r in judged if r["name"] in ("a-normal", "f-running")]
    k = ad.schedule_counts(rows)
    assert k["sched_silent"] is None
    assert _tile(page, k, rows)[:2] == ["1개 확인 불가", "mute"]
    nov = [dict(r, verdict=None) for r in judged if r["name"] in ("a-normal", "f-running")]
    k2 = ad.schedule_counts(nov)
    assert k2["sched_stopped"] is None
    assert _tile(page, k2, nov)[:2] == ["2개 확인 불가", "mute"]             # 고장을 모르면 '정상'이 아니다
    good = [r for r in judged if r["name"] in ("a-normal", "f-running")]
    assert _tile(page, ad.schedule_counts(good), good)[:2] == ["정상", ""]
    waiting = [r for r in judged if r["name"] in ("a-normal", "e-waiting")]
    assert _tile(page, ad.schedule_counts(waiting), waiting)[:2] == ["1개 아직 때가 안 됨", ""]   # 표의 무채색 칩 글자


def test_tile_stopped_null_alone_is_mute_not_plain(page, judged):
    """서버가 sched_stopped 를 못 셌으면(null) 볼 것이 없어도 '정상'(무채색)이 아니다."""
    good = [r for r in judged if r["name"] in ("a-normal", "f-running")]
    k = dict(ad.schedule_counts(good), sched_stopped=None)
    assert _tile(page, k, good)[1] == "mute"


def test_tile_empty_list_is_unread_not_zero_ok(page):
    k = ad.schedule_counts([])
    assert _tile(page, k, [])[:2] == ["예약 작업을 읽지 못했다", "mute"]


# ════════════════════════════════════════════════════════════════════════
# 배선 — 표와 타일이 이 함수를 실제로 부른다(함수만 맞고 화면이 옛 규칙이면 소용없다)
# ════════════════════════════════════════════════════════════════════════
def test_table_and_tile_are_wired_to_the_shared_verdict():
    table = _cut("$('#sched').innerHTML", "예약 작업을 읽지 못했다.</div>';")
    assert "schedState(s)" in table and "s.ok ?" not in table and "pill ok\">정상" not in table
    assert '<i class="sb why">${schedWhy(x.sub)}</i>' in table
    assert ".join(' · ')" not in table                                       # 구분자가 조각 밖에 없다(design r2 #3)
    assert "kpi('예약 작업', `${k.sched_total}개`, ...schedTile(k, d.schedule || []))" in HTML
    assert "td .sb.why{color:var(--soft);max-width:20em;word-break:keep-all}" in HTML
    assert "td .sb.why .seg{display:inline-block;max-width:100%}" in HTML
    assert "td .sb.why .nw{white-space:nowrap}" in HTML
    # '아직 때가 안 됨' 칩은 결재함 '대기'와 **같은 클래스**다
    assert "(o.status === 'doing' ? 'ok' : 'idle')" in HTML and ".pill.idle{" in HTML
    state = _cut("const schedState = s => {", "\n};")
    assert "calm('idle', v.label)" in state and "calm('ok', v.label)" in state
    assert "s.verdict" in state


def test_comments_describe_the_new_rule():
    """주석이 옛 규칙을 말하지 않는다(CLAUDE.md 운영 규칙 8 — 가리키는 곳이 아니라 말하는 내용이 거짓이 된다)."""
    assert "행 배경은 칩과 같은 심각도 — '아직 때가 안 됨'·'조용히 안 돎'(주황 칩)을 빨강 행에 두지 않는다" not in HTML
    assert "→ 주황 — 아직 때가 안 됨(행 late)·실행 중" not in HTML
    table_comment = HTML[HTML.index("// 예약 작업(작업 스케줄러) — 칩·행 색은 schedState"):HTML.index("$('#sched').innerHTML")]
    assert "주황 칩 + late 행은 silence.bad" in table_comment and "무채색 idle" in table_comment
    head = HTML[HTML.index("// 예약 작업 행의 판정"):HTML.index("const schedState = s => {")]
    for w in ("verdict.broken", "silence.bad", "verdict 가 null", "모르는 것을 초록으로 그리지 않는다", "judge_task"):
        assert w in head, w


# ════════════════════════════════════════════════════════════════════════
# 어휘 · 피드 톤 · 주석(r2)
# ════════════════════════════════════════════════════════════════════════
def test_scheduler_list_is_called_yeyak_jakeop():
    assert "<h2>예약 작업 <small>" in HTML and "<h2>정기 작업" not in HTML
    assert "kpi('정기 작업'" not in HTML
    assert "정기 작업 표" not in HTML                                        # 주석 포인터도(design #2)
    assert "routine:'정기'" in HTML                                         # 정기 점검 지시서 사유는 그대로


def test_feed_label_default_is_soft_not_ink():
    rule = _cut(".feed .k{", "}")
    assert "color:var(--soft)" in rule
    assert "--soft:#9fb0c3" in HTML


def test_red_comment_no_longer_says_supply_stop_only():
    assert "빨강은 공급 '멈춤'에만 쓴다" not in HTML
    assert "빨강은 **사실 판정**" in HTML
