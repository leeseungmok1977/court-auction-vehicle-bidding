"""PANEL-35(아이콘 톤) · PANEL-37(히어로 3건) 검수용 캡처 + 측정.

⚠ 대상 물건을 아무거나 고르면 공허하다. 히어로는 `detail.html:288`
   `{% if v.median_price is not none and expected and expected.price %}` 로 막혀 있어
   **med·exp 가 둘 다 있는 물건만** 아이콘·게이지가 렌더된다. 운영 DB 전수 분류로
   고른 물건만 쓴다(lowconf 는 115건 중 exp 가 있는 5건에서만 배너가 뜬다).

사용: python scripts/capture_panel35_37.py --tag before|after
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys
import urllib.parse

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[1]
UA = ("Mozilla/5.0 (Linux; Android 14; SM-A536N) AppleWebKit/537.36 "
      "Chrome/140.0 Mobile Safari/537.36")
PUBLIC_HDR = {"x-forwarded-for": "203.0.113.7"}      # nginx 경유 = 공개 화면(폰 프레임 O)
HERO = 'div.overflow-hidden.rounded-2xl.text-white'

# (이름, 물건id, 상태 설명) — 운영 DB 실측으로 고른 것
TARGETS = {
    "lowconf-wait": ("2026타경70785_1", "lowconf/wait 시세 신뢰도 낮음 — 판정 보류"),
    "lowconf-stop": ("2026타경50032_1", "lowconf/stop 시동·운행 불가 — 판정 보류"),
    "overmarket":   ("2026타경30130_1", "over_market/caution 예상 경쟁가가 상한선 초과"),
    "blocked":      ("2025타경13417_1", "blocked/stop 침수·전손 의심"),
    "usepick-ok":   ("2026타경50344_1", "usepick/ok 지금 사면 이득"),
    "wait":         ("2025타경11988_1", "wait/wait 지난 기일"),
}

# (대상, 폭, 큰글씨, 관리자)
SHOTS = [
    ("lowconf-wait", 360, False, False), ("lowconf-wait", 360, True, False),
    ("lowconf-wait", 320, True, False),  ("lowconf-wait", 430, False, False),
    ("lowconf-wait", 390, False, True),
    ("lowconf-stop", 360, False, False),
    ("overmarket", 360, False, False),   ("overmarket", 320, True, False),
    ("overmarket", 390, False, True),
    ("blocked", 360, False, False),
    ("usepick-ok", 360, False, False),
    ("wait", 360, False, False),
]

# 판정 칩·아이콘·게이지 라벨을 DOM 에서 그대로 뽑는다(눈 + 기계 이중 확인)
PROBE = """() => {
  const hero = document.querySelector('div.overflow-hidden.rounded-2xl.text-white');
  if (!hero) return {err: 'hero 없음'};
  // ⚠ 히어로 첫 아이콘은 'AI 낙찰 예측 분석' 배지(psychology)다 — 판정 배너 아이콘은
  //    'text-lg shrink-0 mt-px' 를 가진 쪽이다. 처음에 이걸 틀려 psychology 를 쟀다.
  const icon = [...hero.querySelectorAll('span.material-symbols-outlined')]
        .find(s => /text-lg/.test(s.className) && /shrink-0/.test(s.className));
  const chip = [...hero.querySelectorAll('span')].find(s => /px-2\\.5 py-1 rounded /.test(s.className));
  const gauge = hero.querySelector('.nc-gauge-judge');
  const caps = [...hero.querySelectorAll('div')].filter(d => /AI 예상낙찰가/.test(d.textContent) && d.children.length <= 3);
  const big = hero.querySelector('.nc-heronum-lg');
  return {
    icon_cls: icon ? icon.className : null, icon_glyph: icon ? icon.textContent.trim() : null,
    chip_cls: chip ? chip.className : null, chip_txt: chip ? chip.textContent.trim() : null,
    gauge_txt: gauge ? gauge.textContent.trim() : null,
    gauge_cls: gauge ? gauge.className : null,
    cap_cls: caps.length ? caps[caps.length - 1].className : null,
    big_cls: big ? big.className : null,
  };
}"""

OVERFLOW = """() => {
  const de = document.documentElement;
  const bad = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    // ⚠ 오프캔버스 네비(aside)는 화면 밖에 **있는 것이 정상**이다. CLAUDE.md 가 기록한
    //    측정 오류 6회 중 하나가 바로 이것 — 걸러내지 않으면 매 폭마다 거짓 양성이 뜬다.
    if (el.closest('aside')) continue;
    if (r.right <= 0) continue;
    if (r.right > de.clientWidth + 1 || r.left < -1) {
      bad.push((el.tagName + '.' + (el.className || '').toString().slice(0, 60)).slice(0, 90)
               + ` L${Math.round(r.left)} R${Math.round(r.right)}`);
    }
  }
  return {hscroll: de.scrollWidth > de.clientWidth + 1,
          scrollW: de.scrollWidth, clientW: de.clientWidth, bad: bad.slice(0, 6)};
}"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True, choices=["before", "after"])
    ap.add_argument("--base", default="http://127.0.0.1:8011")
    a = ap.parse_args()

    out = ROOT / "screenshots" / "panel35-37" / a.tag
    out.mkdir(parents=True, exist_ok=True)
    probes: dict[str, dict] = {}

    with sync_playwright() as p:
        b = p.chromium.launch()
        for key, w, large, admin in SHOTS:
            vid, desc = TARGETS[key]
            ctx = b.new_context(viewport={"width": w, "height": 900}, device_scale_factor=2,
                                user_agent=UA,
                                extra_http_headers={} if admin else PUBLIC_HDR)
            if large:
                ctx.add_init_script(
                    "try{localStorage.setItem('naechaget:large','1')}catch(e){}")
            pg = ctx.new_page()
            url = a.base + "/vehicle/" + urllib.parse.quote(vid, safe="")
            r = pg.goto(url, wait_until="networkidle", timeout=60000)
            pg.wait_for_timeout(500)
            name = f"{key}-{w}{'-large' if large else ''}{'-admin' if admin else ''}"
            # 1) 히어로 요소만 — 바뀐 영역을 실제 크기로 본다
            loc = pg.locator(HERO).first
            dest = out / f"{name}.png"
            if loc.count():
                loc.scroll_into_view_if_needed()
                pg.wait_for_timeout(250)
                loc.screenshot(path=str(dest))
            else:
                pg.screenshot(path=str(dest))
                print(f"  ! {name}: 히어로 없음 — 전체 화면 대체")
            md5 = hashlib.md5(dest.read_bytes()).hexdigest()
            pr = pg.evaluate(PROBE)
            ov = pg.evaluate(OVERFLOW)
            probes[name] = pr
            print(f"\n[{name}] {vid} · {desc} (HTTP {r.status})")
            print(f"  md5 {md5}  {dest.relative_to(ROOT)}")
            print(f"  chip  {pr.get('chip_txt')!r}\n        {pr.get('chip_cls')}")
            print(f"  icon  {pr.get('icon_glyph')!r}  {pr.get('icon_cls')}")
            print(f"  gauge {pr.get('gauge_txt')!r}")
            print(f"  cap   {pr.get('cap_cls')}")
            print(f"  big   {pr.get('big_cls')}")
            print(f"  overflow hscroll={ov['hscroll']} {ov['scrollW']}/{ov['clientW']} bad={ov['bad']}")
            ctx.close()
        b.close()
    print("\nOUT:", out)
    return 0


sys.exit(main())
