# -*- coding: utf-8 -*-
"""Play 스토어 제출용 스크린샷을 찍는다 — **찍힌 것이 맞는지 스스로 확인한다.**

    python tools/capture_store_shots.py --slide5      # 5번(상세 하단·입찰 상한선)만
    python tools/capture_store_shots.py --all         # 후보 전부

## 왜 이 파일이 생겼나

2026-09-23 `pm-orchestrator` 가 잡아냈다: 제출 예정 **4번과 5번이 같은 파일**이었다
(`07_detail.png` = `08_detail_lower.png`, md5 `8e6ff630…`). 5번 캡션은 "입찰 상한선까지
계산해 드립니다" 인데 그 그림에는 입찰 상한선 숫자가 없다. 같은 그림이 두 번 올라가고
캡션이 그림에 의해 뒷받침되지 않는 상태였다.

원인 둘.
  ① 캡처 스크립트가 **저장소에 없었다**(scratchpad 에만 있었다). 재현도 검토도 불가능했다.
  ② 스크롤을 `window.scrollBy(0, innerHeight)` 로 밀었는데 **안 먹었다.** 그런데 아무도
     확인하지 않았다. 같은 실패가 `screenshots/tour/09_detail_0/1/2` 에도 있었다 —
     세 장이 md5 까지 같았다(growth 보고서 §4.2).

그래서 이 스크립트는 **찍고 나서 자기가 검사한다.**
  · 목표 요소가 실제로 뷰포트 안에 들어왔는가(scrollIntoView 가 먹었는가)
  · 화면에 기대한 문구가 있는가
  · 기존 제출본과 md5 가 다른가
  · 규격 1080×1920 인가
검사에 걸리면 **파일을 남기지 않는다.** 조용히 잘못된 자산이 제출되는 것이 최악이다.

## 촬영 조건 (docs/STORE_LISTING.md 와 같다)

논리폭 540 × DPR 2 = **1080×1920**(9:16). Play 세로 스크린샷 최소 1080×1920,
최대변÷최소변 ≤ 2 를 둘 다 만족한다.

⚠ **공개 사용자 화면으로 찍는다**(`X-Forwarded-For`). 로컬 직결은 관리자로 판정돼
'다시 분석' 같은 운영 버튼이 섞인다 — 스토어에 올라가면 안 되는 화면이다.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import pathlib
import sys

for _s in ("stdout", "stderr"):
    try:
        setattr(sys, _s, io.TextIOWrapper(getattr(sys, _s).buffer,
                                          encoding="utf-8", errors="replace"))
    except Exception:                                        # noqa: BLE001
        pass

from playwright.sync_api import sync_playwright

BASE = "https://naechaget.co.kr"
OUT = pathlib.Path(__file__).resolve().parents[1] / "screenshots" / "store"
VIEW = {"width": 540, "height": 960}
DPR = 2
PUBLIC = {"X-Forwarded-For": "203.0.113.9"}      # 공개 사용자로 보이게 한다


def md5(p: pathlib.Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def find_vehicle_with_cap(pg) -> tuple[str, str] | None:
    """**입찰 상한선이 렌더되는** 물건을 찾는다.

    아무 물건이나 쓰면 안 된다 — `detail.html:323` 이 `bidst.max_bid` 가 있을 때만 이 블록을
    그린다. 상한선이 없는 물건을 찍으면 캡션이 또 그림을 앞서게 된다.
    """
    pg.goto(BASE + "/vehicles?bucket=review&sort=expected", wait_until="networkidle", timeout=45000)
    hrefs = pg.evaluate("""() => [...document.querySelectorAll('a')]
        .map(a => a.getAttribute('href'))
        .filter(h => h && h.startsWith('/vehicle/') && h.split('/').length === 3)""")
    seen = []
    for h in dict.fromkeys(hrefs):               # 순서 유지 중복 제거
        if len(seen) >= 6:
            break
        seen.append(h)
        pg.goto(BASE + h, wait_until="networkidle", timeout=45000)
        pg.wait_for_timeout(700)
        if pg.query_selector("text=입찰 상한선"):
            return h, pg.title()
    return None


def shoot_slide5(pg) -> int:
    got = find_vehicle_with_cap(pg)
    if not got:
        print("★ 입찰 상한선이 있는 물건을 찾지 못했다 — 촬영하지 않는다")
        return 1
    href, title = got
    print(f"대상: {href}")

    # scrollBy 로 밀지 않는다. 그게 이번 사고의 원인이다 — 요소를 직접 데려온다.
    pg.evaluate("""() => {
        const el = [...document.querySelectorAll('div')]
            .find(d => d.textContent.trim().startsWith('입찰 상한선'));
        if (el) el.scrollIntoView({block: 'center'});
    }""")
    pg.wait_for_timeout(600)

    # ★ 정말 보이는가. 뷰포트 안에 들어왔는지 좌표로 확인한다.
    vis = pg.evaluate("""() => {
        const el = [...document.querySelectorAll('div')]
            .find(d => d.textContent.trim().startsWith('입찰 상한선'));
        if (!el) return {ok: false, why: '요소 없음'};
        const r = el.getBoundingClientRect();
        const h = document.documentElement.clientHeight;
        return {ok: r.top >= 0 && r.bottom <= h, top: Math.round(r.top),
                bottom: Math.round(r.bottom), vh: h,
                text: (el.parentElement || el).innerText.replace(/\\s+/g, ' ').slice(0, 70)};
    }""")
    if not vis.get("ok"):
        print(f"★ 입찰 상한선이 화면 안에 안 들어왔다 — {vis}")
        print("   저장하지 않는다. 조용히 잘못된 자산을 남기지 않는다.")
        return 1
    print(f"   화면 안 확인: top={vis['top']} bottom={vis['bottom']} / 뷰포트 {vis['vh']}")
    print(f"   내용: {vis['text']}")

    # '준비 중' 같은 미출시 기능 표시가 섞이지 않았는지
    soon = pg.evaluate("() => document.body.innerText.includes('준비 중')")
    if soon:
        print("★ 화면에 '준비 중' 문구가 있다 — 아직 없는 기능을 광고하는 자산은 만들지 않는다")
        return 1

    tmp = OUT / "_slide5_tmp.png"
    OUT.mkdir(parents=True, exist_ok=True)
    pg.screenshot(path=str(tmp))

    from PIL import Image
    w, h = Image.open(tmp).size
    if not (min(w, h) >= 1080 and max(w, h) >= 1920 and max(w, h) / min(w, h) <= 2):
        print(f"★ 규격 미달 {w}x{h} — 저장하지 않는다")
        tmp.unlink(missing_ok=True)
        return 1

    prev = OUT / "07_detail.png"
    new_md5 = md5(tmp)
    if prev.exists() and md5(prev) == new_md5:
        print("★ 4번(07_detail.png)과 md5 가 같다 — 스크롤이 또 안 먹은 것이다. 저장하지 않는다")
        tmp.unlink(missing_ok=True)
        return 1

    dest = OUT / "08_detail_lower.png"
    tmp.replace(dest)
    print(f"\n합격 저장: {dest.name} · {w}x{h} · md5 {new_md5[:12]}…")
    print(f"      4번과 다름(07_detail.png md5 {md5(prev)[:12]}…)" if prev.exists() else "")
    return 0


def audit() -> int:
    """제출 8장의 md5 를 **전부** 대조한다. 이번 사고는 일부만 본 탓이다."""
    files = sorted(OUT.glob("*.png"))
    if not files:
        print("screenshots/store 가 비었다")
        return 1
    seen: dict[str, list[str]] = {}
    for f in files:
        seen.setdefault(md5(f), []).append(f.name)
    print("\n=== 제출 후보 md5 대조 ===")
    for h, names in seen.items():
        mark = "★ 중복" if len(names) > 1 else "     "
        print(f"  {mark} {h[:12]}…  {', '.join(names)}")
    dup = [n for n in seen.values() if len(n) > 1]
    print(f"\n  {'★ 중복 ' + str(len(dup)) + '쌍' if dup else '합격  중복 없음'}")
    return 1 if dup else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="스토어 제출 스크린샷 촬영(자가 검사 포함)")
    ap.add_argument("--slide5", action="store_true", help="5번(상세 하단·입찰 상한선) 재촬영")
    ap.add_argument("--audit", action="store_true", help="촬영하지 않고 md5 중복만 검사")
    a = ap.parse_args(argv)

    if a.audit:
        return audit()
    if not a.slide5:
        ap.print_help()
        return 2

    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport=VIEW, device_scale_factor=DPR,
                            is_mobile=True, has_touch=True, extra_http_headers=PUBLIC)
        pg = ctx.new_page()
        rc = shoot_slide5(pg)
        b.close()
    if rc == 0:
        rc = audit()                     # 찍었으면 전체 중복 검사까지 하고 끝낸다
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
