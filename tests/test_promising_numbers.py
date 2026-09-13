"""유망 물건(홈)·즐겨찾기 모바일 카드의 세 숫자는 한 줄에 — 2026-09-14 사용자 실기기 제보.

'10,200,000'(8자리)이 가운데 칸(1/3 폭)에서 '10,200,00 / 0'으로 접혔다. 로컬 재현: 일반 모드도 320·360px 에서
8자리가 2줄, 큰글씨는 430px 까지, OS 글자 크기 130% 흉내에서는 전 폭에서 접혔다.
처방: 가운데 칸은 내용 폭(auto), 양옆은 남는 폭을 나누고(minmax(0,1fr)), 숫자는 줄바꿈 금지 + 크기는
rem 과 화면 폭(vw) 중 작은 쪽 — 확대 설정에서도 좁은 화면에서는 칸에 맞춘다.
"""
import re
from pathlib import Path

TPL = Path(__file__).resolve().parents[1] / "web" / "templates"
GRID = "grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]"
FLUID = "font-size:min(.875rem,3.3vw)"   # 미지원 브라우저 폴백 — 320px 큰글씨 격자(65/77/65px)에서 실측된 안전값. 지원 브라우저는 @container 가 3행 + .875rem 으로 바꾼다


def test_narrow_cards_switch_to_rows_by_rem_not_px():
    """검수: vw 상한만으로는 320px 에서 10.6px — 큰글씨 라벨(15px)보다 작았다. 조건은 폭이 아니라 rem 대비 폭이어야
    320px·큰글씨·OS 확대를 한 규칙이 덮는다."""
    css_in = (TPL.parent / "static" / "tailwind_input.css").read_text(encoding="utf-8")
    assert ".nc-pricegrid-host { container-type: inline-size; }" in css_in
    assert "@container (max-width: 19rem)" in css_in
    blk = css_in[css_in.index("@container (max-width: 19rem)"):]
    blk = blk[:blk.index("\n}\n") + 3]
    assert "grid-template-columns: minmax(0, 1fr) !important" in blk and "font-size: .875rem !important" in blk
    assert ".nc-pricegrid > .nc-price-hero { margin-inline: -.25rem; }" in blk, "알약 띠 패딩만큼 바깥으로 — 1의 자리 세로 정렬"
    built = (TPL.parent / "static" / "app.css").read_text(encoding="utf-8")
    assert "@container (max-width: 19rem)" in built and ".nc-pricegrid-host{container-type:inline-size}" in built.replace(" ", ""), "app.css 재빌드 누락"
    for name in ("dashboard.html", "watchlist.html"):
        src = (TPL / name).read_text(encoding="utf-8")
        assert "nc-pricegrid-host" in src and "nc-pricegrid grid" in src and src.count("nc-price font-mono") == 3, name
        # 3열일 때 정렬은 왼/가운데/오른 — 아래 minigauge 의 양끝과 맞춘다
        assert 'class="text-left"><div class="text-[10px] text-mut">최저매각가' in src and 'class="nc-price-hero text-center rounded-md bg-primary/5' in src


def _card_grid(src: str, label: str) -> str:
    i = src.index(GRID)
    return src[i:src.index("</div>\n      </div>", i) + 20] if "</div>\n      </div>" in src[i:] else src[i:i + 1500]


def test_dashboard_promising_numbers_cannot_wrap():
    src = (TPL / "dashboard.html").read_text(encoding="utf-8")
    assert GRID in src, "가운데 칸이 1/3 고정 폭이면 8자리가 접힌다"
    seg = _card_grid(src, "예상낙찰가")
    assert seg.count("whitespace-nowrap") >= 3 and seg.count(FLUID) >= 3, seg
    assert "grid-cols-3 gap-2 mt-2 text-right tabular-nums" not in src, "예전 3등분 격자가 남아 있다"
    assert "mt-2 text-right tabular-nums" not in src, "래퍼 text-right 는 왼쪽 숫자를 알약 쪽으로 밀어 게이지 왼끝과 어긋난다(검수)"


def test_watchlist_numbers_follow_the_same_recipe():
    src = (TPL / "watchlist.html").read_text(encoding="utf-8")
    assert GRID in src
    seg = _card_grid(src, "예상낙찰가")
    assert seg.count("whitespace-nowrap") >= 3 and seg.count(FLUID) >= 3, seg
    assert "grid-cols-3 gap-2 mt-2 text-right tabular-nums" not in src


def test_other_price_rows_use_the_same_fluid_cap():
    """목록 카드(320px·130%에서 카드 밖 20px)와 오늘의 추천 카드(간격 10px)도 같은 처방 — 확대 설정에서 두 금액이 한 줄."""
    v = (TPL / "vehicles.html").read_text(encoding="utf-8")
    assert 'whitespace-nowrap" style="font-size:min(1rem,4.6vw)">{{ v.min_sale_price|won }}' in v
    assert "font-size:min(1.125rem,5.2vw)" in v and "font-mono text-lg font-bold tnum" not in v
    d = (TPL / "dashboard.html").read_text(encoding="utf-8")
    assert 'style="font-size:min(.875rem,4vw)">{{ v.min_sale_price|won }}' in d
    assert 'leading-tight whitespace-nowrap" style="font-size:min(1.125rem,5.2vw)"' in d


def test_grid_class_exists_in_built_css():
    """새 Tailwind 임의값 클래스는 build:css 전엔 존재하지 않는다 — 빌드 산출물에 있어야 한다."""
    css = (TPL.parent / "static" / "app.css").read_text(encoding="utf-8").replace("\n", "")
    assert re.search(r"grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto\s+minmax\(0,\s*1fr\)", css), "app.css 재빌드 누락"
