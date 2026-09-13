"""18인 페르소나 패널용 화면 캡처 — 원 패널(2026-09-11)과 **같은 5개 화면**.

원본: 홈 · 차량목록 · 물건 상세 · 리포트 · 경매달력
비교가 목적이므로 화면 구성과 폭을 바꾸지 않는다.

주의(앞서 세 번 당한 것):
  · #splash 가 화면을 덮는다 — 사라질 때까지 기다린다
  · ≥1024px 는 /static/frame.html 폰 프레임 셸이라 본문이 iframe 안이다 → 모바일 폭으로 찍는다
  · 한글 물건 id 는 파이썬 안에서 quote() 한다
"""
import asyncio
import os
import sqlite3
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from playwright.async_api import async_playwright  # noqa: E402

OUT = ROOT / "screenshots" / "persona" / "2026-09-13"
BASE = "https://naechaget.co.kr"
WIDTH, HEIGHT = 390, 900
SPLASH = ("() => { const s = document.getElementById('splash');"
          " return !s || getComputedStyle(s).display === 'none'; }")


def pick_vehicle() -> str:
    """패널이 볼 대표 물건 — 분석이 끝났고 사진·시세가 다 있는 것."""
    con = sqlite3.connect(ROOT / "data" / "auction.db")
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT id FROM vehicles WHERE status='완료' AND median_price IS NOT NULL"
        " AND photo_count >= 5 AND upper_bid IS NOT NULL"
        " AND (auction_result IS NULL OR auction_result <> '낙찰')"
        " AND sale_date >= date('now') ORDER BY sale_date LIMIT 1").fetchone()
    if not row:
        row = con.execute(
            "SELECT id FROM vehicles WHERE status='완료' AND median_price IS NOT NULL"
            " ORDER BY id DESC LIMIT 1").fetchone()
    return row["id"]


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vid = pick_vehicle()
    q = urllib.parse.quote(vid, safe="")
    screens = [
        ("01-home", "/"),
        ("02-list", "/vehicles"),
        ("03-detail", f"/vehicle/{q}"),
        ("04-report", f"/vehicle/{q}/report"),
        ("05-calendar", "/calendar"),
    ]
    print(f"대표 물건: {vid}\n")
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for name, path in screens:
            ctx = await b.new_context(viewport={"width": WIDTH, "height": HEIGHT},
                                      device_scale_factor=2)
            pg = await ctx.new_page()
            await pg.goto(BASE + path, wait_until="networkidle", timeout=120000)
            try:
                await pg.wait_for_function(SPLASH, timeout=15000)
            except Exception:
                print(f"  ! {name}: 스플래시가 안 사라짐")
            await pg.wait_for_timeout(700)
            dest = OUT / f"{name}.png"
            await pg.screenshot(path=str(dest), full_page=True)
            info = await pg.evaluate(
                "() => ({t: document.title, n: document.body.innerText.length})")
            print(f"  {name}.png  {os.path.getsize(dest)//1024:>5}KB  "
                  f"본문 {info['n']:>5}자  [{info['t'][:34]}]")
            await ctx.close()
        await b.close()
    print(f"\nOUT: {OUT}")
    print(f"대표 물건 id: {vid}")


asyncio.run(main())
