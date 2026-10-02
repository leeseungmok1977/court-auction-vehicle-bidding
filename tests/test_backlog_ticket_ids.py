"""백로그 티켓 번호 하나는 일 하나를 가리킨다.

2026-10-02: 새로 단 AUD-11·12·13 이 09-27 감사 티켓과 같은 번호여서, 오너에게
'다음은 AUD-13' 이라고 권고하면 서로 다른 두 일 중 어느 것인지 알 수 없었다
(AUD-16·17·18 로 정정). 같은 티켓이 두 절에 다시 실린 경우(PS-03~06 — 감사 목록과
PHASE 3 절)는 제목이 같으므로 통과한다.
"""
import re
from pathlib import Path

BACKLOG = Path(__file__).resolve().parents[1] / "docs" / "backlog.md"
ROW = re.compile(r"^\|\s*([A-Z][A-Z0-9]*-\d+[a-z]?)\s*\|\s*([^|]*)\|")


def _norm(title):
    return re.sub(r"[\s*`'\"]", "", title)


def _same_work(a, b):
    n = min(6, len(a), len(b))
    return a[:n] == b[:n]


def test_ticket_id_is_not_reused_for_different_work():
    first = {}
    clashes = []
    for line in BACKLOG.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if not m:
            continue
        tid, title = m.group(1), _norm(m.group(2))
        if tid in first and not _same_work(first[tid], title):
            clashes.append(f"{tid}: {first[tid][:20]} / {title[:20]}")
        first.setdefault(tid, title)
    assert not clashes, "같은 번호가 다른 일에 쓰였다 — 다음 빈 번호를 쓸 것: " + "; ".join(clashes)


def test_guard_catches_the_10_02_collision():
    a = _norm("수동 '낙찰결과 지금 실행' 런이 'done' 이 되지 못하고")
    b = _norm("09-23 전수 대조의 '티켓 없던 지적 51건' 표")
    assert not _same_work(a, b)
    assert _same_work(_norm("매각기일 D-3 알림(이메일/앱내)"), _norm("매각기일 D-3 알림(앱내)"))
