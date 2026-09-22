# -*- coding: utf-8 -*-
"""주간 보고서 → docs/weekly-reports/YYYY-Www.md

일일 리포트가 "어제 작업이 제대로 돌았는가"를 본다면, 주간은 **"제품이 나아지고 있는가"**를 본다.
하루 단위로는 숫자가 오르내려 추세가 안 보이고, 화면을 고친 효과도 하루로는 못 잰다.

담는 것: 제품(운영 DB) · 품질(전문가 패널) · 배포(git) · 성장·고객의 소리(오너 입력)

⚠ 접속 로그 기반 성장 지표(방문자·이탈률·유입 출처)는 **2026-09-22 제거했다**(오너 결정).
  IP 로 묶어 방문자를 세는 것은 Play '앱 상호작용' 수집이고, 이 앱은 '수집된 데이터 없음'으로
  신고돼 있다. 출시 후에는 Play Console·Search Console 이 우리 서버에서 아무것도 모으지 않고
  같은 질문에 답한다 — 그 값은 오너가 기입한다.

정직 규칙(docs/ORG.md §4):
  - 0건을 성공으로 부풀리지 않는다. 읽지 못한 곳은 '확인 불가'로 적는다.
  - 표본이 없으면 그 줄을 통째로 숨긴다 — 빈칸을 추정치로 채우지 않는다.
  - 서버 주소·키 경로는 리포트에 남기지 않는다(저장소에 커밋되는 문서다).

    python tools/weekly_report.py             # 이번 주(월~일)
    python tools/weekly_report.py 2026-09-22  # 그 날짜가 속한 주
"""
from __future__ import annotations

import argparse
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
OUT_DIR = ROOT / "docs" / "weekly-reports"
REVIEW_DIR = ROOT / "docs" / "reviews"
SERVER = "ubuntu@43.202.126.180"
KEY = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Downloads" / "naechaget.pem"

OK, FAIL, UNKNOWN = "✅", "❌", "❔"


def _scrub(text) -> str:
    """오류 문구에서 서버 주소·키 경로를 지운다 — 리포트는 저장소에 남는 문서다."""
    t = str(text)
    for secret in (SERVER, SERVER.split("@")[-1], str(KEY), KEY.name):
        t = t.replace(secret, "[서버]" if "@" in secret or secret[0].isdigit() else "[키]")
    return re.sub(r"\s+", " ", t).strip()[:200]


def week_range(anchor: date) -> tuple[date, date]:
    """anchor 가 속한 주(월~일)."""
    mon = anchor - timedelta(days=anchor.weekday())
    return mon, mon + timedelta(days=6)


# ── 운영 서버에서 읽기 전용으로 긁어올 스크립트 ────────────────────────────
# 날짜는 JSON 문자열 리터럴로만 끼워 넣는다(주입·따옴표 사고 방지).
_REMOTE = r'''
import json, sys, datetime
sys.path.insert(0, ".")
out = {}

# ⚠ 접속 로그 집계(방문자·이탈률·유입 출처)를 2026-09-22 제거했다 — 오너 결정. 되살리지 말 것.
#   IP 로 묶어 방문자를 세는 것은 Play '앱 상호작용' 수집이고, 이 앱은 '수집된 데이터 없음'
#   으로 신고했다. 되돌리려면 신고 변경과 개인정보처리방침 수정이 함께 가야 한다.

# ── 제품: 운영 DB(읽기 전용) ──────────────────────────────────────────────
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
        "wait": lc["wait"], "lowconf": lc["lowconf"], "won": lc["won"],
        "upcoming": len(fut),
        "with_price": sum(1 for v in fut if v.get("median_price")),
        "mae_pct": bt.get("mae_pct"), "within10": bt.get("within10_pct"),
        "within20": bt.get("within20_pct"), "pred_n": bt.get("pred_n"),
        "history_n": bt.get("history_n"),
    }
except Exception as e:
    out["product"] = {"error": type(e).__name__}

print(json.dumps(out, ensure_ascii=True))
'''


def collect_server() -> dict:
    """제품 지표는 '지금' 값이라 기간이 필요 없다 — 접속 로그를 읽지 않게 되면서 기간 인자가 사라졌다."""
    ssh = shutil.which("ssh") or os.path.join(
        os.environ.get("WINDIR", r"C:\Windows"), "System32", "OpenSSH", "ssh.exe")
    cmd = [ssh, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20",
           "-o", "StrictHostKeyChecking=accept-new", "-i", str(KEY), SERVER,
           "cd ~/app && .venv/bin/python -"]
    try:
        p = subprocess.run(cmd, input=_REMOTE, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=240)
    except Exception as e:                                   # noqa: BLE001
        return {"error": _scrub(e)}
    if p.returncode != 0:
        return {"error": _scrub(p.stderr or f"exit {p.returncode}")}
    try:
        return json.loads((p.stdout or "").strip().splitlines()[-1])
    except Exception as e:                                   # noqa: BLE001
        return {"error": _scrub(f"응답 해석 실패: {e}")}


def collect_git(since: date, until: date) -> dict:
    """이번 주 배포 내역. 저장소는 이 PC에 있으므로 로컬에서 읽는다."""
    try:
        args = ["git", "log", f"--since={since.isoformat()}", f"--until={(until + timedelta(days=1)).isoformat()}",
                "--pretty=format:%h\t%ad\t%s", "--date=short"]
        p = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        if p.returncode != 0:
            return {"error": _scrub(p.stderr)}
        rows = [l.split("\t", 2) for l in (p.stdout or "").splitlines() if l.strip()]
        return {"commits": [{"sha": r[0], "date": r[1], "subject": r[2]} for r in rows if len(r) == 3]}
    except Exception as e:                                   # noqa: BLE001
        return {"error": _scrub(e)}


def collect_panel(since: date, until: date) -> dict:
    """전문가 패널 리포트(주간 클라우드 루틴이 커밋한다)."""
    if not REVIEW_DIR.exists():
        return {"files": []}
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
    return {"files": got}


def build_markdown(since: date, until: date, server: dict, git: dict, panel: dict) -> str:
    product = server.get("product") or {}
    unknown: list[str] = []
    if server.get("error"):
        unknown.append(f"운영 서버: {_scrub(server['error'])}")
    if product.get("error"):
        unknown.append(f"제품 지표: {_scrub(product['error'])}")
    if git.get("error"):
        unknown.append(f"배포 내역: {_scrub(git['error'])}")

    y, w, _ = since.isocalendar()
    L = [f"# 주간 보고서 {y}-W{w:02d}", "",
         f"기간 **{since:%Y-%m-%d}(월) ~ {until:%Y-%m-%d}(일)** · 생성 {datetime.now():%Y-%m-%d %H:%M}", "",
         "> 일일 리포트가 '어제 작업이 돌았는가'라면, 이 보고서는 **'제품이 나아지고 있는가'**를 본다.", ""]

    # ── 성장 ───────────────────────────────────────────────
    L += ["## 성장", "",
          "**우리 서버에서는 측정하지 않는다.** 방문자·이탈률은 접속 로그를 IP 로 묶어야 나오는데,",
          "그것은 Play 데이터 안전의 '앱 상호작용' 수집에 해당한다. '수집된 데이터 없음' 신고와",
          "개인정보처리방침을 지키는 쪽을 택했다(2026-09-22 오너 결정).", "",
          "- **Play Console**(설치·순증·유지율)과 **Search Console**(검색 노출·클릭)은 우리 서버가",
          "  아무것도 모으지 않고도 같은 질문에 답한다 — 오너가 확인해 아래에 적는다.",
          "- 이번 주 설치·노출: _(오너 기입 — 없으면 '없음')_", ""]

    # ── 제품 ───────────────────────────────────────────────
    L += ["## 제품", ""]
    if product and not product.get("error"):
        L += ["| 지표 | 값 | 뜻 |", "|---|---:|---|",
              f"| 모니터링 물건 | {product.get('total'):,}대 | 목록에 보이는 전체 |",
              f"| 지금 입찰 가능 | {product.get('upcoming'):,}대 | 기일이 남고 안 끝난 물건 |",
              f"| 그중 시세 있음 | {product.get('with_price'):,}대 | 시세를 못 구하면 판정 자체를 못 한다 |",
              f"| 지금 입찰 추천 | {product.get('review')}대 | 되팔아도 남는 물건 |",
              f"| 실사용 추천 | {product.get('usepick')}대 | 내가 타면 싼 물건 |",
              f"| 예측 오차 | ±{product.get('mae_pct')}% | 검증 표본 {product.get('pred_n')}건 |",
              f"| ±10% 적중 | {product.get('within10')}% | ±20% 적중 {product.get('within20')}% |", ""]
    else:
        L += ["확인 불가 — 운영 DB를 읽지 못했다.", ""]

    # ── 품질 ───────────────────────────────────────────────
    L += ["## 품질 — 전문가 패널", ""]
    files = (panel or {}).get("files") or []
    if files:
        L += [f"이번 주 패널 리포트 {len(files)}건: " + ", ".join(f"`{f}`" for f in files),
              "", "> 점수와 합의 지적은 [`docs/reviews/`](../reviews/)에서 본다.", ""]
    else:
        L += ["이번 주 패널 리포트 **없음**.", ""]

    # ── 배포 ───────────────────────────────────────────────
    L += ["## 배포", ""]
    commits = (git or {}).get("commits") or []
    if commits:
        L += [f"커밋 **{len(commits)}건**", "", "| 날짜 | 커밋 | 내용 |", "|---|---|---|"]
        for c in commits[:20]:
            L.append(f"| {c['date']} | `{c['sha']}` | {c['subject'][:80]} |")
        if len(commits) > 20:
            L.append(f"| … | | 외 {len(commits) - 20}건 |")
        L.append("")
    else:
        L += ["이번 주 커밋 없음.", ""]

    # ── 고객의 소리 ────────────────────────────────────────
    L += ["## 고객의 소리", "",
          "스토어 리뷰·이메일은 **오너만 볼 수 있다**(Play Console·메일함). 앱에 피드백 창구를",
          "두지 않기로 한 결정(2026-09-22)에 따른 것이며, Play '수집된 데이터 없음' 신고를 지키기 위함이다.", "",
          "- 이번 주 들어온 말: _(오너 기입 — 없으면 '없음')_",
          "- 갈래별 분류·우선순위: `voice` 에이전트에 붙여넣어 받는다.", "",
          "> 리뷰 0건이 문제 0건을 뜻하지 않는다. 우리는 행동 데이터를 모으지 않으므로, 말이 없으면",
          "> **정말로 모른다** — 그래서 위 성장 칸을 오너가 직접 채워야 한다.", ""]

    if unknown:
        L += ["## 확인 불가", ""] + [f"- {u}" for u in unknown] + [""]

    L += ["---", "",
          "`tools/weekly_report.py` 가 만듭니다. 운영 서버·이 PC를 **읽기만** 하며 "
          "법원·시세 같은 외부 사이트에는 요청하지 않습니다.", ""]
    return "\n".join(L)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="주간 보고서 생성")
    ap.add_argument("anchor", nargs="?", help="기준 날짜(YYYY-MM-DD). 생략하면 오늘이 속한 주")
    ap.add_argument("--dry-run", action="store_true", help="파일로 쓰지 않고 화면에만 출력")
    a = ap.parse_args(argv)

    anchor = date.fromisoformat(a.anchor) if a.anchor else date.today()
    since, until = week_range(anchor)
    print(f"[주간 보고서] {since} ~ {until} 수집 중…", file=sys.stderr)

    server = collect_server()
    git = collect_git(since, until)
    panel = collect_panel(since, until)
    md = build_markdown(since, until, server, git, panel)

    if a.dry_run:
        print(md)
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    y, w, _ = since.isocalendar()
    out = OUT_DIR / f"{y}-W{w:02d}.md"
    out.write_text(md, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
