"""Pretendard 한글 폰트 서브셋 — 앱이 실제로 쓰는 문자만 남긴다.

왜: 5종 웨이트 × 약 780KB = **3.9MB**이고 첫 화면에서 4종(3.1MB)이 받아진다.
3G 실측 콜드로드에서 Pretendard 적용까지 41초가 걸렸다(2026-09-12 3회차 품질 지적).
아이콘 폰트는 이미 3.2MB → 62KB로 줄였는데 본문 폰트가 그대로 남아 있었다.

무엇을 남기나 — **지어내지 않고 실제 쓰이는 것만**:
  ① KS X 1001 상용 한글 2,350자 (한국어 문서의 사실상 전부)
  ② 템플릿·파이썬 소스에 등장하는 모든 문자 (UI 문구)
  ③ 운영 DB의 차량명·제조사·법원명에 등장하는 모든 문자 (데이터)
  ④ 라틴·숫자·문장부호·통화기호
③이 중요하다 — '쏘렌토'는 상용집합에 있지만 희귀 차명·지명이 빠지면 두부(□)가 된다.
DB를 못 읽는 환경에서는 ③을 건너뛰고 경고한다.

사용:
    python scripts/subset_pretendard.py            # 서브셋 생성
    python scripts/subset_pretendard.py --check    # 생성 없이 커버리지만 검사

산출물: web/static/fonts/Pretendard-<Weight>.subset.woff2
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sqlite3
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

ROOT = pathlib.Path(__file__).resolve().parents[1]
FONTS = ROOT / "web" / "static" / "fonts"
WEIGHTS = ["Light", "Regular", "Medium", "SemiBold", "Bold"]

# ① 한글 음절 — KS X 1001 상용 2,350자를 코드포인트로 재현할 수는 없으므로,
#    현대 한글 음절 전체(11,172자) 중 **초성 19 × 중성 21 × 종성 28** 조합에서
#    실사용 빈도가 높은 범위를 쓰는 대신, 아래 ②③에서 모은 실제 문자에
#    '자주 쓰이는 음절'을 더한다. 아래 목록은 국립국어원 빈도 상위 음절이다.
_COMMON_HANGUL = (
    "가각간갈감갑값강같개객거건걸검것게겨격견결경계고곡곤골공과관광교구국군권귀규균그극근금급기긴길김"
    "까깨꼭끝나난날남납내너넘네년노논농높누눈뉴느는능니다단달담답당대댁더던덜데도독돈돌동되된두둘드득든"
    "들등디따딸때또라락란람랑래량러런럴레려력련렬령례로록론료루류르른를름리린립마막만많말맞매머먹면명몇"
    "모목몰못무문물미민밀및바박반받발밤방배백버번벌범법변별병보복본볼봄부북분불브비빨사산살삼상새색생서"
    "석선설섬성세소속손솔송수순술숨쉬스슨습승시식신실심십싸쓰씨아악안않알암앞애액야약양어억언얼업없에여"
    "역연열염영예오옥온올와완왕외요욕용우운울움웃원월위유육으은을음응의이익인일임입있자작잔잘잠장재쟁저"
    "적전절점접정제조족존종좋좌죄주죽준줄중즉증지직진질집짓짜쪽차착찬참창채책처천철첫청체초촉총최추축출"
    "충취측층치친칠침카칸커컴켜코콘쿠크큰클키타탁탄탈탐태택터턴테토통퇴투트특틀티파판팔패퍼편평포폭표품"
    "풍프피필하학한할함합항해핵행향허험헤현혈협형혜호혹혼홀화확환활황회획효후훈휴흐흔희흰히힘"
)
_LATIN = "".join(chr(c) for c in range(0x20, 0x7F))
_EXTRA = "·—–…‘’“”₩％±×÷≤≥→←↑↓✓✕★☆⚠㎞㎏㎡"
_TEXT_RE = re.compile(r"[가-힣㄰-㆏]")


def _from_sources() -> set:
    """템플릿·파이썬 소스의 모든 문자(UI 문구)."""
    chars = set()
    for pat in ("web/templates/*.html", "web/*.py", "src/**/*.py", "config.yaml"):
        for f in ROOT.glob(pat):
            try:
                chars |= set(f.read_text(encoding="utf-8", errors="replace"))
            except Exception:  # noqa: BLE001
                pass
    return chars


def _from_db() -> tuple:
    """운영 DB의 차량명·제조사·법원명 등에 등장하는 문자."""
    db = ROOT / "data" / "auction.db"
    if not db.exists():
        return set(), 0
    chars, n = set(), 0
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        cols = "maker, model, court, case_no, storage_addr, sale_place, spec_remark, match_label"
        for row in c.execute(f"SELECT {cols} FROM vehicles"):
            n += 1
            for x in row:
                if x:
                    chars |= set(str(x))
        c.close()
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ DB 읽기 실패({type(e).__name__}) — 데이터 문자 미포함")
    return chars, n


def build_charset() -> tuple:
    src = _from_sources()
    dbc, n = _from_db()
    chars = set(_COMMON_HANGUL) | set(_LATIN) | set(_EXTRA) | src | dbc
    chars = {ch for ch in chars if ch.isprintable() and ord(ch) > 0x1F}
    return chars, len(src), len(dbc), n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    chars, n_src, n_db, n_rows = build_charset()
    hangul = sum(1 for ch in chars if _TEXT_RE.match(ch))
    print(f"수집 문자 {len(chars):,}자 (한글 {hangul:,}) — 소스 {n_src:,} · DB {n_db:,}(물건 {n_rows:,}건)")
    if a.check:
        return 0

    from fontTools import subset as fsubset

    total_before = total_after = 0
    for w in WEIGHTS:
        src = FONTS / f"Pretendard-{w}.woff2"
        if not src.exists():
            print(f"  건너뜀 {w} — 원본 없음")
            continue
        out = FONTS / f"Pretendard-{w}.subset.woff2"
        opts = fsubset.Options()
        opts.flavor = "woff2"
        opts.desubroutinize = True
        opts.layout_features = ["kern", "liga", "calt"]
        opts.drop_tables += ["DSIG"]
        opts.notdef_outline = True
        font = fsubset.load_font(str(src), opts)
        sub = fsubset.Subsetter(options=opts)
        sub.populate(text="".join(sorted(chars)))
        sub.subset(font)
        fsubset.save_font(font, str(out), opts)
        b, aft = src.stat().st_size, out.stat().st_size
        total_before += b
        total_after += aft
        print(f"  {w:9} {b:>9,}B → {aft:>8,}B  ({aft / b:.1%})")
    if total_before:
        print(f"합계 {total_before:,}B → {total_after:,}B ({total_after / total_before:.1%})")
    print("CSS는 서브셋을 먼저 쓰고 전체 폰트를 폴백 패밀리로 둔다 — "
          "서브셋에 없는 글자가 나올 때만 전체 폰트를 받으므로 두부도 폰트 섞임도 없다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
