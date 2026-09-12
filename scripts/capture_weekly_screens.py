"""주간 전문가 패널용 화면 캡처 — 라이브 사이트를 모바일/데스크톱으로 찍는다.

전문가 에이전트(특히 앱 디자인)는 스크린샷을 눈으로 보고 채점하므로, 매주 같은 화면을
같은 폭으로 찍어 회차 간 비교가 가능하게 한다.

⚠ 이 앱은 **문서가 아니라 #appscroll 컨테이너가 스크롤된다**(base.html). 그래서
window.scrollTo나 full_page 캡처로는 첫 화면만 반복해서 찍힌다 — 2026-09-12 2회차에
상세·리포트 분할 캡처 4장이 바이트 단위로 동일해 경매·품질 두 전문가가 하단을 보지
못했다. 아래 _slices()는 실제 스크롤 컨테이너를 찾아 그것을 스크롤한다.
캡처 후 md5로 중복을 검사해, 같은 화면이 반복되면 실패로 보고한다(조용히 넘어가지 않는다).

사용: python scripts/capture_weekly_screens.py [--date 2026-09-12] [--base https://naechaget.co.kr]
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
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


# 스크롤 컨테이너를 직접 찾는다 — 문서(scrollingElement)가 안 움직이는 레이아웃이기 때문.
_SCROLLER = """() => {
  const de = document.scrollingElement || document.documentElement;
  if (de.scrollHeight > de.clientHeight + 8) return {sel: null, h: de.scrollHeight, c: de.clientHeight};
  let best = null;
  for (const el of document.querySelectorAll('div,main,section')) {
    const cs = getComputedStyle(el);
    if (!/auto|scroll/.test(cs.overflowY)) continue;
    if (el.scrollHeight - el.clientHeight < 8) continue;
    if (!best || el.scrollHeight > best.scrollHeight) best = el;
  }
  if (!best) return {sel: null, h: de.scrollHeight, c: de.clientHeight};
  if (!best.id) best.id = '__capscroll';
  return {sel: '#' + best.id, h: best.scrollHeight, c: best.clientHeight};
}"""


def _scroll_to(pg, sel, y):
    if sel:
        pg.evaluate("([s, y]) => { document.querySelector(s).scrollTop = y; }", [sel, y])
    else:
        pg.evaluate("y => window.scrollTo(0, y)", y)


def _slices(pg, out, stem, max_slices=4):
    """화면 높이만큼 끊어 위→아래로 찍는다. 실제로 내려갔는지 md5로 확인한다."""
    info = pg.evaluate(_SCROLLER)
    sel, total, view = info["sel"], info["h"], info["c"]
    n = max(1, min(max_slices, -(-total // max(view, 1))))
    seen, files = {}, []
    for i in range(n):
        _scroll_to(pg, sel, i * view)
        pg.wait_for_timeout(450)
        f = out / f"{stem}-{i + 1}.png"
        pg.screenshot(path=str(f))
        digest = hashlib.md5(f.read_bytes()).hexdigest()
        if digest in seen:
            f.unlink()                    # 같은 화면이 또 찍혔으면 남기지 않는다
            print(f"  ⚠ {f.name}: {seen[digest]}와 동일 — 스크롤이 안 먹음(컨테이너 {sel})")
            break
        seen[digest] = f.name
        files.append(f.name)
    _scroll_to(pg, sel, 0)
    return files


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
        for label, w, h in (("mobile", 390, 844), ("mobile360", 360, 800), ("desktop", 1440, 1000)):
            pg = b.new_page(viewport={"width": w, "height": h},
                            user_agent=UA if label.startswith("mobile") else None)
            for name, path in screens:
                try:
                    pg.goto(a.base + path, wait_until="networkidle", timeout=90000)
                    pg.wait_for_timeout(700)          # 폰트·이미지 안정화
                    if label.startswith("mobile"):
                        # 세로로 긴 화면(상세·리포트)은 전체 캡처가 축소돼 글씨를 못 읽는다.
                        # 화면 높이 단위로 끊어 실제 사용자가 보는 크기로 남긴다.
                        made += _slices(pg, out, f"{name}-{label}")
                    else:
                        f = out / f"{name}-{label}.png"
                        pg.screenshot(path=str(f), full_page=True)
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
