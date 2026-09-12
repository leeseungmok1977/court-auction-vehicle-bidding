"""'뒤로' 버튼 내비게이션 회귀 테스트 (2026-09-12 사용자 제보).

증상: 목록 → 상세 → 리포트 → '상세로' → 상세 에서 '뒤로'를 누르면 **리포트로** 갔다.
      '뒤로'는 차량목록으로 가는 버튼인데 브라우저 히스토리를 무조건 되감고 있었다.

수정 두 곳:
  · 상세의 `_goBack` — 직전 화면이 목록일 때만 되감고, 아니면 back_url(마지막 목록)로 이동.
  · 리포트의 `_reportBack` — 링크 이동 대신 히스토리를 되감아 스택을 늘리지 않는다.

실제 히스토리 동작은 브라우저에서만 재현되므로(이 테스트는 가드가 살아 있는지만 지킨다)
배포 후 Playwright로 목록→상세→리포트→상세→뒤로 흐름을 별도 확인했다.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = (ROOT / "web" / "templates" / "base.html").read_text(encoding="utf-8")
REPORT = (ROOT / "web" / "templates" / "report.html").read_text(encoding="utf-8")
DETAIL = (ROOT / "web" / "templates" / "detail.html").read_text(encoding="utf-8")


def test_detail_back_button_wired():
    assert 'onclick="return _goBack(event)"' in DETAIL
    assert "{{ back_url or '/vehicles' }}" in DETAIL, "폴백 목록 URL이 사라졌다"


def test_go_back_only_rewinds_from_a_list_page():
    """무조건 history.back() 하면 리포트로 되돌아가는 루프가 재발한다."""
    m = re.search(r"window\._goBack = function\(e\)\{(.*?)\n\};", BASE, re.S)
    assert m, "_goBack 정의를 찾지 못했다"
    body = m.group(1)
    assert "vehicles|calendar|courts|watchlist" in body, \
        "직전 화면이 목록인지 확인하는 가드가 없다 — 무조건 되감으면 루프가 난다"
    assert "history.back()" in body
    # 가드보다 먼저 되감으면 의미가 없다
    assert body.index("vehicles|calendar") < body.index("history.back()")


def test_report_back_does_not_grow_history():
    assert 'onclick="return _reportBack(event)"' in REPORT
    m = re.search(r"function _reportBack\(e\)\{(.*?)\n\}", REPORT, re.S)
    assert m, "_reportBack 정의를 찾지 못했다"
    body = m.group(1)
    assert "history.back()" in body, "링크로만 이동하면 히스토리가 쌓여 '뒤로'가 리포트로 간다"
    assert "window.opener" in body, "새 창으로 열린 경우 창을 닫는 처리가 사라졌다"
    assert "/report$" in body, "직전이 리포트가 아닌 상세인지 확인하는 조건이 없다"


def test_section_chips_do_not_push_history():
    """해시 링크는 누를 때마다 방문 기록이 쌓인다.

    칩을 몇 번 누르고 '상세로'를 누르면 차량정보가 아니라 직전에 눌렀던 섹션으로
    되돌아갔다(2026-09-12 제보). scrollIntoView + replaceState로 주소만 갱신한다.
    """
    assert "replaceState" in REPORT, "섹션칩이 여전히 히스토리를 쌓는다"
    assert "scrollIntoView" in REPORT
    assert ".secnav a[href^=" in REPORT, "섹션칩 클릭 가로채기 셀렉터가 없다"


def test_report_back_has_fallback():
    """되감기가 어긋나도 '상세로'는 반드시 그 차량 화면으로 가야 한다."""
    assert "location.href = target" in REPORT, "되감기 실패 시 직접 이동하는 안전망이 없다"


def test_report_toolbar_is_sticky():
    """11화면 문서에서 스크롤을 내려도 '상세로'·인쇄·섹션칩이 남아야 한다."""
    m = re.search(r"\.rtop\{([^}]*)\}", REPORT)
    assert m and "position:sticky" in m.group(1), "상단 바가 고정되지 않는다"
    assert 'class="rtop no-print"' in REPORT
    assert re.search(r"\.sec-head\[id\]\{scroll-margin-top:\d+px\}", REPORT), \
        "고정 바에 제목이 가리지 않도록 하는 scroll-margin이 없다"
