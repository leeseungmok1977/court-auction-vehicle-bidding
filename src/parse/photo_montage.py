"""차량 사진들을 번호 붙인 몽타주 1장으로 합쳐 비전 분류에 사용.

대법원 경매 사진은 GIF(팔레트)라 비전 판독 전 RGB로 변환한다. 물건당 사진 N장을
번호(1..N) 그리드로 합쳐 **한 장의 이미지**로 만들면, 비전 에이전트가 이미지 1장만
보고 '몇 번=정면/측면/실내'를 판정할 수 있어 판독 비용이 크게 준다.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from ..paths import DATA_DIR  # 배포 시 DATA_DIR 환경변수로 영속 볼륨 지정


def _font(size: int):
    for p in ("arial.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def list_photos(fk: str) -> list[str]:
    d = DATA_DIR / fk / "photos"
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_file())


def build_montage(fk: str, out_dir: Path, cell: int = 300, cols: int = 4,
                  max_photos: int = 16, name: Optional[str] = None) -> Optional[tuple]:
    """물건 fk의 사진들을 번호 그리드 PNG로 저장. (montage_path, [파일명들]) 반환.

    name 지정 시 파일명을 `{name}.png`로 저장(미지정 시 fk 기반). 워크플로 args를
    vid로 경로 재구성할 수 있게 vid를 name으로 넘긴다.
    """
    names = list_photos(fk)[:max_photos]
    if not names:
        return None
    d = DATA_DIR / fk / "photos"
    rows = (len(names) + cols - 1) // cols
    W, H = cols * cell, rows * cell
    canvas = Image.new("RGB", (W, H), (28, 30, 36))
    draw = ImageDraw.Draw(canvas)
    font = _font(46)
    kept: list[str] = []
    for i, n in enumerate(names):
        try:
            im = Image.open(d / n).convert("RGB")
        except Exception:  # noqa: BLE001
            continue
        im.thumbnail((cell - 10, cell - 10))
        x, y = (i % cols) * cell, (i // cols) * cell
        canvas.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
        label = str(i + 1)
        tw = draw.textlength(label, font=font)
        draw.rectangle([x + 3, y + 3, x + 3 + tw + 18, y + 3 + 56], fill=(83, 58, 253))
        draw.text((x + 12, y + 4), label, fill=(255, 255, 255), font=font)
        kept.append(n)
    if not kept:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = (name or fk).replace("/", "_")
    fp = out_dir / f"{stem}.png"
    canvas.save(fp, "PNG")
    return str(fp), kept
