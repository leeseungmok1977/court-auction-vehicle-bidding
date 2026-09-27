# -*- coding: utf-8 -*-
"""운영·공급 절 — 주간·월간 보고가 **같은 함수**로 센다.

OPS-3(2026-09-27)이 주간 보고에 '운영·공급' 절을 만들었고, OPS-4 가 월간 보고에 같은 절을 붙이면서
구현을 여기로 옮겼다. 정의가 두 벌이면 둘이 다른 말을 한다 — 주간과 월간이 이 모듈 하나를 쓴다.

그 기간 **일일 리포트 파일**(`docs/daily-reports/`)을 다시 읽어 센다: 신호별 이상 일수 · 연결 티켓 ·
'티켓 없음'이던 날 · 정기 작업 실패 횟수. 서버를 다시 읽지 않는다(그날의 판정은 그날 리포트가 이미 남겼다).
표는 `docs/org-contracts.md` §3.1, 해석은 `org_runtime.parse_daily_report`(순환계와 같은 파서).
외부 요청·서버 접속 없음.

W39 보고는 케이카 경보(3일)와 패널 정기 실행 실패를 한 번도 적지 않았고, 패널은 '리포트 2건'으로 적어
실패를 가렸다(AUDIT-1 A-05·A-11). 월간 보고도 같은 구멍('전문가 패널 리포트 N건')을 갖고 있었다.
"""
from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
DAILY_DIR = ROOT / "docs" / "daily-reports"
PANEL_JOB = "주간 전문가 패널"          # 일일 리포트 `## 정기 작업` 표의 작업 이름(daily_ops_report 와 같은 글자)


def _clip(text) -> str:
    """기본 정리 — 공백을 접고 200자로 자른다. 보고서는 자기 `_scrub`(서버 주소·키 경로 지우기)을 넘긴다."""
    return re.sub(r"\s+", " ", str(text)).strip()[:200]


def collect_ops(since: date, until: date, today: Optional[date] = None, *, root: Path = ROOT,
                daily_dir: Optional[Path] = None, scrub: Callable = _clip) -> dict:
    """그 기간 일일 리포트(이 저장소의 파일)와 경보 → 티켓 표. 외부 요청·서버 접속 없음."""
    tools_dir = str(Path(__file__).resolve().parent)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        import org_runtime as rt                             # noqa: PLC0415
        tickets = rt.Org(root).signal_tickets()
    except Exception as e:                                   # noqa: BLE001
        return {"error": scrub(f"경보 표를 읽지 못함({type(e).__name__})")}
    daily_dir = daily_dir or (Path(root) / "docs" / "daily-reports")
    today = today or date.today()
    reports, missing = [], []
    d = since
    while d <= until:
        f = daily_dir / f"{d.isoformat()}.md"
        if f.exists():
            reports.append((d.isoformat(), rt.parse_daily_report(f.read_text(encoding="utf-8", errors="replace"),
                                                                 day=d.isoformat())))
        elif d <= today:
            missing.append(d.isoformat())
        d += timedelta(days=1)
    return {"reports": reports, "missing": missing, "tickets": tickets}


def days_text(ds: list[str], compact: bool = False) -> str:
    """날짜 목록 → '09-24·09-25'. `compact` 면 사흘 넘게 이어진 날을 '09-01~09-14' 로 접는다(월간 — 줄이 길어진다)."""
    if not compact:
        return "·".join(x[5:] for x in ds)
    runs: list[list[date]] = []
    for d in sorted(date.fromisoformat(x) for x in ds):
        if runs and (d - runs[-1][1]).days == 1:
            runs[-1][1] = d
        else:
            runs.append([d, d])
    parts: list[str] = []
    for a, b in runs:
        n = (b - a).days + 1
        if n >= 3:
            parts.append(f"{a:%m-%d}~{b:%m-%d}")
        else:
            parts += [f"{x:%m-%d}" for x in ([a, b] if n == 2 else [a])]
    return "·".join(parts)


def ticket_md(name: str, tickets: dict) -> tuple[str, str]:
    t = (tickets.get(name) or {})
    if not t.get("ticket"):
        return "—", "—"
    status = re.sub(r"[*`|]", "", t.get("status") or "").strip()
    if len(status) > 40:
        status = status[:40].rstrip() + "…"
    return f"`{t['ticket']}`", (t.get("state") or "") + (f" · {status}" if status else "")


def ops_stats(ops: dict) -> dict:
    """신호·작업별 일수. 주간·월간 보고와 테스트가 같은 수를 쓴다."""
    reps = ops.get("reports") or []
    names: list[str] = []
    for _, p in reps:
        names += [n for n in p["supply"] if n not in names]
    sup: dict[str, dict] = {n: {"alert": [], "unknown": [], "no_ticket": [], "unmarked": []} for n in names}
    jobs: dict[str, dict] = {}
    for day, p in reps:
        for name in names:
            s, r = sup[name], p["supply"].get(name)
            if r is None:                                    # 공급 표가 없는 날(지난 기간·서버 못 읽음) = 모름
                s["unknown"].append(day)
            elif r["state"] == "alert":
                s["alert"].append(day)
                if r.get("ticket") is None:
                    s["unmarked"].append(day)                # 티켓 칸이 생기기 전 리포트 — 몰랐던 것이지 있던 게 아니다
                elif "티켓 없음" in r["ticket"]:
                    s["no_ticket"].append(day)
            elif r["state"] == "unknown":
                s["unknown"].append(day)
        for name, r in p["jobs"].items():
            j = jobs.setdefault(name, {"due": [], "ok": [], "bad": [], "unknown": []})
            if r["state"] == "na":
                continue
            j["due"].append(day)
            {"ok": j["ok"], "alert": j["bad"]}.get(r["state"], j["unknown"]).append(day)
    return {"supply": sup, "jobs": jobs}


def ops_section(ops: Optional[dict], *, period: str = "이번 주", scrub: Callable = _clip,
                compact: bool = False) -> list[str]:
    """'## 운영·공급' 절. `period` 는 사람이 읽는 기간 이름('이번 주'·'이 달')."""
    L = ["## 운영·공급", ""]
    if not ops or ops.get("error"):
        return L + [f"확인 불가 — {(ops or {}).get('error') or '일일 리포트를 읽지 않았다'}.", ""]
    reps = ops.get("reports") or []
    if not reps:
        return L + [f"확인 불가 — {period} 일일 리포트가 한 편도 없다. **이상이 없었다는 뜻이 아니다.**", ""]
    st = ops_stats(ops)
    tickets = ops.get("tickets") or {}
    miss = ops.get("missing") or []

    def dd(ds: list[str]) -> str:
        return days_text(ds, compact)

    L += [f"> {period} 일일 리포트 **{len(reps)}편**(`docs/daily-reports/`)에서 셌다"
          + (f" · 리포트 없는 날 {dd(miss)}" if miss else "")
          + ". 서버를 다시 읽지 않았다. 티켓은 `docs/org-contracts.md` §3.1 과 백로그 상태(지금 기준)다.", ""]
    # 형식이 어긋난 리포트는 아래 수를 **작게** 만든다(모름으로 읽힌다) — 조용히 두지 않는다(QA-OPS3-2)
    drift = [(d, p.get("issues")) for d, p in reps if p.get("issues")]
    if drift:
        L += ["> ⚠ **형식이 달라 못 읽었을 수 있는 리포트** — 아래 일수가 실제보다 작을 수 있다: "
              + " · ".join(f"{d[5:]}({scrub('; '.join(i))[:160]})" for d, i in drift), ""]
    L += ["**공급 신호**", "",
          "| 신호 | 이상·멈춤 | 확인 불가 | 연결 티켓 | 티켓 상태(지금) | '티켓 없음'이던 날 |",
          "|---|---|---|---|---|---|"]
    for name, s in st["supply"].items():
        t, ts = ticket_md(name, tickets)
        marked = len(s["alert"]) - len(s["unmarked"])     # 티켓 칸이 있던 리포트의 경보 일수
        if not s["alert"]:
            nt = "—"
        elif not marked:
            nt = f"모름 — 티켓 칸 생기기 전 리포트 {len(s['unmarked'])}일"
        else:
            nt = (f"**{len(s['no_ticket'])}일**" if s["no_ticket"] else "0일") + (
                f" · 칸 생기기 전 {len(s['unmarked'])}일" if s["unmarked"] else "")
        bad = f"**{len(s['alert'])}일** ({dd(s['alert'])})" if s["alert"] else "0일"
        L.append(f"| {name} | {bad} | {len(s['unknown'])}일 | {t} | {ts} | {nt} |")
    if not st["supply"]:
        L.append("| (공급 표가 있는 리포트 없음) | — | — | — | — | — |")
    L += ["", "**정기 작업** — 예정이 있던 날만 센다(주간 작업은 그 요일만)", "",
          "| 작업 | 판정한 날 | 성공 | 실패·경고 | 확인 불가 | 연결 티켓 |",
          "|---|---|---|---|---|---|"]
    for name, j in st["jobs"].items():
        t, ts = ticket_md(name, tickets)
        bad = f"**{len(j['bad'])}회** ({dd(j['bad'])})" if j["bad"] else "0회"
        L.append(f"| {name} | {len(j['due'])}회 | {len(j['ok'])}회 | {bad} | {len(j['unknown'])}회 | "
                 f"{t}{' ' + ts if t != '—' else ''} |")
    L += ["", "> '티켓 없음'이던 날은 그날 리포트가 경보 줄에 **❗ 티켓 없음**을 적은 날이다. "
          "경보가 연속으로 이어지면 순환계가 결재함에 지시서를 만든다(org-contracts §3).", ""]
    return L


def panel_line(ops: Optional[dict], *, period: str = "이번 주", compact: bool = False) -> list[str]:
    """패널 **정기 실행** 결과 — 파일 수로 실패를 가리지 않는다(A-05)."""
    if not ops or ops.get("error") or not ops.get("reports"):
        return ["- 정기 실행(토 09:20): 확인 불가 — 일일 리포트를 읽지 못했다."]
    j = ops_stats(ops)["jobs"].get(PANEL_JOB)
    if not j or not j["due"]:
        return [f"- 정기 실행(토 09:20): {period} 일일 리포트에 판정된 회차가 없다."]
    s = (f"- 정기 실행(토 09:20, 일일 리포트 기준): 예정 {len(j['due'])}회 · 성공 {len(j['ok'])}회 · "
         + (f"**실패 {len(j['bad'])}회**({days_text(j['bad'], compact)})" if j["bad"] else "실패 0회")
         + (f" · 확인 불가 {len(j['unknown'])}회" if j["unknown"] else ""))
    return [s]
