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
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from playwright.async_api import async_playwright  # noqa: E402

OUT = ROOT / "screenshots" / "persona" / "2026-09-13-r3"
BASE = "https://naechaget.co.kr"
WIDTH, HEIGHT = 390, 900
SPLASH = ("() => { const s = document.getElementById('splash');"
          " return !s || getComputedStyle(s).display === 'none'; }")


def _candidates() -> list[str]:
    """로컬 DB에서 후보를 넉넉히 뽑는다(분석 끝·사진 많음·기일 남음)."""
    con = sqlite3.connect(ROOT / "data" / "auction.db")
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id FROM vehicles WHERE status='완료' AND median_price IS NOT NULL"
        " AND photo_count >= 5 AND upper_bid IS NOT NULL"
        " AND (auction_result IS NULL OR auction_result <> '낙찰')"
        " AND sale_date >= date('now') ORDER BY sale_date LIMIT 40").fetchall()
    return [r["id"] for r in rows]


def pick_vehicle() -> str:
    """⚠ 후보는 **로컬** DB에서 고르는데 화면은 **프로덕션**에서 찍는다.

    두 DB가 갈릴 수 있다 — 실제로 2026타경51038 은 로컬엔 시세가 있는데 프로덕션에선
    사건번호 충돌 격리로 파생값이 지워져 리포트가 "시세 미산정" 한 줄짜리 빈 페이지였다.
    그 상태로 패널에 넘기면 리포트 화면을 아무도 평가하지 못한다(직전 패널이 그랬다).
    그래서 **프로덕션 응답을 실제로 받아 보고** 리포트가 내용이 있는지 확인한 뒤 고른다.
    """
    for vid in _candidates():
        q = urllib.parse.quote(vid, safe="")
        try:
            with urllib.request.urlopen(f"{BASE}/vehicle/{q}/report", timeout=40) as r:
                html = r.read().decode("utf-8")
        except Exception as e:
            print(f"  · {vid} 확인 실패({e}) — 다음 후보")
            continue
        if "종합 리포트를 생성할 수 없습니다" in html:
            print(f"  · {vid} 프로덕션에서 시세 미산정 — 다음 후보")
            continue
        if html.count('class="sec-no"') < 12:
            print(f"  · {vid} 섹션이 12개가 아님 — 다음 후보")
            continue
        return vid
    raise SystemExit("프로덕션에서 리포트가 온전한 물건을 못 찾았다 — 데이터 확인 필요")


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
        # 큰글씨 모드 — 60·70대 페르소나가 실제로 쓸 화면. 원 패널 비교용 5개는
        # 그대로 두고 2장을 덧붙인다(대체가 아니라 추가).
        ("06-list-large", "/vehicles"),
        ("07-report-large", f"/vehicle/{q}/report"),
    ]
    print(f"대표 물건: {vid}\n")
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for name, path in screens:
            ctx = await b.new_context(viewport={"width": WIDTH, "height": HEIGHT},
                                      device_scale_factor=2)
            if name.endswith("-large"):
                await ctx.add_init_script(
                    "try{localStorage.setItem('naechaget:large','1')}catch(e){}")
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
