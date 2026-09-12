"""전문가 패널 1회차 P1 수정 회귀 테스트 (2026-09-12).

P1-1 리포트에 낙찰 전후 절차(보증금 10%·대금지급기한·몰수·앱 내 입찰 불가)가 없었다.
      인쇄해서 법정에 들고 가는 문서인데 절차가 빠져 확정적 손실을 부른다.
P1-2 리포트 9,600px에 고정 요소 0개, STOP RULE 배지 10px → 도달률 사실상 0.
P1-3 '상한가 적중률'은 재판매 지표인데 예측 적중률로 오독된다. /accuracy에선 이미 뺐다.
P1-4 /api/vehicles/count 와 /vehicles 의 모수가 달라 "1,320건" 알림 뒤 1,167건이 나왔다.
P1-5 hidden 속성이 Tailwind .flex에 져서 즐겨찾기 0 배지가 상시 노출됐다.
P1-7 /docs·/openapi.json·/run/status 가 무인증 공개라 관리자 엔드포인트 목록이 드러났다.
"""
import pathlib
import re

import pytest
from starlette.testclient import TestClient

from web import service

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    for i in range(3):
        db.upsert_vehicle({
            "id": f"Q{i}_1", "folder_key": f"Q{i}_1", "case_no": f"2026타경{900+i}", "item_no": "1",
            "court": "수원지방법원", "maker": "현대", "model": "그랜저", "year": 2018,
            "min_sale_price": 16_000_000, "appraisal_value": 20_000_000, "fail_count": 1,
            "sale_date": "2999-01-01", "median_price": 17_300_000, "upper_bid": 11_283_000,
            "market_confidence": 77, "market_confidence_label": "높음",
            "judgment": "유찰 대기", "status": "완료", "accident_grade": "none",
            "mileage_km": 134_000,
        })
    monkeypatch.setattr(service, "backtest_stats",
                        lambda *a, **k: {"discount_median": 0.74, "sample": 172, "mae_pct": 9.2,
                                         "upper_hit_rate": 0.20, "upper_n": 171, "history_n": 175,
                                         "within10_pct": 62, "within20_pct": 96, "pred_n": 172,
                                         "pred_pool": [], "n": 172})
    monkeypatch.setattr(service, "expected_band",
                        lambda *a, **k: {"price": 18_100_000, "lo": 16_800_000, "hi": 19_000_000,
                                         "premium": 1.129, "basis": {}})
    import web.app as A
    return TestClient(A.app)


# ── P1-1 낙찰 전후 절차 ──────────────────────────────────────
@pytest.mark.parametrize("must", [
    "낙찰 전후 절차", "입찰보증금", "대금지급기한", "보증금은 몰수",
    "이 앱에서는 입찰할 수 없습니다", "전액을 현금으로 준비",
])
def test_report_has_post_award_procedure(app_client, must):
    assert must in app_client.get("/vehicle/Q0_1/report").text


def test_report_shows_deposit_amount(app_client):
    """보증금은 최저매각가의 10% — 금액으로 찍혀야 법정에 들고 갈 수 있다."""
    html = app_client.get("/vehicle/Q0_1/report").text
    assert "1,600,000원" in html, "최저매각가 16,000,000의 10%가 금액으로 안 보인다"


# ── P1-2 도달성 ─────────────────────────────────────────────
def test_report_has_sticky_section_nav(app_client):
    html = app_client.get("/vehicle/Q0_1/report").text
    assert 'class="secnav' in html and "position:sticky" in html
    for anchor in ("#sec01", "#sec09", "#sec12"):
        assert anchor in html, f"{anchor} 점프 링크가 없다"
    for sec in ("sec01", "sec09", "sec12"):
        assert f'id="{sec}"' in html, f"{sec} 앵커 대상이 없다"


def test_stop_rule_badge_is_readable():
    css = (ROOT / "web" / "templates" / "report.html").read_text(encoding="utf-8")
    m = re.search(r"\.stop \.tg\{[^}]*font-size:(\d+)px", css)
    assert m and int(m.group(1)) >= 12, "STOP RULE 배지가 다시 작아졌다"


# ── P1-3 오해 지표 제거 ─────────────────────────────────────
def test_upper_hit_rate_tile_removed(app_client):
    """/accuracy 에서 뺀 지표가 리포트에만 남아 있으면 안 된다(같은 오해를 부른다)."""
    html = app_client.get("/vehicle/Q0_1/report").text
    assert "상한가 적중률" not in html
    acc = app_client.get("/accuracy").text
    assert "상한가 적중률" not in acc


# ── P1-4 모수 일치 ──────────────────────────────────────────
def test_count_api_matches_list_population(app_client):
    api = app_client.get("/api/vehicles/count").json()["total"]
    html = app_client.get("/vehicles").text
    m = re.search(r"총 <b[^>]*>([\d,]+)</b>건", html)
    assert m, "목록 총 건수를 찾지 못했다"
    assert api == int(m.group(1).replace(",", "")), "저장한 검색 건수와 목록 건수의 모수가 다르다"


# ── P1-5 hidden 우선순위 ────────────────────────────────────
def test_hidden_attribute_wins_over_utilities():
    css = (ROOT / "web" / "static" / "app.css").read_text(encoding="utf-8")
    assert "[hidden]{display:none!important}" in css.replace(" ", ""), \
        "hidden 속성이 .flex 유틸리티에 져서 0 배지가 다시 보인다"


# ── P1-7 관리자 표면 은닉 ───────────────────────────────────
@pytest.mark.parametrize("path", ["/docs", "/openapi.json", "/redoc"])
def test_api_docs_hidden_from_public(app_client, path):
    assert app_client.get(path).status_code == 404


def test_run_status_minimal_when_idle(app_client):
    d = app_client.get("/run/status").json()
    assert d.get("running") is False
    for leaked in ("run", "total", "upcoming", "pending", "ok", "wait"):
        assert leaked not in d, f"유휴 상태 공개 응답에 {leaked}가 들어 있다"
