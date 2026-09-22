"""홈 '유망 물건'의 차별화 — 두 추천 칸의 근거 순위 (사용자 결정 A안, 2026-09-14).

실측: 예전 유망 물건은 '입찰 검토 가능' 7대를 절감액(원) 순으로 보여줘 오늘의 추천 5대와 100% 겹치고,
절대액 정렬이라 고가차가 위로 갔고(아반떼 −40%가 카니발 −52% 위), 실사용 추천과는 무관했으며,
정렬 기준 부제는 모바일에서 숨겨져 있었다.

새 정의(service.promising_rows): 시세 신뢰도 '높음' + 오매칭 아님 + (재판매 검토가능 | 실사용 '지금 사면 이득'),
시세 대비 절감률 × 신뢰도 순. 홈은 캐러셀의 차를 빼고 상위 8, 목록(?picks=1)은 전부 — 홈 ⊂ 목록.
"""
import re

import pytest
from starlette.testclient import TestClient

from web import service
from tests.test_dashboard_link_parity import BT

_PUBLIC = {"x-forwarded-for": "203.0.113.7"}
BASE = {"court": "수원지방법원", "maker": "현대", "model": "쏘나타", "item_no": "1", "year": 2020,
        "sale_date": "2999-01-01", "status": "완료", "fail_count": 1, "market_confidence": 80,
        "market_confidence_label": "높음", "photo_count": 3}


def _rows():
    return [
        # 재판매 검토가능 — 시세 1,300만 · 최저 1,000만 → 예상 1,130만, 절감 13%
        dict(BASE, id="R1_1", case_no="2026타경31", judgment="입찰 검토 가능", min_sale_price=10_000_000,
             appraisal_value=12_000_000, median_price=13_000_000),
        # 실사용 '지금 사면 이득' — 시세 4,000만 · 최저 1,600만 → 예상 1,808만, 절감 55% (가장 위)
        dict(BASE, id="N1_1", case_no="2026타경32", judgment="유찰 대기", min_sale_price=16_000_000,
             appraisal_value=30_000_000, median_price=40_000_000),
        # 실사용 '싸게 낙찰되면 이득'(cheap) — 유망 아님
        dict(BASE, id="C1_1", case_no="2026타경33", judgment="유찰 대기", min_sale_price=28_000_000,
             appraisal_value=38_000_000, median_price=40_000_000),
        # 검토가능인데 신뢰도 보통 — 근거 약함
        dict(BASE, id="B1_1", case_no="2026타경34", judgment="입찰 검토 가능", min_sale_price=10_000_000,
             appraisal_value=12_000_000, median_price=13_000_000, market_confidence=60, market_confidence_label="보통"),
        # 검토가능인데 시세가 최저가의 4배 — 오매칭 의심
        dict(BASE, id="M1_1", case_no="2026타경35", judgment="입찰 검토 가능", min_sale_price=10_000_000,
             appraisal_value=12_000_000, median_price=40_000_000),
        # 검토가능인데 기일 지남
        dict(BASE, id="P1_1", case_no="2026타경36", judgment="입찰 검토 가능", min_sale_price=10_000_000,
             appraisal_value=12_000_000, median_price=13_000_000, sale_date="2020-01-01"),
        # 순수 유찰 대기(비쌈)
        dict(BASE, id="W1_1", case_no="2026타경37", judgment="유찰 대기", min_sale_price=39_000_000,
             appraisal_value=40_000_000, median_price=40_000_000),
    ]


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "p.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    # 오늘의 추천 캐러셀은 비운다(고정) — 유망 물건이 캐러셀 제외 규칙에 흔들리지 않게 따로 검사
    monkeypatch.setattr(service, "get_daily_picks", lambda n=5: [])
    db.init_db()
    for r in _rows():
        db.upsert_vehicle(r)
    import web.app as A
    return TestClient(A.app)


def test_promising_rows_take_both_kinds_and_rank_by_discount_times_confidence(client):
    rows = service.promising_rows(BT)
    ids = [r["id"] for r in rows]
    assert ids == ["N1_1", "R1_1"], ids                       # 실사용 now(55%) 가 재판매(13%) 위
    n1, r1 = rows
    assert n1["pick_kind"] == "now" and n1["pick_label"] == "지금 사면 이득" and n1["pick_disc"] == 55
    assert r1["pick_kind"] == "resale" and r1["pick_label"] == "되팔아도 남음" and 12 <= r1["pick_disc"] <= 14
    assert n1["pick_score"] > r1["pick_score"] > 0 and n1["expected_win"] and n1["use_tier"]["tier"] == "now"
    for bad in ("C1_1", "B1_1", "M1_1", "P1_1", "W1_1"):
        assert bad not in ids, f"{bad} 는 유망이 아니어야 한다"


def test_home_excludes_carousel_and_caps_at_eight(client):
    assert [r["id"] for r in service.promising_rows(BT, exclude_ids={"N1_1"})] == ["R1_1"]
    assert len(service.promising_rows(BT, limit=1)) == 1


def test_labels_match_the_two_cards():
    # 홈 '유망 물건'이 쓰는 두 축은 그대로다 — 문구가 카드와 갈리면 한 물건이 두 이름을 갖는다.
    assert service.PICK_LABELS["resale"] == "되팔아도 남음"
    assert service.PICK_LABELS["now"] == service.USE_TIER_LABELS["now"] == "지금 사면 이득"
    # 2026-09-22 홈 캐러셀을 두 축으로 넓히며 'cheap'이 들어왔다(유망 물건은 여전히 두 축만 쓴다).
    # 새 라벨도 **실사용 갈래와 같은 문구**여야 한다 — 화면마다 다른 이름을 붙이지 않는다.
    assert service.PICK_LABELS["cheap"] == service.USE_TIER_LABELS["cheap"], "실사용 갈래와 같은 문구"
    assert set(service.PICK_LABELS) == {"resale", "now", "cheap"}, "축이 말없이 늘지 않게 고정한다"


def test_dashboard_section_explains_itself_on_mobile_and_links_to_the_full_list(client):
    html = client.get("/", headers=_PUBLIC).text
    i = html.index("유망 물건")
    sec = html[i:i + 12000]
    assert 'href="/vehicles?picks=1"' in sec, "전체 보기는 같은 순위의 전체 목록으로"
    # 부제는 카드에 실제로 보이는 낱말로(검수: "절감률 × 신뢰도 순"은 독스트링 문장) — 홈·목록이 같은 문장(PICK_SUBTITLE)
    assert "".join(service.PICK_SUBTITLE) == "지금 입찰 추천·실사용 추천 가운데 시세보다 많이 싸고 시세 신뢰도가 높은 차부터"
    assert "시세보다 많이 싸고 시세 신뢰도가 높은" in sec and "오늘의 추천 5대 제외" in sec
    assert "절감률 × 시세 신뢰도" not in sec, "수식 표기는 카드에 없다"
    assert "hidden sm:inline\">— 신뢰도" not in html, "정렬 기준 부제가 모바일에서 숨겨져 있었다"
    for lbl in ("지금 사면 이득", "되팔아도 남음"):
        assert lbl in sec, lbl
    # 갈래 태그는 두 추천 카드와 같은 아이콘으로 이어진다(색만으로는 앰버=주의로 읽힘)
    assert "directions_car</span>지금 사면 이득" in sec and "check_circle</span>되팔아도 남음" in sec
    # 절감률은 기준이 보이는 자리(예상낙찰가 라벨)에, 우상단은 '● 높음'(상수) 대신 신뢰도 숫자
    assert re.search(r"예상낙찰가 <span[^>]*>· 시세보다</span> <b[^>]*>−55%</b>", sec) and re.search(r"· 시세보다</span> <b[^>]*>−1[234]%</b>", sec)
    assert re.search(r"신뢰 <b[^>]*>80</b>", sec)
    assert 'class="nc-gauge">' in sec, "게이지는 3열일 때만(3행에서 CSS 로 숨김) — 래퍼가 있어야 한다"
    assert sec.index("N1_1") < sec.index("R1_1"), "절감률 × 신뢰도 순"


def test_full_list_and_count_api_use_the_same_ranking(client):
    html = client.get("/vehicles?picks=1", headers=_PUBLIC).text
    m = re.search(r"총\s*<b[^>]*>([\d,]+)</b>\s*건", html)
    assert m and int(m.group(1)) == 2 == len(service.promising_rows(BT))
    assert html.index("N1_1") < html.index("R1_1")
    assert "유망 물건 2 ✕" in html and 'name="picks" value="1"' in html
    assert "되팔아도 남음" in html and "지금 사면 이득" in html and "예상낙찰가 · 시세보다 <b" in html and "−55%" in html
    assert "시세보다 많이 싸고 시세 신뢰도가 높은" in html, "목록 배너도 홈 부제와 같은 문장"
    assert client.get("/api/vehicles/count?picks=1", headers=_PUBLIC).json()["total"] == 2
