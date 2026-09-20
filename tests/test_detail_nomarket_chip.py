"""상세 첫 화면의 칩이 목록·배너와 같은 말을 해야 한다.

2026-09-19 육안 검수에서 발견했다(측정으로는 안 잡힌다 — 가로 스크롤도 이탈도 0이었다).
목록에서는 배너와 카드 배지가 나란히 "동급 시세 없음"이라고 말하는데, 그 물건을 눌러
상세로 들어가면 제목 아래 첫 칩이 **"시세 신뢰도 낮음, 수동 검토"** 였다.

원인은 detail.html 이 `v.judgment` 를 그대로 찍었기 때문이다. judgment 는 DB 값이라
이번 버킷·판정 작업으로 바뀌지 않는다. 반면 '비교 대상이 없다'는 판정은 `bid_state()` 가
단일 진실원천이므로, 칩도 그 label 을 써야 화면끼리 어긋나지 않는다.

이 칩은 상세에서 **가장 먼저 읽히는 자리**다. 안내 블록을 아무리 잘 고쳐도 폴드 아래라
사용자는 먼저 틀린 말을 본다 — 그래서 본문이 아니라 여기를 고정한다.
"""
import re

import pytest
from starlette.testclient import TestClient

from tests.test_dashboard_link_parity import BT

_PUBLIC = {"x-forwarded-for": "203.0.113.7"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db, service
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "d.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    base = {"court": "군산지원", "item_no": "1", "year": 2017, "sale_date": "2999-01-01",
            "status": "완료", "fail_count": 0, "mileage_km": 674381, "photo_count": 3,
            "min_sale_price": 32_000_000, "appraisal_value": 32_000_000}
    db.upsert_vehicle(dict(base, id="NM_1", case_no="2026타경10418",
                           maker="대우자동차(타타대우)", model="삼부4.5톤극플러스카고트럭",
                           judgment="시세 신뢰도 낮음, 수동 검토"))
    # 대조군: 표본이 부족한 승용차 — 이쪽은 기존 문구가 그대로여야 한다
    db.upsert_vehicle(dict(base, id="LC_1", case_no="2026타경10419",
                           maker="현대", model="쏘나타", median_price=13_000_000,
                           market_confidence_label="낮음",
                           judgment="시세 신뢰도 낮음, 수동 검토"))
    import web.app as A
    return TestClient(A.app)


def _chip_area(html: str) -> str:
    """제목 아래 첫 칩 영역(연식 칩 ~ 사건번호 줄) 텍스트만 뽑는다."""
    i = html.find("년식")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html[max(0, i - 400):i + 600]))


def test_건설기계_상세_첫_칩이_동급시세_없음이라고_말한다(client):
    html = client.get("/vehicle/NM_1", headers=_PUBLIC).text
    area = _chip_area(html)
    assert "동급 시세 없음" in area, f"첫 칩이 목록과 다른 말을 한다: {area[:200]}"
    assert "시세 신뢰도 낮음, 수동 검토" not in area, (
        "표본이 부족하다는 뜻의 옛 문구가 남아 있다 — 곧 표본이 생길 것처럼 읽힌다")


def test_표본_부족한_승용차는_기존_문구를_유지한다(client):
    """차단이 과해지면 '고칠 수 있는 문제'까지 '어쩔 수 없는 것'으로 감춘다."""
    area = _chip_area(client.get("/vehicle/LC_1", headers=_PUBLIC).text)
    assert "동급 시세 없음" not in area, "승용차의 표본 부족은 성격이 다르다"


def test_상세_안내_블록도_같은_말을_한다(client):
    """칩과 본문이 서로 다른 말을 하면 그것대로 또 어긋난다."""
    body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", client.get("/vehicle/NM_1", headers=_PUBLIC).text))
    assert "동급으로 비교할 중고차가 없어" in body
    assert "자동 동급 매칭이 되지 않아" not in body, "옛 안내 문구가 함께 나온다"
