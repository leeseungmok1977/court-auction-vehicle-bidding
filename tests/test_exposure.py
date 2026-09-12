"""엔카/케이카 원자료 격리 회귀 테스트 (MONETIZATION_SPEC TASK-M01/M02).

비관리자 응답에는 개별 동급 매물·케이카·표본수 등 원자료가 절대 나오지 않아야 하고,
관리자에게는 보여야 한다. 소매 시세(median)·신뢰도·재판매 손익분기는 유지.
"""
import pytest
from starlette.testclient import TestClient


def test_public_view_strips_private_keeps_public():
    from web import service
    v = {"id": "x", "median_price": 13000000, "market_confidence": 72,
         "min_sale_price": 10000000, "judgment": "입찰 검토 가능",
         "comps": [{"badge": "z"}], "kcar_median": 8, "encar_total": 9,
         "sample_count": 42, "mean_price": 6, "min_price": 5, "market_cv": 0.1,
         "market_vs_appraisal": 0.9, "match_label": "연식±1", "cross_source_status": "agree",
         "breakdown": {"기준시세": 13000000, "마진": 900000, "플랫폼": "encar", "표본수": 42}}
    u = service.public_view(v, is_admin=False)
    for k in ("comps", "kcar_median", "encar_total", "sample_count", "mean_price",
              "min_price", "market_cv", "market_vs_appraisal", "match_label",
              "cross_source_status"):
        assert u.get(k) is None, f"PRIVATE 누출: {k}"   # 키는 있되 값은 None(finalize가 ''로 렌더)
    # 유지돼야 하는 '반영된 결과'
    assert u["median_price"] == 13000000 and u["market_confidence"] == 72
    assert u["judgment"] == "입찰 검토 가능"
    # breakdown은 유지하되 엔카 메타(플랫폼·표본수)만 제거, 원가항목은 유지
    assert "플랫폼" not in u["breakdown"] and "표본수" not in u["breakdown"]
    assert u["breakdown"]["마진"] == 900000 and u["breakdown"]["기준시세"] == 13000000
    # 관리자는 원본 그대로
    assert service.public_view(v, is_admin=True) is v


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    db.upsert_vehicle({
        "id": "T1_1", "folder_key": "T1_1", "case_no": "2026타경1", "item_no": "1",
        "court": "수원지방법원", "maker": "현대", "model": "쏘나타", "year": 2020,
        "min_sale_price": 10000000, "appraisal_value": 15000000, "fail_count": 1,
        "sale_date": "2999-01-01", "median_price": 13000000,
        "market_confidence": 72, "market_confidence_label": "높음",
        "judgment": "입찰 검토 가능", "status": "완료",
        # 엔카 원자료 — 개별 매물 badge에 verbatim 감시 문자열
        "encar_total": 99999, "sample_count": 42, "mean_price": 66660000, "min_price": 55550000,
        "market_cv": 0.19, "market_vs_appraisal": 0.87,
        "comps": [{"year": 2020, "mileage_km": 50000, "price_won": 7770000, "badge": "ZZLEAKZZ"}],
        "kcar_median": 8880000, "kcar_sample": 7,
        "cross_source_status": "agree", "cross_source_rel": 0.03,
        # 보배드림 신차가격표 파생값 — compliance §6: 허락 전 공개 노출 금지(관리자 전용)
        "newcar_min": 3294, "newcar_max": 4517, "newcar_n": 5, "newcar_model": "더 뉴 그랜저",
        "newcar_release": "19.11~21.05", "newcar_checked_at": "2026-09-11 10:00:00",
    })
    import web.app as A
    return TestClient(A.app)


def _paths():
    return ["/vehicle/T1_1", "/vehicles", "/vehicle/T1_1/report"]


# 공개 사용자 = nginx 경유(X-Forwarded-For 존재). 관리자 = SSH 터널(loopback Host, XFF 없음).
_PUBLIC = {"x-forwarded-for": "203.0.113.7"}
_TUNNEL = {"host": "127.0.0.1"}


def test_user_responses_have_no_encar_raw(app_client):
    c = app_client
    for p in _paths():
        r = c.get(p, headers=_PUBLIC)
        assert r.status_code == 200, p
        assert "ZZLEAKZZ" not in r.text, f"엔카 개별매물 누출(user): {p}"
        assert "동급 매물" not in r.text, f"동급 매물 섹션 누출(user): {p}"
        assert "보배드림" not in r.text, f"출처명 공개 노출(user): {p}"   # 권리자 조건: 출처명은 어떤 경우에도 비공개


def test_newcar_hidden_from_public_when_flag_off(app_client, monkeypatch):
    from web import service
    base = service.load_config()
    monkeypatch.setattr(service, "load_config", lambda: {**base, "newcar_public": False})
    for p in ("/vehicle/T1_1", "/vehicle/T1_1/report"):
        r = app_client.get(p, headers=_PUBLIC)
        assert r.status_code == 200 and "당시 출시가" not in r.text, p


def test_admin_sees_newcar_range(app_client):
    r = app_client.get("/vehicle/T1_1/report", headers=_TUNNEL)
    assert r.status_code == 200 and "당시 출시가" in r.text and "3,294" in r.text


def test_newcar_public_flag_shows_range_without_source(app_client, monkeypatch):
    """config newcar_public=true: 공개 사용자도 범위를 보되, 출처명(보배드림)은 어떤 경우에도 공개 응답에 없다."""
    from web import service
    base = service.load_config()
    monkeypatch.setattr(service, "load_config", lambda: {**base, "newcar_public": True})
    for p in ("/vehicle/T1_1", "/vehicle/T1_1/report"):
        r = app_client.get(p, headers=_PUBLIC)
        assert r.status_code == 200 and "당시 출시가" in r.text and "3,294" in r.text, p
        assert "보배드림" not in r.text, f"출처명 공개 노출: {p}"


def test_admin_responses_show_encar_raw(app_client):
    c = app_client
    r = c.get("/vehicle/T1_1", headers=_TUNNEL)
    assert r.status_code == 200
    assert "ZZLEAKZZ" in r.text, "관리자(터널)에게 개별 동급 매물이 보여야 함"


def test_xff_beats_loopback_host(app_client):
    """공개 사용자가 Host를 127.0.0.1로 위조해도 nginx가 붙인 XFF가 있으면 관리자 아님(보안)."""
    c = app_client
    r = c.get("/vehicle/T1_1", headers={"host": "127.0.0.1", "x-forwarded-for": "203.0.113.7"})
    assert "ZZLEAKZZ" not in r.text


# ── 플랫폼 출처명 격리 ────────────────────────────────────────────────
# 2026-09-12 2회차 패널: 공개 상세에 "엔카"가 그대로 찍히고 있었다. 위 테스트가 못 잡은 이유는
# 픽스처가 '분석 완료·시세 있음' 물건 하나뿐이라 시세 없음/신뢰도 낮음 분기가 렌더된 적이 없어서다.
# 금칙어와 함께 **그 분기를 실제로 렌더시키는 픽스처**를 넣는다.
_PLATFORM_TOKENS = ("엔카", "케이카", "SK엔카", "보배드림")


@pytest.fixture
def branch_client(tmp_path, monkeypatch):
    """시세 없음 / 신뢰도 낮음 / 입찰 보류 — 안내 배너 분기를 각각 렌더시키는 픽스처."""
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "b.db")
    db.init_db()
    base = {"court": "수원지방법원", "maker": "현대", "model": "쏘나타", "year": 2020,
            "min_sale_price": 10000000, "appraisal_value": 15000000, "fail_count": 1,
            "sale_date": "2999-01-01", "status": "완료", "item_no": "1"}
    db.upsert_vehicle({**base, "id": "NOMED_1", "folder_key": "NOMED_1", "case_no": "2026타경2",
                       "median_price": None, "judgment": "시세 정보 없음"})
    db.upsert_vehicle({**base, "id": "LOWC_1", "folder_key": "LOWC_1", "case_no": "2026타경3",
                       "median_price": 13000000, "market_confidence": 31,
                       "market_confidence_label": "낮음", "sample_count": 3,
                       "market_vs_appraisal": 2.4, "match_label": "트림 미확인",
                       "judgment": "시세 신뢰도 낮음, 수동 검토"})
    db.upsert_vehicle({**base, "id": "FLOOD_1", "folder_key": "FLOOD_1", "case_no": "2026타경4",
                       "median_price": 13000000, "accident_grade": "flood",
                       "judgment": "입찰 보류"})
    import web.app as A
    return TestClient(A.app)


@pytest.mark.parametrize("vid", ["NOMED_1", "LOWC_1", "FLOOD_1"])
def test_no_platform_name_in_public_detail(branch_client, vid):
    """어떤 분기에서도 공개 응답에 시세 플랫폼 이름이 나오면 안 된다(권리자·계약 조건)."""
    for p in (f"/vehicle/{vid}", f"/vehicle/{vid}/report"):
        r = branch_client.get(p, headers=_PUBLIC)
        assert r.status_code == 200, p
        for tok in _PLATFORM_TOKENS:
            assert tok not in r.text, f"플랫폼 출처명 '{tok}' 공개 노출: {p}"


def test_no_platform_name_in_public_list(branch_client):
    for p in ("/vehicles", "/vehicles?all=1", "/"):
        r = branch_client.get(p, headers=_PUBLIC)
        assert r.status_code == 200, p
        for tok in _PLATFORM_TOKENS:
            assert tok not in r.text, f"플랫폼 출처명 '{tok}' 공개 노출: {p}"


def test_admin_still_sees_platform_source(branch_client):
    """관리자 화면에서는 출처가 보여야 한다 — 위 테스트가 관리자 기능까지 지우지 않았는지 확인."""
    r = branch_client.get("/vehicle/LOWC_1", headers=_TUNNEL)
    assert r.status_code == 200 and "엔카" in r.text


# ── '확인하지 못한 것'을 초록으로 칠하지 않는다 (5회차 미조치) ──────
def test_unverified_history_is_never_green():
    """'이력 미확인'에 초록 chip.ok 를 붙이면 안 된다.

    리포트 §차량 상태의 사고·침수 행이 STOP이 아니면 무조건 `chip ok`(초록)였다.
    보험이력이 실제로 있는 물건은 1,320건 중 **25건뿐**이고, 나머지 1,295건(98%)이
    초록 칩에 '이력 미확인'이라고 적혀 나갔다. 확인하지 못한 것을 확인해서
    괜찮은 것처럼 읽히게 만드는 것은 이 앱에서 가장 하면 안 되는 오독이다.

    초록은 `v.insurance_history`가 **실제로 내용이 있을 때만**. 미확인은 앰버.
    """
    import pathlib
    import re
    src = pathlib.Path("web/templates/report.html").read_text(encoding="utf-8")
    m = re.search(r'<span class="chip \{\{([^}]+)\}\}">\{\{[^}]*이력 미확인', src, re.S)
    assert m, "사고·침수 행의 칩 표현식을 찾지 못했다"
    expr = m.group(1)
    assert "insurance_history" in expr, (
        "칩 색이 이력 유무를 보지 않는다 — 이력이 없어도 초록이 된다: " + expr.strip())
    # 초록('ok')은 이력이 있을 때만 나올 수 있어야 한다
    assert re.search(r"'ok'\s+if\s+v\.insurance_history", expr), (
        "초록이 이력 유무와 무관하게 걸린다: " + expr.strip())
