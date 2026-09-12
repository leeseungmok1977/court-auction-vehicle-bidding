"""주간 전문가 패널용 화면 캡처 — 라이브 사이트를 모바일/데스크톱으로 찍는다.

전문가 에이전트(특히 앱 디자인)는 스크린샷을 눈으로 보고 채점하므로, 매주 같은 화면을
같은 폭으로 찍어 회차 간 비교가 가능하게 한다.

사용: python scripts/capture_weekly_screens.py [--date 2026-09-12] [--base https://naechaget.co.kr]
"""
from __future__ import annotations

import argparse
import datetime
import pathlib
import re
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
UA = "Mozilla/5.0 (Linux; Android 14; SM-A536N) AppleWebKit/537.36 Chrome/140.0 Mobile Safari/537.36"


def first_vehicle(base: str) -> str | None:
    req = urllib.request.Request(base + "/vehicles", headers={"User-Agent": UA})
    html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
    hits = [h for h in re.findall(r'href="(/vehicle/[^"]+?)"', html) if not h.endswith("/report")]
    return urllib.parse.quote(hits[0], safe="/") if hits else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--base", default="https://naechaget.co.kr")
    a = ap.parse_args()

    out = ROOT / "screenshots" / "weekly" / a.date
    out.mkdir(parents=True, exist_ok=True)

    vid = first_vehicle(a.base)
    screens = [("01-home", "/"), ("02-list", "/vehicles"), ("03-calendar", "/calendar"),
               ("04-courts", "/courts"), ("05-accuracy", "/accuracy"), ("06-watchlist", "/watchlist")]
    if vid:
        screens += [("07-detail", vid), ("08-report", vid + "/report")]

    made = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for label, w, h in (("mobile", 390, 844), ("desktop", 1440, 1000)):
            pg = b.new_page(viewport={"width": w, "height": h},
                            user_agent=UA if label == "mobile" else None)
            for name, path in screens:
                try:
                    pg.goto(a.base + path, wait_until="networkidle", timeout=90000)
                    pg.wait_for_timeout(700)          # 폰트·이미지 안정화
                    f = out / f"{name}-{label}.png"
                    pg.screenshot(path=str(f), full_page=(label == "desktop"))
                    made.append(f.name)
                except Exception as e:
                    print(f"  실패 {name}-{label}: {type(e).__name__}")
            pg.close()
        b.close()

    print(f"{out} 에 {len(made)}장 저장")
    for f in made:
        print("  -", f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
