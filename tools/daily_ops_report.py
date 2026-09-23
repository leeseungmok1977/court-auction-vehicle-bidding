#!/usr/bin/env python3
"""매일 12시 작업 결과 리포트 → docs/daily-reports/YYYY-MM-DD.md

사용자 지시(2026-09-16): 매일 1회 12시에 작업 결과를 리포트로 남긴다 — 어떤 작업을 했고, 실제 몇 건이며,
성공·실패 여부. 일자별 md 파일로 별도 폴더에 정리한다.

기간은 **전날 12:00 ~ 당일 12:00(한국 시간)** 이다. 매일 06:30 갱신이 늘 이 창 안에 들어온다.

어디서 무엇을 읽나 — 전부 읽기 전용이고, 법원·엔카 같은 외부 사이트에는 요청하지 않는다(CLAUDE.md C.4).
  ① 운영 서버(ssh): runs 테이블 · 엔카 연결 상태(settings) · SSL 갱신(certbot 저널) · 서비스 가동 상태
  ② 이 PC: 주간 사진 점검 작업 · 집 회선 터널 작업과 로그
  ③ GitHub: 주간 전문가 패널 루틴이 커밋한 리포트(공개 저장소라 인증 없이 fetch 된다)
읽지 못한 곳은 '확인 불가'로 적는다. **모르는 것을 성공으로 적지 않는다.**

이 PC에서 도는 이유: 세 곳을 모두 볼 수 있는 곳이 여기뿐이다(클라우드 루틴은 서버 키도 PC도 못 본다).

서버 기록을 읽는 규칙(web/service.py::daily_update 의 요약 문장 형식):
  "입찰예정 441 · 분석 32 · 동급참조 22 · 출시가 3건(대기 282) · 사진정렬 49건 · 낙찰결과 256건 · ⚠엔카 error(HTTP None)"
  - 0건인 단계는 문장에서 **빠진다** → 빠진 단계는 '0건'이다(성공으로 부풀리지 않고 '처리 없음'으로 적는다).
  - 중간에 끊긴 실행은 요약 대신 **마지막 진행 메시지**가 남는다 → 그 메시지로 어느 단계에서 멈췄는지 판정한다.

사용:
  python tools/daily_ops_report.py                 # 오늘 날짜 리포트 작성
  python tools/daily_ops_report.py --date 2026-09-15
  python tools/daily_ops_report.py --stdout        # 파일 대신 화면에
작업 등록(관리자 1회): tools/register_daily_report_task.ps1
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from web import ops_health  # noqa: E402 — 판정은 앱과 같은 한 곳을 쓴다(표준 라이브러리만 쓰는 모듈)

OUT_DIR = ROOT / "docs" / "daily-reports"
SERVER = "ubuntu@43.202.126.180"
KEY = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Downloads" / "naechaget.pem"
LOCAL_STATE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "naechaget"
PHOTO_LOG = ROOT / "data" / "_photo_work" / "weekly_check.log"
TUNNEL_LOG = LOCAL_STATE / "home_tunnel.log"
REPORT_HOUR = 12
# 공급 판정에 쓸 운영 `runs` 를 리포트 창보다 며칠 더 읽는다(연속 0건 판정에 필요).
SUPPLY_RUN_DAYS = 7
# 사내 대시보드(tools/agent_dashboard.py)가 읽는 자리. data/ 는 git 제외이고 같은 PC 안이다.
# ⚠ 대시보드가 **로컬 auction.db 로 공급을 판정하면 안 된다** — 그건 수집이 꺼진 개발 사본이라
#   매일 '수집 멈춤' 거짓 경보가 뜬다(2026-09-23 실측: 로컬 09-17 vs 운영 09-23).
SUPPLY_OUT = ROOT / "data" / "ops_supply.json"

OK = "✅ 성공"
FAIL = "❌ 실패"
WARN = "⚠️ 경고"
SKIP = "⏭️ 미실행"
NA = "— 없음"
UNKNOWN = "❔ 확인 불가"
RUNNING = "⏳ 진행 중"

# 정기 작업 일정(2026-09-16 실측: 서버 settings·작업 스케줄러·클라우드 루틴). 바뀌면 여기와 README를 같이 고친다.
PANEL_WEEKDAY, PANEL_AT = 5, (9, 20)        # 토요일 09:20 — 클라우드 루틴 '경매로 내차GET 주간 전문가 패널'
PHOTO_WEEKDAY, PHOTO_AT = 6, (8, 17)        # 일요일 08:17 — PC 작업 NaechaGet-PhotoClassify
PHOTO_TASK = "NaechaGet-PhotoClassify"
TUNNEL_TASK = "naechaget-home-tunnel"


# ── 기간 ──────────────────────────────────────────────────────────
def report_window(day: date) -> tuple[datetime, datetime]:
    """리포트 날짜의 기간: 전날 12:00 이상 ~ 당일 12:00 미만."""
    until = datetime.combine(day, dtime(REPORT_HOUR, 0))
    return until - timedelta(days=1), until


def weekly_due(since: datetime, until: datetime, weekday: int, hh: int, mm: int) -> Optional[datetime]:
    """기간 안에 든 주간 예정 시각. 없으면 None. weekday 는 월=0 … 일=6."""
    d = since.date()
    while datetime.combine(d, dtime(0, 0)) < until:
        at = datetime.combine(d, dtime(hh, mm))
        if d.weekday() == weekday and since <= at < until:
            return at
        d += timedelta(days=1)
    return None


def _dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


# ── 서버 기록 해석 ────────────────────────────────────────────────
_TOKENS = [
    ("stored", re.compile(r"^입찰예정 (\d+)$")),
    ("analyzed", re.compile(r"^분석 (\d+)$")),
    ("reuse", re.compile(r"^동급참조 (\d+)$")),
    ("requery", re.compile(r"^0표본 재조회 (\d+)$")),
    # 2026-09-16부터 멈춘 사유가 붙는다: '출시가 3건(대기 282·예산 2400 소진)', '…(대기 0·⚠차단 HTTP 403)'
    ("newcar", re.compile(r"^출시가 (\d+)건\(대기 (\d+)(?:·([^)]+))?\)$")),
    ("newcar_running", re.compile(r"^출시가 수집 중$")),       # 긴 수집 직전에 먼저 남기는 요약의 꼬리표
    ("photos", re.compile(r"^사진정렬 (\d+)건$")),
    ("photos_skipped", re.compile(r"^⚠사진정렬 건너뜀$")),
    ("results", re.compile(r"^낙찰결과 (\d+)건$")),
    ("review", re.compile(r"^검토 재확인 (\d+)\(복원 (\d+)·보류 (\d+)\)$")),
    ("encar", re.compile(r"^⚠엔카 (\S+)\(HTTP ([^)]*)\)$")),
]

# 매일 갱신 단계 — daily_update 의 실행 순서 그대로(중단 지점 판정에 순서가 쓰인다).
# 2026-09-16: 출시가 수집을 맨 뒤로 옮겼다(상한 2,400회 × 5초 = 최대 3시간 20분이라 앞에 두면 낙찰결과·추천이 늦어진다).
DAILY_STEPS = [
    ("list", "입찰예정 목록 수집"),
    ("encar", "엔카 시세 조회 연결"),
    ("analyze", "시세 분석"),
    ("requery", "0표본 차종 재조회"),
    ("reuse", "동급 시세 참조 보완"),
    ("photos", "사진 자동 정렬"),
    ("results", "낙찰결과 반영"),
    ("review", "무결성 검토"),
    ("newcar", "당시 출시가 수집"),
]
# 그 전 기록(출시가가 동급 참조 바로 다음이던 시절)의 중단 지점은 옛 순서로 판정해야 뒤 단계를 '완료'로 오판하지 않는다.
# 옛 코드만 '당시 출시가 범위 수집(보배드림)' 진행 메시지를 남겼으므로 그 문구로 구분한다.
LEGACY_DAILY_STEPS = [
    ("list", "입찰예정 목록 수집"),
    ("encar", "엔카 시세 조회 연결"),
    ("analyze", "시세 분석"),
    ("requery", "0표본 차종 재조회"),
    ("reuse", "동급 시세 참조 보완"),
    ("newcar", "당시 출시가 수집"),
    ("photos", "사진 자동 정렬"),
    ("results", "낙찰결과 반영"),
    ("review", "무결성 검토"),
]
_STEP_LABEL = dict(DAILY_STEPS)

# 끝나지 못한 실행의 마지막 진행 메시지 → 멈춘 단계. 위에서부터 먼저 맞는 것.
_PROGRESS = [
    (re.compile(r"^목록 \d+페이지 순회"), "list"),
    (re.compile(r"분석 중 엔카 차단 감지"), "analyze"),
    (re.compile(r"엔카 차단 감지"), "encar"),
    (re.compile(r"^시세 분석 \d+/\d+"), "analyze"),
    (re.compile(r"^시세 0표본 재조회"), "requery"),
    (re.compile(r"^동급 시세 참조 적용"), "reuse"),
    (re.compile(r"^당시 출시가 범위 수집"), "newcar"),
    (re.compile(r"^사진 자동 정렬"), "photos"),
    (re.compile(r"^낙찰결과 조회"), "results"),
    (re.compile(r"^최종 검토"), "review"),
]


RESTART_SUFFIX = " (서버 재시작으로 중단됨)"      # web/db.py 가 재시작 때 실행 중이던 기록 뒤에 붙이는 문구


def is_daily_summary(msg: Optional[str]) -> bool:
    return bool(re.match(r"^입찰예정 \d+ · 분석 \d+", msg or ""))


def parse_daily_message(msg: str) -> dict:
    """매일 갱신 요약 문장 → 단계별 값. 모르는 조각은 unknown 에 모은다(버리지 않는다).

    서버가 재시작되면 마지막 메시지 뒤에 ' (서버 재시작으로 중단됨)'이 붙는다 — 떼어 내고 interrupted 로 표시한다.
    """
    out: dict = {"unknown": []}
    text = msg or ""
    if RESTART_SUFFIX in text:
        text = text.replace(RESTART_SUFFIX, "")
        out["interrupted"] = True
    for part in text.split(" · "):
        part = part.strip()
        if not part:
            continue
        for key, rx in _TOKENS:
            m = rx.match(part)
            if m:
                g = m.groups()
                if key in ("photos_skipped", "newcar_running"):
                    out[key] = True
                elif key == "encar":
                    out[key] = (g[0], g[1])
                elif key == "newcar":
                    out[key] = (int(g[0]), int(g[1]))
                    if g[2]:
                        out["newcar_why"] = g[2].strip()
                elif len(g) == 1:
                    out[key] = int(g[0])
                else:
                    out[key] = tuple(int(x) for x in g)
                break
        else:
            out["unknown"].append(part)
    return out


def progress_step(msg: Optional[str]) -> Optional[str]:
    for rx, key in _PROGRESS:
        if rx.search(msg or ""):
            return key
    return None


def _row(key: str, count: str, status: str) -> dict:
    return {"step": _STEP_LABEL[key], "count": count, "status": status}


def _newcar_row(p: dict, run_status: Optional[str]) -> dict:
    """당시 출시가 수집 행. 예산 소진은 백필을 여러 날에 나눠 도는 정상 동작이라 성공, 차단·오류는 실패."""
    nc, why = p.get("newcar"), p.get("newcar_why") or ""
    if p.get("newcar_running") and not nc:
        # 앞 단계 요약은 남았는데 수집이 끝나지 않았다 — 아직 도는 중이거나 재시작으로 끊겼다
        live = run_status == "running"
        return _row("newcar", "진행 중" if live else "중단", RUNNING if live else FAIL)
    if not nc:
        return _row("newcar", "0건", NA)
    count = f"{nc[0]}건 (대기 {nc[1]}{' · ' + why if why else ''})"
    return _row("newcar", count, FAIL if why.startswith("⚠") else OK)


def daily_steps(run: dict) -> list[dict]:
    """매일 갱신 1회의 단계별 건수·결과."""
    msg = (run.get("message") or "").strip()
    status = run.get("status")
    if is_daily_summary(msg):
        # 요약이 있으면, 끝났든(done) 맨 끝 출시가 수집에서 끊겼든(error·running) 앞 단계 건수는 확정이다
        p = parse_daily_message(msg)
        enc = p.get("encar")
        rv = p.get("review")
        return [
            _row("list", f"{p.get('stored', 0)}건", OK),
            _row("encar", f"{enc[0]} (HTTP {enc[1]})" if enc else "정상", FAIL if enc else OK),
            # 엔카 연결이 실패한 날에도 분석 건수가 찍힐 수 있다 — 건수는 기록대로 두고 경고로 표시한다
            _row("analyze", f"{p.get('analyzed', 0)}건", WARN if enc else OK),
            _row("requery", f"{p['requery']}건", OK) if p.get("requery") else _row("requery", "0건", NA),
            _row("reuse", f"{p['reuse']}건", OK) if p.get("reuse") else _row("reuse", "0건", NA),
            (_row("photos", "건너뜀", FAIL) if p.get("photos_skipped")
             else _row("photos", f"{p['photos']}건", OK) if p.get("photos")
             else _row("photos", "0건", NA)),
            _row("results", f"{p.get('results', 0)}건", OK),
            (_row("review", f"재확인 {rv[0]} · 복원 {rv[1]} · 보류 {rv[2]}", WARN if rv[2] else OK) if rv
             else _row("review", "이상 없음", OK)),
            _newcar_row(p, status),
        ]

    # 요약 없이 진행 메시지만 남은 실행 — 어느 단계에서 멈췄는지로 판정한다.
    # 옛 코드만 '당시 출시가 범위 수집(보배드림)' 진행 메시지를 남겼다 → 그 기록은 옛 단계 순서로 읽는다.
    steps = LEGACY_DAILY_STEPS if "당시 출시가 범위 수집" in msg else DAILY_STEPS
    at = progress_step(msg)
    keys = [k for k, _ in steps]
    live = status == "running"
    rows = []
    for i, (k, _label) in enumerate(steps):
        if at is None:
            rows.append(_row(k, "기록 없음", RUNNING if live else UNKNOWN))
            continue
        j = keys.index(at)
        if i < j:
            rows.append(_row(k, "완료 · 건수 기록 없음", OK))
        elif i == j:
            rows.append(_row(k, "진행 중" if live else "중단", RUNNING if live else FAIL))
        else:
            rows.append(_row(k, "—", RUNNING if live else SKIP))
    return rows


def daily_counts(run: dict) -> str:
    msg = (run.get("message") or "").strip()
    if is_daily_summary(msg):
        p = parse_daily_message(msg)
        base = f"입찰예정 {p.get('stored', 0)} · 분석 {p.get('analyzed', 0)} · 낙찰결과 {p.get('results', 0)}"
        if p.get("newcar"):
            base += f" · 출시가 {p['newcar'][0]}"
        elif p.get("newcar_running"):
            base += " · 출시가 수집 중" if run.get("status") == "running" else " · 출시가 수집 중 끊김"
        return base
    at = progress_step(msg)
    return f"{_STEP_LABEL[at]} 단계에서 멈춤" if at else "건수 기록 없음"


_KINDS = [
    (re.compile(r"^입찰예정 \d+ · 분석"), "매일 갱신(수동)"),
    (re.compile(r"^일일 갱신 오류"), "매일 갱신(수동)"),
    (re.compile(r"^입찰예정 \d+건 갱신|^목록 \d+페이지"), "입찰예정 목록 갱신"),
    (re.compile(r"^재분석"), "시세 재분석"),
    (re.compile(r"낙찰결과"), "낙찰결과 반영"),
    (re.compile(r"^시세 재교정|^시세 0표본"), "시세 재교정"),
    (re.compile(r"^완료 \d+건 / 스캔|^수집 오류"), "물건 수집"),
]


def run_kind(msg: Optional[str]) -> str:
    for rx, name in _KINDS:
        if rx.search(msg or ""):
            return name
    return "기타 작업"


def split_runs(runs: list[dict], until: datetime, daily_time: str = "06:30") -> tuple[datetime, Optional[dict], list[dict]]:
    """(정기 예정 시각, 정기 실행 1건 또는 None, 나머지=수동 실행). 예정 시각부터 15분 안에 시작한 첫 실행이 정기 실행이다."""
    try:
        hh, mm = (int(x) for x in daily_time.split(":"))
    except ValueError:
        hh, mm = 6, 30
    due = datetime.combine(until.date(), dtime(hh, mm))
    sched, manual = None, []
    for r in runs:
        st = _dt(r.get("started_at"))
        if sched is None and st and due <= st < due + timedelta(minutes=15):
            sched = r
        else:
            manual.append(r)
    return due, sched, manual


# ── PC 로그 해석 ──────────────────────────────────────────────────
_UNC = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+UNCLASSIFIED=(\d+)")


def last_unclassified(raw: bytes) -> Optional[tuple[str, int]]:
    """사진 점검 로그의 마지막 미분류 건수. 로그는 UTF-8 뒤에 UTF-16이 덧붙은 **혼합 인코딩**이다
    (PowerShell 5.1 Tee-Object -Append) — 두 인코딩과 두 바이트 정렬을 모두 읽어 가장 늦은 기록을 쓴다."""
    found = []
    for data, enc in ((raw, "utf-8"), (raw, "utf-16-le"), (raw[1:], "utf-16-le")):
        text = data.decode(enc, errors="ignore")
        found += [(m.group(1), int(m.group(2))) for m in _UNC.finditer(text)]
    return max(found) if found else None


_TUN = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (.*)$")


def tunnel_events(text: str, since: datetime, until: datetime) -> dict:
    out = {"connecting": 0, "closed": 0, "service_start": 0, "last": None}
    for line in (text or "").splitlines():
        m = _TUN.match(line.strip())
        if not m:
            continue
        at = _dt(m.group(1))
        out["last"] = f"{m.group(1)} {m.group(2)}"
        if not at or not (since <= at < until):
            continue
        body = m.group(2)
        if body.startswith("tunnel connecting"):
            out["connecting"] += 1
        elif body.startswith("tunnel closed"):
            out["closed"] += 1
        elif body.startswith("service start"):
            out["service_start"] += 1
    return out


# ── 수집(외부 명령) ────────────────────────────────────────────────
_REMOTE = r'''
import json, os, sqlite3, subprocess
from src.paths import DATA_DIR
SINCE = __SINCE__
UNTIL = __UNTIL__
out = {}
con = sqlite3.connect(os.path.join(str(DATA_DIR), "auction.db"))
con.row_factory = sqlite3.Row
out["runs"] = [dict(r) for r in con.execute(
    "select id, started_at, finished_at, status, scanned, processed, target, message from runs "
    "where started_at >= ? and started_at < ? order by id", (SINCE, UNTIL))]
# 공급 감시용(web/ops_health.evaluate 가 먹는 스냅샷). 창(window) 밖까지 본다 —
# '분석 0건 2일 연속' 같은 판정은 하루치만 봐서는 절대 나오지 않는다.
fresh = con.execute("select max(collected_at) c, max(analyzed_at) a, "
                    "max(result_checked_at) r, max(kcar_checked_at) k from vehicles").fetchone()
out["supply"] = {
    "collected_at": fresh["c"], "analyzed_at": fresh["a"],
    "result_checked_at": fresh["r"], "kcar_checked_at": fresh["k"],
    "zero_sample": {"zero": con.execute(__ZERO_SQL__).fetchone()["n"],
                    "total": con.execute("select count(*) n from vehicles").fetchone()["n"]},
    "runs": [dict(r) for r in con.execute(
        "select started_at, status, message from runs where started_at >= ? order by started_at",
        (__RUNS_SINCE__,))],
}
keys = ("daily_time", "daily_enabled", "last_run_date", "encar_health_state", "encar_health_code",
        "encar_health_at", "encar_health_ok_at", "last_upcoming_count", "supply_zero_history",
        "kcar_health_state", "kcar_health_at", "kcar_health_msg")
out["settings"] = {r["key"]: r["value"] for r in con.execute(
    "select key, value from settings where key in (%s)" % ",".join("?" * len(keys)), keys)}
def sh(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return ""
log = sh(["journalctl", "--no-pager", "-u", "certbot.service", "--since", SINCE, "--until", UNTIL])
out["certbot"] = {"started": log.count("Starting certbot.service"),
                  "finished": log.count("Finished certbot.service"),
                  "failed": log.count("Failed with result")}
out["service"] = {"active": sh(["systemctl", "is-active", "naechaget"]).strip(),
                  "since": sh(["systemctl", "show", "naechaget", "-p", "ActiveEnterTimestamp", "--value"]).strip()}

# ⚠ 방문자·이탈률 집계를 **2026-09-22 제거했다**(오너 결정). 되살리지 말 것.
#   접속 로그를 IP 로 묶어 방문자를 세는 것은 Google Play 데이터 안전의 '앱 상호작용'
#   (= "the number of times they visit a page") 수집에 해당한다. 우리는 스토어에
#   '수집된 데이터 없음'으로 신고했고, 개인정보처리방침도 그 근거로 "분석·프로필 연결이
#   없다"고 적어 두었다 — 집계를 하는 순간 방침이 스스로 거짓이 된다.
#   접속 로그는 **인프라 진단에만** 쓴다(가동 상태·certbot·오류).
#   되돌리려면 신고 변경과 방침 수정이 함께 가야 한다. 코드만 되살리면 허위 신고가 된다.

print(json.dumps(out, ensure_ascii=True))
'''


def remote_script(since: datetime, until: datetime) -> str:
    """서버에서 실행할 읽기 전용 파이썬. 날짜는 JSON 문자열 리터럴로만 끼워 넣는다(주입·따옴표 사고 방지).

    0표본 문장은 `web/ops_health.ZERO_SAMPLE_SQL` 을 그대로 실어 보낸다 — 여기에 손으로
    베껴 쓰면 앱이 세는 0표본과 리포트가 세는 0표본이 조용히 갈라진다.
    """
    runs_since = (since - timedelta(days=SUPPLY_RUN_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    return (_REMOTE.replace("__SINCE__", json.dumps(since.strftime("%Y-%m-%d %H:%M:%S")))
                   .replace("__UNTIL__", json.dumps(until.strftime("%Y-%m-%d %H:%M:%S")))
                   .replace("__RUNS_SINCE__", json.dumps(runs_since))
                   .replace("__ZERO_SQL__", json.dumps(ops_health.ZERO_SAMPLE_SQL)))


def _scrub(text: str) -> str:
    """오류 문구에서 서버 주소·키 경로를 지운다 — 리포트는 저장소에 남는 문서다."""
    t = str(text)
    for secret in (SERVER, SERVER.split("@")[-1], str(KEY), KEY.name):
        t = t.replace(secret, "[서버]" if "@" in secret or secret[0].isdigit() else "[키]")
    return re.sub(r"\s+", " ", t).strip()[:200]


def collect_server(since: datetime, until: datetime) -> dict:
    ssh = shutil.which("ssh") or os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "ssh.exe")
    cmd = [ssh, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-o", "StrictHostKeyChecking=accept-new",
           "-i", str(KEY), SERVER, "cd ~/app && .venv/bin/python -"]
    p = subprocess.run(cmd, input=remote_script(since, until), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    lines = [ln for ln in (p.stdout or "").splitlines() if ln.startswith("{")]
    if p.returncode != 0 or not lines:
        raise RuntimeError(f"서버 조회 실패(코드 {p.returncode}): {(p.stderr or p.stdout or '').strip()[-160:]}")
    return json.loads(lines[-1])


_PS_TASKS = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$out = @{}
foreach ($n in @('__PHOTO__', '__TUNNEL__')) {
  try {
    $t = Get-ScheduledTask -TaskName $n -ErrorAction Stop
    $i = $t | Get-ScheduledTaskInfo
    $last = ''; if ($i.LastRunTime -and $i.LastRunTime.Year -gt 2000) { $last = $i.LastRunTime.ToString('yyyy-MM-dd HH:mm:ss') }
    $next = ''; if ($i.NextRunTime) { $next = $i.NextRunTime.ToString('yyyy-MM-dd HH:mm:ss') }
    $out[$n] = @{ state = "$($t.State)"; last = $last; next = $next; result = [int64]$i.LastTaskResult }
  } catch { $out[$n] = @{ error = $_.Exception.Message } }
}
$out | ConvertTo-Json -Compress
"""


def collect_tasks() -> dict:
    ps = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    script = _PS_TASKS.replace("__PHOTO__", PHOTO_TASK).replace("__TUNNEL__", TUNNEL_TASK)
    p = subprocess.run([ps, "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=90)
    lines = [ln for ln in (p.stdout or "").splitlines() if ln.strip().startswith("{")]
    if not lines:
        raise RuntimeError(f"작업 스케줄러 조회 실패: {(p.stderr or '').strip()[-160:]}")
    return json.loads(lines[-1])


def collect_panel_commits(since: datetime, until: datetime) -> dict:
    git = shutil.which("git")
    if not git:
        raise RuntimeError("git 을 찾지 못함")
    subprocess.run([git, "-C", str(ROOT), "fetch", "--quiet", "origin", "main"], capture_output=True, timeout=120, check=True)
    p = subprocess.run(
        [git, "-C", str(ROOT), "-c", "i18n.logOutputEncoding=UTF-8", "log", "origin/main",
         f"--since={since:%Y-%m-%d %H:%M:%S}", f"--until={until:%Y-%m-%d %H:%M:%S}",
         "--date=format:%Y-%m-%d %H:%M", "--pretty=%h|%ad|%s", "--", "docs/reviews/"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=True)
    commits = []
    for line in (p.stdout or "").splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({"hash": parts[0], "at": parts[1], "subject": parts[2]})
    return {"commits": commits}


def read_photo_log() -> dict:
    if not PHOTO_LOG.exists():
        return {"error": "사진 점검 로그 없음"}
    got = last_unclassified(PHOTO_LOG.read_bytes())
    return {"at": got[0], "count": got[1]} if got else {}


def read_tunnel_log(since: datetime, until: datetime) -> dict:
    if not TUNNEL_LOG.exists():
        return {"error": "터널 로그 없음"}
    return tunnel_events(TUNNEL_LOG.read_text(encoding="utf-8", errors="replace"), since, until)


def collect(day: date, now: Optional[datetime] = None) -> dict:
    since, until = report_window(day)
    data: dict = {"since": since, "until": until, "generated": now or datetime.now()}
    for key, fn in (("server", lambda: collect_server(since, until)), ("tasks", collect_tasks),
                    ("panel", lambda: collect_panel_commits(since, until))):
        try:
            data[key] = fn()
        except Exception as e:  # noqa: BLE001 — 한 곳이 실패해도 나머지로 리포트를 쓴다
            data[key] = {"error": _scrub(e)}
    data["photo_log"] = read_photo_log()
    data["tunnel_log"] = read_tunnel_log(since, until)
    # 공급 판정은 여기서 한 번만 한다(리포트와 사내 대시보드가 같은 결론을 쓰도록).
    data["supply"] = supply_verdict(data, data["generated"])
    return data


# ── 리포트 작성 ────────────────────────────────────────────────────
def _cell(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def _hm(s: Optional[str]) -> str:
    d = _dt(s)
    return d.strftime("%H:%M") if d else "?"


_SUPPLY_MARK = {"ok": "✅ 정상", "warn": "⚠️ 이상", "down": "🛑 멈춤", "unknown": "❔ 확인 불가"}


def _zero_history(raw) -> list:
    try:
        rows = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        return []
    return [r for r in rows if isinstance(r, dict) and r.get("date")]


def supply_verdict(data: dict, now: Optional[datetime] = None) -> Optional[dict]:
    """운영 서버 스냅샷 → 공급 판정. 읽지 못했으면 **None** 이다(모르는 것을 정상으로 적지 않는다).

    ⚠ 판정은 **지금** 값이다. 지난 날짜 리포트(--date)에 지금 값을 쓰면 그날을 오판한다 —
      터널 행이 9/15 드라이런에서 실제로 그렇게 틀렸다. 호출자가 기간을 보고 거른다.
    """
    server = data.get("server") or {}
    supply = server.get("supply")
    if server.get("error") or not supply:
        return None
    s = server.get("settings") or {}
    snap = dict(supply)
    snap.update({"encar_state": s.get("encar_health_state"),
                 "encar_code": s.get("encar_health_code"),
                 "encar_ok_at": s.get("encar_health_ok_at"),
                 "kcar_state": s.get("kcar_health_state"),
                 "kcar_state_at": s.get("kcar_health_at"),
                 "kcar_msg": s.get("kcar_health_msg"),
                 "daily_enabled": s.get("daily_enabled"),
                 "zero_history": _zero_history(s.get("supply_zero_history")),
                 "source": "운영 서버"})
    return ops_health.evaluate(snap, ops_health.load_thresholds(),
                               now=now or data.get("generated"))


def supply_block(verdict: Optional[dict], live: bool) -> list:
    """리포트 **맨 위**에 들어가는 공급 상태 블록.

    왜 맨 위인가 — 2026-09-19~21 의 기록은 이 리포트 안에 **이미 있었다**(분석 0건이 표에 찍혔다).
    그런데 아무도 몰랐다. 묻혀 있는 기록과 먼저 보이는 판정은 다르다.
    """
    if not live:
        return ["## 공급 상태", "",
                "> ❔ **지난 기간** — 공급 판정은 지금 값이라 지난 날짜 리포트에는 적지 않는다.", ""]
    if not verdict:
        return ["## 공급 상태", "",
                "> ❔ **확인 불가** — 운영 서버 스냅샷을 읽지 못했다. 정상이라는 뜻이 아니다.", ""]
    mark = _SUPPLY_MARK.get(verdict["state"], verdict["state"])
    head = (f"> {mark} — {_cell(verdict['headline'])}"
            f" · 기준 {verdict.get('source') or '운영 서버'} {verdict['checked_at'][:16]}")
    L = ["## 공급 상태", "", head, ""]
    if verdict["alerts"]:
        L += ["**먼저 볼 것**", ""]
        L += [f"- {_SUPPLY_MARK.get(a['state'], a['state'])} **{_cell(a['label'])}** "
              f"{_cell(a['head'])} — {_cell(a['detail'])}" for a in verdict["alerts"]]
        L += [""]
    L += ["| 신호 | 상태 | 값 | 근거 |", "|---|---|---|---|"]
    L += [f"| {_cell(s['label'])} | {_SUPPLY_MARK.get(s['state'], s['state'])} | "
          f"{_cell(s['head'])} | {_cell(s['detail'])} |" for s in verdict["signals"]]
    L += ["", "> 임계는 `config.yaml: ops_alert`, 판정은 `web/ops_health.py` 한 곳에 있습니다.", ""]
    return L


def build_markdown(data: dict) -> str:
    since, until, now = data["since"], data["until"], data["generated"]
    server = data.get("server") or {}
    tasks = data.get("tasks") or {}
    panel = data.get("panel") or {}
    photo_log = data.get("photo_log") or {}
    tunnel_log = data.get("tunnel_log") or {}
    unknown_notes = []
    for name, src in (("운영 서버", server), ("PC 작업 스케줄러", tasks), ("GitHub", panel),
                      ("사진 점검 로그", photo_log), ("터널 로그", tunnel_log)):
        if src.get("error"):
            unknown_notes.append(f"{name}: {src['error']}")

    rows: list[dict] = []
    step_rows: list[dict] = []
    manual_rows: list[dict] = []
    raw_daily = None

    # ① 매일 시세·낙찰 갱신
    settings = server.get("settings") or {}
    row = {"job": "매일 시세·낙찰 갱신", "where": "운영 서버", "plan": f"매일 {settings.get('daily_time', '06:30')}"}
    if server.get("error"):
        row.update(actual="—", count="—", status=UNKNOWN)
    else:
        due, sched, manual = split_runs(server.get("runs") or [], until, settings.get("daily_time", "06:30"))
        for r in manual:
            manual_rows.append({"start": (r.get("started_at") or "")[5:16], "kind": run_kind(r.get("message")),
                                "count": (r.get("message") or "").strip()[:80] or f"처리 {r.get('processed')}",
                                "status": {"done": OK, "error": FAIL, "running": RUNNING}.get(r.get("status"), UNKNOWN)})
        if sched is None:
            if now < due:
                row.update(actual="예정 시각 전", count="—", status=NA)
            elif settings.get("daily_enabled") != "1":
                row.update(actual="자동 갱신이 꺼져 있음", count="—", status=WARN)
            else:
                row.update(actual="실행 기록 없음", count="—", status=FAIL)
        else:
            step_rows = daily_steps(sched)
            raw_daily = sched.get("message")
            fin = sched.get("finished_at")
            actual = f"{_hm(sched.get('started_at'))}~{_hm(fin)}" if fin else f"{_hm(sched.get('started_at'))} 시작"
            st = sched.get("status")
            if st == "running":
                status = RUNNING
            elif st == "error" and is_daily_summary(sched.get("message")):
                # 앞 단계를 끝내고 요약까지 남긴 뒤 맨 끝 출시가 수집에서 끊겼다 — 갱신 전체를 실패로 적지 않는다
                status = WARN
            elif st == "error":
                status = FAIL
            elif any(s["status"] in (FAIL, WARN) for s in step_rows):
                status = WARN
            else:
                status = OK
            row.update(actual=actual, count=daily_counts(sched), status=status)
    rows.append(row)

    # ② SSL 인증서 갱신 확인
    row = {"job": "SSL 인증서 갱신 확인", "where": "운영 서버", "plan": "하루 2회"}
    if server.get("error"):
        row.update(actual="—", count="—", status=UNKNOWN)
    else:
        cb = server.get("certbot") or {}
        started, failed = int(cb.get("started", 0)), int(cb.get("failed", 0))
        row.update(actual=f"{started}회 실행", count=f"실패 {failed}회",
                   status=FAIL if failed else (WARN if started == 0 else OK))
    rows.append(row)

    # ③ 주간 전문가 패널
    row = {"job": "주간 전문가 패널", "where": "클라우드 루틴", "plan": "매주 토 09:20"}
    due = weekly_due(since, until, PANEL_WEEKDAY, *PANEL_AT)
    if not due:
        row.update(actual="이번 기간 예정 없음", count="—", status=NA)
    elif now < due:
        row.update(actual="예정 시각 전", count="—", status=NA)
    elif panel.get("error"):
        row.update(actual="—", count="—", status=UNKNOWN)
    else:
        hits = [c for c in panel.get("commits") or [] if "주간평가" in c.get("subject", "")]
        if hits:
            row.update(actual=f"리포트 커밋 {hits[-1]['at'][11:]}", count=hits[-1]["subject"][:60], status=OK)
        else:
            row.update(actual="리포트 커밋 없음", count="—", status=FAIL)
    rows.append(row)

    # ④ 사진 미분류 점검
    row = {"job": "사진 미분류 점검", "where": "이 PC", "plan": "매주 일 08:17"}
    due = weekly_due(since, until, PHOTO_WEEKDAY, *PHOTO_AT)
    task = tasks.get(PHOTO_TASK) or {}
    if not due:
        row.update(actual="이번 기간 예정 없음", count="—", status=NA)
    elif now < due:
        row.update(actual="예정 시각 전", count="—", status=NA)
    elif tasks.get("error") or task.get("error"):
        row.update(actual="—", count="—", status=UNKNOWN)
    else:
        last = _dt(task.get("last"))
        if last and since <= last < until:
            at = _dt(photo_log.get("at"))
            count = (f"미분류 {photo_log['count']}건" if at and since <= at < until else "건수 기록 없음")
            code = int(task.get("result", -1))
            row.update(actual=f"{last:%m-%d %H:%M}", count=count, status=OK if code == 0 else FAIL)
            if code != 0:
                row["count"] += f" · 종료 코드 {code}"
        else:
            row.update(actual="실행 기록 없음", count="—", status=FAIL)
    rows.append(row)

    # ⑤ 집 회선 터널(상시)
    row = {"job": "집 회선 터널", "where": "이 PC", "plan": "상시(시스템 시작)"}
    ttask = tasks.get(TUNNEL_TASK) or {}
    enc = None if server.get("error") else settings.get("encar_health_state")
    # ⚠ 작업 상태·엔카 상태·터널 로그는 **지금** 값이다. 지난 날짜 리포트(--date)에 지금 값을 쓰면 터널이 꺼져 있던
    #   날을 '정상'으로 적는다 — 9/15 드라이런이 실제로 그렇게 나왔다. 과거 기간은 그날 정기 실행 기록의 엔카 결과로 판정한다.
    live = since <= now <= until + timedelta(hours=2)
    if not live:
        _dtime = settings.get("daily_time", "06:30")
        day_run = None if server.get("error") else split_runs(server.get("runs") or [], until, _dtime)[1]
        if day_run and day_run.get("status") == "done" and is_daily_summary(day_run.get("message")):
            enc_day = parse_daily_message(day_run["message"]).get("encar")
            row.update(actual=(f"그날 {_dtime} 엔카 {enc_day[0]} (HTTP {enc_day[1]})" if enc_day
                               else f"그날 {_dtime} 엔카 정상"),
                       count="— (지난 기간)", status=FAIL if enc_day else OK)
        else:
            row.update(actual="그날 기록으로 판정할 수 없음", count="— (지난 기간)", status=UNKNOWN)
    elif (tasks.get("error") or ttask.get("error")) and enc is None:
        row.update(actual="—", count="—", status=UNKNOWN)
    else:
        parts = []
        if not (tasks.get("error") or ttask.get("error")):
            parts.append(f"작업 {ttask.get('state')}")
        if enc is not None:
            parts.append(f"엔카 {enc} (최종 정상 {(settings.get('encar_health_ok_at') or '?')[:16]})")
        closed = int(tunnel_log.get("closed", 0)) if not tunnel_log.get("error") else None
        bad = (ttask.get("state") not in (None, "Running") and not ttask.get("error")) or (enc is not None and enc != "ok")
        status = FAIL if bad else (WARN if closed is not None and closed >= 3 else OK)
        row.update(actual=" · ".join(parts), count=f"재접속 {closed}회" if closed is not None else "로그 없음",
                   status=status)
    rows.append(row)

    counted = [r["status"] for r in rows if r["status"] != NA]
    summary = (f"성공 {counted.count(OK)} · 경고 {counted.count(WARN)} · 실패 {counted.count(FAIL)}"
               f" · 진행 중 {counted.count(RUNNING)} · 확인 불가 {counted.count(UNKNOWN)}")

    # 공급 상태 — 표보다 **먼저** 읽히는 자리에 둔다. '지금' 판정이므로 지난 기간 리포트에는 적지 않는다.
    supply_live = since <= now <= until + timedelta(hours=2)
    verdict = data.get("supply") if "supply" in data else supply_verdict(data, now)
    if supply_live and verdict:
        summary += f" · 공급 {_SUPPLY_MARK.get(verdict['state'], verdict['state'])}"
        if verdict["state"] != "ok":
            # 요약 줄에서는 **가장 나쁜 1건 + 외 N건**만 부른다 — 세 건을 다 적으면 줄이 넘쳐
            # 정작 '공급 멈춤'이라는 낱말이 뒤로 밀린다.
            summary += f"({ops_health.headline(verdict['state'], verdict['alerts'], limit=1)})"

    L = [
        f"# 작업 결과 리포트 · {until:%Y-%m-%d}",
        "",
        f"- **기간** {since:%Y-%m-%d %H:%M} ~ {until:%Y-%m-%d %H:%M} (한국 시간)",
        f"- **생성** {now:%Y-%m-%d %H:%M} · 이 PC 작업 스케줄러",
        f"- **요약** {summary}",
        "",
    ] + supply_block(verdict, supply_live) + [
        "## 정기 작업",
        "",
        "| 작업 | 실행 위치 | 예정 | 실제 실행 | 건수 | 결과 |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        L.append(f"| {_cell(r['job'])} | {_cell(r['where'])} | {_cell(r['plan'])} | {_cell(r['actual'])} | "
                 f"{_cell(r['count'])} | {r['status']} |")
    L += ["", "## 매일 시세·낙찰 갱신 · 단계별", ""]
    if step_rows:
        L += ["| 단계 | 건수 | 결과 |", "|---|---|---|"]
        L += [f"| {_cell(s['step'])} | {_cell(s['count'])} | {s['status']} |" for s in step_rows]
        L += ["", f"> 서버 기록 원문: `{_cell(raw_daily or '')}`",
              "> 0건인 단계는 서버 기록에서 빠지므로 '0건 · 없음'으로 적습니다."]
    else:
        L.append("이번 기간에 정기 실행 기록이 없습니다." if not server.get("error") else "서버를 읽지 못해 확인할 수 없습니다.")
    L += ["", "## 수동 실행 (정기 작업 외)", ""]
    if manual_rows:
        L += ["| 시작 | 종류 | 건수 | 결과 |", "|---|---|---|---|"]
        L += [f"| {_cell(m['start'])} | {_cell(m['kind'])} | {_cell(m['count'])} | {m['status']} |" for m in manual_rows]
    else:
        L.append("없음" if not server.get("error") else "서버를 읽지 못해 확인할 수 없습니다.")
    if unknown_notes:
        L += ["", "## 확인 불가", ""] + [f"- {_cell(n)}" for n in unknown_notes]
    L += ["", "---", "",
          "`tools/daily_ops_report.py` 가 만듭니다. 운영 서버·이 PC·GitHub를 읽기만 하며 "
          "법원·엔카 같은 외부 사이트에는 요청하지 않습니다.", ""]
    return "\n".join(L)


def write_supply_sidecar(data: dict) -> Optional[Path]:
    """공급 판정을 기계가 읽을 수 있게 한 줄 남긴다 — 사내 대시보드가 이 파일을 읽는다.

    대시보드는 같은 PC 에 있지만 **운영 DB 를 못 본다**. 로컬 `auction.db` 로 판정하면
    개발 사본의 낡은 시각 때문에 매일 거짓 '수집 멈춤'이 뜬다 — 그래서 서버를 읽은
    이 도구가 결론을 남기고, 대시보드는 그 결론과 **언제 잰 것인지**를 함께 보여준다.
    """
    verdict = data.get("supply")
    if not verdict:
        return None
    try:
        SUPPLY_OUT.parent.mkdir(parents=True, exist_ok=True)
        SUPPLY_OUT.write_text(json.dumps(verdict, ensure_ascii=False, indent=1), encoding="utf-8")
        return SUPPLY_OUT
    except OSError:
        return None


def _log_local(line: str) -> None:
    try:
        LOCAL_STATE.mkdir(parents=True, exist_ok=True)
        with open(LOCAL_STATE / "daily_report.log", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {line}\n")
    except OSError:
        pass


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="매일 12시 작업 결과 리포트")
    ap.add_argument("--date", help="리포트 날짜 YYYY-MM-DD (기본: 오늘)")
    ap.add_argument("--stdout", action="store_true", help="파일 대신 화면에 출력")
    a = ap.parse_args(argv)
    day = date.fromisoformat(a.date) if a.date else date.today()
    try:
        data = collect(day)
        md = build_markdown(data)
        write_supply_sidecar(data)      # 사내 대시보드가 읽는 자리(data/ops_supply.json)
    except Exception as e:  # noqa: BLE001
        _log_local(f"FAIL {day} {_scrub(e)}")
        raise
    if a.stdout:
        print(md)
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{day:%Y-%m-%d}.md"
    path.write_text(md, encoding="utf-8")
    _log_local(f"OK {path.name}")
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
