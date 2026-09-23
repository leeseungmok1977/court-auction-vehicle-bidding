#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""스토어 스크린샷 오버레이 시안 — 기준 월 캡슐(안 A) · 상단 캡션 띠(안 B-1 / B-2).

배경(오너 승인 2026-09-24): 스토어 스크린샷은 영구 공개물인데 화면 속 수치는 8시간 안에
움직인다(±9.5→±9.6%, 275→288건). 그림 안에 ``2026년 9월 기준`` 을 얹으면 값이 움직여도
"그때는 참이었다"가 성립한다. Play 콘솔에는 사용자에게 보이는 스크린샷별 캡션 필드가 없다
(alt text 는 스크린리더용) — 캡션이 보이려면 그림 안이 유일한 경로다.

원본 ``screenshots/store/NN_*.png`` 은 절대 덮어쓰지 않는다. 출력은 ``--out`` 아래(기본
``screenshots/store/overlay-draft/``) 에 ``NN_name__A.png`` · ``__B1.png`` · ``__B2.png`` 로 쓴다.

안 A   : 헤더 바로 아래 우측에 반투명 네이비 캡슐 ``2026년 9월 기준`` 만 얹는다(앱 UI 가림 없음 —
         캡슐 밑 픽셀이 균일한지 스크립트가 검사한다).
안 B-1 : 상단 띠(캡션 + 기준 월) + 스크린샷을 **비율 유지 축소**해 띠 아래 배치. 최종 1080×1920.
안 B-2 : 상단 띠 + 스크린샷을 **원크기**로 띠 아래 배치, 하단 띠 높이만큼 잘린다. 최종 1080×1920.

색은 코드에서 읽은 값만 쓴다(추측 금지):
  - 띠·캡슐 배경 NAVY  #0b142b  ← web/static/manifest.webmanifest theme_color / background_color
  - 캡션 글자   WHITE #ffffff
  - 기준 월 글자 CREAM #f5e9d4  ← tailwind.config.js colors.cream (brand-dark 와 짝인 강조 스톱)
폰트는 맑은 고딕(``C:/Windows/Fonts/malgun.ttf`` · ``malgunbd.ttf``)만 쓴다. 없으면 대체를 찾지
않고 종료한다.

사용::

    python tools/store_overlay.py                       # 02_accuracy·01_home·06_landing × A/B1/B2
    python tools/store_overlay.py --shots 01_home       # 한 장만
    python tools/store_overlay.py --variants A          # 한 안만
    python tools/store_overlay.py --out /tmp/x --no-thumbs

표준출력에 규격·md5·글자 크기·대비·잘린 픽셀을 마크다운 표로 낸다(보고서에 그대로 붙인다).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "screenshots" / "store"
OUT_DIR = SRC_DIR / "overlay-draft"

# docs/STORE_LISTING.md "제출할 8장 (오너 확정 2026-09-22)" 의 캡션 — 문구를 바꾸지 않는다.
CAPTIONS = {
    "06_landing": "감으로 입찰하지 않습니다 — 데이터로 먼저 봅니다",
    "01_home": "최저매각가와 AI 예상낙찰가를 한 카드에서",
    "02_accuracy": "오차까지 숨기지 않고 공개합니다",
    "07_detail": "감정가·유찰이력·당시 출시가까지 한 화면에",
    "08_detail_lower": "입찰 상한선까지 계산해 드립니다",
    "09_report": "물건마다 한 장짜리 종합 분석 리포트",
    "10_report_lower": "가격·시세신뢰도·사고·주행·잔존가치·유동성 6축",
    "05_calendar": "날짜별 매각기일과 지난달 낙찰 실적까지",
}
DEFAULT_SHOTS = ["02_accuracy", "01_home", "06_landing"]

# 색 — 출처는 모듈 docstring 참조
NAVY = (0x0B, 0x14, 0x2B)
WHITE = (0xFF, 0xFF, 0xFF)
CREAM = (0xF5, 0xE9, 0xD4)

FONT_REG = Path("C:/Windows/Fonts/malgun.ttf")
FONT_BOLD = Path("C:/Windows/Fonts/malgunbd.ttf")

CANVAS = (1080, 1920)  # Play 휴대전화 스크린샷 규격(원본과 동일)


# ── WCAG 대비 ─────────────────────────────────────────────────────────────────
def _lum(rgb):
    def ch(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def blend(fg, bg, alpha: float):
    return tuple(round(fg[i] * alpha + bg[i] * (1 - alpha)) for i in range(3))


# ── 글자 측정 ─────────────────────────────────────────────────────────────────
def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def ink(f: ImageFont.FreeTypeFont, text: str):
    """(w, h, left, top) — 실제 잉크 상자. draw 할 때 (x-left, y-top) 으로 넣으면 잉크가 (x,y)에 온다."""
    l, t, r, b = f.getbbox(text)
    return r - l, b - t, l, t


def fit_caption(text: str, max_w: int, sizes=range(54, 43, -1)):
    """한 줄로 들어가는 가장 큰 크기. ' — ' 가 있으면 그 자리에서 두 줄로 나눠도 된다.
    반환 (size, lines) — 못 맞추면 (None, None)."""
    for s in sizes:
        f = font(FONT_BOLD, s)
        if ink(f, text)[0] <= max_w:
            return s, [text]
        if " — " in text:
            a, b = text.split(" — ", 1)
            if max(ink(f, a)[0], ink(f, b)[0]) <= max_w:
                return s, [a, b]
    return None, None


def uniform_caption_size(texts, max_w):
    """세트 전체에 같은 크기를 쓴다 — 캐러셀에서 장마다 글자 크기가 다르면 튄다."""
    sizes = []
    for t in texts:
        s, _ = fit_caption(t, max_w)
        if s is None:
            raise SystemExit(f"캡션이 44px 에서도 안 들어간다: {t!r}")
        sizes.append(s)
    return min(sizes)


# ── 원본 검사(탭바·헤더) ─────────────────────────────────────────────────────────
LINE_TOKEN = (0xE3, 0xE8, 0xEE)  # tailwind.config.js colors.line — 앱 셸의 hairline 보더(탭바 상단선)


def find_tabbar_top(im: Image.Image) -> int | None:
    """하단 탭바 상단 보더 y. 화면 폭 전체가 `line` 토큰 색(±8)인 줄 두 칸 아래가 순백이면 탭바 상단선으로
    본다(01·02 실측: y=1806 이 (227,232,238), 1808 부터 흰색). 랜딩처럼 탭바가 없으면 None."""
    px = im.convert("RGB").load()
    W, H = im.size
    xs = range(8, W - 8, 4)

    def rowmean(y):
        acc = [0, 0, 0]
        n = 0
        for x in xs:
            p = px[x, y]
            acc[0] += p[0]
            acc[1] += p[1]
            acc[2] += p[2]
            n += 1
        return tuple(v / n for v in acc)

    for y in range(H - 60, H - 200, -1):
        m = rowmean(y)
        if all(abs(m[i] - LINE_TOKEN[i]) <= 8 for i in range(3)) and rowmean(y + 2) == (255.0, 255.0, 255.0):
            return y
    return None


def region_kind(im: Image.Image, box) -> tuple[str, int]:
    """캡슐 밑 픽셀이 무엇인가. 채널 최대 편차로 분류: ≤12 평면 / ≤40 그라데이션(글자·선 없음) / 그 이상 UI.
    글자·아이콘 가장자리는 편차가 100 을 훌쩍 넘는다(헤더 우측 실측 min 94 vs max 246)."""
    crop = im.convert("RGB").crop(box)
    ext = crop.getextrema()
    spread = max(hi - lo for lo, hi in ext)
    kind = "flat" if spread <= 12 else "gradient" if spread <= 40 else "UI"
    return kind, spread


# ── 오버레이 ─────────────────────────────────────────────────────────────────
def draw_capsule(src: Image.Image, basis: str, *, size: int, alpha: float, margin: int, top: int):
    """안 A — 헤더 아래 우측 캡슐. 반환 (이미지, 메트릭)."""
    W, H = src.size
    f = font(FONT_BOLD, size)
    tw, th, tl, tt = ink(f, basis)
    pad_x, pad_y = 26, 16
    cw, chh = tw + pad_x * 2, th + pad_y * 2
    x1 = W - margin
    x0 = x1 - cw
    y0 = top
    y1 = y0 + chh
    box = (x0, y0, x1, y1)

    kind, spread = region_kind(src, box)
    # 대비: 캡슐 밑 픽셀마다 합성한 뒤 흰 글자와의 최소 대비(가장 불리한 픽셀)
    under = src.convert("RGB").crop(box)
    worst = min(contrast(WHITE, blend(NAVY, p, alpha)) for p in set(under.getdata()))

    base = src.convert("RGBA")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius=chh // 2, fill=NAVY + (round(alpha * 255),))
    base.alpha_composite(layer)
    d = ImageDraw.Draw(base)
    d.text((x0 + pad_x - tl, y0 + pad_y - tt), basis, font=f, fill=WHITE)
    metrics = {
        "capsule_box": box,
        "capsule_size_px": (cw, chh),
        "font_px": size,
        "alpha": alpha,
        "under_kind": kind,  # flat / gradient / UI — UI 면 캡슐이 앱 화면을 가린 것
        "under_spread": spread,
        "contrast_min": round(worst, 2),
    }
    return base.convert("RGB"), metrics


def draw_band(caption_lines, basis, *, band_h: int, cap_size: int, basis_size: int):
    """상단 띠 이미지(1080×band_h) 와 메트릭."""
    W = CANVAS[0]
    band = Image.new("RGB", (W, band_h), NAVY)
    d = ImageDraw.Draw(band)
    fc = font(FONT_BOLD, cap_size)
    fb = font(FONT_REG, basis_size)
    line_h = round(cap_size * 1.28)
    gap = 14
    bw, bh, bl, bt = ink(fb, basis)
    block_h = line_h * len(caption_lines) + gap + bh
    y = (band_h - block_h) // 2
    widths = []
    for line in caption_lines:
        tw, th, tl, tt = ink(fc, line)
        widths.append(tw)
        # 줄 상자 안에서 세로 가운데
        d.text(((W - tw) // 2 - tl, y + (line_h - th) // 2 - tt), line, font=fc, fill=WHITE)
        y += line_h
    y += gap
    d.text(((W - bw) // 2 - bl, y - bt), basis, font=fb, fill=CREAM)
    metrics = {
        "band_h": band_h,
        "band_ratio_of_1920": round(band_h / CANVAS[1], 3),
        "caption_font_px": cap_size,
        "caption_lines": len(caption_lines),
        "caption_width_px": max(widths),
        "basis_font_px": basis_size,
        "contrast_caption": round(contrast(WHITE, NAVY), 2),
        "contrast_basis": round(contrast(CREAM, NAVY), 2),
    }
    return band, metrics


def compose_b1(src: Image.Image, band: Image.Image):
    """B-1: 비율 유지 축소해 띠 아래 배치. 남는 좌우는 띠 색."""
    W, H = CANVAS
    bh = band.height
    avail_h = H - bh
    scale = avail_h / src.height
    sw = round(src.width * scale)
    scaled = src.convert("RGB").resize((sw, avail_h), Image.LANCZOS)
    canvas = Image.new("RGB", CANVAS, NAVY)
    canvas.paste(band, (0, 0))
    x = (W - sw) // 2
    # 위쪽 모서리만 둥글게(카드처럼) — 아래는 캔버스 끝에 닿는다
    r = 28
    mask = Image.new("L", scaled.size, 255)
    md = ImageDraw.Draw(mask)
    md.rectangle((0, 0, sw, r), fill=0)
    md.rounded_rectangle((0, 0, sw - 1, r * 2), radius=r, fill=255)
    md.rectangle((0, r, sw, avail_h), fill=255)
    canvas.paste(scaled, (x, bh), mask)
    return canvas, {"scale": round(scale, 4), "scaled_size": (sw, avail_h), "side_gutter_px": x}


def compose_b2(src: Image.Image, band: Image.Image):
    """B-2: 원크기로 띠 아래 배치, 하단 band_h 픽셀이 잘린다."""
    W, H = CANVAS
    bh = band.height
    canvas = Image.new("RGB", CANVAS, NAVY)
    canvas.paste(band, (0, 0))
    canvas.paste(src.convert("RGB"), (0, bh))
    cropped_from = H - bh  # 원본에서 이 y 이후가 사라진다
    tab_top = find_tabbar_top(src)
    if tab_top is None:
        tab_cut = "탭바 없음"
    elif tab_top >= cropped_from:
        tab_cut = f"전부 잘림(탭바 y={tab_top}..{H - 1} 전체가 잘린 구간 안)"
    else:
        tab_cut = f"일부 잘림(탭바 상단 y={tab_top} 는 남고 아래 {H - cropped_from}px 잘림)"
    m = {
        "cropped_px": bh,
        "src_rows_kept": f"0..{cropped_from - 1}",
        "src_rows_lost": f"{cropped_from}..{H - 1}",
        "tabbar_top": tab_top,
        "tabbar_cut": tab_cut,
    }
    return canvas, m


# ── 유틸 ─────────────────────────────────────────────────────────────────
def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception as e:  # noqa: BLE001
        return f"unknown ({e})"


def save_png(im: Image.Image, p: Path):
    if im.size != CANVAS:
        raise SystemExit(f"규격 위반 {p.name}: {im.size} != {CANVAS}")
    im.convert("RGB").save(p, "PNG", optimize=False)  # 24-bit, alpha 없음(Play 요구)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=SRC_DIR)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--shots", nargs="+", default=DEFAULT_SHOTS, help="파일명 stem (예: 01_home)")
    ap.add_argument("--variants", nargs="+", default=["A", "B1", "B2"], choices=["A", "B1", "B2"])
    ap.add_argument("--basis", default="2026년 9월 기준")
    ap.add_argument("--band-h", type=int, default=220, help="띠 높이(px) — 180~240 권장")
    ap.add_argument("--basis-size", type=int, default=32, help="띠 안 기준 월 글자 크기")
    ap.add_argument("--capsule-size", type=int, default=34, help="캡슐 글자 크기")
    ap.add_argument("--capsule-alpha", type=float, default=0.90)
    ap.add_argument("--capsule-top", type=int, default=140, help="캡슐 상단 y (헤더 보더 126~127 아래)")
    ap.add_argument("--capsule-margin", type=int, default=32, help="캡슐 우측 여백")
    ap.add_argument("--no-thumbs", action="store_true", help="1/4 축소본·컨택트시트 생략")
    args = ap.parse_args(argv)
    # Windows 콘솔(cp949)은 '—' 같은 글자를 못 내보낸다 — 표는 보고서에 붙일 것이라 utf-8 로 낸다
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    for p in (FONT_REG, FONT_BOLD):
        if not p.exists():
            raise SystemExit(f"맑은 고딕 폰트가 없다: {p} — 대체 폰트를 쓰지 않는다. 사람에게 보고할 것.")
    if not (180 <= args.band_h <= 240):
        print(f"경고: 띠 높이 {args.band_h}px 는 180~240 범위 밖", file=sys.stderr)

    args.out.mkdir(parents=True, exist_ok=True)
    head = git_head()
    (args.out / "HEAD").write_text(head + "\n", encoding="utf-8")

    srcs = {}
    for stem in args.shots:
        p = args.src / f"{stem}.png"
        if not p.exists():
            raise SystemExit(f"원본 없음: {p}")
        if stem not in CAPTIONS:
            raise SystemExit(f"캡션 없음(STORE_LISTING 표에 없는 장): {stem}")
        im = Image.open(p)
        if im.size != CANVAS:
            raise SystemExit(f"원본 규격이 {CANVAS} 가 아니다: {p} {im.size}")
        srcs[stem] = (p, im)

    band_max_w = CANVAS[0] - 2 * 56
    cap_size = uniform_caption_size([CAPTIONS[s] for s in args.shots], band_max_w)

    rows = []
    metrics = {"HEAD": head, "basis": args.basis, "caption_font_px_uniform": cap_size, "shots": {}}
    thumbs = []
    for stem, (p, im) in srcs.items():
        src_md5 = md5(p)
        m_shot = {"src": str(p), "src_md5": src_md5, "caption": CAPTIONS[stem], "variants": {}}
        for v in args.variants:
            if v == "A":
                out_im, m = draw_capsule(
                    im, args.basis, size=args.capsule_size, alpha=args.capsule_alpha,
                    margin=args.capsule_margin, top=args.capsule_top,
                )
            else:
                _, lines = fit_caption(CAPTIONS[stem], band_max_w, sizes=[cap_size])
                band, mb = draw_band(lines, args.basis, band_h=args.band_h, cap_size=cap_size,
                                     basis_size=args.basis_size)
                out_im, mc = (compose_b1 if v == "B1" else compose_b2)(im, band)
                m = {**mb, **mc}
            outp = args.out / f"{stem}__{v}.png"
            save_png(out_im, outp)
            m["out"] = str(outp)
            m["out_md5"] = md5(outp)
            m["out_size"] = Image.open(outp).size
            m_shot["variants"][v] = m
            rows.append((outp.name, m["out_size"], m["out_md5"], src_md5))
            if not args.no_thumbs:
                thumbs.append((outp.name, out_im))
        metrics["shots"][stem] = m_shot

    # 1/4 축소본 + 컨택트시트 — 스토어 썸네일 가독성 판단용(눈으로 열어 본다)
    if thumbs:
        tdir = args.out / "thumb"
        tdir.mkdir(exist_ok=True)
        tw, th = CANVAS[0] // 4, CANVAS[1] // 4
        cols = len(args.variants)
        rows_n = (len(thumbs) + cols - 1) // cols
        gap = 12
        sheet = Image.new("RGB", (cols * tw + (cols + 1) * gap, rows_n * th + (rows_n + 1) * gap), (230, 230, 230))
        for i, (name, im) in enumerate(thumbs):
            t = im.resize((tw, th), Image.LANCZOS)
            t.save(tdir / name)
            r, c = divmod(i, cols)
            sheet.paste(t, (gap + c * (tw + gap), gap + r * (th + gap)))
        sheet.save(tdir / "_contact_sheet_quarter.png")
        metrics["thumb"] = {"size": (tw, th), "contact_sheet": str(tdir / "_contact_sheet_quarter.png")}

    (args.out / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2, default=str),
                                           encoding="utf-8")

    # md5 전부 상이한지(원본·출력 간)
    all_md5 = [r[2] for r in rows] + list({r[3] for r in rows})
    dup = len(all_md5) != len(set(all_md5))

    print(f"HEAD {head}")
    print(f"캡션 글자 크기(세트 공통) {cap_size}px · 띠 {args.band_h}px({args.band_h / 19.2:.1f}% of 1920) "
          f"· 기준 월 {args.basis_size}px · 캡슐 {args.capsule_size}px")
    print()
    print("| 출력 | 규격 | md5 | 원본 md5 |")
    print("|---|---|---|---|")
    for name, size, h, sh in rows:
        print(f"| `{name}` | {size[0]}×{size[1]} | `{h[:12]}…` | `{sh[:12]}…` |")
    print()
    print("md5 전부 상이:", "아니오 — 중복 있음!" if dup else "예")
    print()
    print(json.dumps(metrics, ensure_ascii=False, indent=2, default=str))
    return 1 if dup else 0


if __name__ == "__main__":
    sys.exit(main())
