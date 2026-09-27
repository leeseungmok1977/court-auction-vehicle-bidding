# -*- coding: utf-8 -*-
"""테스트 공용 — 사내 대시보드 예약 작업 칩을 **실제 HTML 의 `schedState`** 로 판정한다(OPS-4 r3 qa, 지시서 2026-09-27-76).

왜 있나: 칩 규칙을 테스트 파일에 옮겨 두면 화면이 바뀌어도 사본은 그대로라, 그 사본을 근거로 한 단언이 조용히 낡는다.
`test_ops4_qa_adversarial._dashboard_pill`·`test_ops3_qa_adversarial._dashboard_class` 가 그랬다 — r1 규칙(결과 `s.ok`
만 본다)에 멈춘 채, r3 에서 표가 '꺼짐(Disabled)'·'다음 실행 없음'을 빨강으로 칠한 뒤에도 '정상'이라고 말했다.
이제 두 파일은 이 모듈로 **실제 JS** 를 돌린다. 사본이 다시 생기지 않는지는 `test_ops4_qa_r3` 가 본다.

- 행에는 대시보드가 싣는 순서 그대로 판정을 붙인다: `agent_dashboard.attach_verdict`(고장) → `org_runtime.judge_task`
  의 silence(조용한 누락 — `Org.silence_rows` 가 행마다 부르는 것과 같은 함수·같은 인자).
- JS 블록은 줄 번호가 아니라 앵커 문자열로 자른다(CLAUDE.md 운영 규칙 8).
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
import agent_dashboard as ad  # noqa: E402
import org_runtime as rt  # noqa: E402

HTML_PATH = ROOT / "tools" / "agent_dashboard.html"


def js() -> str:
    """칩 판정에 필요한 최소 JS — esc · RSN · schedState(실제 HTML 에서 앵커로 자른다)."""
    html = HTML_PATH.read_text(encoding="utf-8")

    def cut(start: str, end: str) -> str:
        i = html.index(start)
        return html[i:html.index(end, i) + len(end)]
    return "\n".join([cut("const esc = ", "\n"), cut("  {'&':'&amp;'", "\n"), cut("const RSN = {", "};"),
                      cut("const schedState = s => {", "\n};")])


def judge(rows: list[dict], now: datetime, settings: dict, seen: str = "") -> list[dict]:
    """행 사본에 `verdict`·`silence` 를 붙여 돌려준다(대시보드 `build_state` 순서). `seen` 은 task_seen 한 값."""
    out = [dict(r) for r in rows]
    warns, err = ad.attach_verdict(out)
    assert err is None and not warns, (err, warns)
    for r in out:
        r["silence"] = rt.judge_task(r, now, settings, seen or now.isoformat())[1]
    return out


@contextmanager
def page():
    """Chromium(없으면 chrome) 한 장 — `schedState` 가 올라가 있다. 둘 다 없으면 skip."""
    pw = pytest.importorskip("playwright.sync_api")
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
        pg.add_script_tag(content=js())
        try:
            yield pg
        finally:
            b.close()


def states(pg, rows: list[dict]) -> list[dict]:
    """행마다 실제 `schedState` 결과 — {row, pill, text, sub, alarm}."""
    return pg.evaluate("rows => rows.map(schedState)", rows)
