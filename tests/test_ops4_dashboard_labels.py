# -*- coding: utf-8 -*-
"""OPS-4 ④ — 순환계가 만드는 사유·이벤트는 사내 대시보드에 **한국어 라벨**이 있어야 한다.

2026-09-27 OPS-3(c202dfe)이 지시서 사유 `alert`·`task` 와 버스 이벤트 `handoff.skipped`·`result.skipped` 를
새로 만들었는데 `tools/agent_dashboard.html` 의 라벨표(`RSN`·`EVK`)에는 없어서 **영문 코드가 그대로** 결재함
표와 피드에 섰다(백엔드 보고서가 스스로 적은 후속). 라벨표는 '없으면 코드를 그대로 보인다'(숨기지 않는다)라서
빠져도 아무 데서도 빨개지지 않는다 — 그래서 여기서 **순환계 소스와 라벨표를 맞대어** 본다.
다음에 순환계가 사유나 이벤트를 더하면 이 테스트가 먼저 빨개진다.

톤(Steward 지시 2026-09-27): 경보는 경고색이되 '멈춤'과 구분한다 — 주황(`warn`)이고 빨강(`bad`)이 아니다.
빨강은 사실 판정(공급 멈춤·예약 작업 실패·리듬 끊김·맥박 굳음)에만 쓰고 지시서 사유에는 쓰지 않는다
(agent_dashboard.html `.ord .rs.warn` 주석 — r2 에서 '공급 멈춤에만'을 고쳤다, design-critic 2026-09-27 #1).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
import org_runtime as rt  # noqa: E402

HTML = (ROOT / "tools" / "agent_dashboard.html").read_text(encoding="utf-8")
SRC = (ROOT / "tools" / "org_runtime.py").read_text(encoding="utf-8")


def _block(start: str) -> str:
    """`const X = {` 부터 그 객체를 닫는 `};` 까지 — 줄 수가 늘어도 따라온다(줄 번호를 쓰지 않는다)."""
    s = HTML[HTML.index(start):]
    return s[:s.index("};") + 2]


RSN = dict(re.findall(r"(\w+):'([^']*)'", _block("const RSN = {")))
RSNC = dict(re.findall(r"(\w+):'([^']*)'", _block("const RSNC = {")))
EVK = {k: (lb, cls) for k, lb, cls in re.findall(r"'([\w.]+)':\['([^']*)','([^']*)'\]", _block("const EVK = {"))}


def _runtime_reasons() -> set[str]:
    return set(re.findall(r'reason="(\w+)"', SRC))


def _runtime_kinds() -> set[str]:
    kinds = {k for k in re.findall(r'self\.emit\("([\w.]+)"', SRC) if not k.endswith(".")}  # "order." + status 는 아래
    kinds |= set(re.findall(r'\bskip\(\s*[^,\n]+,\s*"([\w.]+)"', SRC))      # 워크플로 건너뜀(OPS-3)
    # set_status 는 `"order." + status` 로 낸다. 상태는 열린 상태 + CLI 로 닫는 상태.
    close = re.search(r'"--status", required=True, choices=\[([^\]]+)\]', SRC)
    states = set(rt.OPEN_STATES) | set(re.findall(r'"(\w+)"', close.group(1)))
    assert not re.search(r'set_status\([^\n]*"open"', SRC)                  # open 은 order.created 가 낸다
    kinds |= {"order." + s for s in states - {"open"}}
    return kinds - {"scan"}                                                   # board() 가 피드에서 뺀다


def test_every_reason_the_runtime_can_write_has_a_korean_label():
    reasons = _runtime_reasons()
    assert {"alert", "task", "handoff", "manual"} <= reasons                 # 추출이 헛돌지 않는다
    missing = sorted(reasons - set(RSN))
    assert not missing, f"대시보드 RSN 에 라벨이 없는 사유: {missing} — 결재함 표에 영문 코드가 선다"
    for r in reasons:
        assert RSN[r] and not re.fullmatch(r"[a-z_.]+", RSN[r]), (r, RSN[r])


def test_every_event_the_feed_can_show_has_a_korean_label():
    kinds = _runtime_kinds()
    assert {"handoff.skipped", "result.skipped", "order.created", "order.cancelled"} <= kinds
    missing = sorted(kinds - set(EVK))
    assert not missing, f"대시보드 EVK 에 라벨이 없는 이벤트: {missing} — 피드에 영문 코드가 선다"


def test_alert_and_task_are_orange_not_red():
    """경보·예약 작업 = 결정 대기의 한 종류. 주황이다. 빨강('멈춤')으로 올리지 않는다."""
    assert RSN["alert"] == "경보" and "예약 작업" in RSN["task"]
    assert set(rt.NO_DISPATCH_REASONS) <= set(RSNC)                          # 당직이 안 부르는 사유 = 사람이 볼 사유
    assert all(v == "warn" for v in RSNC.values()), RSNC
    assert ".ord .rs.warn{color:var(--warn);font-weight:600}" in HTML
    # 피드에서도 경보 지시서는 파란 '지시서'(평소 흐름)가 아니라 제 사유·주황으로 선다
    ev = HTML[HTML.index("const evk = e =>"):]
    ev = ev[:ev.index(";\n")]
    assert "e.kind === 'order.created' && RSNC[e.reason]" in ev and "[RSN[e.reason], RSNC[e.reason]]" in ev
    assert "const [lb, cls] = evk(e);" in HTML


def test_skipped_events_are_neutral_records_not_warnings():
    """건너뜀은 '지시서를 만들지 않았다'는 기록이다 — 다음 단계는 워크플로가 부른다. 경고색이 아니다."""
    for k in ("handoff.skipped", "result.skipped"):
        assert EVK[k][1] == "", (k, EVK[k])
    # 이름은 만들지 않은 지시서의 사유 라벨을 그대로 쓴다 — 같은 화면에서 어휘가 갈리지 않게
    assert EVK["handoff.skipped"][0].startswith(RSN["handoff"])
    assert EVK["result.skipped"][0].startswith(RSN["result"])


def test_purpose_text_drops_markdown_bold():
    """OPS-3 경보 목적 줄이 `**2개 리포트 연속**` 을 쓴다 — 화면에 별표를 그대로 두지 않는다."""
    line = HTML[HTML.index("const tx = s =>"):]
    line = line[:line.index("\n")]
    assert r"\*\*" in line and "`" in line
    assert "**" in SRC[SRC.index('reason="alert"'):]                          # 원천이 아직 굵게를 쓴다
