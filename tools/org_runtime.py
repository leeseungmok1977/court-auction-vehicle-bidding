# -*- coding: utf-8 -*-
"""조직 순환계 — 지시서 대기열·인계·리듬을 사람 없이 돌린다.

    python tools/org_runtime.py scan                  # 보고서·리듬·백로그를 읽어 지시서를 만든다(LLM 호출 없음)
    python tools/org_runtime.py standup               # scan + 오늘의 브리핑 docs/standups/YYYY-MM-DD.md
    python tools/org_runtime.py standup --dispatch 3  # + 자동 실행 가능한 지시서를 당직 Steward 가 처리
    python tools/org_runtime.py order --to insight --purpose "…" [--ticket FEAT-1] [--input reports/x.md]
    python tools/org_runtime.py close 2026-09-26-04 --status cancelled --note "중복"
    python tools/org_runtime.py dispatch 2026-09-26-04 [--dry-run]
    python tools/org_runtime.py board                 # 대기열 요약 JSON (대시보드가 같은 함수를 쓴다)

## 왜 만들었나 (2026-09-26 오너 지시)

*"회사라면 각각의 조직원들이 유기적으로 움직여야 하는데, 그렇지 않다."*

실측해 보니 조직도는 멀쩡했고 **순환계가 없었다.** 서브에이전트는 서로 부르지 못하므로
(ORG §1) 모든 인계가 Steward 를 거치는데, Steward 는 **오너가 세션을 열 때만 존재한다.**
그래서 `리듬중단` 3자리는 13일째 화면에 떠 있기만 했고, PM 은 3일째 안 불렸고,
인계는 Steward 의 기억 속에만 있었다. 이 도구는 세 가지만 한다.

1. 보고서 머리말(`.claude/agents/_handoff-protocol.md`)을 읽어 **다음 지시서를 파일로** 만든다.
2. 리듬 중단·미배분 티켓·정체·왕복 상한 초과를 감지해 **맡을 자리에 지시서를** 만든다.
3. 정해진 시각에 **당직 Steward**(헤드리스 `claude -p`)를 깨워 자동 실행 가능한 지시서를 처리한다.

규칙은 전부 `docs/org-contracts.md` 표에서 읽는다 — 코드에 박지 않는다(대시보드와 같은 원칙).

## 이 도구가 하지 않는 것

- **지어내지 않는다.** 보고서가 안 나오면 지시서를 `done` 으로 바꾸지 않고 `blocked` 로 적는다.
- **오너 승인 항목을 실행하지 않는다.** 당직은 허용 목록(`DISPATCH_ALLOWED`) 밖 도구를 못 쓴다 —
  헤드리스 실행에서 허용 목록 밖 도구는 묻지 않고 거부된다. 커밋·푸시·ssh·코드 편집은 목록에 없다.
- **LLM 을 부르는 것은 `dispatch` 뿐이다.** `scan` 은 파일만 읽고 쓰므로 매시간 돌려도 비용이 없다.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml                                            # requirements.txt 에 있다(PyYAML)
except Exception:                                          # noqa: BLE001
    yaml = None

REPO = Path(__file__).resolve().parents[1]

# 당직 Steward 가 쓸 수 있는 도구. **여기 없는 것은 헤드리스에서 전부 거부된다.**
# 오너 승인 항목(ORG §3)을 페르소나가 아니라 권한으로 막는다 — ORG §1 "가드레일은 도구 권한으로 건다".
DISPATCH_ALLOWED = [
    "Read", "Grep", "Glob", "Agent", "Task",
    "Write(reports/**)", "Edit(reports/**)",          # 보고서만 쓴다
    "Write(orders/**)", "Edit(orders/**)",            # 지시서 상태만 고친다
    "Bash(python -m pytest:*)",                        # 테스트 게이트(qa)
    "Bash(python tools/org_runtime.py:*)",
    "Bash(git log:*)", "Bash(git diff:*)", "Bash(git status:*)", "Bash(git show:*)",
    "Bash(sqlite3:*)",
    "WebFetch(domain:naechaget.co.kr)",                # 라이브 확인(C.4 는 우리 서버에 해당하지 않는다)
]
# 허용 목록이 1차 문이고, 이것은 **두 번째 문**이다. 한 줄 실수로 허용 목록이 넓어져도
# 되돌릴 수 없는 것만은 막는다(agent-utilization §6-15: 문은 울리는지가 아니라 막는지로 확인한다).
DISPATCH_DENIED = [
    "Bash(git commit:*)", "Bash(git push:*)", "Bash(ssh:*)", "Bash(scp:*)",
    "Bash(rm:*)", "Bash(schtasks:*)", "Bash(pip install:*)",
    "Edit(src/**)", "Edit(web/**)", "Edit(config.yaml)", "Edit(.claude/**)",
    "Write(src/**)", "Write(web/**)", "Write(config.yaml)", "Write(.claude/**)",
]
DISPATCH_TIMEOUT_SEC = 25 * 60        # 서브에이전트 최장 실측 6분대(2026-09-22). 넉넉히 4배

STEWARD = "steward"                   # 오너·Steward 결재함 — 에이전트가 아니다
OPEN_STATES = ("open", "doing", "blocked")
RESULTS = ("done", "fail", "blocked", "needs-owner")
_ID = re.compile(r"^(\d{4}-\d{2}-\d{2})-(\d{2,3})$")
ORDER_REF = re.compile(r"\b\d{4}-\d{2}-\d{2}-\d{2,3}\b")   # 호출 라벨에 지시서 번호가 있는가
_TICK = re.compile(r"`([^`]+)`")
# OPS-3(2026-09-27): 경보·예약 작업 지시서는 **당직이 부르지 않는다.** 고치려면 코드·서버·관리자 권한이
# 필요한데 당직에는 그 권한이 없다(DISPATCH_DENIED). 결재함에 쌓아 오너가 연 세션에서 처리한다.
NO_DISPATCH_REASONS = ("alert", "task")
ALERT_LOOKBACK_DAYS = 21              # 주간 작업(토요일 패널)의 '연속 2회'가 들어올 만큼
# 일일 리포트에 `## 공급 상태` 절이 생긴 날(daily_ops_report, 2026-09-24 첫 실물). 이 날 이후 리포트에
# 공급 절이 **흔적도 없으면** 형식이 달라진 것이다 — 그 전 리포트는 원래 없었으니 경고하지 않는다(QA-OPS3-2).
SUPPLY_SECTION_SINCE = "2026-09-24"


# ── 경보 입력(OPS-3) — 일일 리포트·백로그를 읽는 순수 함수 ─────────────────────
# 일일 리포트 표의 결과 칸 → 경보 여부. 앞에서부터 먼저 맞는 것(🛑 를 ⚠ 보다 먼저 본다).
_SUPPLY_STATE = (("🛑", "alert"), ("⚠", "alert"), ("✅", "ok"), ("❔", "unknown"))
_JOB_STATE = (("❌", "alert"), ("⚠", "alert"), ("⏭", "alert"), ("✅", "ok"),
              ("— 없음", "na"), ("❔", "unknown"), ("⏳", "unknown"))
# '완료'로 시작해도 배포 전이면 아직 누가 맡고 있는 것이다 — '완료(배포 대기)'(CLAUDE.md 운영 규칙 7)
_CLOSED = re.compile(r"^(✅|완료|done|취소|cancelled|폐기|종결|판정)", re.I)


def _cells(line: str) -> list[str]:
    """표 한 줄 → 칸. 일일 리포트는 칸 안의 `|` 를 `\\|` 로 적는다(daily_ops_report._cell)."""
    s = line.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") and not s.endswith("\\|") else s
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def _section_lines(text: str, heading: str) -> list[str] | None:
    """`## <heading>` 절의 줄(머리글 제외, 다음 `## ` 전까지). 절이 없으면 **None** — 빈 절과 다르다."""
    lines: list[str] = []
    inside = found = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            if inside:
                break
            inside = s[3:].strip().startswith(heading)
            found = found or inside
            continue
        if inside:
            lines.append(s)
    return lines if found else None


def _first_table(lines: list[str]) -> tuple[list[str] | None, list[dict], int]:
    """절 안 **첫 표** → (열 이름, 행, 본문 줄 수). 칸 수가 열 수와 다른 줄은 행에서 빠지지만 본문 줄 수에는
    센다 — 둘이 다르면 '읽다 버린 줄'이 있다는 뜻이다(부분 생성·칸 안의 막대)."""
    cols: list[str] | None = None
    rows: list[dict] = []
    body = 0
    for s in lines:
        if not s.startswith("|"):
            if cols is not None:
                break                                      # 표가 끝났다 — 다음 표를 이 표로 읽지 않는다
            continue
        cells = _cells(s)
        if cols is None:
            cols = cells
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        body += 1
        if len(cells) == len(cols):
            rows.append(dict(zip(cols, cells)))
    return cols, rows, body


def section_table(text: str, heading: str) -> list[dict]:
    """`## <heading>` 절의 **첫 표**를 [{열 이름: 칸}] 로. 열 이름으로 읽는다 — 열이 늘어도 따라온다."""
    return _first_table(_section_lines(text, heading) or [])[1]


def _mark_of(cell: str, table) -> str | None:
    """결과 칸 → 상태. **아는 표시가 하나도 없으면 None** — '❔ 확인 불가'(아는 모름)와 '읽지 못함'을 가른다."""
    for mark, st in table:
        if mark in (cell or ""):
            return st
    return None


def _state_of(cell: str, table) -> str:
    return _mark_of(cell, table) or "unknown"


_SUPPLY_NOTES = ("지난 기간", "확인 불가")                 # daily_ops_report.supply_block 의 표 없는 두 문장
_ANY_SUPPLY_HEAD = re.compile(r"^#{1,6}\s*공급 상태")


def _read_table(sec: list[str], what: str, name_col: str, state_col: str, marks,
                issues: list[str]) -> dict[str, dict]:
    """절 → {이름: 행 + state}. 형식이 어긋난 곳은 `issues` 에 적는다(조용한 0 을 만들지 않는다)."""
    cols, rows, body = _first_table(sec)
    if cols is None:
        return {}
    miss = [c for c in (name_col, state_col) if c not in cols]
    if miss:
        issues.append(f"{what} 표에 `{'`·`'.join(miss)}` 열이 없다(열: {'·'.join(cols)})")
        return {}
    if not rows:
        issues.append(f"{what} 표에서 읽힌 행이 0이다(본문 {body}줄)")
    elif body > len(rows):
        issues.append(f"{what} 표에서 칸 수가 열과 다른 줄 {body - len(rows)}개를 읽지 못했다")
    out: dict[str, dict] = {}
    odd: list[str] = []
    for r in rows:
        name = (r.get(name_col) or "").strip()
        if not name:
            continue
        cell = r.get(state_col, "")
        st = _mark_of(cell, marks)
        if st is None:
            odd.append(f"{name} '{cell[:12]}'")
        out[name] = dict(r, state=st or "unknown")
    if odd:
        issues.append(f"{what} 표 `{state_col}` 칸의 표시를 모른다 — 모름으로 읽었다: "
                      + ", ".join(odd[:3]) + (f" 외 {len(odd) - 3}개" if len(odd) > 3 else ""))
    return out


def parse_daily_report(text: str, day: str | None = None) -> dict:
    """일일 리포트 한 편 → 공급 신호·정기 작업의 상태 + 형식 문제(`issues`).

    `supply` 는 `## 공급 상태` 표(ops_health 신호 이름이 키), `jobs` 는 `## 정기 작업` 표(작업 이름이 키).
    공급 표가 없으면(09-24 이전·지난 기간·서버 못 읽음) `supply` 는 비고, 그날은 **모름**이다.

    ★ QA-OPS3-2(2026-09-27): 표 형식이 조금만 달라져도(이모지 없는 상태 칸·`###` 머리글·머리글 없는 표·
      열 이름 변경) 모든 신호가 '모름'이 되고 경보가 **경고 없이** 0건이 됐다. 그래서 읽다가 어긋난 곳을
      `issues` 에 적는다 — 호출자(순환계·주간 보고)가 파일명을 붙여 드러낸다. `day` 를 주면 공급 절이
      생긴 뒤(SUPPLY_SECTION_SINCE) 리포트에 공급 절 흔적이 없는 것도 적는다.
    """
    out: dict = {"supply": {}, "jobs": {}, "ticket_column": False, "issues": []}
    issues: list[str] = out["issues"]
    sec = _section_lines(text, "공급 상태")
    if sec is None:
        heads = [ln.strip() for ln in text.splitlines() if _ANY_SUPPLY_HEAD.match(ln.strip())]
        stray = any(ln.strip().startswith("|") and "신호" in _cells(ln) for ln in text.splitlines())
        if heads:
            issues.append(f"공급 절 머리글이 `{heads[0][:20]}` 다 — `## 공급 상태` 여야 읽힌다")
        elif stray:
            issues.append("`신호` 표가 `## 공급 상태` 절 밖에 있다 — 머리글이 빠졌다")
        elif day and day >= SUPPLY_SECTION_SINCE:
            issues.append("`## 공급 상태` 절이 없다")
    elif _first_table(sec)[0] is None:
        if not any(k in ln for ln in sec for k in _SUPPLY_NOTES):
            issues.append("공급 절에 표도 '지난 기간'·'확인 불가' 문장도 없다")
    else:
        for name, r in _read_table(sec, "공급", "신호", "상태", _SUPPLY_STATE, issues).items():
            out["supply"][name] = {"state": r["state"], "mark": r.get("상태", ""), "head": r.get("값", ""),
                                   "detail": r.get("근거", ""), "ticket": r.get("티켓")}
            out["ticket_column"] = out["ticket_column"] or ("티켓" in r)
    jsec = _section_lines(text, "정기 작업")
    if jsec is None:
        issues.append("`## 정기 작업` 절이 없다")
    elif _first_table(jsec)[0] is None:
        issues.append("정기 작업 절에 표가 없다")
    else:
        for name, r in _read_table(jsec, "정기 작업", "작업", "결과", _JOB_STATE, issues).items():
            out["jobs"][name] = {"state": r["state"], "mark": r.get("결과", ""),
                                 "head": r.get("실제 실행", ""), "detail": r.get("건수", "")}
    return out


def alert_streaks(reports: list[tuple], kind: str) -> dict[str, dict]:
    """최신 리포트에서 끝나는 **경보 구간**. reports: [(날짜, parse_daily_report 결과, 경로)] 오래된→최신.

    - 구간을 **끊는 것은 ✅ 정상뿐이다**(`stop` = 끊은 날).
    - `na`(그 기간에 예정이 없던 주간 작업)는 세지도 끊지도 않는다 — 토요일 패널은 토요일에만 판정된다.
    - `unknown`(표가 없거나 ❔ — 서버 못 읽음·지난 기간·14:00 넘어 만든 당일 리포트)도 **세지도 끊지도 않는다.**
      세지 않은 날은 `gaps`(경보 사이)·`tail`(마지막 경보 뒤)로 돌려준다 — 건너뛴 사실을 숨기지 않는다.
      ★ 전에는 모름이 끊었다. 늦은 리포트가 하루걸러 끼면 🛑 8일이 지시서 0건·경고 0건이었다(QA-OPS3-3).
    """
    names: list[str] = []
    for _, p, _ in reports:
        names += [n for n in p[kind] if n not in names]
    out: dict[str, dict] = {}
    for name in names:
        run, gaps, tail, pend, stop = [], [], [], [], None
        for day, p, rel in reversed(reports):
            row = p[kind].get(name)
            st = row["state"] if row else "unknown"
            if st == "na":
                continue
            if st == "ok":
                stop = day
                break
            if st == "alert":
                (gaps if run else tail).extend(pend)
                pend = []
                run.append((day, row, rel))
            else:
                pend.append(day)
        if run:
            run.reverse()
            last = run[-1][1]
            out[name] = {"start": run[0][0], "end": run[-1][0], "n": len(run),
                         "days": [d for d, _, _ in run], "gaps": sorted(gaps), "tail": sorted(tail),
                         "stop": stop, "mark": last.get("mark", ""), "head": last.get("head", ""),
                         "detail": last.get("detail", ""), "files": [r for _, _, r in run]}
    return out


def ticket_is_open(status: str) -> bool:
    """백로그 상태 칸 → 아직 누가 맡고 있는가. '완료(배포 대기)'는 열린 것이다(라이브에는 아직 없다)."""
    s = re.sub(r"[*`]", "", status or "").strip()
    if not _CLOSED.match(s):
        return True
    return "대기" in s[:12]


def schedule_verdict(t: dict) -> tuple[bool, str]:
    """예약 작업 1건 → (고장인가, 사람이 읽는 상태). 사내 대시보드 정기 작업 표(`agent_dashboard.html` 의
    `d.schedule.map` — defaccc 2026-09-27)와 **같은 규칙에 둘을 더했다.**

    대시보드와 같은 것: 한 번도 안 돌았어도 다음 실행이 잡혀 있으면 '아직 때가 안 됨'(고장 아님),
    돌지도 않고 다음 실행도 없으면 고장('실행된 적 없음 · 예정도 없음' — 대시보드도 `bad`), 실행 중은
    정상(267009), 결과 0 이 아니면 실패(터널 09-16 0xC0000005 는 이것이다 — 대시보드에서도 이미 `bad`).

    대시보드에 **없는** 규칙 둘(대시보드는 결과가 0 이면 정상으로 칠한다):
    ⓐ 결과 0 인데 **다음 실행이 없으면** '다음 실행 없음' — 다시는 안 돈다.
    ⓑ **꺼진 작업**(Disabled)은 '꺼짐(Disabled)'. 일부러 끈 작업이면 org-contracts §3.1 받는 자리를 `-` 로 둔다
       — 아니면 24시간 뒤 결재함에 올라간다.
    """
    nxt = str(t.get("next_run") or "")
    if t.get("never_ran"):
        return (False, "아직 때가 안 됨") if nxt else (True, "실행된 적 없음 · 예정도 없음")
    if t.get("running"):
        return False, "실행 중"
    if t.get("enabled") is False:
        return True, "꺼짐(Disabled)"
    if not t.get("ok"):
        res = str(t.get("last_result", ""))
        hx = f"(0x{int(res) & 0xFFFFFFFF:08X})" if res.lstrip("-").isdigit() else ""
        return True, f"실패 · 결과 {res}{hx}" + ("" if nxt else " · 다음 실행 없음")
    if not nxt:
        return True, "다음 실행 없음"
    return False, "정상"


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


# ── 마크다운·머리말 ─────────────────────────────────────────────────────────
def md_rows(text: str, section: str, ncells: int) -> list[list[str]]:
    """`## <section>` 구간 안 표에서 셀 수가 맞고 첫 칸이 백틱인 행만.

    agent_dashboard._md_rows 와 같은 규칙이다 — 구간을 안 자르면 다른 절의 표까지 먹는다
    (2026-09-23 부서표 파서가 §4 보고 리듬 표를 부서로 읽은 전례).
    """
    out, inside = [], False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            inside = s.startswith(section)
            continue
        if not inside or not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) != ncells or not cells[0].startswith("`"):
            continue
        out.append(cells)
    return out


def split_front(text: str) -> tuple[dict | None, str]:
    """맨 첫 줄이 `---` 인 YAML 머리말만 읽는다. 없거나 깨졌으면 (None, 원문).

    ★ 깨진 머리말을 빈 dict 로 바꾸지 않는다 — '머리말 없음' 과 '머리말이 틀림' 은 다르다.
      틀린 것은 호출자가 경고로 드러낸다.
    """
    if not text.startswith("---"):
        return None, text
    lines = text.splitlines()
    for i in range(1, min(len(lines), 80)):
        if lines[i].strip() == "---":
            head = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1:])
            if yaml is None:
                raise RuntimeError("PyYAML 이 없다 — pip install -r requirements.txt")
            try:
                meta = yaml.safe_load(head) or {}
            except Exception:                              # noqa: BLE001
                return {"__broken__": True}, body
            return (meta if isinstance(meta, dict) else {"__broken__": True}), body
    return None, text


def dump_front(meta: dict, body: str) -> str:
    head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, default_flow_style=False).strip()
    return f"---\n{head}\n---\n{body.rstrip()}\n"


# ── 조직 ────────────────────────────────────────────────────────────────────
class Org:
    """한 저장소의 순환계. 테스트에서는 임시 폴더를 root 로 준다."""

    def __init__(self, root: Path | str = REPO):
        self.root = Path(root)
        self.contracts_md = self.root / "docs" / "org-contracts.md"
        self.orders_dir = self.root / "orders"
        self.reports_dir = self.root / "reports"
        self.backlog_md = self.root / "docs" / "backlog.md"
        self.standups = self.root / "docs" / "standups"
        self.bus = self.root / "data" / "org-bus.jsonl"
        self.state_file = self.root / "data" / "org-state.json"
        self.dispatch_logs = self.root / "data" / "org-dispatch"
        self.daily_dir = self.root / "docs" / "daily-reports"
        self.warnings: list[str] = []
        self.claude_exe = ""
        # scan --dry-run: 지시서·버스·상태 파일을 **하나도 쓰지 않고** 무엇이 생길지만 본다(OPS-3)
        self.dry_run = False
        self.dry_events: list[dict] = []
        self.dry_orders: list[dict] = []

    def dry_orders_summary(self) -> list[dict]:
        return [{"id": o["meta"]["id"], "to": o["meta"]["to"], "reason": o["meta"]["reason"],
                 "key": o["meta"]["key"], "ticket": o["meta"]["ticket"],
                 "purpose": o["body"].split("## 목적", 1)[-1].strip().splitlines()[0][:200]}
                for o in self.dry_orders]

    # ── 계약 ──
    def contracts(self) -> tuple[dict, dict]:
        """(설정, 자리별 계약). 문서가 없으면 빈 값 + 경고 — 0 으로 채운 척하지 않는다."""
        settings = {"자동 디스패치": "꺼짐", "하루 디스패치 상한": 0,
                    "정체 기준(일)": 3, "기본 왕복 상한": 3}
        seats: dict[str, dict] = {}
        if not self.contracts_md.exists():
            self.warnings.append("docs/org-contracts.md 가 없다 — 인계 계약을 읽지 못했다")
            return settings, seats
        text = self.contracts_md.read_text(encoding="utf-8")
        for c in md_rows(text, "## 1.", 3):
            k = c[0].strip("`")
            v = c[1].strip("`")
            settings[k] = int(v) if v.isdigit() else v
        for c in md_rows(text, "## 2.", 6):
            name = c[0].strip("`")
            rh = c[4].strip("`").strip()
            cap = c[5].strip("`").strip()
            seats[name] = {
                "name": name,
                "wakes_on": c[1],
                "routes": _TICK.findall(c[2]),
                "auto": c[3].strip("`").strip() == "예",
                "rhythm": int(rh) if rh.isdigit() else None,
                "cap": int(cap) if cap.isdigit() else None,
            }
        if not seats:
            self.warnings.append("org-contracts.md §2 에서 계약 표를 찾지 못했다 — 형식이 바뀌었는지 볼 것")
        return settings, seats

    def alert_routes(self) -> dict[str, dict]:
        """§3.1 '경보 신호 → 담당 · 티켓' 표 → {신호: {source, seat, watch, ticket, note}}.

        - `받는 자리` 가 `-` 면 **이 신호로는 지시서를 만들지 않는다**(같은 원인을 다른 신호가 본다 —
          두 번 세면 결재함에 같은 일이 두 장 쌓인다). 티켓 칸은 그래도 리포트 표기에 쓴다.
        - 표에 없는 신호는 `steward`·티켓 없음으로 본다(OPS-3 지시: 표에 없으면 steward).
        """
        if not self.contracts_md.exists():
            return {}
        out: dict[str, dict] = {}
        for c in md_rows(self.contracts_md.read_text(encoding="utf-8"), "## 3.", 5):
            name = c[0].strip("`").strip()
            seat = c[2].strip("`").strip()
            t = c[3].strip("`* ").strip()
            watch = seat not in ("-", "—")
            out[name] = {"name": name, "source": c[1].strip("`").strip(),
                         "seat": seat if watch and seat else "", "watch": watch,
                         "ticket": "" if t in ("", "-", "—") else t, "note": c[4]}
        if not out:
            self.warnings.append("org-contracts.md §3.1 경보 표를 찾지 못했다 — 경보는 전부 steward·티켓 없음으로 본다")
        return out

    def backlog_tickets(self) -> dict[str, dict]:
        """백로그의 `ID … 상태` 표 **전부**에서 {ID: {status, title}}. 담당 열이 없는 표도 읽는다
        (티켓이 열려 있는지만 보면 되기 때문이다 — 배분 대상 판정인 backlog_todo 와 목적이 다르다)."""
        if not self.backlog_md.exists():
            return {}
        out: dict[str, dict] = {}
        cols = None
        for line in self.backlog_md.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s.startswith("|"):
                cols = None
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if cells and cells[0] == "ID":
                cols = cells
                continue
            if not cols or "상태" not in cols or len(cells) != len(cols) or set(cells[0]) <= set("-: "):
                continue
            out.setdefault(cells[0].strip("`* "), {"status": cells[cols.index("상태")], "title": cells[1][:60]})
        return out

    def signal_tickets(self) -> dict[str, dict]:
        """{신호: {ticket, state, status}} — 일일 리포트·주간 보고가 쓰는 티켓 표기의 원천(§3.1 + 백로그)."""
        routes, tickets = self.alert_routes(), self.backlog_tickets()
        out = {}
        for name, r in routes.items():
            t = r.get("ticket") or ""
            state, _ = self._ticket_view(t, tickets)
            out[name] = {"ticket": t, "state": state, "status": (tickets.get(t) or {}).get("status", "")}
        return out

    def _ticket_view(self, ticket: str, tickets: dict) -> tuple[str, bool]:
        """(상태 낱말, 열려 있나). 낱말은 '' · '열림' · '닫힘' · '백로그에 없음'."""
        if not ticket:
            return "", False
        info = tickets.get(ticket)
        if info is None:
            return "백로그에 없음", False
        return ("열림", True) if ticket_is_open(info["status"]) else ("닫힘", False)

    # ── 지시서 ──
    def orders(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        if not self.orders_dir.exists():
            return out
        for f in sorted(self.orders_dir.glob("*.md")):
            if f.name == "README.md":
                continue
            meta, body = split_front(f.read_text(encoding="utf-8"))
            if not meta or meta.get("__broken__") or not meta.get("id"):
                self.warnings.append(f"지시서 머리말을 읽지 못했다: {f.name}")
                continue
            meta["id"] = str(meta["id"])
            out[meta["id"]] = {"meta": meta, "body": body, "path": f}
        return out

    def _next_id(self, orders: dict, day: str) -> str:
        n = 0
        for oid in orders:
            m = _ID.match(oid)
            if m and m.group(1) == day:
                n = max(n, int(m.group(2)))
        return f"{day}-{n + 1:02d}"

    def save_order(self, o: dict) -> None:
        if self.dry_run:
            return
        self.orders_dir.mkdir(parents=True, exist_ok=True)
        o["path"].write_text(dump_front(o["meta"], o["body"]), encoding="utf-8", newline="\n")

    def create_order(self, orders: dict, *, to: str, frm: str, purpose: str, reason: str,
                     key: str = "", ticket: str = "", inputs: list[str] | None = None,
                     scope: str = "", done_when: str = "", due_days: int = 2,  # 0 = 당일(경보)
                     rnd: int | None = None, now: datetime | None = None) -> dict:
        now = now or _now()
        oid = self._next_id(orders, now.date().isoformat())
        ticket = ticket or oid
        if rnd is None:
            rnd = 1 + sum(1 for x in orders.values()
                          if str(x["meta"].get("ticket")) == ticket and x["meta"].get("to") == to
                          and x["meta"].get("status") != "cancelled")
        # 티켓이 없으면 지시서 번호가 티켓이 된다 — 그때 파일명에 날짜가 두 번 찍히지 않게 사유를 쓴다
        slug = re.sub(r"[^\w가-힣-]+", "-", ticket if ticket != oid else reason)[:40].strip("-")
        meta = {
            "id": oid, "to": to, "from": frm, "ticket": ticket, "status": "open",
            "round": rnd, "reason": reason, "key": key or f"{reason}:{oid}",
            "due": (now + timedelta(days=due_days)).date().isoformat(),
            "created": now.isoformat(),
            "inputs": list(inputs or []),
            "output": (f"reports/{now.date().isoformat()}-{to}-{slug}"
                       f"{'-r' + str(rnd) if rnd > 1 else ''}.md") if to != STEWARD else "",
        }
        body = (f"## 목적\n{purpose.strip()}\n\n"
                f"## 범위\n{scope.strip() or '포함: 목적에 적힌 것 · 제외: 오너 승인 항목(ORG §3) 전부'}\n\n"
                f"## 완료 기준\n{done_when.strip() or '보고서 머리말(`_handoff-protocol.md`)에 이 지시서 번호를 달아 `output` 경로에 남긴다.'}\n")
        o = {"meta": meta, "body": body, "path": self.orders_dir / f"{oid}.md"}
        orders[oid] = o
        if self.dry_run:
            self.dry_orders.append(o)
        self.save_order(o)
        self.emit("order.created", order=oid, to=to, frm=frm, ticket=ticket,
                  note=purpose.strip().splitlines()[0][:80], reason=reason)
        return o

    def set_status(self, o: dict, status: str, note: str = "", **extra) -> None:
        o["meta"]["status"] = status
        o["meta"]["updated"] = _now().isoformat()
        if note:
            o["meta"]["note"] = note
        o["meta"].update({k: v for k, v in extra.items() if v not in (None, "")})
        self.save_order(o)
        self.emit("order." + status, order=o["meta"]["id"], to=o["meta"].get("to"),
                  ticket=o["meta"].get("ticket"), note=note)

    # ── 이벤트 버스(data/ — git 제외) ──
    def emit(self, kind: str, **kw) -> None:
        rec = {"ts": _now().isoformat(), "kind": kind}
        rec.update({k: v for k, v in kw.items() if v not in (None, "")})
        if self.dry_run:
            self.dry_events.append(rec)
            return
        try:
            self.bus.parent.mkdir(parents=True, exist_ok=True)
            with open(self.bus, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass                                           # 기록 한 줄 때문에 순환을 세우지 않는다

    def events(self, since: datetime | None = None) -> list[dict]:
        if not self.bus.exists():
            return []
        out = []
        with open(self.bus, "r", encoding="utf-8", errors="replace") as f:
            for ln in f:
                try:
                    e = json.loads(ln)
                except Exception:                          # noqa: BLE001
                    continue
                if since and str(e.get("ts", "")) < since.isoformat():
                    continue
                out.append(e)
        return out

    def _state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:                                  # noqa: BLE001
            return {"reports": {}}

    def _save_state(self, st: dict) -> None:
        if self.dry_run:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── 백로그 ──
    def backlog_todo(self) -> list[dict]:
        """`담당` 열이 있는 표에서 상태가 todo 로 시작하는 티켓. 분류 표(유료 훅 등)는 배분 대상이 아니다."""
        if not self.backlog_md.exists():
            return []
        out, cols = [], None
        for line in self.backlog_md.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s.startswith("|"):
                cols = None
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if cells and cells[0] == "ID":
                cols = cells
                continue
            if not cols or len(cells) != len(cols) or "담당" not in cols or set(cells[0]) <= set("-: "):
                continue
            st = cells[cols.index("상태")] if "상태" in cols else ""
            if not re.match(r"^\**todo", st):
                continue
            out.append({"id": cells[0].strip("`* "), "title": cells[1][:60],
                        "owner": cells[cols.index("담당")], "status": st})
        return out

    # ── 리듬 — 대시보드와 **같은 함수**로 잰다(정의가 두 벌이면 둘이 다른 말을 한다) ──
    def rhythm_states(self) -> list[dict]:
        tools_dir = str(Path(__file__).resolve().parent)
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        try:
            import agent_dashboard as ad                   # noqa: WPS433
        except Exception as e:                             # noqa: BLE001
            self.warnings.append(f"리듬을 재지 못했다(agent_dashboard import 실패: {type(e).__name__})")
            return []
        saved = (ad.ROOT, ad.UTIL_MD)
        ad.ROOT, ad.UTIL_MD = self.root, self.root / "docs" / "agent-utilization.md"
        try:
            _, rhythms, err = ad.read_utilization()
            if err:
                self.warnings.append(err)
            return ad.check_rhythms(rhythms)
        finally:
            ad.ROOT, ad.UTIL_MD = saved

    # ── 예약 작업 — 대시보드 정기 작업 표와 **같은 함수**(agent_dashboard.read_schedule) ──
    def schedule_states(self) -> tuple[list[dict], str | None]:
        """(작업 목록, 못 읽은 사유). 빈 목록 + 사유는 '작업이 없다'가 아니라 **'못 읽었다'** 이다."""
        tools_dir = str(Path(__file__).resolve().parent)
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        try:
            import agent_dashboard as ad                   # noqa: WPS433
        except Exception as e:                             # noqa: BLE001
            return [], f"예약 작업을 읽지 못했다(agent_dashboard import 실패: {type(e).__name__})"
        return ad.read_schedule()

    # ── 경보 입력(OPS-3) ────────────────────────────────────────────────────
    def daily_reports(self, now: datetime, days: int = ALERT_LOOKBACK_DAYS) -> list[tuple]:
        """최근 일일 리포트 [(날짜, 해석, 경로)] 오래된→최신. 오늘 이후 날짜 파일은 보지 않는다.

        형식이 어긋난 리포트(`parse_daily_report` 의 `issues`)는 **파일명을 붙여 경고**로 올린다 —
        스탠드업 '읽지 못한 것'에 나온다. 경고 없이 경보 0건이 되는 것을 막는다(QA-OPS3-2).
        """
        if not self.daily_dir.exists():
            return []
        lo, hi = (now - timedelta(days=days)).date().isoformat(), now.date().isoformat()
        out = []
        for f in sorted(self.daily_dir.glob("*.md")):
            m = re.match(r"^(\d{4}-\d{2}-\d{2})\.md$", f.name)
            if not m or not (lo <= m.group(1) <= hi):
                continue
            rel = f.relative_to(self.root).as_posix()
            p = parse_daily_report(f.read_text(encoding="utf-8", errors="replace"), day=m.group(1))
            if p["issues"]:
                self.warnings.append(f"일일 리포트 `{rel}` 형식이 달라 경보를 못 읽었을 수 있다 — "
                                     + " · ".join(p["issues"]))
            out.append((m.group(1), p, rel))
        return out

    def alert_eval(self, now: datetime, settings: dict, seats: dict, orders: dict,
                   routes: dict | None = None, tickets: dict | None = None,
                   st: dict | None = None) -> list[dict]:
        """지금 경보인 신호마다 무엇을 할지. 지시서는 만들지 않는다(scan 이 action=='order' 만 만든다).

        action: order(만든다) · below(연속 기준 전) · ticket-open(열린 티켓이 맡음) · done-before
        (이 연속 구간의 지시서를 이미 만들었다 — 닫혔어도 다시 안 만든다) · open-order(같은 신호의
        열린 지시서가 있다) · not-watched(§3.1 받는 자리 `-`).

        ★ 구간의 정체(시작일·지시서 id)는 상태 파일 `alert_runs` 에 **고정**한다(QA-OPS3-1).
          멱등 키 `alert:<신호>:<구간 첫 날짜>` 의 날짜를 리포트에서 매번 다시 계산하면 날짜가 움직였다 —
          ⑴ 조회 창(ALERT_LOOKBACK_DAYS)보다 긴 경보는 창이 밀릴 때마다 첫 날짜가 하루씩 밀렸고(30일 멈춤 →
          '의도된 상태'로 닫을 때마다 새 지시서, 9건), ⑵ 지난 리포트를 다시 만들면 그날이 '❔ 지난 기간'이
          되어 첫 날짜가 밀렸다(같은 장애로 두 번째 지시서). 이제 **✅ 정상 리포트가 끼기 전까지** 같은 구간이고
          첫 날짜는 처음 본 날 그대로다. `st` 를 안 주면(순수 조회) 이번 계산만 쓴다.
        """
        need = int(settings.get("경보 연속 기준(리포트)") or 2)
        routes = self.alert_routes() if routes is None else routes
        tickets = self.backlog_tickets() if tickets is None else tickets
        reps = self.daily_reports(now)
        lo = (now - timedelta(days=ALERT_LOOKBACK_DAYS)).date().isoformat()
        segs = (st if st is not None else {}).setdefault("alert_runs", {})
        out = []
        for kind, source in (("supply", "공급"), ("jobs", "정기 작업")):
            runs = alert_streaks(reps, kind)
            # 지금 경보가 아닌 신호의 구간 — ✅ 를 봤으면 끝났다. 창 안에 모름뿐이면 아직 모른다(남겨 둔다).
            # 다만 마지막 경보가 창보다 오래됐으면 버린다: 3주 넘게 아무것도 몰랐던 뒤의 경보는 새로 본다.
            for name in [n for n, g in segs.items() if g.get("kind", kind) == kind and n not in runs]:
                seen_ok = any((p[kind].get(name) or {}).get("state") == "ok" for _, p, _ in reps)
                if seen_ok or str(segs[name].get("last", "")) < lo:
                    segs.pop(name, None)
            for name, s in runs.items():
                old = segs.get(name) or {}
                same = (bool(old) and old.get("kind", kind) == kind and str(old.get("last", "")) >= lo
                        and (s["stop"] is None or s["stop"] < str(old.get("start", ""))))
                if same:
                    start = str(old["start"])
                    days = sorted(set(old.get("days") or []) | set(s["days"]))
                    oid = str(old.get("order") or "")
                else:
                    start, days, oid = s["start"], list(s["days"]), ""
                segs[name] = {"kind": kind, "start": start, "last": days[-1], "days": days, "order": oid}
                s = dict(s, start=start, n=len(days))
                r = routes.get(name) or {}
                ticket = r.get("ticket", "")
                tstate, topen = self._ticket_view(ticket, tickets)
                seat = r.get("seat") or STEWARD
                if seat != STEWARD and seat not in seats:
                    self.warnings.append(f"§3.1 `{name}` 의 받는 자리 `{seat}` 가 §2 에 없다 — steward 로 보낸다")
                    seat = STEWARD
                key = f"alert:{name}:{s['start']}"
                if r and not r.get("watch", True):
                    action = "not-watched"
                elif s["n"] < need:
                    action = "below"
                elif topen:
                    action = "ticket-open"
                elif oid or any(x["meta"].get("key") == key for x in orders.values()):
                    action = "done-before"
                elif any(str(x["meta"].get("key", "")).startswith(f"alert:{name}:")
                         and x["meta"].get("status") in OPEN_STATES for x in orders.values()):
                    action = "open-order"
                else:
                    action = "order"
                out.append({"name": name, "source": source, "n": s["n"], "need": need,
                            "start": s["start"], "end": s["end"], "mark": s["mark"], "head": s["head"],
                            "detail": s["detail"], "files": s["files"], "gaps": s["gaps"], "tail": s["tail"],
                            "order": oid, "ticket": ticket,
                            "ticket_state": tstate, "seat": seat, "key": key, "action": action,
                            "note": r.get("note", "")})
        return out

    def task_eval(self, now: datetime, settings: dict, seats: dict, orders: dict, st: dict,
                  routes: dict | None = None, tickets: dict | None = None) -> list[dict]:
        """예약 작업 고장이 `예약 작업 실패 지속(시간)` 을 넘었는가. 고장 시작은 상태 파일에 적어 둔다.

        고장 시작 = min(처음 본 시각, 실패한 마지막 실행 시각). 마지막 실행이 실패였다면 그 뒤로 성공이
        없었다는 뜻이라 그 시각부터 센다(09-16 에 죽은 터널은 첫 스캔에서 바로 '11일째'다). 매시 실패하는
        작업은 마지막 실행이 늘 최근이므로 **처음 본 시각**이 기준이 된다 — 그래서 상태 파일에 남긴다.
        """
        sched, err = self.schedule_states()
        if err:
            self.warnings.append(err)
            return []
        hours = int(settings.get("예약 작업 실패 지속(시간)") or 24)
        routes = self.alert_routes() if routes is None else routes
        tickets = self.backlog_tickets() if tickets is None else tickets
        bad_since = st.setdefault("task_bad", {})
        present = {t["name"] for t in sched}
        rows = [dict(t) for t in sched]
        # 표(§3.1 예약 작업)에 있는데 목록에 없으면 '미등록' — 목록을 **읽었을 때만**(defaccc 규칙)
        rows += [{"name": n, "missing": True} for n, r in routes.items()
                 if r.get("source") == "예약 작업" and n not in present]
        out = []
        for t in rows:
            name = t["name"]
            bad, label = (True, "미등록") if t.get("missing") else schedule_verdict(t)
            if not bad:
                bad_since.pop(name, None)
                continue
            cand = now.isoformat()
            last = str(t.get("last_run") or "")
            if label.startswith("실패") or label == "다음 실행 없음":
                with contextlib.suppress(ValueError):
                    cand = min(cand, datetime.fromisoformat(last).isoformat())
            since = min(bad_since.get(name) or cand, cand)
            bad_since[name] = since
            age_h = int((now - datetime.fromisoformat(since)).total_seconds() // 3600)
            r = routes.get(name) or {}
            ticket = r.get("ticket", "")
            tstate, topen = self._ticket_view(ticket, tickets)
            seat = r.get("seat") or STEWARD
            if seat != STEWARD and seat not in seats:
                seat = STEWARD
            key = f"task:{name}:{since[:16]}"
            if r and not r.get("watch", True):
                action = "not-watched"
            elif age_h < hours:
                action = "below"
            elif topen:
                action = "ticket-open"
            elif any(x["meta"].get("key") == key for x in orders.values()):
                action = "done-before"
            elif any(str(x["meta"].get("key", "")).startswith(f"task:{name}:")
                     and x["meta"].get("status") in OPEN_STATES for x in orders.values()):
                action = "open-order"
            else:
                action = "order"
            out.append({"name": name, "label": label, "since": since, "hours": age_h, "need_hours": hours,
                        "last_run": last, "next_run": str(t.get("next_run") or ""),
                        "ticket": ticket, "ticket_state": tstate, "seat": seat, "key": key,
                        "action": action, "note": r.get("note", "")})
        for n in [n for n in bad_since if n not in {t["name"] for t in rows}]:
            bad_since.pop(n, None)                         # 지워진 작업의 기록을 끌고 다니지 않는다
        return out

    # ── 스캔 ────────────────────────────────────────────────────────────────
    def scan(self, now: datetime | None = None) -> dict:
        now = now or _now()
        settings, seats = self.contracts()
        orders = self.orders()
        st = self._state()
        made: list[str] = []
        closed: list[str] = []
        legacy = 0

        def has_key(key: str, open_only: bool = False) -> bool:
            return any(x["meta"].get("key") == key
                       and (not open_only or x["meta"].get("status") in OPEN_STATES)
                       for x in orders.values())

        def make(**kw) -> None:
            o = self.create_order(orders, now=now, **kw)
            made.append(o["meta"]["id"])

        # ① 보고서 머리말 → 지시서 닫기·인계
        for f in sorted(self.reports_dir.glob("*.md")) if self.reports_dir.exists() else []:
            if f.name == "README.md":
                continue
            rel = f.relative_to(self.root).as_posix()
            mt = f.stat().st_mtime
            if st["reports"].get(rel) == mt:
                continue
            meta, _ = split_front(f.read_text(encoding="utf-8", errors="replace"))
            if meta is None:
                legacy += 1
                st["reports"][rel] = mt
                continue
            if meta.get("__broken__") or not meta.get("from"):
                self.warnings.append(f"보고서 머리말이 규약과 다르다: {rel} (from 없음 또는 YAML 오류)")
                st["reports"][rel] = mt
                continue
            frm = str(meta["from"])
            result = str(meta.get("result") or "done")
            if result not in RESULTS:
                self.warnings.append(f"{rel}: result '{result}' 는 규약에 없다 — done 으로 읽지 않고 blocked 로 본다")
                result = "blocked"
            parent = orders.get(str(meta.get("order") or ""))
            ticket = str(meta.get("ticket") or (parent["meta"].get("ticket") if parent else "") or "")
            if parent and parent["meta"].get("status") in OPEN_STATES:
                self.set_status(parent, "blocked" if result == "blocked" else "done",
                                note=f"보고서 {rel} · result {result}", report=rel, result=result)
                closed.append(parent["meta"]["id"])
            elif meta.get("order") and not parent:
                self.warnings.append(f"{rel}: 지시서 {meta.get('order')} 가 orders/ 에 없다")
            ticket = ticket or (parent["meta"]["id"] if parent else "")
            # OPS-3 ⑦: 워크플로가 쓴 보고서의 다음 단계는 **워크플로가 부른다.** 여기서 또 만들면
            # 이미 돌고 있는 단계가 두 장이 된다(2026-09-27 중복 지시서 11건 — Steward 가 취소).
            workflow = str(meta.get("workflow") or "").strip()
            skipped = st.setdefault("skipped", [])

            def skip(key: str, kind: str, to: str, why: str) -> None:
                if key not in skipped:                     # 같은 보고서를 다시 읽어도 기록은 한 번
                    skipped.append(key)
                    self.emit(kind, frm=frm, to=to, ticket=ticket, note=why[:120], report=rel)

            hand = meta.get("handoff") or []
            if isinstance(hand, dict):
                hand = [hand]
            routes = set(seats.get(frm, {}).get("routes", []))
            for h in hand:
                to = str((h or {}).get("to") or "").strip()
                why = str((h or {}).get("why") or "").strip() or "(사유 없음 — 보고서를 읽을 것)"
                if not to:
                    continue
                key = f"handoff:{rel}>{to}"
                if has_key(key):
                    continue
                if workflow:
                    skip(key, "handoff.skipped", to, f"workflow {workflow} 가 다음 단계를 부른다")
                    continue
                if parent and str(parent["meta"].get("from")) == STEWARD and ticket:
                    dup = [x["meta"]["id"] for x in orders.values()
                           if x is not parent and str(x["meta"].get("ticket")) == ticket
                           and x["meta"].get("to") == to and x["meta"].get("status") in ("open", "doing")]
                    if dup:
                        skip(key, "handoff.skipped", to,
                             f"Steward 발행 지시서의 답 — 같은 티켓·같은 자리로 열린 지시서 {dup[0]} 가 있다")
                        continue
                if to != STEWARD and (to not in seats or to not in routes):
                    make(to=STEWARD, frm="org-runtime", reason="route", key=key, ticket=ticket,
                         inputs=[rel], purpose=f"계약에 없는 인계: `{frm}` → `{to}` — {why}",
                         scope="포함: 이 경로를 허용할지(org-contracts §2 개정 = 오너 승인) 또는 다른 담당으로 돌릴지 결정")
                    self.emit("handoff.rejected", frm=frm, to=to, ticket=ticket, note=why[:80])
                    continue
                rnd = 1 + sum(1 for x in orders.values()
                              if str(x["meta"].get("ticket")) == ticket and x["meta"].get("to") == to
                              and x["meta"].get("status") != "cancelled") if ticket else 1
                cap = (seats.get(to, {}).get("cap") or int(settings.get("기본 왕복 상한") or 3))
                if to != STEWARD and ticket and rnd > cap:
                    ck = f"cap:{ticket}>{to}"
                    if not has_key(ck, open_only=True):
                        make(to=STEWARD, frm="org-runtime", reason="cap", key=ck, ticket=ticket,
                             inputs=[rel], purpose=(f"왕복 상한 초과 — `{ticket}` 에서 `{to}` 가 {rnd}번째 "
                                                    f"지시서를 받을 차례다(상한 {cap}). 더 돌리지 말고 결정한다: {why}"),
                             scope="포함: 지금 안으로 닫을지 · 범위를 줄여 분리할지(CLAUDE.md 운영 규칙 7) · 오너 판단")
                    self.emit("handoff.capped", frm=frm, to=to, ticket=ticket, note=f"{rnd}>{cap}")
                    st.setdefault("capped", []).append(key)
                    continue
                make(to=to, frm=frm, reason="handoff", key=key, ticket=ticket, inputs=[rel],
                     purpose=why, rnd=rnd)
                self.emit("handoff", frm=frm, to=to, ticket=ticket, note=why[:80])

            if result in ("fail", "blocked") and not hand and not has_key(f"result:{rel}"):
                if workflow:
                    # 반려·재배분도 워크플로가 결과를 읽고 정한다 — PM 에게 같은 판정을 한 번 더 맡기지 않는다.
                    # needs-owner 는 막지 않는다(오너 결정은 결재함에 반드시 올라가야 한다).
                    skip(f"result:{rel}", "result.skipped", "pm-orchestrator",
                         f"workflow {workflow} 가 {result} 를 받는다")
                else:
                    make(to="pm-orchestrator", frm=frm, reason="result", key=f"result:{rel}", ticket=ticket,
                         inputs=[rel], purpose=f"`{frm}` 가 `{result}` 로 끝냈는데 다음 담당을 적지 않았다. 반려·재배분을 판정한다.")
            if result == "needs-owner" and not has_key(f"owner:{rel}"):
                make(to=STEWARD, frm=frm, reason="owner", key=f"owner:{rel}", ticket=ticket, inputs=[rel],
                     purpose=f"`{frm}` 가 오너 결정을 요청했다 — 보고서를 재현한 뒤(CLAUDE.md 규칙 5) 오너에게 올린다.")
            st["reports"][rel] = mt

        # ② 리듬 중단 → 담당 또는 결재함
        for r in self.rhythm_states():
            if r.get("state") not in ("늦음", "끊김", "없음"):
                continue
            key = f"rhythm:{r['glob']}"
            if has_key(key, open_only=True):
                continue
            owners = [n for n in _TICK.findall(r.get("owner", "")) if seats.get(n, {}).get("auto")]
            to = owners[0] if owners else STEWARD
            make(to=to, frm="org-runtime", reason="rhythm", key=key,
                 purpose=(f"리듬 `{r['state']}` — `{r['glob']}` 마지막 {r.get('last') or '없음'}"
                          f"({r.get('age') if r.get('age') is not None else '—'}일 전, 주기 {r['period']}일). "
                          f"끊기면: {r.get('impact', '')}"),
                 scope=("포함: 왜 멈췄는지 산출물·로그로 확인하고, 사람이 할 조치가 있으면 그것만 적는다. "
                        "제외: 리듬을 맞추려고 파일을 대신 쓰는 것(agent-utilization §3)"))

        # ③ 미배분 티켓 → PM (하루 한 건)
        referenced = {str(x["meta"].get("ticket")) for x in orders.values()
                      if x["meta"].get("status") != "cancelled"}
        todo = [t for t in self.backlog_todo() if t["id"] not in referenced]
        ukey = f"unassigned:{now.date().isoformat()}"
        if todo and "pm-orchestrator" in seats and not has_key(ukey) \
                and not any(x["meta"].get("reason") == "unassigned" and x["meta"].get("status") in OPEN_STATES
                            for x in orders.values()):
            lines = "\n".join(f"- `{t['id']}` {t['title']} — 담당 칸: {t['owner']}" for t in todo[:60])
            make(to="pm-orchestrator", frm="org-runtime", reason="unassigned", key=ukey,
                 inputs=["docs/backlog.md", "docs/org-contracts.md"],
                 purpose=(f"백로그 `todo` 중 지시서가 없는 티켓 {len(todo)}건. 이번 주에 착수할 것 최대 3건을 고르고 "
                          f"각각 담당·완료 기준을 정해 보고서 `handoff:` 로 넘긴다. 나머지는 왜 기다리는지 한 줄씩."),
                 scope=f"대상 티켓:\n{lines}" + ("\n- …(60건까지만 적었다)" if len(todo) > 60 else ""))

        # ④ 정체 → PM (하루 한 건)
        lim = int(settings.get("정체 기준(일)") or 3)
        stale = []
        for x in orders.values():
            m = x["meta"]
            if m.get("status") not in ("open", "doing") or m.get("to") == STEWARD:
                continue
            try:
                age = (now - datetime.fromisoformat(str(m.get("created")))).days
            except ValueError:
                continue
            if age > lim:
                stale.append((m["id"], m.get("to"), age))
        skey = f"stale:{now.date().isoformat()}"
        if stale and "pm-orchestrator" in seats and not has_key(skey):
            make(to="pm-orchestrator", frm="org-runtime", reason="stale", key=skey,
                 inputs=[f"orders/{i}.md" for i, _, _ in stale],
                 purpose=f"{lim}일 넘게 열린 지시서 {len(stale)}건 — 막힌 이유를 찾아 재배분·취소·분리를 판정한다.",
                 scope="\n".join(f"- `{i}` → `{t}` · {a}일째" for i, t, a in stale))

        # ⑤ 계약상 리듬(일) — 그 기간 지시서가 한 건도 없던 자리
        for name, s in seats.items():
            if not s.get("rhythm"):
                continue
            since = now - timedelta(days=s["rhythm"])
            recent = any(x["meta"].get("to") == name
                         and str(x["meta"].get("created", "")) >= since.isoformat() for x in orders.values())
            rkey = f"routine:{name}:{now.date().isoformat()}"
            if recent or has_key(rkey):
                continue
            make(to=name, frm="org-runtime", reason="routine", key=rkey,
                 purpose=f"정기 점검({s['rhythm']}일 주기) — {s['wakes_on']}",
                 scope="볼 것이 없으면 `result: done` 한 줄로 닫는다. 분량을 채우지 않는다(_handoff-protocol §3).")

        # ⑥ 경보 → 지시서 (OPS-3) — 일일 리포트의 공급 신호·정기 작업이 연속 N개 리포트에서 이상·멈춤
        #    ★ 2026-09-24~26 케이카 경보가 사흘 떴는데 티켓 0 이었다. 화면에 뜨는 것과 누가 맡는 것은 다르다.
        routes, tickets = self.alert_routes(), self.backlog_tickets()
        alerts = self.alert_eval(now, settings, seats, orders, routes=routes, tickets=tickets, st=st)
        for a in alerts:
            if a["action"] != "order":
                continue
            if a["ticket_state"] == "닫힘":
                tnote = (f"표(org-contracts §3.1)의 티켓 `{a['ticket']}` 는 닫혔는데 경보가 계속된다 — "
                         "다시 열지, 새 티켓을 만들지 정한다.")
            elif a["ticket_state"] == "백로그에 없음":
                tnote = f"표의 티켓 `{a['ticket']}` 가 백로그에 없다 — 표를 고치거나 티켓을 만든다."
            else:
                tnote = "표(org-contracts §3.1)에 이 신호의 티켓이 없다 — **티켓 없음**."
            make(to=a["seat"], frm="org-runtime", reason="alert", key=a["key"],
                 ticket=a["ticket"] if a["ticket_state"] == "닫힘" else "",
                 inputs=a["files"] + ["docs/org-contracts.md", "docs/backlog.md"], due_days=0,
                 purpose=(f"경보 `{a['name']}`({a['source']}) — {a['mark']} **{a['n']}개 리포트 연속**"
                          f"({a['start']}~{a['end']}){_gap_note(a)}: {a['head']} · {a['detail'][:200]}"
                          f"\n\n{tnote}"),
                 scope=("포함: ⑴ 일일 리포트·서버 기록으로 원인 확인 ⑵ 티켓을 만들거나 기존 티켓에 붙이고 "
                        "org-contracts §3.1 티켓 칸을 채운다 ⑶ 의도된 상태면 근거를 적어 닫는다. "
                        "제외: 코드 수정·배포·서버 조작(오너 세션에서 담당에게 지시한다). "
                        "당직은 이 지시서를 부르지 않는다(org-contracts §3)."),
                 done_when="오늘 안에 티켓 ID 가 생기거나(백로그) '의도된 상태' 판정이 지시서 note 에 적힌다.")
            a["order"] = made[-1]
            st.setdefault("alert_runs", {}).setdefault(a["name"], {})["order"] = made[-1]   # 구간 = 지시서 한 장

        # ⑦ 예약 작업 고장 → 결재함 (OPS-3) — 대시보드 정기 작업 표와 같은 목록·같은 규칙
        tasks = self.task_eval(now, settings, seats, orders, st, routes=routes, tickets=tickets)
        for t in tasks:
            if t["action"] != "order":
                continue
            tnote = (f"표의 티켓 `{t['ticket']}` 는 {t['ticket_state']}." if t["ticket"]
                     else "표(org-contracts §3.1)에 이 작업의 티켓이 없다 — **티켓 없음**.")
            make(to=t["seat"], frm="org-runtime", reason="task", key=t["key"],
                 ticket=t["ticket"] if t["ticket_state"] == "닫힘" else "",
                 inputs=["docs/org-contracts.md", "docs/backlog.md"], due_days=0,
                 purpose=(f"예약 작업 `{t['name']}` — {t['label']} · **{t['hours']}시간째**"
                          f"(마지막 실행 {t['last_run'] or '없음'} · 다음 실행 {t['next_run'] or '없음'})\n\n{tnote}"),
                 scope=("포함: 작업 스케줄러·로그로 원인 확인, 티켓화, 재등록·재시작이 필요하면 오너에게 올린다"
                        "(관리자 권한). 제외: 당직이 작업을 고치는 것 — schtasks 는 당직 금지 목록에 있다."),
                 done_when="오늘 안에 티켓 ID 가 생기거나 작업이 정상으로 돌아왔음을 스케줄러 값으로 적는다.")
            t["order"] = made[-1]

        st["last_scan"] = now.isoformat()
        self._save_state(st)
        self.emit("scan", note=f"new {len(made)} · closed {len(closed)} · legacy {legacy}")
        return {"created": made, "closed": closed, "legacy_reports": legacy,
                "alerts": alerts, "tasks": tasks, "warnings": list(self.warnings)}

    # ── 대기열 요약(대시보드·브리핑 공용) ──────────────────────────────────
    def board(self, now: datetime | None = None) -> dict:
        now = now or _now()
        settings, seats = self.contracts()
        orders = self.orders()
        per: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        oldest: dict[str, int] = {}
        open_list = []
        for x in orders.values():
            m = x["meta"]
            to, stt = str(m.get("to")), str(m.get("status"))
            per[to][stt] += 1
            if stt in OPEN_STATES:
                try:
                    age = (now - datetime.fromisoformat(str(m.get("created")))).days
                except ValueError:
                    age = None
                if age is not None:
                    oldest[to] = max(oldest.get(to, 0), age)
                purpose = x["body"].split("## 목적", 1)[-1].strip().splitlines()
                open_list.append({"id": m["id"], "to": to, "from": m.get("from"), "status": stt,
                                  "ticket": m.get("ticket"), "reason": m.get("reason"), "round": m.get("round"),
                                  "age": age, "purpose": (purpose[0] if purpose else "")[:140],
                                  "auto": bool(seats.get(to, {}).get("auto"))})
        open_list.sort(key=lambda o: (o["to"] != STEWARD, -(o["age"] or 0)))
        week = now - timedelta(days=7)
        ev = self.events(since=week)
        routes = collections.Counter((e.get("frm"), e.get("to")) for e in ev if e.get("kind") == "handoff")
        today = now.date().isoformat()
        dispatched_today = sum(1 for e in ev if e.get("kind") == "dispatch.start"
                               and str(e.get("ts", "")).startswith(today))
        st = self._state()
        return {
            "enabled": self.contracts_md.exists(),
            "settings": settings,
            "seats": {n: {"auto": s["auto"], "rhythm": s["rhythm"], "routes": s["routes"]}
                      for n, s in seats.items()},
            "queue": {to: {"open": c["open"], "doing": c["doing"], "blocked": c["blocked"],
                           "done": c["done"], "oldest": oldest.get(to)} for to, c in per.items()},
            "open": open_list,
            "inbox": [o for o in open_list if o["to"] == STEWARD],
            "totals": {"open": sum(c["open"] for c in per.values()),
                       "doing": sum(c["doing"] for c in per.values()),
                       "blocked": sum(c["blocked"] for c in per.values()),
                       "inbox": sum(1 for o in open_list if o["to"] == STEWARD)},
            "routes_7d": [{"from": a, "to": b, "n": n} for (a, b), n in routes.most_common(20)],
            # 인계는 `handoff` 한 줄로 충분하다 — 같은 순간의 `order.created`(인계로 생긴 지시서)까지 두면
            # 피드가 두 줄씩 겹쳐 움직임이 두 배로 보인다(2026-09-26 첫 캡처에서 실측).
            "feed": [e for e in ev if e.get("kind") != "scan"
                     and not (e.get("kind") == "order.created" and e.get("reason") == "handoff")][-30:][::-1],
            "handoffs_7d": sum(routes.values()),
            "dispatched_today": dispatched_today,
            "last_scan": st.get("last_scan"),
            "warnings": list(self.warnings),
        }

    # ── 스탠드업 ────────────────────────────────────────────────────────────
    def standup(self, dispatch: int = 0, dry_run: bool = False, now: datetime | None = None) -> Path:
        now = now or _now()
        res = self.scan(now=now)
        b = self.board(now=now)
        settings = b["settings"]
        on = str(settings.get("자동 디스패치")) == "켜짐"
        cap = int(settings.get("하루 디스패치 상한") or 0)
        # 부를 수 있는 것(계약·상한 기준)과 이번에 실제로 부르는 것(--dispatch)을 따로 센다.
        # 브리핑만 요청한 실행에서 "부를 것이 없다"고 적으면 거짓이다 — 2026-09-27 첫 실제 실행에서 그렇게 적혔다.
        room = max(0, cap - b["dispatched_today"]) if on else 0
        eligible = self.dispatch_plan(b, limit=room)
        plan = eligible[:max(0, dispatch)]
        t = b["totals"]
        since = now - timedelta(days=1)
        ev = [e for e in self.events(since=since) if e.get("kind") in
              ("handoff", "handoff.capped", "handoff.rejected", "order.done", "order.blocked", "order.created")]

        L = [f"# 스탠드업 {now.date().isoformat()}",
             "",
             f"> `tools/org_runtime.py standup` 이 {now.strftime('%H:%M')} 에 썼다. 숫자는 `orders/` 와 "
             "`data/org-bus.jsonl` 에서 센 것이다 — 사람이 옮겨 적지 않았다.",
             "",
             "## [요약]",
             f"열린 지시서 **{t['open']}** · 진행 {t['doing']} · 막힘 **{t['blocked']}** · "
             f"결재함 **{t['inbox']}** · 지난 7일 인계 {b['handoffs_7d']}건",
             f"이번 스캔: 새 지시서 {len(res['created'])}건 · 닫힘 {len(res['closed'])}건"
             + (f" · 머리말 없는 옛 보고서 {res['legacy_reports']}건은 건너뜀" if res["legacy_reports"] else ""),
             ""]
        if b["inbox"]:
            L += ["## 결재함 — 오너·Steward 가 봐야 하는 것", ""]
            L += [f"- `{o['id']}` ({o['reason']}) {o['purpose']}" for o in b["inbox"]]
            L.append("")
        watch = alert_lines(res.get("alerts") or [], res.get("tasks") or [])
        if watch:
            L += ["## 경보 → 티켓", "",
                  "> 일일 리포트의 이상·멈춤과 예약 작업 고장이 **누구에게 가 있는지**. "
                  "표는 `docs/org-contracts.md` §3.1 이다.", ""] + watch + [""]
        L += ["## 자리별 대기열", "", "| 담당 | 자동 | 열림 | 진행 | 막힘 | 가장 오래된 |", "|---|---|---|---|---|---|"]
        for to in sorted(b["queue"], key=lambda k: (k == STEWARD, k)):
            q = b["queue"][to]
            if not (q["open"] or q["doing"] or q["blocked"]):
                continue
            auto = "결재함" if to == STEWARD else ("예" if b["seats"].get(to, {}).get("auto") else "아니오")
            L.append(f"| `{to}` | {auto} | {q['open']} | {q['doing']} | {q['blocked']} | "
                     f"{'—' if q['oldest'] is None else str(q['oldest']) + '일'} |")
        L.append("")
        L += ["## 지난 24시간 흐름", ""]
        L += ([f"- {str(e.get('ts', ''))[11:16]} `{e['kind']}` "
               f"{e.get('frm', '') + ' → ' if e.get('frm') else ''}{e.get('to', '')} "
               f"{e.get('order', '')} {e.get('note', '')}".rstrip() for e in ev] or ["- 움직임 없음"])
        L.append("")
        L += ["## 오늘 당직이 부르는 것", ""]
        if not on:
            L.append("- `자동 디스패치`가 `꺼짐`이다(org-contracts §1) — 부르지 않는다.")
        elif dispatch <= 0:
            L.append("- 이 실행은 **브리핑만** 했다(디스패치 요청 0건). 당직이 부를 수 있는 지시서는 "
                     f"{len(eligible)}건이다" + (":" if eligible else "."))
            L += [f"  - `{o['id']}` → `{o['to']}` · {o['purpose'][:90]}" for o in eligible]
        elif not plan:
            L.append("- 없음 — " + ("자동 실행 가능한 열린 지시서가 없다" if room else "하루 상한을 다 썼다")
                     + f"(오늘 {b['dispatched_today']}/{cap}).")
        else:
            L += [f"- `{o['id']}` → `{o['to']}` · {o['purpose'][:90]}" for o in plan]
            if len(eligible) > len(plan):
                L.append(f"- 그 밖 {len(eligible) - len(plan)}건은 다음 당직 차례다.")
        if res["warnings"]:
            L += ["", "## 읽지 못한 것", ""] + [f"- {w}" for w in res["warnings"]]

        self.standups.mkdir(parents=True, exist_ok=True)
        out = self.standups / f"{now.date().isoformat()}.md"
        out.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")

        for o in plan:
            self.dispatch(o["id"], dry_run=dry_run)
        return out

    # ── 디스패치 ────────────────────────────────────────────────────────────
    def dispatch_plan(self, b: dict, limit: int) -> list[dict]:
        """자동 실행할 지시서 고르기. PM 먼저(배분이 막히면 나머지가 다 막힌다), 그다음 오래된 순.

        한 자리에 `doing` 이 있으면 그 자리는 건너뛴다 — 한 번에 하나(pm-orchestrator 원칙).
        """
        if limit <= 0:
            return []
        busy = {o["to"] for o in b["open"] if o["status"] == "doing"}
        cand = [o for o in b["open"] if o["status"] == "open" and o["auto"] and o["to"] not in busy
                and o.get("reason") not in NO_DISPATCH_REASONS]      # 경보·예약 작업은 결재함에서만(§3)
        cand.sort(key=lambda o: (o["to"] != "pm-orchestrator", -(o["age"] or 0), o["id"]))
        out, seen = [], set()
        for o in cand:
            if o["to"] in seen:
                continue
            seen.add(o["to"])
            out.append(o)
            if len(out) >= limit:
                break
        return out

    def dispatch_prompt(self, o: dict) -> str:
        m = o["meta"]
        return f"""너는 Steward 당직이다 — 오너는 지금 없다(헤드리스 실행). CLAUDE.md 와 docs/ORG.md 를 따른다.
오늘은 지시서 **한 건만** 처리한다: orders/{m['id']}.md

1. orders/{m['id']}.md 와 거기 적힌 inputs 를 읽는다. .claude/agents/_handoff-protocol.md 도 읽는다.
2. `{m['to']}` 서브에이전트에게 Agent 도구로 위임한다. description 은 반드시 `{m['id']} ` 로 시작한다
   (대시보드가 이 번호로 '지시서를 거친 호출'을 센다). 프롬프트는 CLAUDE.md 의 [작업 지시서] 형식으로 쓴다.
3. 결과를 {m.get('output') or 'reports/ 아래 새 파일'} 에 쓴다. 파일 맨 첫 줄부터 머리말을 단다:
   order: {m['id']} / from: {m['to']} / ticket: {m.get('ticket', '')} / result / verified / handoff.
   handoff 의 to 는 docs/org-contracts.md §2 '넘길 수 있는 곳'에서만 고른다. 서브에이전트가 말한 다음 담당만 옮기고 지어내지 않는다.
4. 서브에이전트의 주장 중 코드·DB·라이브로 재현하지 못한 것은 verified: 미검증 으로 적는다(CLAUDE.md 운영 규칙 5).
5. 오너 승인 항목(ORG §3)에 닿으면 실행하지 말고 result: needs-owner 로 닫는다.
   커밋·푸시·배포·ssh·설정 변경·코드 편집은 하지 않는다 — 이 실행에는 그 권한이 없다.
6. 마지막으로 `python tools/org_runtime.py scan` 을 실행한다.
"""

    def dispatch(self, oid: str, dry_run: bool = False) -> dict:
        orders = self.orders()
        o = orders.get(oid)
        if not o:
            return {"ok": False, "why": f"지시서 {oid} 가 없다"}
        m = o["meta"]
        _, seats = self.contracts()
        if m.get("to") == STEWARD or not seats.get(str(m.get("to")), {}).get("auto"):
            return {"ok": False, "why": f"`{m.get('to')}` 는 자동 실행 자리가 아니다(org-contracts §2)"}
        if m.get("reason") in NO_DISPATCH_REASONS:
            # 두 번째 문 — 계약표에서 받는 자리를 자동 자리로 바꿔도 당직은 경보를 고치러 가지 않는다
            return {"ok": False, "why": f"`{m.get('reason')}` 지시서는 당직이 부르지 않는다(org-contracts §3)"}
        if m.get("status") != "open":
            return {"ok": False, "why": f"상태가 {m.get('status')} 다 — open 만 부른다"}
        prompt = self.dispatch_prompt(o)
        cmd = self._claude_cmd()
        if dry_run:
            return {"ok": True, "dry_run": True, "cmd": cmd, "prompt": prompt}
        if not cmd:
            self.set_status(o, "blocked", note="당직 실패 — claude 실행 파일을 찾지 못했다")
            return {"ok": False, "why": "claude 를 찾지 못했다"}
        self.set_status(o, "doing", note="당직 Steward 가 불렀다")
        self.emit("dispatch.start", order=oid, to=m.get("to"))
        self.dispatch_logs.mkdir(parents=True, exist_ok=True)
        log = self.dispatch_logs / f"{oid}.log"
        code: int | str
        try:
            p = subprocess.run(cmd, input=prompt.encode("utf-8"), cwd=str(self.root),
                               capture_output=True, timeout=DISPATCH_TIMEOUT_SEC)
            code = p.returncode
            log.write_bytes(p.stdout[-200_000:] + b"\n--- stderr ---\n" + p.stderr[-50_000:])
        except subprocess.TimeoutExpired:
            code = "timeout"
            log.write_text(f"{DISPATCH_TIMEOUT_SEC}초 제한 초과", encoding="utf-8")
        except Exception as e:                             # noqa: BLE001
            code = type(e).__name__
            log.write_text(f"실행 실패: {e!r}", encoding="utf-8")
        self.scan()                                        # 보고서가 나왔으면 여기서 닫힌다
        again = self.orders().get(oid)
        if again and again["meta"].get("status") == "doing":
            # ★ 보고서가 없는데 끝났다고 치지 않는다. 종료코드 0 은 '일을 했다'가 아니다
            #   (agent-utilization §4: pip 은 실패해도 0 을 돌려줬다 — 상태값이 아니라 산출물로 판정한다).
            self.set_status(again, "blocked",
                            note=f"당직 실행 후 보고서 없음(종료 {code}) — data/org-dispatch/{oid}.log")
        self.emit("dispatch.end", order=oid, to=m.get("to"), note=f"exit {code}")
        return {"ok": code == 0, "exit": code, "log": log.relative_to(self.root).as_posix()}

    def _claude_cmd(self) -> list[str]:
        # ★ 예약 작업(S4U)에는 대화형 PATH 가 보장되지 않는다 — npm 전역 폴더가 빠지면 which 가 못 찾는다.
        #   그래서 등록 스크립트가 전체 경로를 --claude 로 넘긴다(register_daily_report_task.ps1 의 python 과 같은 이유).
        # ★ 2026-09-27 실측: 이 PC 의 claude 는 **VS Code 확장 안에만** 있다(PATH 에 없음) —
        #   `…/extensions/anthropic.claude-code-<버전>-win32-x64/resources/native-binary/claude.exe`.
        #   경로에 버전이 박혀 있어 확장이 업데이트되면 --claude 로 넘긴 경로가 사라진다. 그때 당직이
        #   조용히 '보고서 없음 blocked' 로 쌓이지 않게, 넘긴 경로가 없으면 가장 새 확장을 다시 찾는다.
        exe = self.claude_exe if (self.claude_exe and Path(self.claude_exe).exists()) else ""
        exe = exe or shutil.which("claude") or shutil.which("claude.cmd") or _vscode_claude()
        if not exe:
            return []
        return [exe, "-p", "--output-format", "json",
                "--allowedTools", ",".join(DISPATCH_ALLOWED),
                "--disallowedTools", ",".join(DISPATCH_DENIED)]


_ACTION_TEXT = {
    "order": "지시서를 만들었다",
    "below": "연속 기준 전 — 지시서 없음",
    "ticket-open": "열린 티켓이 맡고 있다 — 지시서 없음",
    "done-before": "이 연속 구간의 지시서는 이미 만들었다",
    "open-order": "같은 신호의 열린 지시서가 있다",
    "not-watched": "이 신호로는 지시서를 만들지 않는다(§3.1)",
}


def _gap_note(a: dict) -> str:
    """세지 않고 건너뛴 모름(❔)을 적는다 — 건너뛴 것을 숨기면 '연속'이 거짓이 된다(QA-OPS3-3)."""
    parts = []
    if a.get("gaps"):
        parts.append(f"사이의 ❔ 모름 {len(a['gaps'])}편은 세지 않음")
    if a.get("tail"):
        parts.append(f"그 뒤 ❔ 모름 {len(a['tail'])}편({a['tail'][-1]}까지 — 지난 기간·확인 불가)")
    return f" [{' · '.join(parts)}]" if parts else ""


def _ticket_md(ticket: str, state: str) -> str:
    if not ticket:
        return "**❗ 티켓 없음**"
    if state == "열림":
        return f"티켓 `{ticket}`"
    return f"티켓 `{ticket}`({state}) · **❗ 열린 티켓 없음**"


def alert_lines(alerts: list[dict], tasks: list[dict]) -> list[str]:
    """스탠드업 '경보 → 티켓' 절. 경보가 없으면 빈 목록(절 자체를 쓰지 않는다)."""
    L = []
    for a in alerts:
        what = _ACTION_TEXT.get(a["action"], a["action"])
        if a["action"] == "order":
            what = f"지시서 `{a.get('order', '?')}` → `{a['seat']}`"
        elif a["action"] == "below":
            what = f"기준 {a['need']}개 전 — 지시서 없음"
        elif a["action"] == "done-before" and a.get("order"):
            what += f" — `{a['order']}`"
        L.append(f"- `{a['name']}` {a['mark']} {a['n']}개 리포트 연속({a['start']}~{a['end']}){_gap_note(a)} · "
                 f"{_ticket_md(a['ticket'], a['ticket_state'])} — {what}")
    for t in tasks:
        what = _ACTION_TEXT.get(t["action"], t["action"])
        if t["action"] == "order":
            what = f"지시서 `{t.get('order', '?')}` → `{t['seat']}`"
        elif t["action"] == "below":
            what = f"{t['need_hours']}시간 전 — 지시서 없음"
        L.append(f"- 예약 작업 `{t['name']}` {t['label']} · {t['hours']}시간째 · "
                 f"{_ticket_md(t['ticket'], t['ticket_state'])} — {what}")
    return L


# ── CLI ─────────────────────────────────────────────────────────────────────
def _vscode_claude(home: Path | None = None) -> str:
    """VS Code 확장에 번들된 claude.exe 중 **버전이 가장 높은 것**의 경로. 없으면 "".

    폴더 이름 `anthropic.claude-code-2.1.282-win32-x64` 의 버전을 숫자 튜플로 비교한다 —
    문자열 정렬이면 2.1.99 가 2.1.282 보다 뒤에 온다. 파일이 실제로 있는 폴더만 센다
    (업데이트 직후 옛 폴더가 비어 남는 경우가 있다)."""
    base = (home or Path.home()) / ".vscode" / "extensions"
    best, best_v = "", ()
    try:
        dirs = list(base.glob("anthropic.claude-code-*"))
    except OSError:
        return ""
    for d in dirs:
        exe = d / "resources" / "native-binary" / ("claude.exe" if os.name == "nt" else "claude")
        m = re.match(r"anthropic\.claude-code-(\d+(?:\.\d+)*)", d.name)
        if not m or not exe.is_file():
            continue
        v = tuple(int(x) for x in m.group(1).split("."))
        if v > best_v:
            best, best_v = str(exe), v
    return best


def _wrap_console() -> None:
    """Windows 콘솔(cp949)에서 '—'·'★' 로 죽지 않게 — main 에서만 부른다(agent_dashboard 와 같은 이유)."""
    for s in ("stdout", "stderr"):
        with contextlib.suppress(Exception):
            setattr(sys, s, io.TextIOWrapper(getattr(sys, s).buffer, encoding="utf-8", errors="replace",
                                             line_buffering=True))   # 없으면 종료까지 아무것도 안 보인다


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="조직 순환계")
    ap.add_argument("--root", default=str(REPO), help=argparse.SUPPRESS)
    ap.add_argument("--claude", default="", help="claude 실행 파일 전체 경로(예약 작업용)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    scp = sub.add_parser("scan")
    scp.add_argument("--dry-run", action="store_true",
                     help="orders/·버스·상태 파일을 쓰지 않고 무엇이 생길지만 보인다")
    sp = sub.add_parser("standup")
    sp.add_argument("--dispatch", type=int, default=0, help="부를 최대 건수(하루 상한 안에서)")
    sp.add_argument("--dry-run", action="store_true")
    sub.add_parser("board")
    op = sub.add_parser("order")
    op.add_argument("--to", required=True)
    op.add_argument("--purpose", required=True)
    op.add_argument("--ticket", default="")
    op.add_argument("--input", action="append", default=[])
    op.add_argument("--scope", default="")
    op.add_argument("--from", dest="frm", default=STEWARD)
    cp = sub.add_parser("close")
    cp.add_argument("id")
    cp.add_argument("--status", required=True, choices=["done", "blocked", "cancelled"])
    cp.add_argument("--note", required=True, help="왜 닫는가 — 비우지 않는다")
    dp = sub.add_parser("dispatch")
    dp.add_argument("id")
    dp.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    org = Org(a.root)
    org.claude_exe = a.claude

    if a.cmd == "scan":
        org.dry_run = bool(getattr(a, "dry_run", False))
        r = org.scan()
        if org.dry_run:
            r = {"dry_run": True, "would_create": org.dry_orders_summary(),
                 "would_close": r["closed"], "alerts": r["alerts"], "tasks": r["tasks"],
                 "bus": [e for e in org.dry_events if e.get("kind") not in ("order.created", "scan")],
                 "legacy_reports": r["legacy_reports"], "warnings": r["warnings"]}
        else:
            # 매시 스캔 로그(org_heartbeat.log)에는 한 줄 요약만 — 전체 판정은 스탠드업·--dry-run 이 보여 준다
            r["alerts"] = [f"{x['name']} {x['n']}편 {x['action']}" for x in r["alerts"]]
            r["tasks"] = [f"{x['name']} {x['hours']}h {x['action']}" for x in r["tasks"]]
        print(json.dumps(r, ensure_ascii=False, indent=1))
    elif a.cmd == "standup":
        p = org.standup(dispatch=a.dispatch, dry_run=a.dry_run)
        print(p.relative_to(org.root).as_posix())
    elif a.cmd == "board":
        print(json.dumps(org.board(), ensure_ascii=False, indent=1))
    elif a.cmd == "order":
        _, seats = org.contracts()
        if a.to != STEWARD and a.to not in seats:
            print(f"`{a.to}` 는 org-contracts §2 에 없는 자리다", file=sys.stderr)
            return 2
        orders = org.orders()
        o = org.create_order(orders, to=a.to, frm=a.frm, purpose=a.purpose, reason="manual",
                             ticket=a.ticket, inputs=a.input, scope=a.scope)
        print(o["path"].relative_to(org.root).as_posix())
    elif a.cmd == "close":
        o = org.orders().get(a.id)
        if not o:
            print(f"지시서 {a.id} 가 없다", file=sys.stderr)
            return 2
        if a.status == "done" and not o["meta"].get("report"):
            # CLAUDE.md 운영 규칙 7 — 보고서(=DoD 대조 근거) 없이 완료로 바꾸지 않는다
            print("보고서 없이 done 으로 닫지 않는다 — 머리말 단 보고서를 먼저 남기거나 cancelled 로 닫는다",
                  file=sys.stderr)
            return 2
        org.set_status(o, a.status, note=a.note)
        print(f"{a.id} → {a.status}")
    elif a.cmd == "dispatch":
        r = org.dispatch(a.id, dry_run=a.dry_run)
        print(json.dumps(r, ensure_ascii=False, indent=1) if not a.dry_run else
              " ".join(r.get("cmd") or ["(claude 없음)"]) + "\n\n" + r.get("prompt", r.get("why", "")))
        return 0 if r.get("ok") else 1
    for w in org.warnings:
        print(f"  ⚠ {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    # ★ 콘솔 감싸기는 **진입점에서만** 한다. main() 안에서 하면 테스트가 main() 을 부를 때
    #   pytest 의 출력 포획을 갈아치워 'I/O operation on closed file' 로 죽는다 — 2026-09-26 실측.
    #   agent_dashboard._wrap_console 주석이 경고한 함정의 다섯 번째 변형이다.
    _wrap_console()
    raise SystemExit(main())
