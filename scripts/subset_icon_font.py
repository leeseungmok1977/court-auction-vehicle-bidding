"""Material Symbols 아이콘 폰트 서브셋 재생성.

왜: 전체 아이콘 폰트는 **3.2MB**다. 모든 페이지가 preload 하므로 느린 회선에서는
`font-display: block`의 차단 구간(약 3초)을 넘겨버리고, 그 순간 리거처 이름이
**글자 그대로 노출**된다(2026-09-12 실기기: 'local_fire_department',
'homedirections_carcalendar_month'). 실제 쓰는 아이콘만 남기면 61KB로 줄어 문제가 사라진다.

리거처 기반 아이콘 폰트라 pyftsubset --text 로는 줄지 않는다(모든 리거처가 a-z로 구성되어
전부 살아남음). 그래서 Google Fonts API의 icon_names 서브셋을 받아 **자체 호스팅**한다.

사용:
    python scripts/subset_icon_font.py            # 템플릿 스캔 → 서브셋 재생성
    python scripts/subset_icon_font.py --check    # 재생성 없이 누락 아이콘만 보고(테스트용)

산출물:
    web/static/fonts/MaterialSymbolsOutlined.subset.woff2
    web/static/fonts/MaterialSymbolsOutlined.subset.icons.txt   (매니페스트 — 테스트가 대조)
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "web" / "templates"
FONT_DIR = ROOT / "web" / "static" / "fonts"
WOFF2 = FONT_DIR / "MaterialSymbolsOutlined.subset.woff2"
MANIFEST = FONT_DIR / "MaterialSymbolsOutlined.subset.icons.txt"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
AXES = "opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200"

NAME = r"[a-z][a-z0-9_]{2,40}"
# ① 스팬 안에 리터럴로 박힌 리거처:  <span class="material-symbols-outlined">search</span>
LITERAL = re.compile(r'material-symbols-outlined[^>]*>\s*(' + NAME + r')\s*<')
# ② 스팬 내용이 Jinja 식인 경우, 그 식 안의 따옴표 문자열:  >{{ 'thumb_up' if ... else 'lock' }}<
EXPR = re.compile(r'material-symbols-outlined[^>]*>\s*\{\{(.*?)\}\}\s*<', re.S)
QUOTED = re.compile(r"['\"](" + NAME + r")['\"]")
# 조건식의 '비교값'은 아이콘이 아니다:  {{ 'info' if verdict.tone=='caution' else 'lock' }}
#   → == / != 오른쪽 문자열을 먼저 지운 뒤 남은 문자열만 아이콘으로 본다.
COMPARAND = re.compile(r"(?:==|!=|in)\s*['\"][^'\"]*['\"]")
# ③ 아이콘을 인자로 받는 매크로 호출:  tab('/', 'home', ...) / navitem('/', 'dashboard', ...)
MACRO = re.compile(r"\b(?:tab|navitem)\(\s*['\"][^'\"]*['\"]\s*,\s*['\"](" + NAME + r")['\"]")


def scan_templates() -> set[str]:
    """템플릿에서 실제로 쓰는 아이콘 이름을 모은다."""
    names: set[str] = set()
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        names.update(LITERAL.findall(text))
        for expr in EXPR.findall(text):
            names.update(QUOTED.findall(COMPARAND.sub("", expr)))
        names.update(MACRO.findall(text))
    return names


def read_manifest() -> set[str]:
    if not MANIFEST.exists():
        return set()
    return {ln.strip() for ln in MANIFEST.read_text(encoding="utf-8").splitlines() if ln.strip()}


def fetch_subset(icons: list[str]) -> bytes:
    url = ("https://fonts.googleapis.com/css2?family="
           + urllib.parse.quote("Material Symbols Outlined") + ":" + AXES
           + "&icon_names=" + ",".join(icons))
    css = urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read().decode()
    m = re.search(r"url\((https://[^)]+)\)\s*format\('woff2'\)", css)
    if not m:
        raise SystemExit("woff2 URL 파싱 실패 — Google Fonts 응답 형식이 바뀌었을 수 있다:\n" + css[:400])
    data = urllib.request.urlopen(
        urllib.request.Request(m.group(1), headers={"User-Agent": UA}), timeout=180).read()
    if data[:4] != b"wOF2":
        raise SystemExit(f"woff2가 아님: {data[:8]!r}")
    return data


try:                       # Windows 기본 cp949에서 ⚠ 같은 문자가 UnicodeEncodeError를 낸다
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:          # noqa: BLE001 — 출력 인코딩 때문에 서브셋을 실패시키지 않는다
    pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="재생성 없이 누락만 보고")
    args = ap.parse_args()

    used = scan_templates()
    have = read_manifest()
    missing = sorted(used - have)

    print(f"템플릿 사용 {len(used)}개 · 매니페스트 {len(have)}개 · 누락 {len(missing)}개")
    if missing:
        print("누락:", ", ".join(missing))

    if args.check:
        return 1 if missing else 0
    if not missing and WOFF2.exists():
        print("이미 최신 — 재생성 불필요 (강제로 다시 만들려면 매니페스트를 지우고 실행)")
        return 0

    icons = sorted(used | have)          # 기존 것도 유지(런타임에만 쓰이는 아이콘 보호)
    data = fetch_subset(icons)
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    WOFF2.write_bytes(data)
    MANIFEST.write_text("\n".join(icons) + "\n", encoding="utf-8")
    print(f"생성 완료: {WOFF2.name} {len(data):,} bytes · 아이콘 {len(icons)}개")
    print("⚠ CSS/preload가 이 파일명을 가리키는지 확인하고, 배포 후 실기기에서 아이콘을 눈으로 확인할 것.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
