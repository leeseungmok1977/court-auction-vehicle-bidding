"""아이콘 폰트 서브셋 회귀 테스트 (2026-09-12 실기기 장애).

장애: 전체 Material Symbols 폰트가 3.2MB라 모든 페이지 preload가 느린 회선에서
`font-display: block`의 차단 구간(약 3초)을 넘겼고, 그 순간 리거처 이름이 글자로 노출됐다.
테스터 폰 20대 중 1대에서 'local_fire_department', 'homedirections_carcalendar_month'가
아이콘 자리에 그대로 찍혔다.

대책 2단:
 1) 실제 쓰는 아이콘만 서브셋(3.2MB → 61KB). 재생성: scripts/subset_icon_font.py
 2) base.html의 head 가드가 폰트 로드 전까지 ms-pending으로 감춤(CSS: visibility:hidden).

이 테스트가 지키는 것: **새 아이콘을 템플릿에 추가하고 서브셋을 다시 만들지 않으면**
그 아이콘은 글리프가 없어 리거처 이름이 글자로 나온다. 그걸 CI에서 먼저 잡는다.
"""
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WOFF2 = ROOT / "web" / "static" / "fonts" / "MaterialSymbolsOutlined.subset.woff2"
MANIFEST = ROOT / "web" / "static" / "fonts" / "MaterialSymbolsOutlined.subset.icons.txt"
BASE = ROOT / "web" / "templates" / "base.html"
APP_CSS = ROOT / "web" / "static" / "app.css"

sys.path.insert(0, str(ROOT))
from scripts.subset_icon_font import scan_templates, read_manifest  # noqa: E402


def test_scanner_finds_icons():
    """스캐너가 0개를 반환하면 이 테스트가 아무것도 지키지 못한다 — 가드."""
    used = scan_templates()
    assert len(used) >= 40, f"아이콘 스캔 결과가 비정상적으로 적다: {sorted(used)}"
    assert "search" in used and "directions_car" in used


def test_every_used_icon_is_in_the_subset():
    """템플릿이 쓰는 아이콘은 전부 서브셋에 들어 있어야 한다."""
    missing = sorted(scan_templates() - read_manifest())
    assert not missing, (
        "서브셋에 없는 아이콘이 템플릿에 추가됐다. 이대로 두면 실기기에서 아이콘 대신 "
        f"이름이 글자로 표시된다. `python scripts/subset_icon_font.py` 로 재생성할 것: {missing}")


def test_subset_font_exists_and_is_small():
    """3.2MB 전체 폰트를 되돌려 놓으면 장애가 재발한다."""
    assert WOFF2.exists(), f"서브셋 폰트가 없다: {WOFF2}"
    assert WOFF2.read_bytes()[:4] == b"wOF2", "woff2 파일이 아니다"
    size = WOFF2.stat().st_size
    assert size < 400_000, f"서브셋이 너무 크다({size:,}B) — 전체 폰트로 되돌아갔는지 확인"


def test_css_and_preload_point_at_the_subset():
    """@font-face와 preload가 서로 다른 파일을 가리키면 3.2MB를 또 받는다."""
    base = BASE.read_text(encoding="utf-8")
    assert 'href="/static/fonts/MaterialSymbolsOutlined.subset.woff2"' in base, \
        "base.html의 preload가 서브셋을 가리키지 않는다"
    assert "MaterialSymbolsOutlined.woff2" not in base, \
        "base.html이 아직 전체 폰트를 preload 한다"
    css = APP_CSS.read_text(encoding="utf-8")
    assert "MaterialSymbolsOutlined.subset.woff2" in css, \
        "빌드된 app.css의 @font-face가 서브셋을 가리키지 않는다 (npm run build:css 실행 필요)"


def test_font_guard_present():
    """폰트가 끝내 실패해도 리거처 이름이 새지 않도록 하는 가드."""
    base = BASE.read_text(encoding="utf-8")
    assert "ms-pending" in base, "base.html에 아이콘 폰트 가드 스크립트가 없다"
    css = APP_CSS.read_text(encoding="utf-8")
    assert re.search(r"ms-pending[^}]*visibility:\s*hidden", css), \
        "app.css에 ms-pending 숨김 규칙이 없다"
