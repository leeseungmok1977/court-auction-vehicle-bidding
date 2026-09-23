# -*- coding: utf-8 -*-
"""Play 스토어 제출용 스크린샷을 찍는다 — **찍힌 것이 맞는지 스스로 확인한다.**

    python tools/capture_store_shots.py --landing     # 1번 06_landing.png (소개)
    python tools/capture_store_shots.py --home        # 2번 01_home.png (홈·히어로)
    python tools/capture_store_shots.py --accuracy    # 3번 02_accuracy.png (적중률 타일 4개)
    python tools/capture_store_shots.py --detail      # 4번 07_detail.png (감정가·유찰·당시 출시가)
    python tools/capture_store_shots.py --slide5      # 5번 08_detail_lower.png (입찰 상한선)
    python tools/capture_store_shots.py --report      # 6번 09_report.png (리포트 상단)
    python tools/capture_store_shots.py --hexa        # 7번 10_report_lower.png (6축 육각형)
    python tools/capture_store_shots.py --calendar    # 8번 05_calendar.png (달력·지난달 실적)
    python tools/capture_store_shots.py --all         # 제출 8장 전부
    python tools/capture_store_shots.py --audit       # 찍지 않고 제출 8장을 대조

⚠ 2026-09-24 이전에는 **이 독스트링만 `--all` 을 안내하고 구현이 없었다**(인자는 `--slide5`·
`--audit` 둘뿐이었다). 문서가 코드보다 앞서 있었고, 그 결과 홈·적중률·소개를 찍을 경로가
저장소에 아예 없어 그 세 장이 9/22 촬영본인 채로 낡았다.

⚠ 같은 날 2차: 나머지 **네 장(07·08·09·10·05)도 경로가 없었다.** 그래서
`09_report.png` 에 `실측 평균오차 ±9.3%` 가, `05_calendar.png` 에 `낙찰 100건` 이 박힌 채
남았다 — 둘 다 **우리가 스스로 "틀렸다"고 판정해 고친 표기**다(`69e1c47` · `6b04e6d`).
낡은 숫자보다 무겁다. 이제 제출 8장이 전부 여기서 나온다.

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
import time

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

# 제출 8장 — **스토어 슬라이드 순서**다(docs/STORE_LISTING.md 의 표와 같은 순서).
# `03_review.png`·`04_usepick.png` 는 같은 디렉터리에 있지만 제출 대상이 아니다.
# 파일명 숫자와 슬라이드 번호가 어긋나 있는데(6번 슬라이드가 `09_report.png`) 이건
# 촬영 순서에서 온 역사적 흔적이다 — 이름을 바꾸면 이미 올라간 콘솔 자산과 갈라진다.
SUBMIT = ("06_landing.png", "01_home.png", "02_accuracy.png", "07_detail.png",
          "08_detail_lower.png", "09_report.png", "10_report_lower.png", "05_calendar.png")
PUBLIC = {"X-Forwarded-For": "203.0.113.9"}      # 공개 사용자로 보이게 한다

# C.4 ②: 모든 외부 요청 전 5~10초 대기. 우리 서버라도 지킨다.
POLITE_SEC = 7

# 스토어 자산에 절대 섞이면 안 되는 문구.
#   · '준비 중'  = 아직 없는 기능을 광고하는 표시(전례: '보관·구매 (준비 중)' 칩)
#   · 나머지     = 관리자 전용 UI 가 새어 들어온 표시(X-Forwarded-For 가 안 먹은 경우)
FORBIDDEN = ("준비 중", "다시 분석", "운영 도구", "분석 대기")

# **우리가 스스로 틀렸다고 판정해 고친 표기.** 화면에 다시 보이면 배포가 되돌아갔다는 뜻이고,
# 그대로 찍으면 스토어에 영구 공개물로 박힌다 — 낡은 숫자보다 무겁다.
#   · '평균오차' : 물건마다 **전체평균** 오차를 붙이던 표기. `69e1c47`(PANEL-01) 에서 유형별로
#                  교체했다. 현행은 '이 유형(…, N건) 실측 오차 ±…%' 이고, 홈·소개·적중률의
#                  '전체 평균 오차' 는 **띄어쓰기가 있어** 이 문자열과 겹치지 않는다.
#                  2026-09-24 실측: `09_report.png`(9/22 촬영)에 `실측 평균오차 ±9.3%` 가
#                  픽셀로 박혀 있었다 — 수정 커밋보다 15시간 이른 캡처였다.
# 달력의 '낙찰 N건'(→ '시세 확인 N건', `6b04e6d`/PANEL-17)은 숫자가 끼어 문자열로 막기 어렵다.
# 그래서 그쪽은 **금지어가 아니라 shoot_calendar() 의 기대 라벨**로 양성 검사한다.
RETIRED = ("평균오차",)


# 이번 회차에 실제로 저장된 장의 기준 커밋·시각. `stamp_head()` 가 기존 기록에 덧쓴다.
_STAMPS: dict[str, dict] = {}


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def md5(p: pathlib.Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def polite_goto(pg, path: str, wait_until: str = "networkidle") -> None:
    """외부 요청 전 지연(C.4 ②)을 넣고 이동한다."""
    print(f"   … {POLITE_SEC}초 대기 후 {path}")
    time.sleep(POLITE_SEC)
    pg.goto(BASE + path, wait_until=wait_until, timeout=45000)


# 라벨이 **정말 화면 안에 그려졌는지** 좌표로 확인한다.
#   · 숨은 요소(innerText '')는 애초에 후보에서 빠진다 — 오프캔버스 메뉴에 속지 않는다.
#   · 같은 문구를 품은 조상들이 줄줄이 잡히므로 **가장 깊은 요소**만 남긴다.
#   · 화면 하단 고정 바(탭 네비)에 가리는 것도 '안 보이는 것'이다 — floor 아래면 탈락.
_JS_LABEL = """(label) => {
    const vh = document.documentElement.clientHeight;
    const vw = document.documentElement.clientWidth;
    const all = [...document.querySelectorAll('body *')].filter(e => {
        const s = getComputedStyle(e);
        if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
        return (e.innerText || '').includes(label);
    });
    const deep = all.filter(e => !all.some(o => o !== e && e.contains(o)));
    const bars = [...document.querySelectorAll('body *')].filter(e => {
        if (getComputedStyle(e).position !== 'fixed') return false;
        const r = e.getBoundingClientRect();
        return r.bottom >= vh - 2 && r.height > 20 && r.height < vh * 0.4;
    }).map(e => e.getBoundingClientRect().top);
    const floor = bars.length ? Math.min(...bars) : vh;
    const hits = deep.map(e => {
        const r = e.getBoundingClientRect();
        return {top: Math.round(r.top), bottom: Math.round(r.bottom),
                left: Math.round(r.left), right: Math.round(r.right),
                inside: r.top >= 0 && r.bottom <= floor && r.left >= -1 && r.right <= vw + 1,
                text: (e.innerText || '').replace(/\\s+/g, ' ').slice(0, 60)};
    });
    return {vh, vw, floor: Math.round(floor), hits};
}"""


def labels_in_view(pg, labels, quiet: bool = False) -> bool:
    """기대 문구가 **하나도 빠짐없이** 뷰포트 안에 있는지 본다.

    ⚠ 라벨에 **숫자를 넣지 않는다.** 값이 움직이는 순간 촬영이 실패하는데, 그건 화면이
    낡은 게 아니라 검사가 낡은 것이다(2026-09-24 지시). 어휘(라벨)로만 검사한다.

    `quiet=True` 는 **스크롤 지점을 찾는 중**일 때 쓴다 — 실패는 아직 실패가 아니라
    "다음 지점을 시도하라"는 뜻이라, 그걸 ★ 로 찍으면 성공한 회차의 로그가 거짓말을 한다.
    """
    ok = True
    for lab in labels:
        r = pg.evaluate(_JS_LABEL, lab)
        hits = r["hits"]
        good = [h for h in hits if h["inside"]]
        if not hits:
            if not quiet:
                print(f"★ '{lab}' 가 화면에 아예 없다 — 문구가 바뀌었거나 페이지가 다르다")
            ok = False
        elif not good:
            near = hits[0]
            if not quiet:
                print(f"★ '{lab}' 는 있지만 프레임 밖이다 — top={near['top']} bottom={near['bottom']}"
                      f" / 뷰포트 {r['vh']} · 고정바 위 {r['floor']}")
            ok = False
        else:
            g = good[0]
            if not quiet:
                print(f"   화면 안 확인: '{lab}' top={g['top']} bottom={g['bottom']}"
                      f" (뷰포트 {r['vh']} · 고정바 위 {r['floor']}) · {g['text']}")
    return ok


# 요소를 **직접 데려온다.** `window.scrollBy` 로 밀지 않는다 — 그게 07/08 이 md5 까지
# 같아진 원인이었고, `screenshots/tour/09_detail_0/1/2` 세 장에도 같은 사고가 있었다.
_JS_SCROLL = """(arg) => {
    const all = [...document.querySelectorAll('body *')].filter(e => {
        const s = getComputedStyle(e);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        return (e.innerText || '').trim().startsWith(arg.needle);
    });
    const deep = all.filter(e => !all.some(o => o !== e && e.contains(o)));
    if (!deep.length) return false;
    deep[0].scrollIntoView({block: arg.block || 'center'});
    return true;
}"""


def scroll_until(pg, labels, plans) -> bool:
    """기대 라벨이 **전부 한 프레임 안에 들어오는 지점**을 찾는다.

    `plans` 는 `(앵커문구|None, block)` 의 순서 있는 후보다. 앵커가 None 이면 맨 위로 간다.
    ⚠ 앵커는 **문자열**로 가리킨다 — 줄 번호나 픽셀 오프셋은 적는 순간부터 썩는다.
    마지막 후보까지 실패하면 그때 한 번만 시끄럽게 이유를 찍는다.
    """
    for i, (needle, block) in enumerate(plans):
        if needle is None:
            pg.evaluate("() => window.scrollTo(0, 0)")
        else:
            pg.evaluate(_JS_SCROLL, {"needle": needle, "block": block})
        pg.wait_for_timeout(600)
        last = i == len(plans) - 1
        if labels_in_view(pg, labels, quiet=not last):
            if not last:
                print(f"   스크롤 지점 {i + 1}/{len(plans)} 채택(앵커 {needle!r}·{block})")
                labels_in_view(pg, labels)      # 채택한 지점을 소리 내어 다시 확인한다
            return True
    return False


def no_forbidden(pg) -> bool:
    """'준비 중'(미출시 기능 광고)·관리자 UI 누수·**폐기된 표기**를 본문에서 찾는다."""
    txt = pg.evaluate("() => document.body.innerText")
    ok = True
    bad = [w for w in FORBIDDEN if w in txt]
    if bad:
        print(f"★ 스토어에 올리면 안 되는 문구가 화면에 있다: {', '.join(bad)}")
        ok = False
    old = [w for w in RETIRED if w in txt]
    if old:
        print(f"★ 우리가 고쳐 없앤 표기가 화면에 다시 있다: {', '.join(old)}"
              f" — 배포가 되돌아갔는지 먼저 확인하라. 찍으면 영구 공개물이 된다")
        ok = False
    return ok


def guard_and_save(pg, dest_name: str) -> int:
    """찍어서 임시로 두고 **규격·중복**을 본 뒤에만 제자리에 놓는다.

    검사에 걸리면 임시 파일을 지운다 — 조용히 잘못된 자산이 남는 것이 최악이다.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / f"_{dest_name.replace('.png', '')}_tmp.png"
    pg.screenshot(path=str(tmp))

    from PIL import Image
    w, h = Image.open(tmp).size
    if not (min(w, h) >= 1080 and max(w, h) >= 1920 and max(w, h) / min(w, h) <= 2):
        print(f"★ 규격 미달 {w}x{h} — 저장하지 않는다")
        tmp.unlink(missing_ok=True)
        return 1

    new = md5(tmp)
    dest = OUT / dest_name
    # ① 다른 파일과 같은 그림이면 실패다. 07/08 이 md5 까지 같았던 사고가 이것이다.
    for other in sorted(OUT.glob("*.png")):
        if other.name in (tmp.name, dest_name):
            continue
        if md5(other) == new:
            print(f"★ {other.name} 과 md5 가 같다 — 같은 그림을 두 번 찍었다. 저장하지 않는다")
            tmp.unlink(missing_ok=True)
            return 1
    # ② 자기 이전 판과 같으면 화면이 하나도 안 바뀐 것이다. 재촬영이면 헛수고이므로 알린다.
    if dest.exists() and md5(dest) == new:
        print(f"※ 이전 {dest_name} 과 md5 가 같다 — 화면이 전혀 바뀌지 않았다(재촬영이면 확인 필요)")

    tmp.replace(dest)
    # ★ **이 장이 어느 커밋에서 나왔는지**를 지금 적는다. 회차 끝에 몰아 적으면, 작업 중
    #   커밋이 들어왔을 때 먼저 찍은 장까지 나중 커밋으로 적히게 된다(실측 사례 있음).
    _STAMPS[dest_name] = {"commit": git_head(), "at": _now_iso(), "md5": new,
                          "size": f"{w}x{h}"}
    print(f"합격 저장: {dest.name} · {w}x{h} · md5 {new[:12]}…")
    return 0


def shoot_landing(pg) -> int:
    """1번 `06_landing.png` — 소개(랜딩) 상단. 캡션은 '감으로 입찰하지 않습니다'."""
    print("\n[1] 06_landing.png — /landing")
    polite_goto(pg, "/landing")
    pg.wait_for_timeout(800)
    pg.evaluate("() => window.scrollTo(0, 0)")
    pg.wait_for_timeout(300)
    if not no_forbidden(pg):
        return 1
    if not labels_in_view(pg, ["데이터로 먼저", "전체 평균 오차"]):
        return 1
    return guard_and_save(pg, "06_landing.png")


def shoot_home(pg) -> int:
    """2번 `01_home.png` — 홈. 히어로의 '전체 평균 오차' 문구와 추천 카드가 함께 보여야 한다."""
    print("\n[2] 01_home.png — /")
    polite_goto(pg, "/")
    pg.wait_for_timeout(1200)          # 캐러셀 첫 장이 자리를 잡을 시간
    pg.evaluate("() => window.scrollTo(0, 0)")
    pg.wait_for_timeout(300)
    if not no_forbidden(pg):
        return 1
    if not labels_in_view(pg, ["전체 평균 오차", "최저매각가", "AI 예상낙찰가"]):
        return 1
    return guard_and_save(pg, "01_home.png")


def shoot_accuracy(pg) -> int:
    """3번 `02_accuracy.png` — /accuracy 의 **지표 타일 4개가 전부** 프레임 안에 들어와야 한다."""
    print("\n[3] 02_accuracy.png — /accuracy")
    polite_goto(pg, "/accuracy")
    pg.wait_for_timeout(800)
    pg.evaluate("() => window.scrollTo(0, 0)")
    pg.wait_for_timeout(300)
    if not no_forbidden(pg):
        return 1
    # 네 장 전부. '검증 표본'이 프레임 밖이면 캡션('오차까지 숨기지 않고 공개합니다')이
    # 그림을 앞서게 된다 — 표본 수가 없으면 공개했다고 말할 수 없다.
    if not labels_in_view(pg, ["전체 평균 오차", "±20% 이내 적중",
                               "±10% 이내 적중", "검증 표본"]):
        return 1
    return guard_and_save(pg, "02_accuracy.png")


# ──────────────────────────────────────────────────────────────────────────
# 대상 물건 고르기 — **아무거나 고르면 공허 통과다.**
# ──────────────────────────────────────────────────────────────────────────
# 제출 4·5·6·7번은 **한 물건**을 위아래로 찍는다. 스토어에서 네 장이 나란히 걸리므로
# 서로 다른 차가 나오면 이야기가 끊긴다. 그래서 물건 하나가 네 캡션을 **전부** 떠받쳐야 한다.
#
#   4번 캡션 '감정가·유찰이력·당시 출시가까지 한 화면에' → 셋이 다 렌더돼야 한다.
#        `당시 출시가` 는 출시가 자료가 있는 물건에만 나온다 — 없는 물건이 실제로 있다.
#   5번 캡션 '입찰 상한선까지 계산해 드립니다'          → `bidst.max_bid` 가 있어야 그려진다.
#   6번 캡션 '물건마다 한 장짜리 종합 분석 리포트'       → 리포트에 상한선 + **유형별** 실측 오차.
#        시세 미산정 물건은 리포트가 통째로 '생성할 수 없습니다' 한 줄로 떨어진다.
#   7번 캡션 '가격·시세신뢰도·사고·주행·잔존가치·유동성 6축'
#        → 육각형이 **6/6축 산출**이어야 한다. 5/6 이면 캡션이 세는 축 하나가 '미산출'로
#          그려져 캡션이 그림을 앞선다(9/22 판 `10_report_lower.png` 가 사고·상태 미산출이었다).
HERO_LISTS = ("/vehicles?bucket=review&sort=expected", "/vehicles?sort=sale_date")
HERO_SCAN_MAX = 10          # C.4: 탐색도 요청이다. 상한을 반드시 건다.

_HERO: dict | None = None   # 한 번 고르면 네 장이 같이 쓴다(같은 차를 다시 찾지 않는다)

_JS_DETAIL_FACTS = """() => {
    const t = document.body.innerText;
    return {
        title: document.title.slice(0, 70),
        appraisal: t.includes('감정가'),
        fails: t.includes('유찰횟수'),
        newcar: t.includes('당시 출시가'),
        cap: t.includes('입찰 상한선'),
        acc: t.includes('실측 오차'),
        sale: (t.match(/\\d{4}-\\d{2}-\\d{2}/) || [''])[0],
    };
}"""

_JS_REPORT_FACTS = """() => {
    const t = document.body.innerText;
    const m = t.match(/(\\d)\\/6축 산출/);
    return {
        cap: t.includes('입찰 상한선'),
        acc: t.includes('실측 오차'),
        axes: m ? Number(m[1]) : 0,
        sale: (t.match(/매각기일\\s*(\\d{4}-\\d{2}-\\d{2})/) || [null, ''])[1],
        case_no: (t.match(/\\d{4}타경\\d+/) || [''])[0],
    };
}"""


def hero_ok(d: dict, r: dict) -> list[str]:
    """네 캡션을 못 떠받치는 이유를 **전부** 모아 돌려준다(빈 목록이면 합격)."""
    why = []
    for key, label in (("appraisal", "감정가"), ("fails", "유찰횟수"),
                       ("newcar", "당시 출시가"), ("cap", "입찰 상한선")):
        if not d.get(key):
            why.append(f"상세에 '{label}' 없음")
    if not r.get("cap"):
        why.append("리포트에 '입찰 상한선' 없음")
    if not r.get("acc"):
        why.append("리포트에 유형별 '실측 오차' 없음")
    if r.get("axes") != 6:
        why.append(f"육각형 {r.get('axes')}/6축 — 7번 캡션이 세는 축이 미산출")
    return why


def pick_hero_vehicle(pg) -> dict | None:
    """네 캡션을 **전부** 떠받치는 물건을 고른다. 한 번 고르면 캐시한다.

    동점 처리: 합격한 후보 중 **매각기일이 가장 먼 물건**을 쓴다. 스토어 스크린샷은 영구
    공개물인데 기일은 지나가므로, 같은 조건이면 수명이 긴 쪽이 낫다.
    ⚠ 이건 **이번 회차의 동점 처리**이지 '영구 공개물 vs 지나가는 기일' 구조 문제의
    해법이 아니다 — 어느 물건을 찍어도 기일은 결국 지나간다. 결정은 오너 몫이다.
    """
    global _HERO
    if _HERO:
        return _HERO

    hrefs: list[str] = []
    for lst in HERO_LISTS:
        polite_goto(pg, lst)
        got = pg.evaluate("""() => [...document.querySelectorAll('a')]
            .map(a => a.getAttribute('href'))
            .filter(h => h && h.startsWith('/vehicle/') && h.split('/').length === 3)""")
        for h in got:
            if h not in hrefs:
                hrefs.append(h)
    print(f"\n[대상 선정] 후보 {len(hrefs)}개 중 최대 {HERO_SCAN_MAX}개를 본다")

    passed: list[dict] = []
    for h in hrefs[:HERO_SCAN_MAX]:
        polite_goto(pg, h)
        pg.wait_for_timeout(600)
        d = pg.evaluate(_JS_DETAIL_FACTS)
        polite_goto(pg, h + "/report")
        pg.wait_for_timeout(600)
        r = pg.evaluate(_JS_REPORT_FACTS)
        why = hero_ok(d, r)
        if why:
            print(f"   탈락 {h} — {'; '.join(why)}")
            continue
        print(f"   합격 {h} · {d['title']} · 매각기일 {r['sale']} · 육각 {r['axes']}/6")
        passed.append({"href": h, "title": d["title"], "sale": r["sale"],
                       "case_no": r["case_no"], "axes": r["axes"]})

    if not passed:
        print("★ 네 캡션을 전부 떠받치는 물건이 없다 — 촬영하지 않는다")
        return None
    _HERO = max(passed, key=lambda x: x["sale"] or "")
    print(f"→ 대상 확정: {_HERO['href']} · {_HERO['title']}"
          f" · 사건 {_HERO['case_no']} · 매각기일 {_HERO['sale']}"
          f" (합격 {len(passed)}개 중 기일이 가장 먼 물건)")
    return _HERO


def shoot_detail(pg) -> int:
    """4번 `07_detail.png` — 캡션 '감정가·유찰이력·당시 출시가까지 한 화면에'."""
    hero = pick_hero_vehicle(pg)
    if not hero:
        return 1
    print(f"\n[4] 07_detail.png — {hero['href']}")
    polite_goto(pg, hero["href"])
    pg.wait_for_timeout(900)
    if not no_forbidden(pg):
        return 1
    # 캡션이 약속한 셋이 **한 프레임 안에** 있어야 한다. 하나라도 밖이면 캡션이 그림을 앞선다.
    if not scroll_until(pg, ["감정가", "유찰횟수", "당시 출시가"],
                        [(None, "start"), ("물건 정보", "center"), ("감정가", "center")]):
        return 1
    return guard_and_save(pg, "07_detail.png")


def shoot_slide5(pg) -> int:
    """5번 `08_detail_lower.png` — 캡션 '입찰 상한선까지 계산해 드립니다'.

    `판정` 라벨도 함께 요구한다. `bb28dd8`·`ff87396` 이 칩의 색·글자를 한 원천으로 묶었는데,
    그 칩이 프레임 밖이면 이 장은 바뀐 것을 하나도 보여주지 못한다.
    """
    hero = pick_hero_vehicle(pg)
    if not hero:
        return 1
    print(f"\n[5] 08_detail_lower.png — {hero['href']}")
    polite_goto(pg, hero["href"])
    pg.wait_for_timeout(900)
    if not no_forbidden(pg):
        return 1
    # ⚠ 라벨을 `입찰 상한선`·`판정` 으로 잡으면 **본문 산문에도 걸린다** — 첫 판이 그랬다.
    #   `한줄 판정` 문단이 "입찰 상한선은 1,420만원입니다" 라고 말하고, `판정` 은 `사고판정`
    #   에도 들어 있다. 둘 다 통과시켜 놓고 정작 값 블록은 프레임 밖일 수 있다.
    #   그래서 **값 블록에만 있는 문구**로 가리킨다: `여기까지만` 은 상한선 숫자 바로 위에
    #   붙는 꼬리표이고, `산정 기준` 은 카드의 마지막 줄이다. 이 둘이 한 프레임에 있으면
    #   카드가 통째로 들어온 것이고, 같은 행 왼쪽에 있는 판정 칩도 따라 들어온다.
    if not scroll_until(pg, ["AI 낙찰 예측 분석", "여기까지만", "산정 기준"],
                        [("여기까지만", "center"), ("AI 낙찰 예측 분석", "start")]):
        return 1
    return guard_and_save(pg, "08_detail_lower.png")


def shoot_report(pg) -> int:
    """6번 `09_report.png` — 캡션 '물건마다 한 장짜리 종합 분석 리포트'.

    `입찰 상한선` 과 **유형별** `실측 오차` 를 **둘 다** 한 프레임에 요구한다.
    9/22 판은 여기에 `실측 평균오차`(전체평균) 가 박혀 있었다 — `no_forbidden()` 의
    RETIRED 검사가 그 표기를 만나면 저장 자체를 막는다.
    """
    hero = pick_hero_vehicle(pg)
    if not hero:
        return 1
    print(f"\n[6] 09_report.png — {hero['href']}/report")
    polite_goto(pg, hero["href"] + "/report")
    pg.wait_for_timeout(900)
    if not no_forbidden(pg):
        return 1
    if not scroll_until(pg, ["입찰 상한선", "실측 오차"],
                        [(None, "start"), ("한줄 판정", "start"), ("입찰 상한선", "end")]):
        return 1
    return guard_and_save(pg, "09_report.png")


# 블록을 **선택자로** 데려온다. `scrollIntoView` 는 부른 그 요소를 맞추므로, 문구('종합
# 프로필')로 잡으면 그 **작은 라벨**이 맞춰지고 블록은 밀려난다 — 실측: 라벨을 'start' 로
# 맞추니 `.hexa` 가 -22px(위 여백만큼) 로, 'center' 로 맞추니 448~1184px 로 삐져나갔다.
_JS_SCROLL_SEL = """(arg) => {
    const el = document.querySelector(arg.sel);
    if (!el) return false;
    el.scrollIntoView({block: arg.block || 'center'});
    return true;
}"""

# ⚠ 좌표 비교에 **1px 여유**를 둔다. `scrollIntoView({block:'start'})` 는 top 을 정확히 0
#   으로 놓지 않는다 — 실측 `-0.296875` 였고, `Math.round` 가 그걸 `-0` 으로 찍어
#   로그만 보면 통과해야 할 것이 떨어진 것처럼 보였다. 잘라내는 건 소수점 셋째자리다.
# ⚠ '미산출' 글자 수를 세지 않는다. `.hexa` 하단 **공식 설명**에 "자료가 없는 축은 …
#   미산출로 둡니다" 라는 안내문이 늘 들어 있어, 6/6 산출인 물건도 1건으로 잡혔다.
#   대신 제품이 스스로 세어 적는 `N/6축 산출` 을 읽는다.
# ⚠ 리포트 상단 **붙박이 도구모음**(상세로·인쇄·큰글씨·앵커 칩)에 가리는 것도 '안 보이는
#   것'이다. 그래서 위쪽 경계는 0 이 아니라 그 바의 아랫변(ceil)이다.
_JS_HEXA = """() => {
    const box = document.querySelector('.hexa');
    const fig = document.querySelector('.hx-fig') || document.querySelector('.hx-svg');
    if (!box || !fig) return {ok: false, why: '육각형 블록이 없다'};
    const r = box.getBoundingClientRect();
    const vh = document.documentElement.clientHeight;
    const tops = [...document.querySelectorAll('body *')].filter(e => {
        const p = getComputedStyle(e).position;
        if (p !== 'fixed' && p !== 'sticky') return false;
        const b = e.getBoundingClientRect();
        return b.top <= 2 && b.height > 20 && b.height < vh * 0.4;
    }).map(e => e.getBoundingClientRect().bottom);
    const ceil = tops.length ? Math.max(...tops) : 0;
    const t = box.innerText || '';
    const names = ['가격 메리트', '시세 신뢰도', '사고·상태', '주행 적정성', '잔존가치', '유동성'];
    return {ok: r.top >= ceil - 1 && r.bottom <= vh + 1,
            top: Math.round(r.top), bottom: Math.round(r.bottom),
            vh, ceil: Math.round(ceil), boxH: Math.round(r.height),
            axes: names.filter(n => t.includes(n)),
            avail: Number((t.match(/(\\d)\\/6축 산출/) || [null, 0])[1]),
            head: (t.split('\\n')[0] || '').slice(0, 60)};
}"""


def shoot_hexa(pg) -> int:
    """7번 `10_report_lower.png` — 캡션 '가격·시세신뢰도·사고·주행·잔존가치·유동성 6축'.

    캡션이 **여섯 축을 이름으로 센다.** 그러니 그림도 여섯을 다 그려야 한다 —
    육각형 도형이 프레임 안에 통째로 들어오고, 축 이름 6개가 다 있고, '미산출'이 없어야 한다.
    """
    hero = pick_hero_vehicle(pg)
    if not hero:
        return 1
    print(f"\n[7] 10_report_lower.png — {hero['href']}/report")
    polite_goto(pg, hero["href"] + "/report")
    pg.wait_for_timeout(900)
    if not no_forbidden(pg):
        return 1
    h = None
    for block in ("end", "center", "start"):
        pg.evaluate(_JS_SCROLL_SEL, {"sel": ".hexa", "block": block})
        pg.wait_for_timeout(700)
        h = pg.evaluate(_JS_HEXA)
        print(f"   지점 시도(block={block}): top={h.get('top')} bottom={h.get('bottom')}"
              f" / 뷰포트 {h.get('vh')} · 도구모음 아래 {h.get('ceil')}")
        if h.get("ok"):
            break
    if not h or not h.get("ok"):
        print(f"★ 육각형 블록이 프레임 안에 통째로 안 들어왔다 — {h}")
        return 1
    if len(h["axes"]) != 6:
        print(f"★ 축 이름이 6개가 아니다: {h['axes']} — 캡션이 여섯을 세는데 그림이 못 따라간다")
        return 1
    if h["avail"] != 6:
        print(f"★ 육각형이 {h['avail']}/6축만 산출됐다 — 캡션이 여섯을 이름으로 세는데"
              f" 그림에는 '미산출' 축이 있다. 대상 선정이 잘못됐다")
        return 1
    print(f"   화면 안 확인: 육각형 블록 top={h['top']} bottom={h['bottom']} / 뷰포트 {h['vh']}")
    print(f"   {h['head']} · 축 이름 {len(h['axes'])}개 · {h['avail']}/6축 산출")
    return guard_and_save(pg, "10_report_lower.png")


def shoot_calendar(pg) -> int:
    """8번 `05_calendar.png` — 캡션 '날짜별 매각기일과 지난달 낙찰 실적까지'.

    두 가지를 더 본다.
      ① `시세 확인` — `6b04e6d`(PANEL-17)에서 고친 **모수 표기**. 9/22 판은 `낙찰 100건`
         이라 적혀 있었는데 실제로는 낙찰 193건 중 100건이었다. 옛 표기로 찍히면 안 된다.
      ② '오늘' 강조 칸이 **정말 오늘**인가. 9/22 판은 22일이 강조된 채 이틀을 넘겼다.
         달력은 날짜가 곧 내용이라, 이 한 장만은 촬영일이 화면에 그대로 드러난다.
    """
    from datetime import date
    print("\n[8] 05_calendar.png — /calendar")
    polite_goto(pg, "/calendar")
    pg.wait_for_timeout(900)
    pg.evaluate("() => window.scrollTo(0, 0)")
    pg.wait_for_timeout(300)
    if not no_forbidden(pg):
        return 1
    today = pg.evaluate("""() => {
        const el = document.querySelector('.bg-primary\\\\/5');
        if (!el) return {day: null};
        const n = (el.innerText || '').trim().split(/\\s+/)[0];
        const r = el.getBoundingClientRect();
        return {day: Number(n), top: Math.round(r.top), bottom: Math.round(r.bottom)};
    }""")
    want = date.today().day
    if today.get("day") != want:
        print(f"★ '오늘' 강조가 {today.get('day')}일에 있다 — 오늘은 {want}일이다."
              f" 달력은 날짜가 곧 내용이라 이대로 찍으면 촬영일이 화면에 박힌다")
        return 1
    print(f"   '오늘' 강조 확인: {today['day']}일 (top={today['top']})")
    if not scroll_until(pg, ["이 달 매각기일", "지난달 낙찰 실적", "시세 확인"],
                        [(None, "start"), ("지난달 낙찰 실적", "start")]):
        return 1
    return guard_and_save(pg, "05_calendar.png")


def audit() -> int:
    """제출 8장을 **한 장도 빼지 않고** 대조한다. 일부만 보는 대조는 대조가 아니다.

    ⚠ 예전 판은 `OUT.glob("*.png")` 만 돌아서 **제출 8장이 다 있는지는 보지 않았다.**
    없는 장은 목록에 안 나오니 조용히 통과한다 — 그래서 목록을 코드가 직접 들고 있는다.
    """
    from PIL import Image
    files = sorted(OUT.glob("*.png"))
    if not files:
        print("screenshots/store 가 비었다")
        return 1
    seen: dict[str, list[str]] = {}
    for f in files:
        seen.setdefault(md5(f), []).append(f.name)

    man = read_manifest()
    print("\n=== 제출 8장 대조 (md5 · 규격 · 기준 커밋) ===")
    missing, bad_size, commits = [], [], set()
    for i, name in enumerate(SUBMIT, 1):
        p = OUT / name
        if not p.exists():
            missing.append(name)
            print(f"  ★ 없음  {i}번 {name}")
            continue
        w, h = Image.open(p).size
        spec = min(w, h) >= 1080 and max(w, h) >= 1920 and max(w, h) / min(w, h) <= 2
        if not spec:
            bad_size.append(f"{name}({w}x{h})")
        rec = man.get(name) or {}
        c = (rec.get("commit") or "")[:7] or "미기록"
        commits.add(c)
        print(f"  {'     ' if spec else '★ 규격'} {i}번 {name:<22} {md5(p)[:12]}…  {w}x{h}"
              f"  {c} {rec.get('at', '')}"
              f"{'' if spec else '  ← Play 세로 최소 1080x1920'}")
    if len(commits) > 1:
        print(f"\n  ※ 여덟 장이 **한 커밋에서 나오지 않았다**: {sorted(commits)}")
        print("     한 줄 HEAD 파일만 보면 전부 마지막 커밋에서 찍힌 것처럼 보인다(PANEL-45).")

    print("\n=== 같은 그림이 두 번 올라가지 않는가 (디렉터리 전체) ===")
    for h, names in seen.items():
        if len(names) > 1:
            print(f"  ★ 중복 {h[:12]}…  {', '.join(names)}")
    dup = [n for n in seen.values() if len(n) > 1]

    bad = bool(dup or missing or bad_size)
    print(f"\n  {'합격  제출 8장 모두 있고 규격·중복 이상 없음' if not bad else '★ 실패'}"
          f"{'' if not missing else f' · 없는 장 {len(missing)}'}"
          f"{'' if not dup else f' · 중복 {len(dup)}쌍'}"
          f"{'' if not bad_size else f' · 규격 미달 {bad_size}'}")
    return 1 if bad else 0


def git_head() -> str | None:
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              cwd=str(pathlib.Path(__file__).resolve().parents[1]),
                              check=True).stdout.strip()
    except Exception as e:                                   # noqa: BLE001
        print(f"※ HEAD 를 못 읽었다({e})")
        return None


MANIFEST = "HEAD.json"          # 장별 기준 커밋. 한 줄짜리 `HEAD` 로는 못 적는 것이 있다.


def read_manifest() -> dict:
    import json
    p = OUT / MANIFEST
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                        # noqa: BLE001
        return {}


def stamp_head(full: bool = True) -> None:
    """캡처의 기준 커밋을 남긴다(PANEL-45) — **장마다 따로** 남긴다.

    ⚠ 한 줄짜리 `HEAD` 파일은 **디렉터리 전체가 한 커밋에서 나왔을 때만** 참말이다.
    2026-09-24 실측: `01_home`·`02_accuracy`·`06_landing` 은 01:49(`7b78b2e`)에,
    나머지 다섯 장은 07:12~07:26(`931a134`)에 찍혔는데 — 그 사이 06:58·07:05 에
    커밋 둘이 들어왔다(둘 다 docs 전용) — 한 줄 파일은 **여덟 장 전부** 를 마지막 커밋에서
    찍은 것처럼 말한다. 찍는 사람과 보는 사람 사이에 커밋이 끼면 아무도 모른다는 게
    PANEL-45 인데, 한 줄 파일은 그걸 **덮어 버린다.**

    그래서 `HEAD.json` 에 장별로 `{커밋, 찍은 시각, md5}` 를 적고, 한 줄 `HEAD` 는
    (호환을 위해) 전 장 성공한 회차에서만 갱신한다.
    """
    import json
    h = git_head()
    OUT.mkdir(parents=True, exist_ok=True)
    man = read_manifest()
    man.update(_STAMPS)
    (OUT / MANIFEST).write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
    if h and full:
        (OUT / "HEAD").write_text(h + "\n", encoding="utf-8")
        print(f"기준 커밋 기록: screenshots/store/HEAD = {h}")
    elif not full:
        print("※ 실패한 장이 있어 한 줄 HEAD 는 갱신하지 않는다"
              " — 실패 회차의 커밋으로 덮으면 '이 커밋에서 찍었다'가 거짓이 된다")
    print(f"장별 기준 커밋: screenshots/store/{MANIFEST} ({len(man)}장)")


# 인자 이름 → 촬영 함수. `--all` 은 이 표를 그대로 돈다(표와 인자가 갈라지지 않게).
# 순서는 스토어 슬라이드 순서가 아니라 **이동 비용** 순이다 — 같은 페이지를 쓰는 장을 붙여
# 둬야 C.4 지연(7초)을 덜 쓴다. 제출 순서는 SUBMIT 이 들고 있다.
SHOTS = [
    ("landing", shoot_landing),
    ("home", shoot_home),
    ("accuracy", shoot_accuracy),
    ("calendar", shoot_calendar),
    ("detail", shoot_detail),
    ("slide5", shoot_slide5),
    ("report", shoot_report),
    ("hexa", shoot_hexa),
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="스토어 제출 스크린샷 촬영(자가 검사 포함)")
    ap.add_argument("--landing", action="store_true", help="1번 06_landing.png (소개)")
    ap.add_argument("--home", action="store_true", help="2번 01_home.png (홈·히어로)")
    ap.add_argument("--accuracy", action="store_true", help="3번 02_accuracy.png (적중률 타일 4개)")
    ap.add_argument("--detail", action="store_true", help="4번 07_detail.png (감정가·유찰·당시 출시가)")
    ap.add_argument("--slide5", action="store_true", help="5번 08_detail_lower.png (입찰 상한선)")
    ap.add_argument("--report", action="store_true", help="6번 09_report.png (리포트 상단)")
    ap.add_argument("--hexa", action="store_true", help="7번 10_report_lower.png (6축 육각형)")
    ap.add_argument("--calendar", action="store_true", help="8번 05_calendar.png (달력·지난달 실적)")
    ap.add_argument("--all", action="store_true", help="제출 8장 전부")
    ap.add_argument("--audit", action="store_true", help="촬영하지 않고 제출 8장을 대조")
    a = ap.parse_args(argv)

    if a.audit:
        return audit()

    todo = [(n, f) for n, f in SHOTS if a.all or getattr(a, n)]
    if not todo:
        ap.print_help()
        return 2

    failed: list[str] = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport=VIEW, device_scale_factor=DPR,
                            is_mobile=True, has_touch=True, extra_http_headers=PUBLIC)
        pg = ctx.new_page()
        for name, fn in todo:
            try:
                if fn(pg) != 0:
                    failed.append(name)
            except Exception as e:                            # noqa: BLE001
                print(f"★ {name} 촬영 중 예외: {e}")
                failed.append(name)
        b.close()

    if failed:
        print(f"\n★ 실패: {', '.join(failed)} — 해당 파일은 **이전 판 그대로**다")
    # 실패한 장이 있어도 **저장에 성공한 장의 기준 커밋은 적는다.** 장별로 적으므로
    # 실패한 장이 남의 커밋을 뒤집어쓸 일이 없다 — 그게 한 줄 HEAD 와 다른 점이다.
    stamp_head(full=not failed)
    rc_audit = audit()                   # 찍었으면 제출 8장 대조까지 하고 끝낸다
    return 1 if (failed or rc_audit) else 0


if __name__ == "__main__":
    raise SystemExit(main())
