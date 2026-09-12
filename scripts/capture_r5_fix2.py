"""5회차 수정 재검수용 캡처 — 디자인 에이전트가 요청한 6장.

히어로는 **DPR 3**으로 찍는다. DPR 1로 찍으면 320px 소스를 늘려 쓰는 뭉개짐이
안 보이고 멀쩡해 보인다 — 실제 갤럭시 A 시리즈에서 보이는 것을 찍어야 한다.

주의(5회차에 세 번 당한 것):
  · #splash 가 화면을 덮은 채로 찍으면 스플래시만 나온다.
  · 1024px 이상은 /static/frame.html 폰 프레임 셸이라 본문이 iframe 안이다.
  · 한글 물건 id 는 파이썬 안에서 quote() 한다 (셸로 넘기면 깨진다).
"""
import asyncio
import os
import sys
import urllib.parse

from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding="utf-8")

OUT = os.path.join(r"C:\Users\14ZB95N", "법원경매조회 및 분석",
                   "screenshots", "weekly", "2026-09-12-r5-fix2")
BASE = "https://naechaget.co.kr"
SPLASH_GONE = ("() => { const s = document.getElementById('splash');"
               " return !s || getComputedStyle(s).display === 'none'; }")

# (파일명, 경로, 폭, DPR, 잘라낼 요소 셀렉터 or None=전체)
CAP_CARD = "h3:has-text('입찰가 산정 근거')"
SHOTS = [
    ("cap-only-360",   "/vehicle/2026타경3534_1",    360, 2, CAP_CARD),
    ("cap-only-390",   "/vehicle/2026타경3534_1",    390, 2, CAP_CARD),
    # ⚠ 2026타경500477은 하한 케이스가 아니라 일반 캡 케이스였다(검수에서 지적).
    #    진짜 하한 되밀림 = raw > cap 이면서 최저매각가가 cap을 다시 밀어올린 물건.
    ("cap-plain-360",  "/vehicle/2026타경500477_1",  360, 2, CAP_CARD),
    ("cap-floor-360",  "/vehicle/2025타경101362_3",  360, 2, CAP_CARD),
    ("cap-floor-320",  "/vehicle/2025타경101362_3",  320, 2, CAP_CARD),
    ("hero-thumb-390", "/vehicle/2026타경30903_1",   390, 3, "#heroImg"),
    ("home-thumb-390", "/",                          390, 3, None),
    ("list-thumb-390", "/vehicles",                  390, 3, None),
    ("list-360",       "/vehicles",                  360, 2, None),
    ("list-320",       "/vehicles",                  320, 2, None),
]


async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for name, path, w, dpr, sel in SHOTS:
            if path.startswith("/vehicle/"):
                vid = path[len("/vehicle/"):]
                path = "/vehicle/" + urllib.parse.quote(vid, safe="")
            ctx = await browser.new_context(viewport={"width": w, "height": 900},
                                            device_scale_factor=dpr)
            pg = await ctx.new_page()
            resp = await pg.goto(BASE + path, wait_until="networkidle", timeout=90000)
            try:
                await pg.wait_for_function(SPLASH_GONE, timeout=15000)
            except Exception:
                print(f"  ! {name}: 스플래시가 안 사라짐")
            await pg.wait_for_timeout(600)
            dest = os.path.join(OUT, name + ".png")
            if sel:
                loc = pg.locator(sel).first
                if await loc.count() == 0:
                    print(f"  ! {name}: '{sel}' 없음 — 전체 화면으로 대체")
                    await pg.screenshot(path=dest)
                else:
                    if sel == CAP_CARD:
                        loc = loc.locator("xpath=..")
                    await loc.scroll_into_view_if_needed()
                    await pg.wait_for_timeout(300)
                    await loc.screenshot(path=dest)
            else:
                await pg.screenshot(path=dest)
            size = os.path.getsize(dest) // 1024
            print(f"  {name}.png  {w}px DPR{dpr}  {size}KB  (status {resp.status})")
            await ctx.close()
        await browser.close()
    print("OUT:", OUT)


asyncio.run(main())
