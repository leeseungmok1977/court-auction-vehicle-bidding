# -*- coding: utf-8 -*-
"""월간 보고서 → docs/monthly-reports/YYYY-MM.md

오너가 **다음 달 우선순위를 정하는 데** 쓰는 문서다.

⚠ 이 도구는 접속 로그를 읽지 않는다. 방문자·이탈률 누적을 **2026-09-22 제거했다**(오너 결정) —
IP 로 묶어 방문자를 세는 것은 Play 데이터 안전의 '앱 상호작용' 수집이고, 이 앱은 '수집된
데이터 없음'으로 신고돼 있다. 출시 후 유입 수치는 Play Console·Search Console 에서
오너가 확인해 기입한다. 되살리려면 신고 변경과 개인정보처리방침 수정이 먼저다.

    python tools/monthly_report.py           # 지난달
    python tools/monthly_report.py 2026-09   # 특정 월
"""
from __future__ import annotations

import argparse
import calendar
import io
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# ⚠ Windows 콘솔 기본 인코딩은 cp949라 '—'·'⚠' 같은 글자에서 UnicodeEncodeError 로 죽는다.
#   파일 쓰기는 encoding="utf-8" 이라 안전하지만 --dry-run 의 print 가 터진다(2026-09-22 실측).
for _stream in ("stdout", "stderr"):
    try:
        setattr(sys, _stream, io.TextIOWrapper(
            getattr(sys, _stream).buffer, encoding="utf-8", errors="replace"))
    except Exception:                                        # noqa: BLE001  (리다이렉트된 경우 등)
        pass

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "monthly-reports"
WEEKLY_DIR = ROOT / "docs" / "weekly-reports"
REVIEW_DIR = ROOT / "docs" / "reviews"
SERVER = "ubuntu@43.202.126.180"
KEY = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Downloads" / "naechaget.pem"


def _scrub(text) -> str:
    t = str(text)
    for secret in (SERVER, SERVER.split("@")[-1], str(KEY), KEY.name):
        t = t.replace(secret, "[서버]" if "@" in secret or secret[0].isdigit() else "[키]")
    return re.sub(r"\s+", " ", t).strip()[:200]


def month_range(ym: str) -> tuple[date, date]:
    y, m = (int(x) for x in ym.split("-"))
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


# ── 제품·수익 현황은 '지금' 값이므로 운영에서 한 번 읽는다 ──────────────────
_REMOTE = r'''
import json, sys, datetime
sys.path.insert(0, ".")
out = {}
try:
    from web import db, service
    bt = service.backtest_stats()
    today = datetime.date.today().isoformat()
    rows = db.list_vehicles(hide_incomplete=True)
    lc = service.lifecycle_partition(rows=rows)
    fut = [v for v in rows if (v.get("sale_date") or "") >= today
           and (v.get("auction_result") or "") not in ("낙찰", "종결")]
    out["product"] = {
        "total": lc["total"], "review": lc["review"], "usepick": lc["usepick"],
        "won": lc["won"], "upcoming": len(fut),
        "with_price": sum(1 for v in fut if v.get("median_price")),
        "mae_pct": bt.get("mae_pct"), "within10": bt.get("within10_pct"),
        "pred_n": bt.get("pred_n"), "history_n": bt.get("history_n"),
    }
except Exception as e:
    out["product"] = {"error": type(e).__name__}
try:
    from web import db as _db
    out["billing"] = {"users": _db.connect().execute("select count(*) c from users").fetchone()["c"]}
except Exception as e:
    out["billing"] = {"error": type(e).__name__}
print(json.dumps(out, ensure_ascii=True))
'''


def collect_server() -> dict:
    ssh = shutil.which("ssh") or os.path.join(
        os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "ssh.exe")
    cmd = [ssh, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20",
           "-o", "StrictHostKeyChecking=accept-new", "-i", str(KEY), SERVER,
           "cd ~/app && .venv/bin/python -"]
    try:
        p = subprocess.run(cmd, input=_REMOTE, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180)
    except Exception as e:                                   # noqa: BLE001
        return {"error": _scrub(e)}
    if p.returncode != 0:
        return {"error": _scrub(p.stderr or f"exit {p.returncode}")}
    try:
        return json.loads((p.stdout or "").strip().splitlines()[-1])
    except Exception as e:                                   # noqa: BLE001
        return {"error": _scrub(f"응답 해석 실패: {e}")}


def collect_git(since: date, until: date) -> dict:
    try:
        p = subprocess.run(
            ["git", "log", f"--since={since.isoformat()}",
             f"--until={(until + timedelta(days=1)).isoformat()}",
             "--pretty=format:%h\t%ad\t%s", "--date=short"],
            cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60)
        if p.returncode != 0:
            return {"error": _scrub(p.stderr)}
        rows = [l.split("\t", 2) for l in (p.stdout or "").splitlines() if l.strip()]
        commits = [{"sha": r[0], "date": r[1], "subject": r[2]} for r in rows if len(r) == 3]
        kinds: dict[str, int] = {}
        for c in commits:
            k = (c["subject"].split("(")[0].split(":")[0] or "기타").strip()[:12]
            kinds[k] = kinds.get(k, 0) + 1
        return {"commits": commits, "kinds": kinds}
    except Exception as e:                                   # noqa: BLE001
        return {"error": _scrub(e)}


def collect_panel(since: date, until: date) -> list[str]:
    if not REVIEW_DIR.exists():
        return []
    got = []
    for f in sorted(REVIEW_DIR.glob("*.md")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", f.name)
        if not m:
            continue
        try:
            d = date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if since <= d <= until:
            got.append(f.name)
    return got


def build_markdown(ym: str, since: date, until: date,
                   server: dict, git: dict, panels: list[str]) -> str:
    product = (server or {}).get("product") or {}
    billing = (server or {}).get("billing") or {}
    unknown: list[str] = []
    if server.get("error"):
        unknown.append(f"운영 서버: {_scrub(server['error'])}")
    if product.get("error"):
        unknown.append(f"제품 지표: {_scrub(product['error'])}")
    if git.get("error"):
        unknown.append(f"배포 내역: {_scrub(git['error'])}")

    L = [f"# 월간 보고서 {ym}", "",
         f"기간 **{since} ~ {until}** · 생성 {datetime.now():%Y-%m-%d %H:%M}", "",
         "> 오너가 **다음 달 우선순위를 정하는 데** 쓰는 문서다. "
         "고객가치 지표가 먼저, 수익이 나중이다.", ""]

    # ── 고객 유입 ─────────────────────────────────────────
    L += ["## 고객 유입", "",
          "**우리 서버에서는 측정하지 않는다.** 방문자·이탈률은 접속 로그를 IP 로 묶어야 나오는데,",
          "그것은 Play 데이터 안전의 '앱 상호작용' 수집에 해당한다. '수집된 데이터 없음' 신고와",
          "개인정보처리방침을 지키는 쪽을 택했다(2026-09-22 오너 결정).", "",
          "- **Play Console**(설치·순증·유지율)과 **Search Console**(검색 노출·클릭)은 우리 서버가",
          "  아무것도 모으지 않고도 같은 질문에 답한다.",
          "- 이 달 설치·순증·유지율: _(오너 기입 — 없으면 '없음')_", ""]

    # ── 고객가치 ─────────────────────────────────────────
    L += ["## 고객가치", ""]
    if product and not product.get("error"):
        L += ["| 지표 | 값 | 뜻 |", "|---|---:|---|",
              f"| 모니터링 물건 | {product.get('total'):,}대 | |",
              f"| 지금 입찰 가능 | {product.get('upcoming'):,}대 | 기일이 남고 안 끝난 물건 |",
              f"| 그중 시세 있음 | {product.get('with_price'):,}대 | 시세가 없으면 판정을 못 한다 |",
              f"| 추천 물건 | 재판매 {product.get('review')}대 · 실사용 {product.get('usepick')}대 | |",
              f"| 예측 오차 | ±{product.get('mae_pct')}% | ±10% 적중 {product.get('within10')}% |",
              f"| 검증 표본 | {product.get('pred_n')}건 | 누적 낙찰 이력 {product.get('history_n')}건 |", "",
              "> 검증 표본이 늘수록 예측이 정교해진다. **이 숫자가 이 제품의 해자다.**", ""]
    else:
        L += ["확인 불가 — 운영 DB를 읽지 못했다.", ""]

    # ── 품질 ─────────────────────────────────────────────
    L += ["## 품질", ""]
    L += [f"전문가 패널 리포트 **{len(panels)}건**" + (": " + ", ".join(f"`{p}`" for p in panels) if panels else " (없음)"),
          "", "> 점수 자체보다 **합의 지적**(둘 이상이 같은 문제를 짚은 것)과 회차 간 증감을 본다.", ""]

    # ── 개발 ─────────────────────────────────────────────
    L += ["## 개발", ""]
    commits = (git or {}).get("commits") or []
    if commits:
        kinds = git.get("kinds") or {}
        L += [f"커밋 **{len(commits)}건** · " +
              " · ".join(f"{k} {v}" for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])[:6]), ""]
        L += ["<details><summary>주요 변경</summary>", "", "| 날짜 | 커밋 | 내용 |", "|---|---|---|"]
        for c in commits[:30]:
            L.append(f"| {c['date']} | `{c['sha']}` | {c['subject'][:80]} |")
        if len(commits) > 30:
            L.append(f"| … | | 외 {len(commits) - 30}건 |")
        L += ["", "</details>", ""]
    else:
        L += ["이 달 커밋 없음.", ""]

    # ── 수익 ─────────────────────────────────────────────
    L += ["## 수익", ""]
    if billing.get("error"):
        L += ["확인 불가 — 사용자 테이블을 읽지 못했다.", ""]
    else:
        L += [f"- 가입 사용자 **{billing.get('users', 0)}명**",
              "- 결제 **비활성**(`billing_enabled=false`). 활성화는 **오너 승인 사항**이며 "
              "준법 검토 통과가 선행 조건이다(`docs/MONETIZATION_SPEC.md`).",
              "- 광고 **비활성**(`adsense_client` 미설정). 켜는 순간 Play '광고 없음' 신고를 갱신해야 한다.", ""]

    # ── 다음 달 ──────────────────────────────────────────
    L += ["## 다음 달 우선순위", "",
          "_(제품기획이 위 지표에서 도출해 3~5건으로 적는다. 오너가 확정한다.)_", "",
          "1. ", "2. ", "3. ", ""]

    if unknown:
        L += ["## 확인 불가", ""] + [f"- {u}" for u in unknown] + [""]

    L += ["---", "",
          "`tools/monthly_report.py` 가 만듭니다. **접속 로그는 읽지 않습니다** — 유입 수치는 "
          "Play Console·Search Console 에서 오너가 확인해 채웁니다.", ""]
    return "\n".join(L)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="월간 보고서 생성")
    ap.add_argument("ym", nargs="?", help="대상 월(YYYY-MM). 생략하면 지난달")
    ap.add_argument("--dry-run", action="store_true", help="파일로 쓰지 않고 화면에만 출력")
    a = ap.parse_args(argv)

    if a.ym:
        ym = a.ym
    else:
        t = date.today().replace(day=1) - timedelta(days=1)
        ym = f"{t.year:04d}-{t.month:02d}"
    since, until = month_range(ym)
    print(f"[월간 보고서] {ym} 수집 중…", file=sys.stderr)

    server = collect_server()
    git = collect_git(since, until)
    panels = collect_panel(since, until)
    md = build_markdown(ym, since, until, server, git, panels)

    if a.dry_run:
        print(md)
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{ym}.md"
    out.write_text(md, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
