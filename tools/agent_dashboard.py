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
| 예약 작업(작업 스케줄러) | PowerShell `Get-ScheduledTask`·`Get-ScheduledTaskInfo`·`Export-ScheduledTask` | 마지막 실행이 1999-11-30 이면 '한 번도 안 돎'. 고장 판정(`verdict` — 순환계 `org_runtime.schedule_verdict`)과 '조용히 안 돎' 판정(`silence` — `org_runtime.silence_verdict`)은 순환계 결과를 그대로 싣는다 |
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
읽지도 내보내지도 않는다. 서버는 **기본값이 127.0.0.1 전용**이다.

사내망의 다른 PC 에서 보려면 `--host 0.0.0.0` 으로 연다. 그때는 **열쇠(토큰)가 반드시 붙는다** —
안 주면 자동으로 만든다. 이 화면에는 로그인이 없어서, 열쇠가 없으면 같은 망의 누구나
회사 내부 상태(조직·배포 이력·물건 수)를 그냥 읽게 된다. 인증 없이 여는 경로는 두지 않는다.
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

def _wrap_console() -> None:
    """Windows 콘솔 기본 인코딩은 cp949 라 '—'·'★' 에서 UnicodeEncodeError 로 죽는다.

    ★ 이 일을 **모듈 수준에서 하면 안 된다.** import 만으로 남의 sys.stdout 을 갈아치우는
      셈이고, 그러면 import 이전에 버퍼에 쌓인 출력이 통째로 사라진다. 2026-09-23 하루에
      이 함정에 **네 번** 걸렸다(weekly_report·monthly_report 에서 두 번, 여기서 두 번).
      라이브러리는 import 만으로 호출자의 환경을 바꾸지 않는다 — main() 에서만 부른다.
    ★ line_buffering=True 가 빠지면 **한 글자도 안 보인다.** 새로 만든 TextIOWrapper 는 줄 단위로
      내보내지 않아서 "첫 스캔 중…"도 접속 주소도 프로그램이 끝날 때까지 버퍼에 갇힌다.
      2026-09-27 02:53 오너가 터미널에서 직접 띄웠을 때 빈 화면만 보였다 — 서버는 떠 있었는데
      떴다는 말을 못 한 것이다. 예약 작업(창 숨김)으로만 띄우던 동안엔 아무도 몰랐다.
    """
    for _s in ("stdout", "stderr"):
        try:
            setattr(sys, _s, io.TextIOWrapper(getattr(sys, _s).buffer,
                                              encoding="utf-8", errors="replace",
                                              line_buffering=True))
        except Exception:                                    # noqa: BLE001
            pass

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / ".claude" / "agents"
ORG_MD = ROOT / "docs" / "ORG.md"
CACHE = ROOT / "data" / "agent_dashboard_cache.json"        # data/ 는 git 제외
EVENTS = ROOT / "data" / "agent-events.jsonl"               # .claude/hooks/agent-log.ps1 이 쓴다
TOKEN_FILE = ROOT / "data" / "dashboard_token.txt"          # 사내망 열쇠 — data/ 는 git 제외
UTIL_MD = ROOT / "docs" / "agent-utilization.md"           # 유휴 판정·리듬 정의(사람이 쓴다)
SUPPLY = ROOT / "data" / "ops_supply.json"                 # 공급 판정 — 매일 12시 리포트가 쓴다
SUPPLY_MAX_AGE_H = 26                                      # 하루(12:00) + 여유 2시간. 넘으면 '낡음'
HTML = Path(__file__).with_name("agent_dashboard.html")
PORT = 8765
TOKEN = ""            # 빈 문자열이면 로컬 전용 — 검사하지 않는다. main() 에서만 채운다.

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
CACHE_SCHEMA = 3      # 집계 방식을 바꾸면 올린다 — 옛 캐시를 그대로 쓰면 숫자가 섞인다


def _local_iso(ts: str) -> str:
    """세션 기록의 시각을 **로컬로 맞춘다.**

    ★ 2026-09-23 실측 버그: 세션 기록은 UTC(끝에 `Z`)이고 훅 기록은 로컬 시각인데 그대로
      한 표에 섞었더니 **9시간이 어긋났다.** 9분 전에 돈 에이전트가 '2026-09-22 19:24' 로
      떠서 전날 저녁 일처럼 보였고, 'N일 전' 과 날짜별 막대까지 UTC 날짜로 묶여 새벽 작업이
      전날 칸으로 밀렸다. 이 도구의 핵심 질문이 '누가 언제 마지막으로 일했나' 인데 그 답이
      틀리면 나머지가 다 무의미하다. 그래서 **받는 즉시** 로컬로 바꿔 저장한다.
    """
    if not ts:
        return ""
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if d.tzinfo is not None:
            d = d.astimezone().replace(tzinfo=None)
        return d.isoformat(timespec="seconds")
    except Exception:                                        # noqa: BLE001
        return ts[:19]


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
                ts = _local_iso(str(o.get("timestamp") or ""))   # UTC → 로컬. 훅 기록과 맞춘다
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


# ── 예약 작업(작업 스케줄러) ─────────────────────────────────────────────────
# 어휘(org-contracts §3.1): '예약 작업' = 작업 스케줄러의 작업, '정기 작업' = 일일 리포트 `## 정기 작업` 표의 작업.
NEVER = "1999-11-30"          # Windows 가 '한 번도 실행 안 됨'을 이 날짜로 표기한다
_PS_DATE = re.compile(r"/Date\((-?\d+)\)/")

# ★ `schtasks /fo CSV` 를 쓰면 안 된다. 2026-09-23 실측: **CSV 헤더가 UI 언어로 나온다** —
#   PowerShell 에서는 `TaskName` 인데 파이썬 subprocess 에서는 `작업 이름` 이었다(호스트
#   프로세스 로케일에 달렸다). 열 이름으로 찾으니 전 행이 걸러져 0건이 됐고, 예외가 아니라
#   **조용히 빈 화면**이 나왔다. Get-ScheduledTask 는 속성 이름이 언어와 무관하게 고정이다.
#   OPS-4(2026-09-27): 트리거(주기)와 등록 날짜도 읽는다 — '조용히 안 도는 작업'을 가르려면 작업마다
#   주기가 필요한데, 작업 이름에 주기를 박지 않고 **트리거에서** 읽기 위해서다(org_runtime.silence_verdict).
#   `Export-ScheduledTask` XML 은 요소 이름이 언어와 무관하다. 실패해도 목록은 그대로 내고 사유만 싣는다
#   (`TriggerError`) — 트리거를 못 읽었다고 작업 목록 전체를 '못 읽음'으로 만들지 않는다. 읽기만 한다.
#   실측(09-27, 작업 9개): 3.2초 → 4.7초.
_PS_SCHED = (
    "Get-ScheduledTask -ErrorAction SilentlyContinue | "
    "Where-Object { $_.TaskName -match 'naechaget' } | "
    "ForEach-Object { $t = $_; $i = $t | Get-ScheduledTaskInfo; $tx = $null; $te = $null; "
    "try { $tx = ([xml](Export-ScheduledTask -TaskName $t.TaskName -TaskPath $t.TaskPath "
    "-ErrorAction Stop)).Task.Triggers.OuterXml } catch { $te = [string]$_.Exception.Message }; "
    "[pscustomobject]@{ "
    "TaskName=$t.TaskName; State=[string]$t.State; LastRunTime=$i.LastRunTime; "
    "LastTaskResult=$i.LastTaskResult; NextRunTime=$i.NextRunTime; "
    "Registered=[string]$t.Date; Triggers=$tx; TriggerError=$te } } | "
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


# ── 예약 작업 주기 — 트리거 XML 에서 읽는다(OPS-4, Steward 결정 2026-09-27) ─────────────
_TASK_NS = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"
_DOW = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December")
_ISO_DUR = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")
DAY_S = 86400
MONTH_S = 31 * DAY_S          # 달 길이가 달라 가장 긴 달로 센다 — 주기를 길게 잡을수록 헛경보가 준다


def _iso_duration(s) -> int | None:
    """작업 스케줄러의 반복 간격(`PT1H`·`PT1M`·`P1D`·`P1DT2H`) → 초. 못 읽으면 None."""
    m = _ISO_DUR.match(str(s or "").strip())
    if not m or not any(m.groups()):
        return None
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return (d * DAY_S + h * 3600 + mi * 60 + se) or None


def _local_naive(s) -> datetime | None:
    """ISO 시각(오프셋 있거나 없거나) → 이 PC 현지 naive 시각. 못 읽으면 None."""
    try:
        dt = datetime.fromisoformat(str(s or "").strip())
    except ValueError:
        return None
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo is not None else dt


def local_minutes(s) -> str:
    """ISO 시각(오프셋 있거나 없거나) → 이 PC 현지 시각 'YYYY-MM-DD HH:MM'. 못 읽으면 ''."""
    dt = _local_naive(s)
    return "" if dt is None else dt.isoformat(sep=" ", timespec="minutes")


def _max_gap(idx: list[int], cycle: int) -> int:
    """한 주기(cycle) 안에서 고른 자리들 사이의 가장 긴 간격(한 바퀴 돌아오는 간격 포함)."""
    s = sorted(set(idx))
    if not s:
        return cycle
    return max([b - a for a, b in zip(s, s[1:])] + [cycle - s[-1] + s[0]])


def trigger_period(xml_text: str, now: datetime | None = None) -> dict:
    """예약 작업 `<Triggers>` XML → {"period_s", "first_start", "error"}.

    - `period_s`: **살아 있는** 트리거들 중 **가장 짧은** 반복 주기(초). 매일 = DaysInterval×1일, 매주 = 고른 요일 사이
      가장 긴 간격(WeeksInterval 반영), 매월 = 고른 달 사이 가장 긴 간격 × 31일. 부팅·로그온·한 번 실행처럼
      **주기가 없는** 작업은 None 이다(이상이 아니다).
      - 반복(`Repetition/Interval`)은 **무기한일 때만** 주기다(`Duration` 이 없거나 0). 끝나는 `Duration` 이 바깥
        트리거 주기보다 짧으면 반복은 그날 창 안에서만 돌므로 **바깥 트리거 주기**를 쓴다 — '토요일 13:00 부터 3시간
        동안 매시'는 매주 작업이다(QA-OPS4-1). `Duration` 이 바깥 주기 이상이면 창이 이어지므로 반복 간격을 쓴다.
        바깥 주기가 없는 한 번 트리거의 유한 반복은 `StartBoundary + Duration` 에 끝난다 — 끝났으면 죽은 트리거다.
        바깥 주기가 있는데 `Duration` 글자를 못 읽으면 무기한으로 치지 않는다(바깥 주기 — 짧게 잡으면 헛경보 쪽으로
        틀린다). 바깥 주기가 없으면 끝을 알 수 없으므로 반복 간격을 쓴다.
    - 죽은 트리거는 세지 않는다: 꺼진 것(`Enabled` false), **끝난 것**(`EndBoundary` 가 `now` 이전 — QA-OPS4-2).
      끝난 매일 트리거 + 살아 있는 매주 트리거인 작업은 매주 작업이다.
    - `first_start`: 살아 있는 트리거의 가장 이른 `StartBoundary`(현지 시각) — 첫 실행은 이보다 빠를 수 없다.
    - `error`: XML 을 못 읽었을 때만. 트리거가 아예 없는 작업은 오류가 아니라 주기 None 이다.
    - `now`: 끝남을 가르는 기준(없으면 지금). 읽는 순간의 판정이다 — 목록을 다시 읽으면 다시 계산한다.
    """
    import xml.etree.ElementTree as ET                       # noqa: PLC0415

    now = now or datetime.now()
    out = {"period_s": None, "first_start": "", "error": ""}
    if not str(xml_text or "").strip():
        return out
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        out["error"] = f"트리거 XML 을 해석하지 못했다({e})"
        return out
    ns = _TASK_NS
    periods, starts = [], []
    for trig in list(root):
        if (trig.findtext(f"{ns}Enabled") or "").strip().lower() == "false":
            continue                                         # 꺼진 트리거는 작업을 부르지 않는다
        end = _local_naive(trig.findtext(f"{ns}EndBoundary") or "")
        if end is not None and end <= now:
            continue                                         # 끝난 트리거도 작업을 부르지 않는다(QA-OPS4-2)
        sb_dt = _local_naive(trig.findtext(f"{ns}StartBoundary") or "")
        base = None
        if trig.tag == f"{ns}CalendarTrigger":
            day, week = trig.find(f"{ns}ScheduleByDay"), trig.find(f"{ns}ScheduleByWeek")
            month = trig.find(f"{ns}ScheduleByMonth")
            if month is None:
                month = trig.find(f"{ns}ScheduleByMonthDayOfWeek")
            if day is not None:
                base = int(day.findtext(f"{ns}DaysInterval") or 1) * DAY_S
            elif week is not None:
                dow = week.find(f"{ns}DaysOfWeek")
                days = [] if dow is None else [_DOW.index(c.tag[len(ns):]) for c in dow
                                                if c.tag[len(ns):] in _DOW]
                base = _max_gap(days, 7 * int(week.findtext(f"{ns}WeeksInterval") or 1)) * DAY_S
            elif month is not None:
                mos = month.find(f"{ns}Months")
                idx = list(range(12)) if mos is None else [_MONTHS.index(c.tag[len(ns):]) for c in mos
                                                          if c.tag[len(ns):] in _MONTHS]
                base = _max_gap(idx, 12) * MONTH_S
        rep = _iso_duration(trig.findtext(f"{ns}Repetition/{ns}Interval"))
        dur_txt = (trig.findtext(f"{ns}Repetition/{ns}Duration") or "").strip()
        if rep and dur_txt:
            dur = _iso_duration(dur_txt)                     # None = 0(무기한) 또는 못 읽음
            unreadable = dur is None and not _ISO_DUR.match(dur_txt)
            if base is not None:
                if unreadable or (dur is not None and dur < base):
                    rep = None                               # 창 안에서만 반복 — 바깥 트리거 주기(QA-OPS4-1)
            elif dur is not None and (sb_dt is None or sb_dt + timedelta(seconds=dur) <= now):
                continue                                     # 한 번 트리거의 유한 반복이 끝났다 — 죽은 트리거
        if sb_dt is not None:
            starts.append(sb_dt.isoformat(sep=" ", timespec="minutes"))
        cand = [x for x in (base, rep) if x]
        if cand:
            periods.append(min(cand))
    out["period_s"] = min(periods) if periods else None
    out["first_start"] = min(starts) if starts else ""
    return out


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
        tp = trigger_period(r.get("Triggers") or "")
        out.append({
            "name": str(r.get("TaskName", "")).lstrip("\\"),
            "status": state, "running": running,
            "last_run": last, "last_result": res,
            "next_run": _ps_date(r.get("NextRunTime")),
            "enabled": state.lower() != "disabled",
            "never_ran": last.startswith(NEVER),
            "ok": res == "0" or running,
            # OPS-4: 주기(초, 없으면 None)·첫 트리거 시작·등록 날짜(없으면 '') — org_runtime.silence_verdict 가 쓴다
            "period_s": tp["period_s"], "first_start": tp["first_start"],
            "registered": local_minutes(r.get("Registered") or ""),
            "trigger_error": str(r.get("TriggerError") or "").strip() or tp["error"],
        })
    if not out:
        return [], "예약 작업이 0건이다 — 등록이 지워졌는지 확인할 것"
    return sorted(out, key=lambda t: t["name"]), None


def attach_verdict(sched: list[dict]) -> tuple[list[str], str | None]:
    """예약 작업 행마다 `verdict` 를 싣는다 — 순환계 `org_runtime.schedule_verdict` 의 결과 **그대로**(OPS-4 r3, QA-OPS4-4 ⓐ).

    `verdict` = {"broken": bool, "label": str}. 결재함 '예약 작업 경보'의 고장 판정과 같은 함수·같은 글자다 —
    '꺼짐(Disabled)'·'다음 실행 없음'(결과 0)도 여기서 고장으로 온다. r2 까지 표는 결과 0 인 이 둘을 초록 '정상'으로
    칠했다(결재함은 경보). 순환계는 같은 함수를 **고장 먼저, 조용한 누락은 고장이 아닐 때만** 순서로 부른다
    (`org_runtime.judge_task`) — 그래서 한 행에 `verdict.broken` 과 `silence.bad` 가 함께 참일 수 없다.
    ★ 규칙(판정 순서·글자)을 이 파일에 다시 짜지 않는다.
    ★ 못 붙이면 행의 `verdict` 는 None 이다(모름) — '정상'(broken False)으로 채우지 않는다. 행에 판정에 쓰는 칸
      (`org_runtime.SCHEDULE_FIELDS`)이 하나라도 없으면 그 행도 None 이다: `enabled` 가 빠진 행을 판정하면 꺼진
      작업이 '정상'으로 나온다. `read_schedule` 은 여섯 칸을 늘 채운다(순환계 `Org.schedule_states` 도 이 함수를 부른다).
    반환: (행 경고 — 칸이 빠짐·판정 실패, 오류). 둘 다 화면 '못 읽은 것'으로 올린다.
    """
    for s in sched:
        s["verdict"] = None
    if not sched:
        return [], None
    try:
        tools_dir = str(Path(__file__).resolve().parent)
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        import org_runtime                                   # noqa: WPS433
        judge, fields = org_runtime.schedule_verdict, tuple(org_runtime.SCHEDULE_FIELDS)
    except Exception as e:                                   # noqa: BLE001
        return [], f"예약 작업 고장 판정을 싣지 못했다: {type(e).__name__}: {e}"[:160]
    warns: list[str] = []
    for s in sched:
        miss = [f for f in fields if f not in s]
        if miss:
            warns.append(f"예약 작업 `{s.get('name', '?')}` 행에 판정 칸({', '.join(miss)})이 없다 — 고장 판정을 싣지 않음")
            continue
        try:
            broken, label = judge(s)
        except Exception as e:                               # noqa: BLE001
            warns.append(f"예약 작업 `{s.get('name', '?')}` 의 고장 판정이 실패했다({type(e).__name__}) — 싣지 않음")
            continue
        s["verdict"] = {"broken": bool(broken), "label": str(label)}
    return warns, None


def attach_silence(sched: list[dict], now: datetime | None = None) -> tuple[list[str], str | None]:
    """예약 작업 행마다 `silence` 를 싣는다 — 순환계 `org_runtime.Org.silence_rows` 의 결과 **그대로**(OPS-4 r2).

    `silence` = {bad, label, since, limit_h, cls, warn} (`org_runtime.silence_verdict` 반환 모양).
    ★ 판정 규칙(주기 분류 · §1 한도 · 첫 실행 기준 · task_seen)을 이 파일에 다시 짜지 않는다. 규칙이 두 벌이면
      결재함은 '예약 작업 경보'(주황)인데 표는 '정상'(초록)이라고 말한다 — design-critic 2026-09-27 #1 이 코드로 확인한 모순.
    ★ 못 붙이면 행의 `silence` 는 None 이다(모름). '정상'(bad False)으로 채우지 않는다.
    반환: (판정 경고 — 트리거를 못 읽음·§1 한도 없음, 오류). 둘 다 화면 '못 읽은 것'으로 올린다.
    """
    for s in sched:
        s["silence"] = None
    if not sched:
        return [], None
    try:
        tools_dir = str(Path(__file__).resolve().parent)
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        import org_runtime                                   # noqa: WPS433
        verdicts = org_runtime.Org(ROOT).silence_rows(sched, now)
    except Exception as e:                                   # noqa: BLE001
        return [], f"조용히 안 도는 예약 작업을 판정하지 못했다: {type(e).__name__}: {e}"[:160]
    warns: list[str] = []
    for s in sched:
        v = verdicts.get(s["name"])
        s["silence"] = v
        if v and v.get("warn") and v["warn"] not in warns:
            warns.append(v["warn"])
    return warns, None


def schedule_counts(sched: list[dict]) -> dict:
    """KPI '예약 작업' 타일의 수. 표(`d.schedule`)와 **같은 행**에서 센다 — 타일과 표가 다른 말을 못 하게.

    - `sched_never`: 실행된 적도 예정도 없음 · `sched_bad`: 실패(결과 ≠ 0) — 둘 다 빨강 몫(전과 같다).
    - `sched_silent`: 조용히 안 돎 + 첫 실행 없음(행의 `silence.bad`) — OPS-4 r2. 판정을 못 붙였으면 None(0 이 아니다).
    - `sched_pending`: 첫 실행 대기(예정 있음) — **첫 실행 없음으로 판정된 작업은 빼고** 센다(대기가 아니라 경보다).
    - `sched_stopped`: 꺼짐(Disabled)·다음 실행 없음 — 행의 `verdict.broken` 인데 never 도 bad 도 아닌 것(결과는 0 인데
      다시 돌지 않는다). OPS-4 r3(QA-OPS4-4 ⓐ). 판정을 못 붙인 행이 있으면 None(0 이 아니다). 꺼졌는데 마지막 결과가
      0 이 아닌 행은 전처럼 bad 에 센다(`verdict.label` 은 '꺼짐(Disabled)') — 두 번 세지 않는다.
    - `sched_alarm`: never + bad + silent + stopped — 볼 것이 있는 작업 수(서로 겹치지 않는다: silent 는 결과 0·예정 있음·
      고장 아님뿐, stopped 는 결과 0·고장뿐). 순환계 결재함에 '예약 작업 경보'가 설 수 있는 작업과 같은 집합이다.
    """
    judged = all(s.get("silence") is not None for s in sched)
    judged_v = all(s.get("verdict") is not None for s in sched)
    quiet = {s["name"] for s in sched if (s.get("silence") or {}).get("bad")}
    never_set = {s["name"] for s in sched if s["never_ran"] and not s.get("next_run")}
    bad_set = {s["name"] for s in sched if not s["ok"] and not s["never_ran"]}
    stopped = {s["name"] for s in sched if (s.get("verdict") or {}).get("broken")} - never_set - bad_set - quiet
    return {
        "sched_total": len(sched),
        "sched_never": len(never_set),
        "sched_pending": sum(1 for s in sched if s["never_ran"] and s.get("next_run") and s["name"] not in quiet),
        "sched_bad": len(bad_set),
        "sched_silent": len(quiet) if judged else None,
        "sched_stopped": len(stopped) if judged_v else None,
        "sched_alarm": len(never_set) + len(bad_set) + len(quiet) + len(stopped),
    }


# ── 산출물·배포·제품 ────────────────────────────────────────────────────────
def read_agent_events() -> dict:
    """훅이 남긴 시작·종료 기록을 읽는다 — **'지금 실행 중'을 지어내지 않고 아는 유일한 길**.

    시작(SubagentStart) 기록은 있는데 같은 `aid` 의 종료(SubagentStop) 기록이 없으면
    그 에이전트는 가동 중이다. 영상의 'Active N' 타일을 정직하게 만드는 방법이 이것뿐이다.

    ⚠ 훅이 설치되기 **전**에는 이 파일이 없다. 그때 실행 중 0명이라고 표시하면 안 된다 —
      0 은 '아무도 안 돈다'가 아니라 '재지 않았다'이다. `enabled: False` 로 구분해 화면이
      '훅 미설치'라고 말하게 한다.

    ⚠ PowerShell 5.1 의 `-Encoding utf8` 은 파일 첫머리에 BOM 을 붙인다 → utf-8-sig 로 읽는다.
    """
    if not EVENTS.exists():
        return {"enabled": False, "running": [], "recent": [], "durations": {}, "count": 0}
    starts: dict[str, dict] = {}
    done: dict[str, float] = collections.defaultdict(float)
    n_done: dict[str, int] = collections.defaultdict(int)
    recent: list[dict] = []
    bad = 0
    try:
        with open(EVENTS, "r", encoding="utf-8-sig", errors="replace") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    o = json.loads(ln)
                except Exception:                            # noqa: BLE001
                    bad += 1
                    continue
                ev, aid = str(o.get("event", "")), str(o.get("aid", ""))
                recent.append({"ts": o.get("ts", ""), "event": ev, "agent": o.get("agent", "")})
                if ev == "SubagentStart":
                    starts[aid] = o
                elif ev == "SubagentStop":
                    s = starts.pop(aid, None)
                    if s:
                        try:
                            d = (datetime.fromisoformat(str(o.get("ts"))[:19])
                                 - datetime.fromisoformat(str(s.get("ts"))[:19])).total_seconds()
                            if 0 <= d < 24 * 3600:
                                agent = str(s.get("agent") or "")
                                done[agent] += d
                                n_done[agent] += 1
                        except Exception:                    # noqa: BLE001
                            pass
    except Exception as e:                                   # noqa: BLE001
        return {"enabled": True, "error": f"이벤트 로그 읽기 실패: {type(e).__name__}",
                "running": [], "recent": [], "durations": {}, "count": 0}

    # ★ Stop 이 유실되면 그 에이전트는 **영원히 '실행 중'** 으로 남는다. 없는 상태를 지어내지
    #   않겠다고 만든 도구가 정확히 그 짓을 하게 된다. 그래서 너무 오래된 시작은 실행 중으로
    #   치지 않고 'stale' 로 따로 뺀다 — 서브에이전트가 30분 넘게 도는 일은 우리 작업에 없었다
    #   (2026-09-22 기준 가장 긴 것이 6분대였다). 모르면 '실행 중'이 아니라 '모름'이다.
    STALE_SEC = 30 * 60
    now = datetime.now()
    running, stale = [], []
    for aid, s in starts.items():
        row = {"agent": str(s.get("agent") or "?"), "since": s.get("ts", ""), "aid": aid}
        try:
            age = (now - datetime.fromisoformat(str(s.get("ts"))[:19])).total_seconds()
        except Exception:                                    # noqa: BLE001
            age = None
        (stale if (age is None or age > STALE_SEC) else running).append(row)
    running.sort(key=lambda r: r["since"])
    stale.sort(key=lambda r: r["since"])
    return {"enabled": True, "running": running, "recent": recent[-20:][::-1],
            "durations": {k: round(done[k] / n_done[k]) for k in n_done if n_done[k]},
            "count": len(recent), "bad": bad}


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


def read_supply() -> tuple[dict, str | None]:
    """공급 상태 — **운영 서버를 읽은 결론 파일**(`data/ops_supply.json`)만 쓴다.

    ★ 옆에 있는 `read_product()` 처럼 로컬 `auction.db` 로 판정하면 안 된다. 그 파일은
      수집이 꺼진 개발 사본이라 `max(collected_at)` 이 며칠씩 낡아 있다(2026-09-23 실측:
      로컬 09-17 vs 운영 09-23). 그 값으로 '수집 멈춤'을 띄우면 **매일 거짓 경보**가 뜨고,
      그러면 사람은 진짜 경보도 안 보게 된다. 결론은 서버를 읽는 쪽이 만든다
      (`tools/daily_ops_report.py` 매일 12:00) — 여기서는 **언제 잰 것인지와 함께** 보여 준다.
    """
    if not SUPPLY.exists():
        return {}, "data/ops_supply.json 이 없다 — 매일 12시 리포트가 만든다"
    try:
        v = json.loads(SUPPLY.read_text(encoding="utf-8"))
    except Exception as e:                                   # noqa: BLE001
        return {}, f"공급 판정 파일을 읽지 못했다: {type(e).__name__}"
    age_h = None
    try:
        age_h = round((datetime.now() - datetime.fromisoformat(v["checked_at"])).total_seconds() / 3600, 1)
    except Exception:                                        # noqa: BLE001
        pass
    v["age_hours"] = age_h
    # 판정 자체가 낡으면 색을 초록으로 두지 않는다 — '어제는 정상이었다'는 오늘의 정상이 아니다.
    v["stale"] = age_h is None or age_h > SUPPLY_MAX_AGE_H
    return v, None


def supply_display(supply: dict, err: str | None) -> tuple[str, str, dict]:
    """공급 판정을 **표시용으로** 한 방향으로 정렬한다: 정상 < 확인 불가 < 이상 < 멈춤.

    ⚠ 판정 자체(`web/ops_health.py`)는 건드리지 않는다. 판정 함수는 옳다 — 여기서 고치는 것은
      **표시**다. 돌려주는 것: (화면 상태, 사유 한 줄, 표시용 supply 사본).

    ★ 2026-09-24 검수 ①. 전에는 머리(띠·타일)만 `unknown` 으로 내리고 표는 파일에 저장된
      원래 `state` 를 그대로 그렸다. 30시간 낡은 '전부 정상' 판정에서 화면은 회색 '확인 불가'
      머리 **바로 아래에 초록 `정상` 칩 7개**를 띄웠다. 사람은 표를 믿는다.
      `web/ops_health.py` 첫머리가 *"'판정 보류(unknown)'를 따로 두는 이유: 모르는 것을
      초록으로 칠하지 않기 위해서다"* 라고 적어 뒀는데 **표가 그 문장을 어기고 있었다.**
      그리고 이 블록이 막으려던 09-19~21 사고의 형태가 정확히 '초록으로 보여서 안 봤다' 다.
      → 낡으면 **행 칩까지 전부** 내린다. 초록이 한 개도 남지 않아야 한다.

    ★ 2026-09-24 검수 ②㉢. 판정 파일을 못 읽은 것을 `problems`(빨간 띠)로 올리지 않는다.
      빨강은 '멈춤'에만 쓴다 — 판정 파일이 없는 첫날 화면이 통째로 빨개지면, 이 파일이
      스스로 적어 둔 *"빨간불을 남발하면 진짜 빨간불을 못 본다"* 를 스스로 어긴다.
      대신 공급 띠 안의 '확인 불가'로 흡수하고 **왜 못 읽었는지**를 그 자리에 적는다
      (파일 부재 · 파싱 실패 · `state` 키 없음 — 세 원인의 문장이 서로 다르다).
    """
    v = dict(supply or {})
    if err:
        return "unknown", err, v
    state = str(v.get("state") or "")
    if not state:
        return "unknown", "판정 파일에 state 가 없다 — 형식이 바뀌었는지 확인할 것", v
    if v.get("stale"):
        age = v.get("age_hours")
        v["signals"] = [{**s, "state": "unknown", "state_stored": s.get("state")}
                        for s in (v.get("signals") or [])]
        # `:g` — 30.0 을 '30' 으로 적는다. 표 머리의 '아래 N행은 30시간 전' 과 같은 수로 읽혀야 한다.
        return "unknown", (f"지금 상태는 모른다 — 저장된 판정이 {age:g}시간 전 것이다"
                           if isinstance(age, (int, float))
                           else "판정 시각을 읽지 못했다 — 언제 잰 것인지 모른다"), v
    return state, str(v.get("headline") or ""), v


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


# ── 편중·유휴 판정·리듬 ──────────────────────────────────────────────────────
# 2026-09-23 오너 지시로 추가. 그때까지 이 화면은 '누가 몇 번 일했나'까지만 말했고
# ① 업무가 한쪽으로 쏠렸는지 ② 정해진 리듬이 끊겼는지는 보지 못했다.
# 실제로 docs/reviews/ 가 11일째 멈춰 있었는데 화면은 전부 초록이었다.

def _md_rows(text: str, section: str, ncells: int) -> list[list[str]]:
    """`## <section>` 구간 안의 표에서 셀 수가 맞는 행만 돌려준다.

    ⚠ 구간을 안 자르면 다른 절의 표까지 먹는다 — read_departments 에서 실제로 당했다.
      첫 칸이 백틱으로 감싸인 행만 데이터로 본다(머리글·구분선은 그래서 저절로 빠진다).
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


_TICK = re.compile(r"^`([^`]+)`$")
_D_DAY = re.compile(r"(20\d\d)-([01]\d)-([0-3]\d)")
_D_WEEK = re.compile(r"(20\d\d)-W([0-5]\d)")
_D_MONTH = re.compile(r"(20\d\d)-([01]\d)(?!\d)")


def _file_date(f: Path) -> tuple[object, str]:
    """이 파일이 '언제 것'인지 — **이름에 적힌 날짜를 mtime 보다 먼저 믿는다.**

    ★ 이름에 날짜가 없으면 mtime 으로 떨어지는데, 그러면 나중에 문서를 손대는 순간
      '방금 돈 것'으로 보인다. 2026-09-23 실측: 주간 보고서의 오타 한 글자를 고쳤더니
      리듬이 곧바로 '0일 전 · 정상'으로 바뀌었다. mtime 을 믿지 말라고 주석까지 달아 놓고
      정작 `2026-W39.md`·`2026-09.md` 는 빠져나가게 뒀다 — 감시 대상이 바로 그 둘이다.
    ★ 주차·월 표기는 **그 구간의 첫날**로 잡는다. 실제보다 늙게 잡는 쪽이 안전하다 —
      늦은 것을 정상으로 보는 오류가, 정상을 늦었다고 보는 오류보다 비싸다.
    """
    n = f.name
    m = _D_DAY.search(n)
    if m:
        try:
            return datetime(int(m[1]), int(m[2]), int(m[3])).date(), "파일명(일)"
        except ValueError:
            pass
    m = _D_WEEK.search(n)
    if m:
        try:
            return datetime.fromisocalendar(int(m[1]), int(m[2]), 1).date(), "파일명(주차)"
        except ValueError:
            pass
    m = _D_MONTH.search(n)
    if m:
        try:
            return datetime(int(m[1]), int(m[2]), 1).date(), "파일명(월)"
        except ValueError:
            pass
    try:
        return datetime.fromtimestamp(f.stat().st_mtime).date(), "수정시각"
    except OSError:
        return None, ""


def read_utilization() -> tuple[dict, list[dict], str | None]:
    """`docs/agent-utilization.md` 의 §2 판정표·§3 리듬표를 읽는다.

    판정을 코드에 박지 않는 이유: 판정은 **사람이 내리는 것**이고 자주 바뀐다.
    문서를 고치면 화면이 따라오게 해 둬야, 문서만 고치고 코드는 방치되는 일이 없다.
    """
    if not UTIL_MD.exists():
        return {}, [], "docs/agent-utilization.md 가 없다 — 유휴 판정과 리듬을 재지 못한다"
    text = UTIL_MD.read_text(encoding="utf-8")

    verdicts: dict[str, dict] = {}
    for c in _md_rows(text, "## 2.", 4):
        m = _TICK.match(c[0])
        if m:
            verdicts[m.group(1)] = {"verdict": c[1].strip("`"), "why": c[2], "when": c[3]}

    rhythms: list[dict] = []
    for c in _md_rows(text, "## 3.", 5):
        m = _TICK.match(c[0])
        if not m:
            continue
        try:
            period = int(c[1])
        except ValueError:                                   # 주기가 숫자가 아니면 리듬이 아니다
            continue
        rhythms.append({"glob": m.group(1), "period": period, "since": c[2],
                        "owner": c[3], "impact": c[4]})

    err = None
    if not verdicts and not rhythms:
        err = "agent-utilization.md 의 §2·§3 표를 찾지 못했다 — 표 형식이 바뀌었는지 확인할 것"
    return verdicts, rhythms, err


def check_rhythms(rhythms: list[dict]) -> list[dict]:
    """산출물이 기대 주기보다 늙었는지 잰다 — 끊긴 리듬을 사람 대신 본다.

    ★ 파일 `mtime` 이 아니라 **파일명의 날짜**를 우선 쓴다. 나중에 문서를 손보면 mtime 이
      갱신돼 '방금 돈 것'처럼 보이기 때문이다. 어느 쪽으로 쟀는지 화면에 함께 적는다.
    ★ '시작' 이전에는 없는 게 정상이다 — 첫 실행 전인 것을 실패로 세면 안 된다.
      2026-09-23 에 주간·월간 예약을 그렇게 오판해 오너에게 잘못 보고했다.
    """
    today = datetime.now().date()
    out = []
    for r in rhythms:
        files = [f for f in ROOT.glob(r["glob"]) if f.is_file() and f.name != "README.md"]
        best, how = None, ""
        for f in files:
            d, h = _file_date(f)
            if d is None:
                continue
            if best is None or d > best:
                best, how = d, h
        try:
            since = datetime.fromisoformat(r["since"]).date()
        except ValueError:
            since = None
        age = (today - best).days if best else None
        if best is None:
            state = "대기" if (since and today < since) else "없음"
        elif age <= r["period"]:
            state = "정상"
        elif age <= r["period"] * 2:
            state = "늦음"
        else:
            state = "끊김"
        out.append({**r, "last": best.isoformat() if best else "", "how": how,
                    "age": age, "count": len(files), "state": state})
    return out


# 담당 구역과 그 주인. ORG.md §1 은 '누가 무엇을 맡는가'를 정하지만 '그 구역에 일이
# 얼마나 있었나'는 거기 없다 — git 이 유일한 실측 출처다.
DELEGATION = [("web/", "frontend-engineer", "화면·템플릿"),
              ("src/", "backend-engineer", "수집·산정 로직"),
              ("tests/", "qa-engineer", "테스트")]


def read_delegation(calls: list[dict], days: int = 30) -> tuple[list[dict], str | None]:
    """담당 구역에 일이 있었는데 담당을 안 불렀는지 본다.

    ★ 2026-09-23 실측: 9/12 이후 `web/` 132커밋·`src/` 24커밋이 있었는데 두 담당의 호출은
      **0회**였다. '호출 0' 을 '일이 없었다' 로 읽으면 정반대 결론이 나온다 —
      실제로 내가 그렇게 읽었고, 그래서 "출시 전이라 일이 없다"고 보고했다. 틀렸다.
    """
    since = (datetime.now() - timedelta(days=days)).date().isoformat()
    out: list[dict] = []
    err = None
    for area, owner, label in DELEGATION:
        commits = None
        try:
            p = subprocess.run(["git", "log", f"--since={since}", "--format=%H", "--", area],
                               cwd=str(ROOT), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=30)
            if p.returncode == 0:
                commits = len([x for x in (p.stdout or "").splitlines() if x.strip()])
        except Exception:                                    # noqa: BLE001
            commits = None
        if commits is None and err is None:
            err = f"git 이력을 읽지 못해 '{label}' 구역의 배분을 재지 못했다"
        n = sum(1 for c in calls if c["agent"] == owner and str(c.get("ts", ""))[:10] >= since)
        out.append({"area": area, "owner": owner, "label": label,
                    "commits": commits, "calls": n, "days": days})
    return out, err


def concentration(roster: list[dict]) -> dict:
    """편중도 — 일이 한 사람에게 얼마나 쏠렸는가."""
    total = sum(a["calls"] for a in roster)
    ranked = sorted(roster, key=lambda a: -a["calls"])
    if not total:
        return {"total": 0, "top1": None, "top1_share": 0.0,
                "top3_share": 0.0, "hhi": 0.0, "ranked": []}
    return {
        "total": total,
        "top1": ranked[0]["name"], "top1_share": round(ranked[0]["calls"] / total * 100, 1),
        "top3_share": round(sum(a["calls"] for a in ranked[:3]) / total * 100, 1),
        # 허핀달 지수 — 1/N 이면 완전히 고르고, 1 이면 한 사람이 전부 한 것이다
        "hhi": round(sum((a["calls"] / total) ** 2 for a in roster), 3),
        "ranked": [{"name": a["name"], "dept": a["dept"], "calls": a["calls"],
                    "share": round(a["calls"] / total * 100, 1),
                    "verdict": a.get("verdict", "")} for a in ranked],
    }


# ── 흐름: 지시서 대기열·인계 (2026-09-26 오너 지시) ─────────────────────────
# 오너 질문: *"뭔가 돌아가는 것 같지 않고, 살아있는 것 같지 않다."* 이 화면은 그때까지
# '누가 몇 번 불렸나'(사후 사실)만 그렸다. 조직이 도는지는 **일이 자리 사이를 흐르는가**로 보인다 —
# 지시서가 쌓이고, 닫히고, 다음 자리로 넘어가는 것. 그 원천은 tools/org_runtime.py 한 곳이다.
ORDER_RULE_SINCE = "2026-09-26"      # 호출 라벨을 지시서 번호로 시작하게 한 날(CLAUDE.md 지휘 절)
FLOW_STALE_H = 2                     # 매시 스캔인데 두 시간 넘게 안 돌았으면 순환이 멈춘 것이다


def read_flow(calls: list[dict]) -> tuple[dict, str | None]:
    """순환계 대기열 요약 + '지시서를 거친 호출' 비율.

    ★ 순환계가 없으면 0 으로 채우지 않는다 — `enabled: False` 로 화면이 '미가동'이라고 말하게 한다
      (훅 미설치를 '0명'으로 그리지 않은 것과 같은 원칙).
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import org_runtime                                   # noqa: WPS433
        org = org_runtime.Org(ROOT)
        b = org.board()
    except Exception as e:                                   # noqa: BLE001
        return {"enabled": False}, f"순환계를 읽지 못했다: {type(e).__name__}: {e}"[:160]
    since = max((datetime.now() - timedelta(days=7)).date().isoformat(), ORDER_RULE_SINCE)
    recent = [c for c in calls if str(c.get("ts", ""))[:10] >= since]
    via = [c for c in recent if org_runtime.ORDER_REF.search(str(c.get("desc", "")))]
    b["via_orders"] = {"since": since, "total": len(recent), "via": len(via),
                       "share": round(len(via) / len(recent) * 100, 1) if recent else None}
    # ★ 분·시간·낡음을 **원시 초에서** 각각 계산한다. 전에는 0.1시간으로 반올림한 값에서 분을 만들어
    #   분이 6분 간격(0·6·…·54)으로만 나왔고, 1.95~2.05시간은 같은 '2시간 전'이 두 색으로 갈렸다
    #   (design-critic 2026-09-27 지적 — 코드로 확인).
    age_s = None
    if b.get("last_scan"):
        try:
            age_s = (datetime.now() - datetime.fromisoformat(b["last_scan"])).total_seconds()
        except ValueError:
            age_s = None
    b["scan_age_h"] = None if age_s is None else round(age_s / 3600, 1)
    b["scan_age_min"] = None if age_s is None else max(0, int(age_s // 60))
    b["scan_stale"] = age_s is None or age_s > FLOW_STALE_H * 3600
    return b, None


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
    # OPS-4 r3: 고장 판정(verdict)도, r2: '조용히 안 돎' 판정(silence)도 순환계 결과를 그대로 싣는다(규칙은 org_runtime 한 곳)
    vwarns, e = attach_verdict(sched)
    if e:
        problems.append(e)
    problems.extend(vwarns)
    warns, e = attach_silence(sched)
    if e:
        problems.append(e)
    problems.extend(warns)
    git, e = read_git()
    if e:
        problems.append(e)
    product, e = read_product()
    if e:
        problems.append(e)
    # ★ 공급 판정을 못 읽은 것은 problems(빨간 띠)로 올리지 않는다 — '확인 불가'지 '멈춤'이
    #   아니다. 아래 supply_display() 가 공급 띠 안으로 흡수하고 사유를 그 자리에 적는다.
    supply, supply_err = read_supply()
    verdicts, rhythms, e = read_utilization()
    if e:
        problems.append(e)
    rhythm = check_rhythms(rhythms)
    deleg, e = read_delegation(stats["calls"])
    if e:
        problems.append(e)

    live = read_agent_events()
    if live.get("error"):
        problems.append(live["error"])
    flow, e = read_flow(stats["calls"])
    if e:
        problems.append(e)
    problems.extend(flow.get("warnings") or [])
    fq = flow.get("queue") or {}
    fseats = flow.get("seats") or {}
    running_now = {r["agent"] for r in live.get("running", [])}

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
                "running": name in running_now,               # 훅이 알려준 '지금 가동 중'
                "avg_sec": live.get("durations", {}).get(name),
                "description": d.get("description", "")[:120],
                "tools": d.get("tools", ""), "model": d.get("model", ""),
                # 순환계 — 이 자리에 쌓인 지시서와 계약. 계약이 없으면 일을 받을 길이 없다.
                "queue": fq.get(name) or {},
                "contract": (fseats.get(name) if flow.get("enabled") else None),
                "auto": bool((fseats.get(name) or {}).get("auto"))}

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

    # 판정을 붙인다. 판정표에 없는 자리는 **조용히 넘기지 않는다** — 조직이 바뀌었는데
    # 문서가 안 따라온 상태이고, 그 자리는 아무도 평가하지 않는 사각지대가 된다.
    total_calls = sum(a["calls"] for a in roster)
    unjudged = []
    for a in roster:
        a["share"] = round(a["calls"] / total_calls * 100, 1) if total_calls else 0.0
        v = verdicts.get(a["name"])
        if v is None:
            unjudged.append(a["name"])
        a["verdict"] = (v or {}).get("verdict", "")
        a["why"] = (v or {}).get("why", "")
        a["when"] = (v or {}).get("when", "")
    if unjudged:
        problems.append(f"판정표에 없는 자리 {len(unjudged)}종({', '.join(unjudged)}) — "
                        "docs/agent-utilization.md §2 에 추가할 것")
    conc = concentration(roster)

    # 우리 15종 밖에서 불린 것(general-purpose 등)도 숨기지 않는다
    known = {a["name"] for a in roster}
    outside = sorted(((k, v) for k, v in per_agent.items() if k not in known),
                     key=lambda kv: -kv[1])

    days = sorted(set(list(stats["per_day"]) + list(stats["tool_per_day"])))[-14:]
    activity = [{"day": d, "agent_calls": stats["per_day"].get(d, 0),
                 "tool_calls": stats["tool_per_day"].get(d, 0)} for d in days]

    week_ago = (now - timedelta(days=7)).isoformat()[:10]
    calls_7d = sum(v for k, v in stats["per_day"].items() if k >= week_ago)

    # 공급 상태 타일 — 화면에서 **제일 먼저** 읽혀야 한다. 2026-09-19~21 의 기록은 이미
    # 어딘가에 다 있었지만 먼저 보이는 자리에 없어서 사흘을 아무도 몰랐다.
    # 띠·타일·행 칩이 **한 함수**를 거쳐 나온다. 셋이 다른 말을 할 수 없게 하기 위해서다.
    _sup_state, _sup_why, supply = supply_display(supply, supply_err)
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "kpi": {
            # 모르면 '정상'이 아니라 '확인 불가'다. 모르는 것을 초록으로 칠하지 않는다.
            "supply_state": _sup_state,
            "supply_why": _sup_why,          # 왜 이 상태인가 — 원인마다 문장이 다르다
            "supply_headline": (supply.get("headline") if supply else ""),
            "supply_alerts": len(supply.get("alerts") or []) if supply else None,
            "agents_total": len(roster), "agents_used": len(used), "agents_never": len(never),
            "calls_total": sum(per_agent.get(a["name"], 0) for a in roster),
            "calls_7d": calls_7d,
            "last_call": (stats["calls"][-1] if stats["calls"] else None),
            # ★ 2026-09-23 정정: '한 번도 실행 안 됨' 을 고장으로 세면 안 된다.
            #   주간(9/26)·월간(10/1) 은 **트리거가 아직 안 온 것**이지 실패가 아니다.
            #   내가 이 표시를 보고 "예약 작업 2개가 한 번도 안 돌았다"고 오너에게 경고했는데,
            #   실제로 dry-run 을 돌려 보니 스크립트는 멀쩡했다. 화면이 나를 오판하게 만든 것이다.
            #   다음 실행 시각이 잡혀 있으면 '대기', 없으면 그때야 '확인 필요'다.
            #   OPS-4 r2: 대기가 등록 후 한도를 넘으면 '첫 실행 없음'(sched_silent)으로 옮긴다 — schedule_counts.
            **schedule_counts(sched),
            # ★ 훅이 없으면 None 이다. 0 이 아니다 — '아무도 안 돈다'와 '재지 않았다'는 다르다.
            "running_now": len(live.get("running", [])) if live.get("enabled") else None,
            # 편중 — 최다 1인이 몇 %를 가져갔나
            "top1": conc["top1"], "top1_share": conc["top1_share"],
            "top3_share": conc["top3_share"],
            # 리듬 — 정해진 주기를 넘긴 산출물. '대기'(시작 전)는 세지 않는다
            "rhythm_total": len(rhythm),
            "rhythm_broken": sum(1 for r in rhythm if r["state"] in ("늦음", "끊김", "없음")),
            # 타일 색을 표의 **최고 심각도**에 묶는다 — 타일과 표가 다른 말을 하면 안 된다
            "rhythm_worst": ("끊김" if any(r["state"] in ("끊김", "없음") for r in rhythm)
                             else ("늦음" if any(r["state"] == "늦음" for r in rhythm) else "정상")),
            # 배분 — 담당 구역에 커밋이 있었는데 담당 호출이 0인 구역
            "unstaffed": sum(1 for d in deleg if d["calls"] == 0 and (d["commits"] or 0) > 0),
        },
        "live": live,
        "flow": flow,
        "departments": dept_out,
        "never_used": [a["name"] for a in never],
        "outside_roster": [{"name": k, "calls": v} for k, v in outside],
        "recent": list(reversed(stats["calls"][-20:])),
        "activity": activity,
        "schedule": sched,
        "concentration": conc,
        "rhythm": rhythm,
        "delegation": deleg,
        "artifacts": read_artifacts(),
        "git": git,
        "product": product,
        "supply": supply,
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
        path, _, qs = self.path.partition("?")
        # ★ 열쇠는 **밖에 열어 둘 때만** 검사한다(로컬 전용이면 TOKEN 이 빈 문자열이라 통과).
        #   이 화면에는 로그인이 없다. 열쇠까지 없으면 같은 망의 누구나 읽는다.
        if TOKEN:
            given = ""
            for part in qs.split("&"):
                if part.startswith("k="):
                    given = part[2:]
                    break
            if given != TOKEN:
                self._send(403, "열쇠가 없다".encode(), "text/plain; charset=utf-8")
                return
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
    _wrap_console()          # ★ 여기서만 감싼다 — 모듈 수준에서 하면 import 한 쪽 출력이 사라진다
    ap = argparse.ArgumentParser(description="에이전트 현황 대시보드(로컬 전용)")
    ap.add_argument("--once", action="store_true", help="JSON 한 번만 출력하고 끝")
    ap.add_argument("--rescan", action="store_true", help="캐시를 버리고 전수 재스캔")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--host", default="127.0.0.1",
                    help="기본값은 이 PC 에서만 열린다. 사내망에 열려면 0.0.0.0")
    ap.add_argument("--token", default="",
                    help="밖에 열 때 요구할 열쇠. 안 주면 자동 생성한다")
    a = ap.parse_args(argv)

    # ★ 인증 없이 밖에 여는 경로를 아예 만들지 않는다. 열쇠를 깜빡하는 쪽이
    #   자연스러운 실수이므로, 깜빡하면 막지 말고 **대신 만들어 준다.**
    global TOKEN                                             # noqa: PLW0603
    TOKEN = a.token
    if a.host not in ("127.0.0.1", "localhost", "::1") and not TOKEN:
        # ★ 켤 때마다 열쇠가 바뀌면 사람이 주소를 매번 다시 받아야 한다. 그게 귀찮아지면
        #   결국 열쇠를 빼고 열게 된다 — 불편한 안전장치는 무력화된다.
        #   그래서 한 번 만들어 data/ 에 남기고 재사용한다. data/ 는 .gitignore 대상이라
        #   저장소에 들어가지 않는다(C.4 ④: 세션값·비밀정보를 코드에 두지 않는다).
        try:
            TOKEN = TOKEN_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            TOKEN = ""
        if not TOKEN:
            TOKEN = os.urandom(9).hex()
            try:
                TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
                TOKEN_FILE.write_text(TOKEN, encoding="utf-8")
            except OSError as e:                             # noqa: BLE001
                print(f"  ⚠ 열쇠를 파일에 남기지 못했다({type(e).__name__}) — "
                      "이번 실행에만 쓰이는 열쇠다", file=sys.stderr)

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
          f" · 예약 작업 {k['sched_total']}개(미실행 {k['sched_never']} · 조용히 안 돎 "
          f"{'판정 못함' if k['sched_silent'] is None else k['sched_silent']} · 꺼짐·다음 실행 없음 "
          f"{'판정 못함' if k['sched_stopped'] is None else k['sched_stopped']})", file=sys.stderr)
    if s["problems"]:
        for p in s["problems"]:
            print(f"  ⚠ {p}", file=sys.stderr)

    # ★ 바인딩 실패에 기대면 안 된다. HTTPServer 는 allow_reuse_address=1 이고,
    #   **Windows 의 SO_REUSEADDR 는 리눅스와 달리 이미 쓰는 주소에도 바인딩을 허용한다.**
    #   2026-09-23 실측: 8765 를 쓰는 중에 또 띄웠더니 에러 없이 둘 다 떠서, 요청이 어느
    #   쪽으로 갈지 알 수 없는 상태가 됐다(한쪽은 옛 코드를 서빙한다). 자동 시작을 걸면
    #   로그온마다 이게 일어난다. 그래서 먼저 접속해 보고 응답이 있으면 물러난다.
    #   TIME_WAIT 소켓은 접속을 받지 않으므로 재시작 직후에 헛걸리지도 않는다.
    import socket
    try:
        with socket.create_connection(("127.0.0.1", a.port), timeout=0.8):
            pass
        print(f"\n  ★ 포트 {a.port} 에 이미 대시보드가 떠 있다 — 두 번 띄우지 않는다.",
              file=sys.stderr)
        print(f"  브라우저에서 http://127.0.0.1:{a.port} 를 열면 된다.", file=sys.stderr)
        print(f"  굳이 따로 띄우려면: python tools/agent_dashboard.py --port {a.port + 1}",
              file=sys.stderr)
        return 1
    except OSError:
        pass                                                 # 아무도 없다 — 정상 경로

    try:
        srv = HTTPServer((a.host, a.port), Handler)
    except OSError as e:
        print(f"\n  ★ 포트 {a.port} 를 열지 못했다: {e}", file=sys.stderr)
        return 1
    key = f"/?k={TOKEN}" if TOKEN else ""
    print(f"\n  http://127.0.0.1:{a.port}{key}  — Ctrl+C 로 종료", file=sys.stderr)
    if TOKEN:
        print(f"  사내망에 열려 있다(바인딩 {a.host}). 다른 PC 는 이 PC 의 IP 로 접속한다:",
              file=sys.stderr)
        print(f"      http://<이 PC 의 IP>:{a.port}/?k={TOKEN}", file=sys.stderr)
        # ★ 2026-09-27 정정: 예전 문구는 "열쇠는 켤 때마다 새로 생긴다" 였는데 위 main() 은 이미
        #   data/dashboard_token.txt 를 **재사용**한다. 문구만 믿고 재기동을 피하거나 --token 을
        #   따로 챙기는 사람이 생긴다 — 동작과 같은 말을 한다.
        print("  열쇠 없는 요청은 403 으로 막는다. 열쇠는 data/dashboard_token.txt 에서 재사용한다"
              " — 바꾸려면 그 파일을 지우고 다시 띄운다(--token 으로 직접 줄 수도 있다).",
              file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
