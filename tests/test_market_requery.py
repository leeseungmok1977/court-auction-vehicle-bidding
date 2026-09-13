"""엔카 분류 계층 수정 + 0표본 재조회 — 2026-09-13 승인 조회(14회) 실측에 기반한 회귀 고정.

실측: 엔카는 ModelGroup(차종) → Model(세대) 두 단계다. ModelGroup '렉스턴' 안에 '렉스턴 스포츠'(픽업)·
'렉스턴 스포츠 칸'·'G4 렉스턴'(SUV)·'올 뉴 렉스턴'이 같이 있어 **차형을 Model 명으로 걸러야** 한다.
2022 렉스턴(SUV, 감정 3,100만)이 픽업 6건으로 2,145만에 평가된 실제 사고가 있었다(2025타경53276_1).

그리고 물건은 수집 시점에 한 번만 시세를 조회했고 실패(0건)는 영구였다 — 매핑을 고쳐도 기존 물건에
적용되지 않았다. requery_missing_market 이 일일 갱신에서 소량씩 다시 묻는다(런당 상한·7일 백오프).
"""
from datetime import date, timedelta
from pathlib import Path

from src.collect import encar
from src.parse.market_match import summarize
from web import service

ROOT = Path(__file__).resolve().parents[1]


def _l(model, price_manwon, year=2020, km=60000, fuel="디젤", _i=[0]):
    _i[0] += 1
    return {"platform": "encar", "id": _i[0], "model": model, "badge": "디젤 2.2 4WD", "fuel": fuel,
            "form_year": year, "mileage_km": km, "price_won": price_manwon * 10000}


REXTON_POOL = ([_l("G4 렉스턴", p) for p in (2500, 2600, 2700, 2800, 2900, 3000)]
               + [_l("렉스턴 스포츠", p) for p in (1900, 2000, 2100, 2200, 2300, 2400)]
               + [_l("렉스턴 스포츠 칸", p) for p in (2350, 2450, 2550)])   # 가격이 겹치면 dedupe 가 재등록으로 지운다


def test_model_hint_splits_pickup_suv_and_ev():
    assert encar.model_hint("렉스턴") == ([], ["스포츠"])
    assert encar.model_hint("G4 렉스턴") == ([], ["스포츠"])
    assert encar.model_hint("렉스턴스포츠") == (["스포츠"], ["칸"])
    assert encar.model_hint("렉스턴스포츠 칸") == (["스포츠", "칸"], [])
    assert encar.model_hint("코란도") == ([], ["스포츠"])
    assert encar.model_hint("코란도스포츠") == (["스포츠"], ["칸"])
    assert encar.model_hint("레이EV") == (["EV"], [])
    assert encar.model_hint("레이") == ([], ["EV"])
    assert encar.model_hint("쏘나타") == ([], [])
    assert encar.model_hint(None) == ([], [])


def test_suv_is_not_priced_with_pickups():
    """실제 사고의 재현: 렉스턴(SUV) 물건이 그룹 '렉스턴' 결과에서 픽업을 한 건도 쓰면 안 된다."""
    inc, exc = encar.model_hint("렉스턴")
    st = summarize(REXTON_POOL, form_year=2020, mileage_km=60000, model_include=inc, model_exclude=exc)
    assert st.sample_count == 6 and st.median_price == 27_500_000
    assert all("스포츠" not in c["model"] for c in st.comps)


def test_pickup_and_khan_are_separated():
    inc, exc = encar.model_hint("렉스턴스포츠")
    st = summarize(REXTON_POOL, form_year=2020, mileage_km=60000, model_include=inc, model_exclude=exc)
    assert st.sample_count == 6 and st.median_price == 21_500_000
    assert "·스포츠" in st.match_label and all("칸" not in c["model"] for c in st.comps)
    inc, exc = encar.model_hint("렉스턴스포츠 칸")
    st = summarize(REXTON_POOL, form_year=2020, mileage_km=60000, model_include=inc, model_exclude=exc)
    assert st.sample_count == 3 and st.median_price == 24_500_000 and "·스포츠/칸" in st.match_label


def test_body_unconfirmed_caps_confidence_instead_of_guessing():
    """포함 표본이 3건 미만이면 차형을 확인한 척하지 않는다 — 신뢰도 '낮음' 상한 + 라벨."""
    pool = [_l("G4 렉스턴", p) for p in (2500, 2600, 2700, 2800, 2900, 3000)] + [_l("렉스턴 스포츠", 2000)]
    st = summarize(pool, form_year=2020, mileage_km=60000, model_include=["스포츠"], model_exclude=["칸"])
    assert st.median_price is not None
    assert st.confidence <= 40 and "차형 미확인" in st.match_label


def test_exclusion_can_empty_the_pool_honestly():
    """SUV 요청인데 픽업뿐이면 '동급 표본 없음' — 픽업 값을 대신 쓰지 않는다."""
    pool = [_l("렉스턴 스포츠", p) for p in (1900, 2000, 2100, 2200, 2300)]
    st = summarize(pool, form_year=2020, mileage_km=60000, model_include=[], model_exclude=["스포츠"])
    assert st.sample_count == 0 and st.median_price is None and st.match_label == "동급 표본 없음"


def test_summarize_without_hint_still_works():
    st = summarize(REXTON_POOL, form_year=2020, mileage_km=60000)
    assert st.median_price is not None and st.sample_count > 0


def test_both_encar_call_sites_pass_the_body_hint():
    """수집(_analyze_item)과 재교정(recompute_all_market) 둘 다 힌트를 넘겨야 한다 — 한쪽만 고치면 재교정이 되돌린다."""
    src = (ROOT / "web" / "service.py").read_text(encoding="utf-8")
    assert src.count("model_include=_mh[0], model_exclude=_mh[1]") >= 2
    assert src.count("encar.model_hint(") >= 2


def test_requery_targets_only_zero_sample_upcoming_and_backs_off(monkeypatch):
    today = date.today()
    old = (today - timedelta(days=10)).isoformat() + " 06:10:00"
    fresh = (today - timedelta(days=1)).isoformat() + " 06:10:00"
    base = {"median_price": None, "status": "완료", "year": 2020, "maker": "KGM(구,쌍용)",
            "model": "렉스턴스포츠", "analyzed_at": old, "sale_date": "2026-09-20", "auction_result": None}
    rows = [
        {**base, "id": "a", "sample_count": 0},                                    # 대상
        {**base, "id": "b", "sample_count": 12, "median_price": 20_000_000},        # 시세 있음 → 제외
        {**base, "id": "c", "sample_count": 0, "maker": "TADANO", "model": "기중기"},  # 매핑 없음 → 제외
        {**base, "id": "d", "sample_count": 0, "analyzed_at": fresh},                # 최근 조회 → 백오프
        {**base, "id": "e", "sample_count": 0, "status": "종결"},                    # 종결 → 제외
        {**base, "id": "f", "sample_count": 0, "median_price": 15_000_000,
         "market_platform": "동급참조"},                                              # 참조 시세 있음 → 제외
        {**base, "id": "g", "sample_count": 0, "sale_date": "2026-09-15"},           # 대상 — 기일 임박이 먼저
    ]
    monkeypatch.setattr(service.db, "list_vehicles", lambda **k: rows)
    captured = {}

    def fake_recompute(run_id=None, finalize=True, targets=None, max_requests=None):
        captured["targets"] = targets
        captured["max"] = max_requests
        captured["run_id"] = run_id
        return 0

    monkeypatch.setattr(service, "recompute_all_market", fake_recompute)
    monkeypatch.setattr(service.encar, "search",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("테스트에서 외부 요청 금지")))
    out = service.requery_missing_market(within_days=30, max_requests=5, min_age_days=7)
    assert [v["id"] for v in captured["targets"]] == ["g", "a"]
    assert captured["max"] == 5 and captured["run_id"] is None
    assert out == {"targets": 2, "updated": 0}
    # 백오프 0일이면 최근 조회분도 다시 묻는다(운영 1회성 실행용)
    service.requery_missing_market(within_days=30, max_requests=5, min_age_days=0)
    assert [v["id"] for v in captured["targets"]] == ["g", "a", "d"]


def test_recompute_caps_groups_and_keeps_target_order(monkeypatch):
    """그룹 1개 = 엔카 요청 1회. 상한에 잘려도 호출자가 정한 순서(기일 임박)가 먼저 조회돼야 한다(C.4-1)."""
    calls = []

    def fake_search(es, manufacturer, model_group, car_type="Y", year_from=None, year_to=None,
                    limit=100, offset=0, premium=False):
        calls.append(model_group)
        return {"count": 0, "results": [], "q": ""}

    monkeypatch.setattr(service.encar, "search", fake_search)
    monkeypatch.setattr(service.encar, "new_session", lambda: None)
    monkeypatch.setattr(service.kcar, "new_session", lambda: None)   # 케이카도 외부 요청 금지
    monkeypatch.setattr(service.db, "update_fields", lambda vid, **f: None)
    # (ks, kcache, kreq, v, fuel, listings, stats, year, config) — stats 는 7번째(인덱스 6)
    monkeypatch.setattr(service, "_kcar_cross_live", lambda *a, **k: (a[6], {}, False))
    common = {"mileage_km": 50000, "photo_count": 3, "status": "완료"}
    targets = [   # requery_missing_market 가 기일 임박 순으로 정렬해 넘긴다
        {"id": "soon", "year": 2019, "maker": "기아", "model": "카니발", "sale_date": "2026-09-15", **common},
        {"id": "mid", "year": 2021, "maker": "현대", "model": "쏘나타", "sale_date": "2026-09-20", **common},
        {"id": "late", "year": 2020, "maker": "현대", "model": "그랜저", "sale_date": "2026-10-01", **common},
    ]
    n = service.recompute_all_market(targets=targets, max_requests=2, finalize=False)
    assert calls == ["카니발", "쏘나타"], "넘긴 순서대로 2그룹만"
    assert n == 2


def test_daily_update_requeries_before_reuse_with_a_cap():
    src = (ROOT / "web" / "service.py").read_text(encoding="utf-8")
    i = src.index("def daily_update(")
    body = src[i:src.index("def photo_autosort_run", i)]
    assert body.index("requery_missing_market(") < body.index("reuse_market_prices("), "실측이 참조보다 먼저"
    assert 'config.get("requery_daily_cap", 20)' in body, "런당 하드캡이 없다(C.4-1)"
    assert 'if health["state"] != "blocked":' in body, "차단 중엔 재조회하지 않는다"
