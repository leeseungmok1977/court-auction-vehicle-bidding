"""예상낙찰가 자동승급 할인모델 단위 테스트(순수 함수 — DB 불요)."""
from web import service


def test_model_key_normalizes_maker():
    # 제조사 표기 변형이 같은 키로 병합돼야 모델별 집계가 파편화되지 않음
    k1 = service._model_key({"maker": "현대자동차", "model": "그랜저(GRANDEUR)"})
    k2 = service._model_key({"maker": "(주)현대자동차", "model": "그랜저"})
    k3 = service._model_key({"maker": "현대", "model": "그랜저 IG "})
    assert k1 == k2 == "현대|그랜저"
    assert k3 == "현대|그랜저 IG"      # 세부 모델은 구분(공백만 정규화)


def test_discount_for_graduation_order():
    bt = {"discount_median": 0.78,
          "discount_by_fail": {"1": 0.90, "2plus": 0.77},
          "discount_by_model": {"기아|쏘렌토": 0.85}}
    # ① 모델별(표본 충분) 우선
    assert service.discount_for(bt, fail_count=2, model_key="기아|쏘렌토") == 0.85
    # ② 모델별 없으면 유찰버킷
    assert service.discount_for(bt, fail_count=1, model_key="현대|없는모델") == 0.90
    assert service.discount_for(bt, fail_count=3, model_key="현대|없는모델") == 0.77
    # ③ 둘 다 없으면 전역
    assert service.discount_for({"discount_median": 0.78}, fail_count=2) == 0.78


def test_expected_for_uses_model_then_fail():
    bt = {"discount_median": 0.78,
          "discount_by_fail": {"1": 0.90, "2plus": 0.77},
          "discount_by_model": {"기아|쏘렌토": 0.85}}
    v_model = {"median_price": 30_000_000, "fail_count": 2, "maker": "기아", "model": "쏘렌토(4세대)"}
    assert service.expected_for(v_model, bt) == 25_500_000          # 0.85 (모델별)
    v_fail = {"median_price": 30_000_000, "fail_count": 1, "maker": "기아", "model": "모닝"}
    assert service.expected_for(v_fail, bt) == 27_000_000           # 0.90 (유찰버킷)


def test_sale_snapshot_shape():
    v = {"id": "C|2026타경1|1", "court_code": "C", "case_no": "2026타경1", "item_no": "1",
         "maker": "기아", "model": "쏘렌토", "year": 2021, "median_price": 30_000_000,
         "fail_count": 1, "encar_total": 500}
    snap = service._sale_snapshot(v, 27_000_000)
    assert snap["id"] == "C|2026타경1|1" and snap["winning_price"] == 27_000_000
    assert snap["ratio"] == 0.9 and snap["model_key"] == "기아|쏘렌토"
