"""큰글씨 토글과 목록 필터 접힘은 **양방향**으로 동기화돼야 한다.

3회차 조치로 목록 필터를 큰글씨에서만 접었다(`<details id="listFilter">` + 숨긴 summary).
처음 구현은 '접기'만 했고, 그래서 디자인 검수에서 차단 지적이 나왔다:

  큰글씨 ON 으로 목록 진입(필터 접힘) → 헤더에서 큰글씨를 끔 → nc-large 가 빠지면서
  summary 가 다시 .hidden 이 되는데 details 는 닫힌 채 남는다 →
  **검색창·판정/제조사/정렬·칩이 전부 사라지고 펼칠 손잡이도 없다.**

동기화 지점이 두 곳(페이지 로드 시 인라인 스크립트, 머무는 중 토글하는 ncToggleLarge)이라
한쪽만 남으면 같은 사고가 재발한다. 두 곳이 모두 살아 있는지 소스로 고정한다.
"""
from pathlib import Path

TPL = Path(__file__).resolve().parents[1] / "web" / "templates"
BASE = (TPL / "base.html").read_text(encoding="utf-8")
LIST = (TPL / "vehicles.html").read_text(encoding="utf-8")


def test_toggle_function_syncs_the_list_filter():
    """머무는 중 큰글씨를 끄면 필터가 다시 펼쳐져야 한다."""
    i = BASE.find("function ncToggleLarge()")
    assert i >= 0, "ncToggleLarge 가 사라졌다 — 큰글씨 토글 자체가 없다"
    body = BASE[i:i + 900]
    assert "listFilter" in body, (
        "ncToggleLarge 가 #listFilter 를 동기화하지 않는다 — 큰글씨를 끄면 "
        "닫힌 details 만 남아 검색·필터가 통째로 사라진다")
    assert "open" in body, "open 상태를 바꾸지 않는다"


def test_list_page_sets_open_in_both_directions():
    """페이지 로드 시에도 한쪽 방향만 정하면 안 된다."""
    i = LIST.find("getElementById('listFilter')")
    assert i >= 0, "목록의 필터 동기화 스크립트가 사라졌다"
    body = LIST[i:i + 300]
    assert "nc-large" in body, "큰글씨 여부를 보지 않는다"
    assert "d.open =" in body or "d.open=" in body, "open 을 명시적으로 정하지 않는다"
    assert "!document.documentElement.classList.contains" in body, (
        "접기만 하고 펼치기를 하지 않는다 — 큰글씨를 끈 뒤 목록으로 돌아오면 닫힌 채 남는다")


def test_summary_is_hidden_by_default_and_shown_only_in_large():
    """일반 모드 렌더는 한 픽셀도 바뀌면 안 된다 — summary 는 기본 숨김."""
    j = LIST.find('<details id="listFilter"')
    assert j >= 0, "필터가 details 가 아니다"
    head = LIST[j:j + 400]
    assert "open" in head, "details 가 기본 펼침이 아니다 — 일반 모드에서 필터가 접혀 보인다"
    assert 'class="hidden' in head, "summary 가 기본 숨김이 아니다 — 일반 모드에 요약줄이 나타난다"
    assert "html.nc-large #listFilter > summary{display:flex}" in BASE, (
        "큰글씨에서 요약줄을 보이게 하는 규칙이 없다 — 접혔는데 펼칠 손잡이가 없다")
