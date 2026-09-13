"""18인 패널 3차(2026-09-13)에서 나온 P0 두 건.

두 건 다 **이번 회차에 내가 만든 것**이다.

P0-1  §01 "동급 실낙찰 평균은 67%" ↔ §05 "이 차종의 법원 실낙찰 기록이 아직 확보되지
      않았습니다" — 세 개 조 전부, 6명 이상이 심각도 5로 지적. 확인해 보니 그 67%는
      `discount_for` 가 내는 **유찰버킷 전국 통계**(표본 76건)이지 '동급'이 아니었다.
      오래된 오표기인데, 05에 정직한 빈 상태를 넣으면서 모순으로 드러났다.
      게다가 이 물건의 예상낙찰가는 그 비율이 아니라 최저매각가×프리미엄으로 냈으므로
      "67%면 2,362만원이어야 하는데 왜 3,880만원이냐"는 반문까지 나왔다.

P0-2  큰글씨에서 가격 스펙트럼 라벨이 겹쳐 판독 불가 — 60·70대 3명 심각도 5.
      원인 둘: (a) 겹침 회피 스크립트의 행 높이가 28px 고정이라 25% 커진 라벨을 못 담음
      (b) 판정 라벨(.sp-blabel)은 .sp-pin 이 아니라 회피 대상 밖인데, 내가 넘침을
      막겠다고 white-space:normal 을 걸어 4줄로 늘어나며 트랙과 '3392'를 덮었다.
      **내 측정은 '넘침 0건'이라 통과시켰다 — 넘침 검사는 겹침을 못 잡는다.**
"""
import pathlib
import re

import pytest
from starlette.testclient import TestClient

from web import service
from tests.test_render_smoke import BT, _BASE

TPL = pathlib.Path(__file__).resolve().parents[1] / "web" / "templates"
_PUBLIC = {"x-forwarded-for": "203.0.113.7"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "p0.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: _BT2)
    db.init_db()
    db.upsert_vehicle({**_BASE, "id": "P0_1", "folder_key": "P0_1",
                       "case_no": "2026타경9101", "judgment": "유찰 대기",
                       "fail_count": 2, "min_sale_price": 33_920_000,
                       "appraisal_value": 53_000_000, "median_price": 35_250_000,
                       "upper_bid": 23_777_500, "market_confidence": 52,
                       "market_confidence_label": "보통", "sample_count": 32,
                       "market_cv": 0.18, "analyzed_at": "2026-09-05 10:00:00",
                       "match_label": "동급 (연식±1·주행±30%)·동세대"})
    import web.app as A
    return TestClient(A.app)


# 유찰버킷 통계는 있고 모델별 통계는 없는 상태 — 실제 프로덕션과 같은 조건
_BT2 = {**BT, "discount_by_fail": {"1": 0.90, "2plus": 0.681},
        "discount_n_by_fail": {"1": 96, "2plus": 76},
        "discount_by_model": {}, "discount_n_by_model": {}, "won_total": 175}


# ── P0-1 ─────────────────────────────────────────────────────────
def test_discount_basis_matches_what_discount_for_actually_picked():
    """라벨과 값이 다른 단계를 가리키면 그게 곧 거짓 표기다 — 판정 순서가 같아야 한다."""
    got = service.discount_basis(_BT2, fail_count=2, model_key="")
    assert got["kind"] == "fail" and got["n"] == 76
    assert "전국" in got["label"] and "동급" not in got["label"]
    assert service.discount_for(_BT2, 2, "") == 0.681

    # 모델별 표본이 쌓이면 그때는 진짜 '동급'이다
    bt_m = {**_BT2, "discount_by_model": {"쏘나타": 0.74},
            "discount_n_by_model": {"쏘나타": 11}}
    m = service.discount_basis(bt_m, fail_count=2, model_key="쏘나타")
    assert m["kind"] == "model" and m["n"] == 11 and "같은 차종" in m["label"]
    assert service.discount_for(bt_m, 2, "쏘나타") == 0.74


def test_report_never_calls_a_national_average_a_same_class_average(client):
    html = client.get("/vehicle/P0_1/report", headers=_PUBLIC).text
    assert "동급 실낙찰 평균" not in html, "전국 통계를 '동급'이라고 부른다"
    assert "유찰 2회 이상 물건의 전국 평균 낙찰률" in html
    assert "표본 76건" in html, "몇 건짜리 통계인지 밝혀야 한다"
    assert "이 차종의 실낙찰 기록이 아니라 전국 통계" in html


def test_report_says_the_rate_was_not_what_produced_the_price(client):
    """'67%면 2,362만원인데 왜 3,880만원이냐'는 반문이 나왔다 — 산출 경로를 밝힌다."""
    html = client.get("/vehicle/P0_1/report", headers=_PUBLIC).text
    assert "최저매각가 기준" in html


def test_section01_and_section05_do_not_contradict(client):
    """05가 '실낙찰 기록 없음'이라고 말할 때 01이 '동급 평균'을 인용하면 안 된다."""
    html = client.get("/vehicle/P0_1/report", headers=_PUBLIC).text
    if "법원 실낙찰 기록이 아직 확보되지 않았습니다" in html:
        s01 = html[html.index('id="sec01"'):html.index('id="sec02"')]
        assert "동급" not in s01 or "전국 통계" in s01, \
            "05는 동급 기록이 없다는데 01이 동급 평균을 말한다"


# ── P0-2 ─────────────────────────────────────────────────────────
def test_spectrum_row_height_is_measured_not_hardcoded():
    """28px 고정이라 큰글씨에서 라벨 25% 커지며 행끼리 겹쳤다."""
    src = (TPL / "report.html").read_text(encoding="utf-8")
    i = src.index("var ROWH")
    seg = src[i:i + 900]
    assert "offsetHeight" in seg or "it.h" in seg, "행 높이를 실측하지 않는다"
    assert re.search(r"ROWH\s*=\s*Math\.max", seg), "실측값을 ROWH 에 반영하지 않는다"


def test_verdict_label_is_clamped_not_wrapped():
    """줄바꿈으로 넘침을 막으면 세로로 늘어나 트랙·핀을 덮는다(그래서 판독 불가가 됐다)."""
    src = (TPL / "report.html").read_text(encoding="utf-8")
    assert "html.nc-large .sp-blabel{white-space:normal" not in src, \
        "판정 라벨에 줄바꿈을 허용하면 4줄로 늘어나 숫자를 덮는다"
    i = src.index("var bl = ")
    seg = src[i:i + 700]
    assert "Math.min(Math.max(" in seg, "가로 클램프가 없다 — 트랙 밖으로 나간다"
    assert "sp-foot" in seg, "판정 라벨 높이만큼 아래 여백을 잡지 않는다"


def test_spectrum_script_finds_the_foot_element():
    """`.sp-foot` 은 `.sp-wrap` 이 아니라 `.spectrum` 의 자식 — 셀렉터가 틀리면 조용히 null."""
    src = (TPL / "report.html").read_text(encoding="utf-8")
    i = src.index("var foot = ")
    assert "closest" in src[max(0, i - 300):i + 120], \
        "parentElement 로 .sp-foot 을 찾으면 못 찾는다(구조상 한 단계 위)"


# ── 디자인 검수 반영분 ────────────────────────────────────────────
def test_spectrum_pin_is_named_for_what_it_actually_is(client):
    """스펙트럼의 '상한'은 입찰 상한선(2,860만)이 아니라 재판매 상한가(2,378만)다.
    같은 리포트 위쪽이 '입찰 상한선'을 크게 말하고 있어 같은 것으로 읽힌다 —
    P0-1(전국 통계를 '동급'이라 부른 것)과 정확히 같은 실패 유형이다(디자인 검수)."""
    html = client.get("/vehicle/P0_1/report", headers=_PUBLIC).text
    i = html.index('class="sp-labels"')
    pins = html[i:html.index("sp-track", i)]
    assert "재판매 상한가" in pins and "재판매상한" in pins
    assert ">상한<" not in pins, "'상한' 두 글자는 입찰 상한선으로 오독된다"


def test_connector_does_not_pierce_a_lower_label():
    """상위 행 연결선이 아래 행 숫자를 관통했다(실측: 선 3525 → '3392')."""
    src = (TPL / "report.html").read_text(encoding="utf-8")
    assert "o.row <= it.row" in src, "상위 행 연결선 회피 로직이 없다"
    assert "PAD = 5" in src, "우측 여백 1px 은 '잘렸나' 싶게 만든다"


def test_section01_has_one_bold_not_three(client):
    """볼드 3개면 눈이 먼저 닿는 게 하필 오독을 유발한 그 숫자(68%)였다."""
    html = client.get("/vehicle/P0_1/report", headers=_PUBLIC).text
    i = html.index("전국 평균 낙찰률")
    seg = html[i - 200:html.index("</li>", i)]
    assert seg.count("<b>") <= 1, f"볼드가 {seg.count('<b>')}개 — 강조가 흩어진다"
    assert "전국 통계" in seg
    assert "· 유찰 2회 반영" not in html, "바로 위 문장과 중복된 고아 줄"
