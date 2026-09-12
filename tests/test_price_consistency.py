"""같은 물건의 '소매 시세'는 모든 화면에서 같은 값이어야 한다.

2026-09-12 2회차 패널(앱품질 지적 1) 실측: 2026타경70050(쏘렌토)의
  상세  → "소매 평균 시세 11,080,000 / 예상 절감 1,180,000원 −11%"
  리포트 → "소매 시세중앙값 9,670,000원 … 약 102%(시세 초과) … 입찰을 권하지 않습니다"
같은 물건에 "11% 싸다"와 "시세 초과·비권장"이 동시에 나왔다. 원인은 상세가
effective_median(엔카+케이카 블렌드)을, 리포트 템플릿이 원본 median_price를 쓴 것.

산정(plain_verdict·report_data)은 이미 블렌드를 쓰고 있었으므로, 리포트 템플릿만
어긋나 **판정문과 그 판정문이 인용하는 숫자가 서로 다른** 상태였다.
"""
import re

import pytest
from starlette.testclient import TestClient


# 테스트 DB에는 낙찰 실적이 없어 backtest_stats()가 비고, 그러면 예상낙찰가 자체가
# 산출되지 않아 가격 블록이 렌더되지 않는다(테스트가 공허해짐). 실측 기반 통계를 고정한다.
BT = {"discount_median": 0.74, "mae_pct": 9.2, "sample": 172,
      "min_premium_median": 1.13, "min_premium_by_fail": {"0": 1.20, "1": 1.13, "2+": 1.06},
      "min_premium_p25": 1.05, "min_premium_p75": 1.22}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db, service
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "p.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    # 케이카 표본이 충분해 블렌드가 실제로 발생하는 물건(eff_median != median_price)
    db.upsert_vehicle({
        "id": "P1_1", "folder_key": "P1_1", "case_no": "2026타경9", "item_no": "1",
        "court": "수원지방법원", "maker": "기아", "model": "쏘렌토", "year": 2019,
        "min_sale_price": 9000000, "appraisal_value": 11000000, "fail_count": 1,
        "sale_date": "2999-01-01", "status": "완료", "judgment": "유찰 대기",
        "median_price": 9670000, "market_confidence": 72, "market_confidence_label": "높음",
        "sample_count": 12, "kcar_median": 13000000, "kcar_sample": 9,
    })
    import web.app as A
    return TestClient(A.app)


_PUBLIC = {"x-forwarded-for": "203.0.113.7"}


def test_blend_actually_differs_from_raw():
    """픽스처가 실제로 블렌드를 발생시키는지 — 아니면 아래 테스트가 공허해진다."""
    from web import service
    v = {"median_price": 9670000, "kcar_median": 13000000, "kcar_sample": 9}
    assert service.effective_median(v) != v["median_price"]


def _won_numbers(text: str) -> set:
    # 끝에 를 쓰면 안 된다 — "10,840,000원"의 '원'은 \w로 취급돼 경계가 성립하지 않아
    # 금액을 통째로 놓친다(이 테스트를 처음 쓸 때 실제로 그렇게 헛돌았다).
    return {int(x.replace(",", "")) for x in
            re.findall(r"(?<!\d)\d{1,3}(?:,\d{3}){2,}(?!\d)", text)}


def test_report_quotes_the_same_median_as_the_calculation(client):
    """리포트가 인용하는 시세 = 판정에 쓰인 시세(effective_median)."""
    from web import db, service
    v = db.get_vehicle("P1_1")
    eff = service.effective_median(v)
    r = client.get("/vehicle/P1_1/report", headers=_PUBLIC)
    assert r.status_code == 200
    nums = _won_numbers(r.text)
    assert eff in nums, f"리포트에 산정 시세 {eff:,}가 없다"
    assert v["median_price"] not in nums, (
        f"리포트가 원본 시세 {v['median_price']:,}를 함께 노출 — 두 값이 섞이면 다시 어긋난다")


def test_detail_and_report_agree_on_median(client):
    """상세와 리포트가 같은 시세를 보여준다."""
    from web import db, service
    eff = service.effective_median(db.get_vehicle("P1_1"))
    detail = client.get("/vehicle/P1_1", headers=_PUBLIC).text
    report = client.get("/vehicle/P1_1/report", headers=_PUBLIC).text
    assert eff in _won_numbers(detail) and eff in _won_numbers(report)


def test_verdict_and_displayed_ratio_cannot_contradict(client):
    """'시세 초과·비권장'과 '−N% 싸다'가 동시에 나오면 안 된다."""
    from web import db, service
    v = db.get_vehicle("P1_1")
    bt = BT
    exp = service.expected_for(v, bt)
    eff = service.effective_median(v)
    report = client.get("/vehicle/P1_1/report", headers=_PUBLIC).text
    over = exp is not None and eff is not None and exp > eff
    assert ("입찰을 권하지 않습니다" in report) == over, (
        f"판정과 수치가 불일치: 예상 {exp}, 시세 {eff}, 비권장문구={'있음' if '입찰을 권하지 않습니다' in report else '없음'}")
