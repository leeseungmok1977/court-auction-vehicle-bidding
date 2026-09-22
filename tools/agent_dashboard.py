# -*- coding: utf-8 -*-
"""에이전트 현황 대시보드 — 로컬 전용. 있는 것만 그리고, 없는 것은 '없음'이라고 쓴다.

    python tools/agent_dashboard.py            # http://127.0.0.1:8765 에서 띄운다
    python tools/agent_dashboard.py --once     # JSON 한 번만 찍고 끝(점검용)
    python tools/agent_dashboard.py --rescan   # 캐시를 버리고 전수 재스캔

## 왜 이렇게 만들었나

오너가 참고로 보낸 영상은 수십 명이 상시 가동되는 조직을 전제로 "Active 12 · Idle 5" 같은
실시간 상태를 보여준다. 우리는 다르다 — 에이전트 15종은 **필요할 때 호출되는 방식**이고,
Claude Code 세션이 떠 있을 때만 움직인다. 그 화면을 그대로 흉내 내면 없는 상태를 지어내게 된다.
이 앱이 파는 것이 정직인데 사내 대시보드가 먼저 거짓말을 하면 안 된다.

그래서 **사후 사실**만 그린다. 대신 그 사실이 꽤 아프다 — 2026-09-23 첫 실측에서
**15종 중 7종이 한 번도 호출된 적이 없었다**(제품기획 총괄 `pm-orchestrator` 포함).
조직도에는 5부서 15명이 있는데 실제로 일한 건 8종이고 그중 39/67회가 디자인 검수 한 명이었다.
그리고 주간·월간 보고서 예약 작업은 **마지막 실행이 1999-11-30**, 즉 한 번도 돌지 않았다.
대시보드가 없었으면 9/26·10/1에야 알았을 것이다.

## 데이터 출처 (전부 로컬 읽기 전용)

| 무엇 | 어디서 | 주의 |
|---|---|---|
| 부서 편성 | `docs/ORG.md` 부서표를 **파싱** | 하드코딩하면 조직을 바꿨을 때 화면이 옛말을 한다 |
| 에이전트 정의 | `.claude/agents/*.md` frontmatter | 부서표에 없는 정의는 '미편성'으로 드러낸다 |
| 호출 이력 | `~/.claude/projects/<slug>/*.jsonl` | ★ 내부 포맷이다 — 아래 경고 참조 |
| 정기 작업 | `schtasks /query /fo CSV /v` | `Last Run Time` 이 1999-11-30 이면 '한 번도 안 돎' |
| 산출물 | `reports/` `docs/reviews/` `docs/*-reports/` | 파일 mtime |
| 배포 | `git log` | 로컬 저장소 |
| 제품 | `data/auction.db` (로컬 사본) | 운영이 아니라 이 PC 사본이라는 점을 화면에 밝힌다 |

## ★ 세션 기록 파싱에 대한 경고

`~/.claude/projects/.../*.jsonl` 은 **Claude Code 내부 포맷이고 공개 API 가 아니다.**
버전이 오르면 말없이 깨질 수 있다. 다만 근거 없는 도박은 아니다 — 2026-09-23 실측에서
한 파일 안에 버전 5개(2.1.195·2.1.233·2.1.266·2.1.268·2.1.269)가 섞여 있었고
**57,460줄 파싱 실패 0줄**이었다. 최근 5개 버전을 건너뛰며 형태가 유지됐다는 뜻이다.

그래도 방어한다. 파싱이 실패하면 **0으로 채우지 않고 화면에 '읽지 못함'을 띄운다.**
조용히 빈 대시보드를 보여주는 쪽이 제일 나쁘다 — 아무 일도 없는 것처럼 보이기 때문이다.

## 개인정보

이 파일들에는 대화 전문이 들어 있다. 이 도구는 **구조만** 읽는다 — 시각, 도구 이름,
`subagent_type`, 그리고 우리가 직접 붙인 짧은 작업 설명뿐이다. 프롬프트·응답 본문은
읽지도 내보내지도 않는다. 서버는 **127.0.0.1 에만** 바인딩한다.
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Windows 콘솔 기본 인코딩은 cp949 라 '—'·'★' 에서 UnicodeEncodeError 로 죽는다.
for _s in ("stdout", "stderr"):
    try:
        setattr(sys, _s, io.TextIOWrapper(getattr(sys, _s).buffer,
                                          encoding="utf-8", errors="replace"))
    except Exception:                                        # noqa: BLE001
        pass

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / ".claude" / "agents"
ORG_MD = ROOT / "docs" / "ORG.md"
CACHE = ROOT / "data" / "agent_dashboard_cache.json"        # data/ 는 git 제외
HTML = Path(__file__).with_name("agent_dashboard.html")
PORT = 8765

# Claude Code 세션 기록. 슬러그는 작업 디렉터리에서 만들어진다 — 고정값을 박지 않고 찾는다.
PROJECTS = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".claude" / "projects"


# ── 조직: ORG.md 부서표를 파싱한다 (하드코딩 금지) ──────────────────────────
_DEPT_ROW = re.compile(r"^\|\s*\*\*(?P<dept>[^*]+)\*\*\s*\|\s*(?P<members>[^|]+)\|\s*(?P<role>[^|]+)\|")
_BACKTICK = re.compile(r"`([^`]+)`")


def read_departments() -> tuple[list[dict], str | None]:
    """ORG.md **§1 조직도 구간 안의** 부서표만 읽는다.

    ⚠ 2026-09-23 실측 버그: 구간을 안 자르면 §4 '보고 리듬' 표까지 부서로 먹는다. 그 표도
      `| **일일** | `docs/daily-reports/…` | … |` 형태라 정규식에 그대로 걸려서, 화면에
      '일일·주간·월간' 부서가 생기고 **파일 경로가 에이전트로** 등록됐다(총원 15 → 18).
      같은 모양의 표가 문서에 더 늘어날 수 있으므로 구간으로 자르는 편이 안전하다.
    """
    if not ORG_MD.exists():
        return [], "docs/ORG.md 가 없다"
    out, in_org = [], False
    for line in ORG_MD.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("## "):
            in_org = s.startswith("## 1.")       # §1 에 들어가고, 다음 ## 에서 빠진다
            continue
        if not in_org:
            continue
        m = _DEPT_ROW.match(s)
        if not m:
            continue
        members = _BACKTICK.findall(m.group("members"))
        if not members:                       # 구성원이 백틱으로 안 적힌 표는 부서표가 아니다
            continue
        out.append({"name": m.group("dept").strip(),
                    "role": m.group("role").strip(),
                    "members": members})
    if not out:
        return [], "ORG.md §1 에서 부서표를 찾지 못했다 — 표 형식이나 절 번호가 바뀌었는지 확인할 것"
    return out, None


_FM = re.compile(r"^---\s*$")


def read_agent_defs() -> dict[str, dict]:
    """`.claude/agents/*.md` frontmatter — name·description·tools·model."""
    defs: dict[str, dict] = {}
    if not AGENT_DIR.exists():
        return defs
    for f in sorted(AGENT_DIR.glob("*.md")):
        if f.name.startswith("_"):            # _panel-context.md 는 에이전트가 아니다
            continue
        text = f.read_text(encoding="utf-8", errors="replace").splitlines()
        if not text or not _FM.match(text[0]):
            continue
        fm: dict[str, str] = {}
        for line in text[1:]:
            if _FM.match(line):
                break
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
        name = fm.get("name") or f.stem
        defs[name] = {"name": name, "file": f.name,
                      "description": fm.get("description", ""),
                      "tools": fm.get("tools", ""), "model": fm.get("model", "")}
    return defs


# ── 호출 이력: 세션 기록을 **증분으로** 읽는다 ──────────────────────────────
CACHE_SCHEMA = 2      # 집계 방식을 바꾸면 올린다 — 옛 캐시를 그대로 쓰면 숫자가 섞인다


def _empty_stats() -> dict:
    return {"schema": CACHE_SCHEMA,
            "calls": [], "per_agent": {}, "per_day": {}, "tool_per_day": {},
            "tool_names": {}, "versions": {}, "offsets": {}, "lines": 0, "bad": 0,
            "skipped_logs": []}


def _log_belongs_to_us(path: Path) -> tuple[bool, str]:
    """이 세션 기록이 **우리 프로젝트의 것인지** 레코드의 cwd 로 판정한다.

    ⚠ 2026-09-23 실측: `projects/*/*.jsonl` 을 전부 읽는 바람에 무관한 프로젝트
      (`Simple_GAME1`)의 세션까지 집계에 섞였다. '우리 조직' 지표가 오염된다.

    경로 슬러그를 역산하지 않는다 — 드라이브 문자 대소문자와 한글 변환 규칙을 내가 모른다.
    레코드의 `cwd` 를 쓰되 **파일 단위로** 판정한다: 레코드의 24~31% 에는 cwd 가 아예 없어서
    레코드마다 거르면 4분의 1을 버리게 된다.
    """
    root = str(ROOT).lower()
    seen: collections.Counter = collections.Counter()
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for i, ln in enumerate(f):
                if i > 600 or sum(seen.values()) >= 40:
                    break
                ln = ln.strip()
                if not ln or '"cwd"' not in ln:
                    continue
                try:
                    cwd = json.loads(ln).get("cwd")
                except Exception:                            # noqa: BLE001
                    continue
                if cwd:
                    seen[str(cwd).lower()] += 1
    except Exception as e:                                   # noqa: BLE001
        return False, f"읽기 실패 {type(e).__name__}"
    if not seen:
        return False, "cwd 를 못 찾음"
    top = seen.most_common(1)[0][0]
    return top.startswith(root), top


def scan_sessions(rescan: bool = False) -> tuple[dict, str | None]:
    """세션 기록에서 에이전트 호출과 도구 사용량을 뽑는다.

    ⚠ 494MB 를 새로고침마다 읽을 수는 없다. 파일별 오프셋을 캐시하고 **새로 붙은 부분만**
      파싱한다. 파일이 줄었으면(세션 교체·삭제) 그 파일만 처음부터 다시 읽는다.
    """
    st = _empty_stats()
    if CACHE.exists() and not rescan:
        try:
            cached = json.loads(CACHE.read_text(encoding="utf-8"))
            if cached.get("schema") == CACHE_SCHEMA:
                st.update(cached)
            # 스키마가 다르면 버린다 — 집계 규칙이 바뀐 캐시를 이어 쓰면 옛 숫자가 섞인다
        except Exception:                                    # noqa: BLE001
            st = _empty_stats()                              # 캐시가 깨졌으면 버리고 다시 센다

    if not PROJECTS.exists():
        return st, f"세션 기록 폴더가 없다: {PROJECTS}"

    logs = sorted(PROJECTS.glob("*/*.jsonl"))
    if not logs:
        return st, "세션 기록(.jsonl)을 찾지 못했다"

    per_agent = collections.Counter(st["per_agent"])
    per_day = collections.Counter(st["per_day"])
    tool_day = collections.Counter(st["tool_per_day"])
    tool_names = collections.Counter(st["tool_names"])
    versions = collections.Counter(st["versions"])
    calls = list(st["calls"])
    offsets = dict(st["offsets"])

    skipped: list[str] = []
    for log in logs:
        ours, why = _log_belongs_to_us(log)
        if not ours:
            skipped.append(f"{log.parent.name} ({why})")
            continue
        key = str(log)
        size = log.stat().st_size
        start = offsets.get(key, 0)
        if start > size:                      # 파일이 줄었다 = 다른 세션으로 갈렸다
            start = 0
        if start == size:
            continue
        with open(log, "r", encoding="utf-8", errors="replace") as f:
            f.seek(start)
            for ln in f:
                st["lines"] += 1
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    o = json.loads(ln)
                except Exception:                            # noqa: BLE001
                    st["bad"] += 1
                    continue
                if o.get("version"):
                    versions[str(o["version"])] += 1
                ts = str(o.get("timestamp") or "")
                day = ts[:10]
                msg = o.get("message")
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                for c in content:
                    if not (isinstance(c, dict) and c.get("type") == "tool_use"):
                        continue
                    nm = str(c.get("name"))
                    tool_names[nm] += 1
                    if day:
                        tool_day[day] += 1
                    if nm in ("Agent", "Task"):
                        inp = c.get("input") or {}
                        agent = str(inp.get("subagent_type") or "(미지정)")
                        # ★ 프롬프트 본문은 읽지 않는다. 우리가 붙인 짧은 라벨만 쓴다.
                        desc = str(inp.get("description") or "")[:40]
                        calls.append({"ts": ts, "agent": agent, "desc": desc})
                        per_agent[agent] += 1
                        if day:
                            per_day[day] += 1
            offsets[key] = f.tell()

    calls.sort(key=lambda c: c["ts"])
    st.update({"calls": calls[-400:], "per_agent": dict(per_agent), "per_day": dict(per_day),
               "tool_per_day": dict(tool_day), "tool_names": dict(tool_names),
               "versions": dict(versions), "offsets": offsets, "skipped_logs": skipped})
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    except Exception:                                        # noqa: BLE001
        pass                                                 # 캐시 실패는 치명적이지 않다
    return st, None


# ── 정기 작업 ───────────────────────────────────────────────────────────────
NEVER = "1999-11-30"          # Windows 가 '한 번도 실행 안 됨'을 이 날짜로 표기한다
_PS_DATE = re.compile(r"/Date\((-?\d+)\)/")

# ★ `schtasks /fo CSV` 를 쓰면 안 된다. 2026-09-23 실측: **CSV 헤더가 UI 언어로 나온다** —
#   PowerShell 에서는 `TaskName` 인데 파이썬 subprocess 에서는 `작업 이름` 이었다(호스트
#   프로세스 로케일에 달렸다). 열 이름으로 찾으니 전 행이 걸러져 0건이 됐고, 예외가 아니라
#   **조용히 빈 화면**이 나왔다. Get-ScheduledTask 는 속성 이름이 언어와 무관하게 고정이다.
_PS_SCHED = (
    "Get-ScheduledTask -ErrorAction SilentlyContinue | "
    "Where-Object { $_.TaskName -match 'naechaget' } | "
    "ForEach-Object { $i = $_ | Get-ScheduledTaskInfo; [pscustomobject]@{ "
    "TaskName=$_.TaskName; State=[string]$_.State; LastRunTime=$i.LastRunTime; "
    "LastTaskResult=$i.LastTaskResult; NextRunTime=$i.NextRunTime } } | "
    "ConvertTo-Json -Compress"
)


def _ps_date(v) -> str:
    """PowerShell 이 JSON 으로 내는 `/Date(epoch밀리초)/` 를 사람이 읽는 시각으로."""
    if not v:
        return ""
    m = _PS_DATE.search(str(v))
    if not m:
        return str(v)
    try:
        return datetime.fromtimestamp(int(m.group(1)) / 1000).isoformat(sep=" ", timespec="minutes")
    except Exception:                                        # noqa: BLE001
        return str(v)


def read_schedule() -> tuple[list[dict], str | None]:
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-Command", _PS_SCHED],
                           capture_output=True, timeout=90)
    except Exception as e:                                   # noqa: BLE001
        return [], f"예약 작업을 읽지 못했다(powershell 실행 실패: {type(e).__name__})"
    if p.returncode != 0:
        return [], f"예약 작업을 읽지 못했다(powershell 종료코드 {p.returncode})"

    text = ""
    for enc in ("utf-8", "cp949", "latin-1"):
        try:
            text = p.stdout.decode(enc).strip()
            break
        except Exception:                                    # noqa: BLE001
            continue
    if not text:
        # ★ 여기서 조용히 [] 를 돌려주면 안 된다 — 화면이 '작업 0개'처럼 보인다.
        return [], "예약 작업이 0건이다 — 이름에 'naechaget' 가 든 작업을 못 찾았다"
    try:
        data = json.loads(text)
    except Exception:                                        # noqa: BLE001
        return [], "예약 작업 JSON 을 해석하지 못했다"
    if isinstance(data, dict):                               # 1건이면 배열이 아니라 객체로 온다
        data = [data]

    out = []
    for r in data:
        last = _ps_date(r.get("LastRunTime"))
        res = str(r.get("LastTaskResult", ""))
        state = str(r.get("State", ""))
        # ★ 267009 는 실패가 아니라 **'지금 실행 중'** 이다(State 도 Running 으로 온다).
        #   상시 가동이 정상인 작업(home-tunnel)을 빨갛게 칠하면 대시보드가 헛되이 경고하고,
        #   헛경고하는 화면은 곧 아무도 안 본다. 2026-09-23 내 첫 판에서 실제로 그랬다.
        running = state.lower() == "running"
        out.append({
            "name": str(r.get("TaskName", "")).lstrip("\\"),
            "status": state, "running": running,
            "last_run": last, "last_result": res,
            "next_run": _ps_date(r.get("NextRunTime")),
            "enabled": state.lower() != "disabled",
            "never_ran": last.startswith(NEVER),
            "ok": res == "0" or running,
        })
    if not out:
        return [], "예약 작업이 0건이다 — 등록이 지워졌는지 확인할 것"
    return sorted(out, key=lambda t: t["name"]), None


# ── 산출물·배포·제품 ────────────────────────────────────────────────────────
def read_artifacts() -> list[dict]:
    out = []
    for pat in ("reports/*.md", "docs/reviews/*.md",
                "docs/daily-reports/*.md", "docs/weekly-reports/*.md",
                "docs/monthly-reports/*.md"):
        for f in ROOT.glob(pat):
            if f.name == "README.md":
                continue
            out.append({"path": f.relative_to(ROOT).as_posix(),
                        "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds")})
    return sorted(out, key=lambda a: a["mtime"], reverse=True)[:30]


def read_git() -> tuple[list[dict], str | None]:
    try:
        p = subprocess.run(["git", "log", "-12", "--pretty=format:%h\t%ad\t%s", "--date=short"],
                           cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
    except Exception as e:                                   # noqa: BLE001
        return [], f"git 실행 실패: {type(e).__name__}"
    if p.returncode != 0:
        return [], "git log 실패"
    out = []
    for line in (p.stdout or "").splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            out.append({"sha": parts[0], "date": parts[1], "subject": parts[2][:90]})
    return out, None


def read_product() -> tuple[dict, str | None]:
    """제품 규모 — **이 PC 의 로컬 사본**이다. 운영 수치가 아니라는 점을 화면에 밝힌다."""
    db = ROOT / "data" / "auction.db"
    if not db.exists():
        return {}, "data/auction.db 가 없다(로컬 사본 미보유)"
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        total = con.execute("select count(*) c from vehicles").fetchone()["c"]
        today = datetime.now().date().isoformat()
        upcoming = con.execute(
            "select count(*) c from vehicles where sale_date >= ? "
            "and coalesce(auction_result,'') not in ('낙찰','종결')", (today,)).fetchone()["c"]
        review = con.execute(
            "select count(*) c from vehicles where judgment = '입찰 검토 가능'").fetchone()["c"]
        con.close()
        return {"total": total, "upcoming": upcoming, "review": review,
                "mtime": datetime.fromtimestamp(db.stat().st_mtime).isoformat(timespec="seconds")}, None
    except Exception as e:                                   # noqa: BLE001
        return {}, f"DB 읽기 실패: {type(e).__name__}"


# ── 조립 ────────────────────────────────────────────────────────────────────
def build_state(rescan: bool = False) -> dict:
    problems: list[str] = []

    depts, e = read_departments()
    if e:
        problems.append(e)
    defs = read_agent_defs()
    if not defs:
        problems.append(".claude/agents 에서 에이전트 정의를 읽지 못했다")
    stats, e = scan_sessions(rescan)
    if e:
        problems.append(e)
    sched, e = read_schedule()
    if e:
        problems.append(e)
    git, e = read_git()
    if e:
        problems.append(e)
    product, e = read_product()
    if e:
        problems.append(e)

    per_agent = stats["per_agent"]
    last_by_agent: dict[str, dict] = {}
    for c in stats["calls"]:
        last_by_agent[c["agent"]] = c

    now = datetime.now()

    def agent_row(name: str, dept: str) -> dict:
        d = defs.get(name, {})
        last = last_by_agent.get(name)
        days = None
        if last:
            try:
                days = (now - datetime.fromisoformat(last["ts"].replace("Z", "")[:19])).days
            except Exception:                                # noqa: BLE001
                days = None
        return {"name": name, "dept": dept, "calls": per_agent.get(name, 0),
                "last_ts": (last or {}).get("ts", ""), "last_desc": (last or {}).get("desc", ""),
                "days_since": days, "defined": name in defs,
                "description": d.get("description", "")[:120],
                "tools": d.get("tools", ""), "model": d.get("model", "")}

    placed: set[str] = set()
    dept_out = []
    for d in depts:
        members = [agent_row(m, d["name"]) for m in d["members"]]
        placed.update(d["members"])
        dept_out.append({"name": d["name"], "role": d["role"], "members": members})

    # 정의는 있는데 어느 부서에도 없는 것 — 조직도와 실제가 어긋난 자리다
    unplaced = [agent_row(n, "미편성") for n in sorted(defs) if n not in placed]
    if unplaced:
        dept_out.append({"name": "미편성", "role": "ORG.md 부서표에 없는 정의", "members": unplaced})

    roster = [m for d in dept_out for m in d["members"]]
    used = [a for a in roster if a["calls"] > 0]
    never = [a for a in roster if a["calls"] == 0]

    # 우리 15종 밖에서 불린 것(general-purpose 등)도 숨기지 않는다
    known = {a["name"] for a in roster}
    outside = sorted(((k, v) for k, v in per_agent.items() if k not in known),
                     key=lambda kv: -kv[1])

    days = sorted(set(list(stats["per_day"]) + list(stats["tool_per_day"])))[-14:]
    activity = [{"day": d, "agent_calls": stats["per_day"].get(d, 0),
                 "tool_calls": stats["tool_per_day"].get(d, 0)} for d in days]

    week_ago = (now - timedelta(days=7)).isoformat()[:10]
    calls_7d = sum(v for k, v in stats["per_day"].items() if k >= week_ago)

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "kpi": {
            "agents_total": len(roster), "agents_used": len(used), "agents_never": len(never),
            "calls_total": sum(per_agent.get(a["name"], 0) for a in roster),
            "calls_7d": calls_7d,
            "last_call": (stats["calls"][-1] if stats["calls"] else None),
            "sched_total": len(sched),
            "sched_never": sum(1 for s in sched if s["never_ran"]),
            "sched_bad": sum(1 for s in sched if not s["ok"] and not s["never_ran"]),
        },
        "departments": dept_out,
        "never_used": [a["name"] for a in never],
        "outside_roster": [{"name": k, "calls": v} for k, v in outside],
        "recent": list(reversed(stats["calls"][-20:])),
        "activity": activity,
        "schedule": sched,
        "artifacts": read_artifacts(),
        "git": git,
        "product": product,
        "source": {
            "cc_versions": sorted(stats["versions"], reverse=True)[:6],
            "lines_parsed": stats["lines"], "parse_failed": stats["bad"],
            "logs": len(stats["offsets"]),
            "skipped_logs": stats.get("skipped_logs", []),   # 다른 프로젝트 세션은 세지 않는다
        },
        "problems": problems,
    }


# ── 서버 ────────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:                                # noqa: N802
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            if not HTML.exists():
                self._send(500, f"{HTML.name} 이 없다".encode(), "text/plain; charset=utf-8")
                return
            self._send(200, HTML.read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/state":
            body = json.dumps(build_state(), ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def log_message(self, *a) -> None:                       # 접근 로그를 남기지 않는다
        pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="에이전트 현황 대시보드(로컬 전용)")
    ap.add_argument("--once", action="store_true", help="JSON 한 번만 출력하고 끝")
    ap.add_argument("--rescan", action="store_true", help="캐시를 버리고 전수 재스캔")
    ap.add_argument("--port", type=int, default=PORT)
    a = ap.parse_args(argv)

    if a.rescan and CACHE.exists():
        CACHE.unlink()
        print("캐시를 지웠다 — 전수 재스캔한다(494MB 기준 30~60초)", file=sys.stderr)

    if a.once:
        print(json.dumps(build_state(a.rescan), ensure_ascii=False, indent=2))
        return 0

    print("첫 스캔 중… 세션 기록이 크면 30~60초 걸린다", file=sys.stderr)
    s = build_state(a.rescan)
    k = s["kpi"]
    print(f"에이전트 {k['agents_used']}/{k['agents_total']}종 사용 · 호출 {k['calls_total']}회"
          f" · 정기작업 {k['sched_total']}개(미실행 {k['sched_never']})", file=sys.stderr)
    if s["problems"]:
        for p in s["problems"]:
            print(f"  ⚠ {p}", file=sys.stderr)

    srv = HTTPServer(("127.0.0.1", a.port), Handler)         # 로컬에만 바인딩한다
    print(f"\n  http://127.0.0.1:{a.port}  — Ctrl+C 로 종료", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
