"""지도 이미지에 **인쇄된** 보관장소 라벨을 읽는다 (Tesseract, 무네트워크).

노리는 것은 작은 지번이 아니라 **크게 인쇄된 라벨**이다:
    "보관장소 전주시 덕진구 덕진동1가 1420"
    "보관장소(호계동 1101번지)"
작은 지번(3~5px)은 대상이 아니다 — 그건 지적도 대조(다음 단계)의 몫이다.

## 서버 실측으로 정한 것

원본은 663px 안팎이고 라벨 글자는 12~16px다. 배율·PSM 조합을 다 돌려 봤다:

    이미지            x1 psm6      x2 psm11     x3 psm11
    전주(라벨상자)    주소 O(오타) 주소 O(정확) 주소 O(정확)
    호계동(괄호형)    라벨 O       라벨 X       라벨 O
    평택(빨간 글씨)   전부 X

→ **한 조합으로는 안 된다.** (x2, psm11)과 (x1, psm6)이 서로 다른 것을 잡아
  둘 다 돌리고 합친다. 배율을 더 올려도 정확도는 안 오르고 시간만 2배가 된다.

## 신뢰 규칙

OCR은 숫자를 틀린다("1101번지" → "11014 7)"). 그래서:
  · 시·도 + 시·군·구가 **둘 다** 파싱되고, 시군구가 앱이 이미 아는 실제 지명일 때만 채택
  · 채택해도 `storage_conf='추정'` — 화면에 '지도 표기'와 함께 낸다
  · 법원 상세·감정서 본문에서 온 값은 **절대 덮지 않는다**
  · 시가 없는 "호계동 1101번지" 같은 부분 주소는 채택하지 않는다
    (호계동은 안양·포항·양산에 다 있다 — 엉뚱한 도시로 보낼 수 있다)
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from typing import Optional

# 라벨 표기 — 법원마다 다르다. '본건'만 있는 것은 보관장소가 아닐 수 있어 제외한다
# (실측 2024타경51422: '본건' 지도는 채무자 주소를 가리키고 있었다).
LABEL_RE = re.compile(r"보\s*관\s*장\s*소")

_SIDO = (r"(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|"
         r"경북|경남|제주)(?:특별자치시|특별자치도|특별시|광역시|도)?")
ADDR_RE = re.compile(
    r"((?:" + _SIDO + r"\s*)?"
    r"([가-힣]{2,6}(?:시|군|구))(?:\s*[가-힣]{2,6}(?:시|군|구|읍|면))*"
    r"\s*[가-힣0-9]{1,12}(?:로|길|동|리|가)\s*[0-9]+(?:\s*-\s*[0-9]+)?(?:\s*번지)?)")

_PASSES = ((2, 11), (1, 6))      # (배율, PSM) — 서로 다른 것을 잡는다
_TIMEOUT = 120


def _tesseract(path: str, scale: int, psm: int) -> str:
    """확대해서 OCR. 실패하면 빈 문자열(한 장 때문에 배치가 멈추면 안 된다)."""
    tmp = ""
    try:
        from PIL import Image
        with Image.open(path) as im:
            im = im.convert("L")
            if scale != 1:
                im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS)
            fd, tmp = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            im.save(tmp)
        r = subprocess.run(
            ["tesseract", tmp, "stdout", "-l", "kor+eng", "--psm", str(psm), "--dpi", "300"],
            capture_output=True, timeout=_TIMEOUT)
        return " ".join(r.stdout.decode("utf-8", "replace").split())
    except Exception:            # noqa: BLE001 — 깨진 파일·타임아웃·미설치 모두 여기로
        return ""
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def parse_label(text: str, known_gu: Optional[set] = None) -> dict:
    """OCR 결과 한 덩어리에서 '보관장소' 라벨과 그 주소를 뽑는다.

    `known_gu` 를 주면 시·군·구 이름이 실제로 존재하는지 대조한다 — OCR이 지명을
    통째로 지어내는 것을 막는다. 앱이 이미 가진 주소들로 만들면 외부 요청이 없다.
    """
    out = {"label": False, "addr": "", "why": ""}
    if not text:
        out["why"] = "인식된 글자 없음"
        return out
    m = LABEL_RE.search(text)
    if not m:
        out["why"] = "보관장소 라벨 없음"
        return out
    out["label"] = True
    near = text[m.start():m.start() + 110]     # 라벨 주변만 본다
    a = ADDR_RE.search(near)
    if not a:
        out["why"] = "라벨은 있으나 시·군·구가 없는 주소"
        return out
    addr, gu = " ".join(a.group(1).split()), a.group(2)
    if known_gu and gu not in known_gu:
        out["why"] = f"'{gu}' 는 아는 시·군·구가 아님"
        return out
    out["addr"] = re.sub(r"\s*-\s*", "-", addr)
    return out


def read_storage_label(path: str, known_gu: Optional[set] = None) -> dict:
    """지도 한 장에서 보관장소 주소를 읽는다. 두 조합을 모두 돌려 합친다."""
    best = {"label": False, "addr": "", "why": "읽지 못함"}
    for scale, psm in _PASSES:
        got = parse_label(_tesseract(path, scale, psm), known_gu)
        if got["addr"]:
            return got
        if got["label"] and not best["label"]:
            best = got
    return best
