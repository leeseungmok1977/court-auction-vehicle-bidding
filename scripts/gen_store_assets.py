# -*- coding: utf-8 -*-
"""Play 스토어 자산 생성: 피처 그래픽(1024x500) + 스크린샷 8장 (라이브 앱, 공개/모바일 뷰)."""
import os
from playwright.sync_api import sync_playwright

BASE = "https://naechaget.co.kr"
OUT = r"c:\Users\14ZB95N\법원경매조회 및 분석\store_assets"
os.makedirs(OUT, exist_ok=True)
ID1 = "2026타경50522_1"
ID2 = "2025타경22366_1"

FEATURE_HTML = """<!doctype html><html lang=ko><head><meta charset=utf-8>
<link rel="stylesheet" href="%s/static/app.css">
<style>
*{margin:0;box-sizing:border-box}
body{width:1024px;height:500px;overflow:hidden;font-family:Pretendard,'Malgun Gothic',sans-serif;
 background:linear-gradient(135deg,#16305e 0%%,#0f2247 55%%,#0b1730 100%%);color:#fff;position:relative}
.glow{position:absolute;right:-80px;top:-140px;width:460px;height:460px;border-radius:50%%;background:rgba(245,182,62,.14);filter:blur(70px)}
.wrap{position:relative;height:100%%;display:flex;align-items:center;gap:52px;padding:0 76px}
.icon{width:136px;height:136px;border-radius:30px;box-shadow:0 14px 44px rgba(0,0,0,.38);flex:none}
.eyebrow{font-size:18px;letter-spacing:.24em;color:rgba(255,255,255,.55);font-weight:700;margin-bottom:14px}
.brand{font-size:58px;font-weight:800;letter-spacing:-1px;line-height:1}
.brand .g{color:#f5b63e}
.tag{font-size:31px;font-weight:700;margin-top:20px;line-height:1.34}
.sub{font-size:19px;color:rgba(255,255,255,.72);margin-top:14px}
.pill{display:inline-block;margin-top:24px;font-size:16px;font-weight:800;color:#0b1730;background:#f5b63e;padding:9px 18px;border-radius:999px}
</style></head><body>
<div class=glow></div>
<div class=wrap>
 <img class=icon src="%s/static/icons/icon-192.png">
 <div>
  <div class=eyebrow>AI COURT AUCTION</div>
  <div class=brand>경매로 내차<span class=g>GET</span></div>
  <div class=tag>법원 자동차 경매,<br>얼마에 써야 할까?</div>
  <div class=sub>유찰 이력·최저매각가로 산정한 예상 낙찰가와 입찰 전략</div>
  <div class=pill>AI 예상 낙찰가 · 입찰 전략 · 실측 검증</div>
 </div>
</div></body></html>""" % (BASE, BASE)


def scroll_to(page, text):
    page.evaluate("""(t)=>{const els=[...document.querySelectorAll('h2,h3')];
      const el=els.find(e=>e.textContent.includes(t));
      if(el)el.scrollIntoView({block:'center'});}""", text)
    page.wait_for_timeout(700)


with sync_playwright() as p:
    b = p.chromium.launch()
    # 1) 피처 그래픽
    fg = b.new_page(viewport={"width": 1024, "height": 500}, device_scale_factor=2)
    fg.set_content(FEATURE_HTML, wait_until="load")
    fg.wait_for_timeout(1800)  # 폰트 로드
    fg.screenshot(path=os.path.join(OUT, "feature_graphic_1024x500.png"),
                  clip={"x": 0, "y": 0, "width": 1024, "height": 500})
    fg.close()
    print("OK feature_graphic_1024x500.png")

    # 2) 스크린샷(모바일 공개 뷰 — 프레임 리다이렉트 회피: is_mobile + no hover)
    ctx = b.new_context(viewport={"width": 412, "height": 820}, device_scale_factor=3,
                        is_mobile=True, has_touch=True, locale="ko-KR")
    pg = ctx.new_page()

    def shot(name, url, scroll=None):
        pg.goto(BASE + url, wait_until="load", timeout=45000)
        pg.wait_for_timeout(1800)
        if scroll:
            scroll_to(pg, scroll)
        pg.screenshot(path=os.path.join(OUT, name))
        print("OK", name)

    shot("01_dashboard.png", "/")
    shot("02_list.png", "/vehicles")
    shot("03_detail_predict.png", "/vehicle/" + ID1)
    shot("04_detail_strategy.png", "/vehicle/" + ID1, scroll="추천 입찰 전략")
    shot("05_detail_retail.png", "/vehicle/" + ID1, scroll="소매 시장 대비 차익")
    shot("06_calendar.png", "/calendar")
    shot("07_courts.png", "/courts")
    shot("08_detail2.png", "/vehicle/" + ID2)

    ctx.close()
    b.close()
print("DONE ->", OUT)
