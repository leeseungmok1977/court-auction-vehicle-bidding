# -*- coding: utf-8 -*-
"""`tools/store_overlay.py` — **캡션 폭 상한이 카드 폭에 연동돼 있다**를 잡아 둔다.

2026-09-24 실측(재검수 ④-1): 상한이 `CANVAS[0] - 2 * CAPTION_SIDE_MARGIN`(=968) 로 **캔버스 기준 고정**이었다.
1차(띠 220, 카드 956)에서는 캡션 최대 950 이라 우연히 카드 안이었고, 2차에서 띠 250 → 카드 939 로 좁아졌는데
상한은 그대로라 `10_report_lower` 캡션 951px 이 카드 밖으로 좌우 6px 씩 나갔다. 스크립트는 아무 말 없이 통과했다.

그래서 세 겹으로 막는다:
  1. 소스(ast): 캡션 상한이 `caption_max_width()` 를 거치고, 그 함수가 `card_geometry` 의 카드 폭에서 나온다.
     `CANVAS[0] - 2 * …` 꼴의 코드가 파일 어디에도 없다(독스트링은 사고 경위를 적으므로 검사에서 뺀다).
  2. 값: 띠 높이를 바꾸면 상한이 **따라 움직인다**(카드 폭 − 2×CARD_EDGE_GAP), 어느 높이에서도 카드 폭 이하.
  3. 실제 글꼴: 8장 캡션이 세트 공통 크기에서 전부 상한 안, 06 은 2줄(대시→줄바꿈, 오너 승인 항목).

변이 시험(보고서 3차 절에 기록): `band_max_w = caption_max_width(args.band_h)` 를 `CANVAS[0] - 2 * 56` 으로 되돌리면
1·3 이 빨간불이어야 한다.
"""
from __future__ import annotations

import ast
import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "tools" / "store_overlay.py"
TEXT = SRC.read_text(encoding="utf-8")
TREE = ast.parse(TEXT)


def _load():
    """모듈을 경로로 읽는다 — 임포트 부작용 없음(상수·함수 정의뿐, main 은 `__main__` 가드 안)."""
    spec = importlib.util.spec_from_file_location("store_overlay_under_test", SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _func(name: str) -> ast.FunctionDef:
    for node in TREE.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name}() 가 {SRC.name} 에 없다")


def _names_called(fn: ast.FunctionDef) -> set[str]:
    return {n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def _names_loaded(fn: ast.FunctionDef) -> set[str]:
    return {n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


# ── 1. 소스 ────────────────────────────────────────────────────────────────
def test_캡션_상한은_caption_max_width_를_거친다():
    main = _func("main")
    # band_max_w 에 대입되는 식이 caption_max_width(...) 호출이어야 한다
    assigns = [n for n in ast.walk(main) if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "band_max_w" for t in n.targets)]
    assert assigns, "main() 에 band_max_w 대입이 없다"
    for a in assigns:
        assert isinstance(a.value, ast.Call) and isinstance(a.value.func, ast.Name) \
            and a.value.func.id == "caption_max_width", \
            f"band_max_w 가 caption_max_width() 로 계산되지 않는다: {ast.unparse(a.value)}"


def test_caption_max_width_는_카드_폭에서_나온다():
    fn = _func("caption_max_width")
    assert "card_geometry" in _names_called(fn), "caption_max_width() 가 card_geometry() 를 부르지 않는다"
    assert "CARD_EDGE_GAP" in _names_loaded(fn), "caption_max_width() 가 CARD_EDGE_GAP 을 쓰지 않는다"
    assert "CANVAS" not in _names_loaded(fn), "caption_max_width() 가 캔버스 폭을 직접 본다 — 카드 폭이어야 한다"


def test_캔버스_폭_빼기_여백_꼴의_코드가_없다():
    """`CANVAS[0] - 2 * X` — 2차 사고의 그 식. 코드(ast)에서만 찾으므로 독스트링의 사고 경위 인용은 걸리지 않는다."""
    hits = []
    for n in ast.walk(TREE):
        if (isinstance(n, ast.BinOp) and isinstance(n.op, ast.Sub)
                and isinstance(n.left, ast.Subscript) and isinstance(n.left.value, ast.Name)
                and n.left.value.id == "CANVAS"):
            hits.append(ast.unparse(n))
    assert not hits, f"캔버스 폭 기준 계산이 남아 있다: {hits}"


def test_main_은_캡션이_카드보다_넓으면_종료코드_1():
    main = _func("main")
    src = ast.get_source_segment(TEXT, main)
    assert "caption_within_card" in src, "장별 caption_within_card 불리언을 기록하지 않는다"
    assert "violations" in src and "return 1 if (dup or violations)" in src, \
        "캡션이 카드보다 넓어도 종료코드가 0 이다 — 조용히 넘어간다"


# ── 2. 값 ─────────────────────────────────────────────────────────────────
def test_상한은_카드_폭을_따라_움직이고_항상_카드_안이다():
    mod = _load()
    for band_h in range(180, 385, 5):
        _, card_w, _, _ = mod.card_geometry(band_h)
        cap = mod.caption_max_width(band_h)
        assert cap == card_w - 2 * mod.CARD_EDGE_GAP
        assert cap < card_w
    # 띠가 높아지면 카드가 좁아지고 상한도 내려온다 — 2차 사고(220→250)가 바로 이 경우
    assert mod.caption_max_width(250) < mod.caption_max_width(220)
    assert mod.card_geometry(250)[1] == 939 and mod.caption_max_width(250) == 939 - 2 * mod.CARD_EDGE_GAP


def test_caption_fits_card():
    mod = _load()
    assert mod.caption_fits_card(951, 939) is False  # 2차 10_report_lower
    assert mod.caption_fits_card(910, 939) is True
    assert mod.caption_fits_card(939, 939) is True


# ── 3. 실제 글꼴 ───────────────────────────────────────────────────────────
_WOFF2 = ROOT / "web" / "static" / "fonts" / "Pretendard-Bold.woff2"


@pytest.mark.skipif(not _WOFF2.exists() or importlib.util.find_spec("fontTools") is None,
                    reason="리포 Pretendard woff2 또는 fontTools 없음")
def test_8장_캡션이_세트_공통_크기에서_전부_카드_안(tmp_path):
    mod = _load()
    mod.ensure_fonts(tmp_path / "_fonts")
    band_h = 250
    cap = mod.caption_max_width(band_h)
    _, card_w, _, _ = mod.card_geometry(band_h)
    size, per = mod.uniform_caption_size(list(mod.CAPTIONS.values()), cap)
    assert size >= 44
    for stem, text in mod.CAPTIONS.items():
        s, lines = mod.fit_caption(text, cap, sizes=[size])
        assert s == size, f"{stem}: 세트 공통 {size}px 에서 안 들어간다"
        for line in lines:
            w = mod.ink(mod.font("bold", size), line)[0]
            assert mod.caption_fits_card(w, cap), f"{stem}: 잉크 {w} > 상한 {cap}"
            assert mod.caption_fits_card(w, card_w)
    # 06 은 " — " 에서 2줄 — 대시를 줄바꿈이 대신한다(오너 승인 항목). 1줄이 되면 승인 항목의 전제가 바뀐 것
    assert len(mod.fit_caption(mod.CAPTIONS["06_landing"], cap, sizes=[size])[1]) == 2
