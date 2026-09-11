# -*- coding: utf-8 -*-
"""Play 스토어 자산 생성: 피처 그래픽(1024x500) + 폰 스크린샷 8장 (라이브 앱, 공개/모바일 뷰).

주의(신뢰):
- 물건 ID는 **매각기일이 지나면 만료**된다. 실행 전 반드시 미래 기일·검토가능 물건인지 확인할 것
  (만료 물건을 스토어에 올리면 '종결' 배지가 박힌 화면이 나간다).
- 공개(비관리자) 뷰로만 찍는다 — nginx 경유라 XFF가 붙어 자동으로 비관리자.
- 광고는 v1에서 비활성(adsense_client='') 상태여야 한다. 화면에 광고가 보이면 중단하고 설정을 확인할 것.

사용: python scripts/gen_store_assets.py   (playwright 필요)
"""
import os

from playwright.sync_api import sync_playwright

BASE = "https://naechaget.co.kr"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "store_assets")
os.makedirs(OUT, exist_ok=True)

# 촬영 대상 물건 — 2026-09-11 기준 검토가능·사진 다수·미래 매각기일로 선정
ID1 = "2025타경52630_1"   # 쏘나타 2015 · 사진 17 · 기일 2026-09-21
ID2 = "2025타경9181_1"    # 카니발 2017 · 사진 14 · 기일 2026-09-22

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


def scroll_to_text(page, text):
    """제목뿐 아니라 아무 요소나 텍스트로 찾아 가운데 정렬(달력 카드·리포트 라벨 대응)."""
    page.evaluate("""(t)=>{
      const els=[...document.querySelectorAll('h1,h2,h3,.v-label,.sec-head,div,span')];
      const el=els.find(e=>e.textContent.trim().startsWith(t));
      if(el)el.scrollIntoView({block:'center'});}""", text)
    page.wait_for_timeout(700)


def scroll_to_sel(page, sel):
    page.evaluate("""(s)=>{const el=document.querySelector(s); if(el)el.scrollIntoView({block:'center'});}""", sel)
    page.wait_for_timeout(700)


with sync_playwright() as p:
    b = p.chromium.launch()
    # 1) 피처 그래픽
    fg = b.new_page(viewport={"width": 1024, "height": 500}, device_scale_factor=2)
    fg.set_content(FEATURE_HTML, wait_until="load")
    fg.wait_for_timeout(1800)  # 폰트 로드
    _fgp = os.path.join(OUT, "feature_graphic_1024x500.png")
    fg.screenshot(path=_fgp, clip={"x": 0, "y": 0, "width": 1024, "height": 500})
    fg.close()
    # Play 피처 그래픽은 **정확히 1024x500**만 허용 — DSF=2로 선명하게 찍은 뒤 정확한 크기로 축소.
    # (2048x1000 그대로 올리면 등록 거부된다.)
    from PIL import Image as _Im
    with _Im.open(_fgp) as _im:
        if _im.size != (1024, 500):
            _im.convert("RGB").resize((1024, 500), _Im.LANCZOS).save(_fgp)
    print("OK feature_graphic_1024x500.png (1024x500 정규화)")

    # 2) 폰 스크린샷 — 모바일 공개 뷰(is_mobile=True로 데스크톱 폰프레임 리다이렉트 회피)
    ctx = b.new_context(viewport={"width": 412, "height": 820}, device_scale_factor=3,
                        is_mobile=True, has_touch=True, locale="ko-KR")
    pg = ctx.new_page()

    def shot(name, url, text=None, sel=None):
        pg.goto(BASE + url, wait_until="load", timeout=45000)
        pg.wait_for_timeout(1800)
        if sel:
            scroll_to_sel(pg, sel)
        elif text:
            scroll_to_text(pg, text)
        # 광고 유출 감시 — v1은 광고 없음이 전제
        if pg.evaluate("()=>document.documentElement.innerHTML.includes('adsbygoogle')"):
            raise SystemExit(f"중단: {name} 에 광고 스크립트가 있음. adsense_client 설정 확인 필요")
        pg.screenshot(path=os.path.join(OUT, name))
        print("OK", name)

    shot("01_home.png", "/")                                        # 오늘의 추천 캐러셀
    shot("02_list.png", "/vehicles")                                # 차종 프리셋 필터 + 물건 카드
    shot("03_detail_predict.png", "/vehicle/" + ID1)                # AI 예상 낙찰가
    shot("04_detail_strategy.png", "/vehicle/" + ID1, text="추천 입찰 전략")
    shot("05_report_profile.png", "/vehicle/" + ID1 + "/report", sel=".hexa")   # 종합 프로필 육각형
    shot("06_accuracy.png", "/accuracy")                            # 예측 적중률 사후검증
    shot("07_calendar.png", "/calendar", text="지난달 낙찰 실적")      # 실측 낙찰 통계
    shot("08_detail2.png", "/vehicle/" + ID2)                       # 두 번째 물건(패밀리카)

    ctx.close()
    b.close()
print("DONE ->", OUT)
