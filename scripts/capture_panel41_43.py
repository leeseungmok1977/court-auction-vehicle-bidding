"""PANEL-41(인쇄본 선택 규칙) · PANEL-43(어포던스·달력 임계값·/accuracy) 검수 캡처 + 측정.

⚠ 대상 물건을 아무거나 고르면 **공허 통과**다(CLAUDE.md 검수 SOP 2번).
   ② 는 `.logic` 이 실제로 렌더되는 리포트여야 하고(= `expected.basis.kind == 'min_premium'`),
   라벨이 `국산` 으로 떨어지면 폭 검사가 무의미하므로 **가격대 층이 실제로 이기는** 물건만 쓴다.
   운영 DB 전수 분류(1,418대)로 고른 것:
     2025타경13156_1   min_premium · capped=False · acc=('가격대','시세 1,000~2,000만',59,9.6)
     2025타경101362_3  min_premium · capped=True  · 같은 층 — 캡 2줄이 더 붙어 세로가 가장 길다
   `시세 1,000~2,000만` 은 현재 층 라벨 중 **최장**이다(가격대 층이 이기는 562건 중 193건).

사용: python scripts/capture_panel41_43.py --tag before|after
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import subprocess
import sys
import urllib.parse

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[1]
UA = ("Mozilla/5.0 (Linux; Android 14; SM-A536N) AppleWebKit/537.36 "
      "Chrome/140.0 Mobile Safari/537.36")
PUBLIC_HDR = {"x-forwarded-for": "203.0.113.7"}      # nginx 경유 = 공개 화면

RPT_UNCAPPED = "2025타경13156_1"
RPT_CAPPED = "2025타경101362_3"

# (이름, 경로, 폭, 큰글씨, 관리자, 인쇄매체)
SHOTS = [
    # ② `.logic` — 폭이 가장 빠듯한 자리. 320 큰글씨가 최악 조건이다.
    ("logic-uncapped", f"/vehicle/{RPT_UNCAPPED}/report", 320, True,  False, False),
    ("logic-uncapped", f"/vehicle/{RPT_UNCAPPED}/report", 320, False, False, False),
    ("logic-uncapped", f"/vehicle/{RPT_UNCAPPED}/report", 360, True,  False, False),
    ("logic-uncapped", f"/vehicle/{RPT_UNCAPPED}/report", 360, False, False, False),
    ("logic-uncapped", f"/vehicle/{RPT_UNCAPPED}/report", 390, True,  False, False),
    ("logic-uncapped", f"/vehicle/{RPT_UNCAPPED}/report", 390, False, False, False),
    ("logic-uncapped", f"/vehicle/{RPT_UNCAPPED}/report", 430, True,  False, False),
    ("logic-uncapped", f"/vehicle/{RPT_UNCAPPED}/report", 430, False, False, False),
    ("logic-capped",   f"/vehicle/{RPT_CAPPED}/report",   320, True,  False, False),
    ("logic-capped",   f"/vehicle/{RPT_CAPPED}/report",   390, True,  False, False),
    ("logic-capped",   f"/vehicle/{RPT_CAPPED}/report",   360, False, False, False),
    # ② 인쇄본 — 툴팁(.pop/.q)이 사라지는 그 조건에서 규칙이 남는지
    ("logic-print",    f"/vehicle/{RPT_UNCAPPED}/report", 390, False, False, True),
    ("logic-print",    f"/vehicle/{RPT_UNCAPPED}/report", 320, True,  False, True),
    # ③⑴ 히어로 한 줄 — `분위수 밴드`(? 있음) vs `이 유형`(? 없음)
    ("hero-afford",    f"/vehicle/{RPT_UNCAPPED}/report", 390, False, False, False),
    ("hero-afford",    f"/vehicle/{RPT_UNCAPPED}/report", 320, True,  False, False),
    # ③⑵ 달력 가격대 막대 — 임계값 22.5em(=360px) 경계 전후
    ("cal-bands",      "/calendar", 320, True,  False, False),
    ("cal-bands",      "/calendar", 360, True,  False, False),
    ("cal-bands",      "/calendar", 390, True,  False, False),
    ("cal-bands",      "/calendar", 430, True,  False, False),
    ("cal-bands",      "/calendar", 390, False, False, False),
    # ③⑶ /accuracy 관리자 표 — 눈으로 안 본 화면
    ("acc-table",      "/accuracy", 390,  False, True, False),
    ("acc-table",      "/accuracy", 768,  False, True, False),
    ("acc-table",      "/accuracy", 1440, False, True, False),
]

# 캡처 대상 컨테이너에 표식을 단다(선택자가 클래스 조합에 의존하지 않게)
MARK = """(kind) => {
  let el = null;
  if (kind.startsWith('logic')) {
    const l = document.querySelector('.logic');
    el = l ? l.closest('.card') : null;
  } else if (kind === 'hero-afford') {
    const lab = [...document.querySelectorAll('.v-label')].find(d => /예상낙찰가/.test(d.textContent));
    el = lab ? lab.parentElement : null;
  } else if (kind === 'cal-bands') {
    const r = document.querySelector('.nc-band-row');
    el = r ? r.parentElement.parentElement : null;
  } else if (kind === 'acc-table') {
    const h = [...document.querySelectorAll('h3')].find(x => /어디서 잘 맞고/.test(x.textContent));
    el = h ? h.closest('div.bg-surface') : null;
  }
  if (el) { el.setAttribute('data-shot', '1'); return true; }
  return false;
}"""

PROBE_LOGIC = """() => {
  const logics = [...document.querySelectorAll('.logic')];
  if (!logics.length) return {err: '.logic 없음 — 공허 통과 위험'};
  const card = logics[0].closest('.card');
  const cs = getComputedStyle(card);
  const ci = card.getBoundingClientRect();
  const innerR = ci.right - parseFloat(cs.paddingRight);
  const rows = logics.map(l => {
    const kids = [...l.children];
    const maxRight = Math.max(...kids.map(k => k.getBoundingClientRect().right));
    return {ln: (l.querySelector('.ln') || {}).textContent,
            h: Math.round(l.getBoundingClientRect().height),
            overR: Math.round(maxRight - innerR)};
  });
  const acc = [...document.querySelectorAll('.logic .ld small')]
        .map(s => s.textContent.replace(/\\s+/g, ' ').trim()).filter(t => /실측 오차/.test(t));
  const vis = e => { const s = getComputedStyle(e); return s.display !== 'none' && s.visibility !== 'hidden'; };
  const rule = [...document.querySelectorAll('p.note')].find(p => /불리한/.test(p.textContent));
  const qs = [...document.querySelectorAll('.gloss .q')];
  const pops = [...document.querySelectorAll('.gloss .pop')];
  return {cardW: Math.round(ci.width), rows,
          accSmall: acc, worstOverR: Math.max(...rows.map(r => r.overR)),
          ruleFound: !!rule, ruleVisible: rule ? vis(rule) : false,
          ruleText: rule ? rule.textContent.replace(/\\s+/g, ' ').trim() : null,
          ruleH: rule ? Math.round(rule.getBoundingClientRect().height) : null,
          ruleColor: rule ? getComputedStyle(rule).color : null,
          qVisible: qs.filter(vis).length, qTotal: qs.length,
          popVisible: pops.filter(e => getComputedStyle(e).display !== 'none').length,
          popTotal: pops.length};
}"""

PROBE_HERO = """() => {
  const lab = [...document.querySelectorAll('.v-label')].find(d => /예상낙찰가/.test(d.textContent));
  if (!lab) return {err: 'v-label 없음'};
  const gl = [...lab.querySelectorAll('.gloss')].map(g => ({
    term: (g.querySelector('.gt') || {}).textContent,
    hasQ: !!g.querySelector('.q'),
    underline: getComputedStyle(g.querySelector('.gt')).textDecorationLine + ' ' +
               getComputedStyle(g.querySelector('.gt')).textDecorationStyle,
    aria: g.getAttribute('aria-label') ? g.getAttribute('aria-label').slice(0, 40) : null,
    tabindex: g.getAttribute('tabindex'),
    h: Math.round(g.getBoundingClientRect().height),
  }));
  return {text: lab.textContent.replace(/\\s+/g, ' ').trim(), gloss: gl,
          lines: Math.round(lab.getBoundingClientRect().height)};
}"""

PROBE_BANDS = """() => {
  const rows = [...document.querySelectorAll('.nc-band-row')];
  if (!rows.length) return {err: '.nc-band-row 없음'};
  return rows.map(r => {
    const lbl = r.querySelector('.nc-band-lbl');
    const track = r.querySelector('.flex-1');
    const lr = lbl.getBoundingClientRect(), tr = track.getBoundingClientRect();
    const lh = parseFloat(getComputedStyle(lbl).lineHeight) || 1;
    return {label: lbl.textContent.trim(), lblW: Math.round(lr.width),
            lblLines: Math.round(lr.height / lh * 10) / 10,
            barW: Math.round(tr.width), rowH: Math.round(r.getBoundingClientRect().height),
            stacked: Math.round(tr.top) >= Math.round(lr.bottom) - 1};
  });
}"""

PROBE_ACC = """() => {
  const h = [...document.querySelectorAll('h3')].find(x => /어디서 잘 맞고/.test(x.textContent));
  if (!h) return {err: '층 표 없음'};
  const card = h.closest('div.bg-surface');
  const groups = [...card.querySelectorAll('.divide-y > div')].map(g => ({
    group: (g.querySelector('.text-xs.font-semibold') || {}).textContent,
    rows: [...g.querySelectorAll('.flex.items-baseline')]
            .map(r => r.textContent.replace(/\\s+/g, ' ').trim()),
  }));
  return {groups, prefixLeak: /시세 [0-9]/.test(card.textContent)};
}"""

OVERFLOW = """() => {
  const de = document.documentElement;
  const bad = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (el.closest('aside')) continue;      // 오프캔버스 네비는 화면 밖이 정상
    if (r.right <= 0) continue;
    if (r.right > de.clientWidth + 1 || r.left < -1) {
      bad.push((el.tagName + '.' + (el.className || '').toString().slice(0, 50)).slice(0, 80)
               + ` L${Math.round(r.left)} R${Math.round(r.right)}`);
    }
  }
  return {hscroll: de.scrollWidth > de.clientWidth + 1,
          scrollW: de.scrollWidth, clientW: de.clientWidth, bad: bad.slice(0, 5)};
}"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True, choices=["before", "after"])
    ap.add_argument("--base", default="http://127.0.0.1:8013")
    a = ap.parse_args()

    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
    out = ROOT / "screenshots" / "panel41-43" / a.tag
    out.mkdir(parents=True, exist_ok=True)
    # ★ 캡처가 스스로 기준 커밋을 말하게 한다(PANEL-45 ⑴ — SOP 2번)
    (out / "COMMIT.txt").write_text(f"{head}\ntag={a.tag}\n", encoding="utf-8")
    print(f"기준 커밋 {head} · tag={a.tag}\n")

    seen: dict[str, str] = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for kind, path, w, large, admin, printed in SHOTS:
            ctx = b.new_context(viewport={"width": w, "height": 900}, device_scale_factor=2,
                                user_agent=UA,
                                extra_http_headers={} if admin else PUBLIC_HDR)
            if large:
                ctx.add_init_script("try{localStorage.setItem('naechaget:large','1')}catch(e){}")
            pg = ctx.new_page()
            if printed:
                pg.emulate_media(media="print")
            url = a.base + "/".join(urllib.parse.quote(s, safe="") if "타경" in s else s
                                    for s in path.split("/"))
            r = pg.goto(url, wait_until="networkidle", timeout=60000)
            pg.wait_for_timeout(400)
            marked = pg.evaluate(MARK, kind)
            name = (f"{kind}-{w}{'-large' if large else ''}"
                    f"{'-admin' if admin else ''}{'-print' if printed else ''}")
            dest = out / f"{name}.png"
            loc = pg.locator("[data-shot='1']").first
            if marked and loc.count():
                loc.scroll_into_view_if_needed()
                pg.wait_for_timeout(200)
                loc.screenshot(path=str(dest))
            else:
                pg.screenshot(path=str(dest))
                print(f"  ! {name}: 대상 컨테이너 못 찾음 — 전체 화면 대체")
            md5 = hashlib.md5(dest.read_bytes()).hexdigest()
            dup = seen.get(md5)
            seen[md5] = name
            ov = pg.evaluate(OVERFLOW)
            print(f"\n[{name}] HTTP {r.status}  md5 {md5}" + (f"  ⚠ {dup} 와 동일" if dup else ""))
            if kind.startswith("logic"):
                pr = pg.evaluate(PROBE_LOGIC)
                if pr.get("err"):
                    print(f"  ★ {pr['err']}")
                else:
                    print(f"  cardW={pr['cardW']} worstOverR={pr['worstOverR']}px "
                          f"(>0 이면 카드를 뚫음)")
                    print(f"  rows={pr['rows']}")
                    print(f"  acc small={pr['accSmall']}")
                    print(f"  rule found={pr['ruleFound']} visible={pr['ruleVisible']} "
                          f"h={pr['ruleH']} color={pr['ruleColor']}")
                    print(f"  rule text={pr['ruleText']}")
                    print(f"  q visible {pr['qVisible']}/{pr['qTotal']} · "
                          f"pop visible {pr['popVisible']}/{pr['popTotal']}")
            elif kind == "hero-afford":
                pr = pg.evaluate(PROBE_HERO)
                print(f"  {pr}")
            elif kind == "cal-bands":
                for row in pg.evaluate(PROBE_BANDS):
                    print(f"  {row}")
            elif kind == "acc-table":
                pr = pg.evaluate(PROBE_ACC)
                if pr.get("err"):
                    print(f"  ★ {pr['err']}")
                else:
                    for g in pr["groups"]:
                        print(f"  [{g['group']}] {g['rows']}")
                    print(f"  '시세' 접두 유출 = {pr['prefixLeak']} (False 여야 정상)")
            print(f"  overflow hscroll={ov['hscroll']} {ov['scrollW']}/{ov['clientW']} "
                  f"bad={ov['bad']}")
            ctx.close()
        b.close()
    print(f"\nOUT: {out}  (기준 커밋 {head})")
    if len(seen) != len(SHOTS):
        print(f"⚠ 서로 다른 캡처 {len(seen)}장 / 총 {len(SHOTS)}장 — 같은 화면이 섞여 있다")
    return 0


sys.exit(main())
