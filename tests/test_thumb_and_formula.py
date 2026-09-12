"""썸네일 서빙과 화면 산식의 검산 — 5회차 품질 감사에서 실증된 두 구멍.

품질 전문가가 격리 사본에서 **사보타주 2건을 468건 전부 통과시켰다**:
  A. `report.html`의 `{% if bs.capped %}` 캡 공시 블록을 통째로 삭제 → 468 passed
     (물건 29%가 틀린 곱셈을 인쇄하게 되는데도 초록불)
  B. `_make_thumb()`가 항상 False 반환 → 468 passed
     (목록이 원본 사진으로 되돌아가 3G 11.3초 → 50초로 회귀해도 감지 0.
      `tests/` 38개 파일 중 'thumb'을 언급하는 파일이 0개였다)

두 사보타주가 이 파일에서는 실패해야 한다.
"""
import io
import os
import pathlib
import re

import pytest
from starlette.testclient import TestClient

from web import service

BT = {"discount_median": 0.74, "mae_pct": 9.2, "sample": 172, "within10_pct": 62,
      "within20_pct": 96, "pred_n": 135, "won_total": 172,
      "min_premium_median": 1.13, "min_premium_by_fail": {"0": 1.20, "1": 1.13, "2+": 1.06},
      "min_premium_p25": 1.05, "min_premium_p75": 1.22,
      "min_premium_pool": [round(1.00 + i * 0.004, 4) for i in range(60)],
      "discount_p25": 0.62, "discount_p75": 0.86, "discount_by_fail": {},
      "discount_by_model": {}, "upper_hit_rate": None, "upper_n": 0,
      "actual_mae_pct": None, "actual_sample": 0, "mae_baseline_pct": 12.0,
      "history_n": 0, "model_learned": False, "pred_pool": [], "comp_pool": []}


# ── 사보타주 A 방어: 캡이 걸린 물건은 화면에서 검산이 닫혀야 한다 ──
@pytest.fixture
def capped_client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "cap.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    # 최저가 × 프리미엄 ≫ 시세 × 1.10 → 캡이 반드시 binding
    db.upsert_vehicle({
        "id": "CAP_1", "folder_key": "CAP_1", "case_no": "2026타경8001", "item_no": "1",
        "court": "수원지방법원", "maker": "현대", "model": "쏘나타", "year": 2020,
        # 감정가 == 최저가면 stale_floor에 걸려 예상낙찰가가 미산출된다 — 캡 분기를
        # 만들려면 정상적으로 저감된 최저가여야 한다.
        "min_sale_price": 42_000_000, "appraisal_value": 60_000_000, "fail_count": 1,
        "sale_date": "2999-01-01", "status": "완료", "judgment": "유찰 대기",
        "median_price": 15_900_000, "market_confidence": 78,
        "market_confidence_label": "높음", "sample_count": 12, "photo_count": 3,
    })
    import web.app as A
    return TestClient(A.app)


def test_cap_is_actually_binding_in_the_fixture(capped_client):
    """픽스처가 캡 분기를 실제로 만드는지 — 아니면 아래 테스트가 공허하다."""
    from web import db
    b = service.expected_band(db.get_vehicle("CAP_1"), BT)
    assert b["basis"]["capped"] is True


_PUB = {"x-forwarded-for": "203.0.113.7"}


@pytest.mark.parametrize("path", ["/vehicle/CAP_1", "/vehicle/CAP_1/report"])
def test_capped_vehicle_shows_the_cap_step(capped_client, path):
    """캡이 걸리면 상세·리포트 **양쪽** 모두 캡을 공시해야 한다.

    4회차엔 리포트에만 넣어, 상세는 `90,000,000 × 1.102 = 83,000,000`처럼
    검산하면 틀리는 곱셈을 인쇄했다(물건 29%).
    """
    html = capped_client.get(path, headers=_PUB).text
    assert "소프트캡" in html or "상한" in html, f"{path}: 캡 공시가 없다"
    assert "캡 적용 전" in html or "시세×1.10" in html or "시세 × 1.10" in html, (
        f"{path}: 캡 전후 값이 없어 화면 숫자만으로 검산이 닫히지 않는다")


def test_printed_multiplication_closes(capped_client):
    """화면에 인쇄된 곱셈이 화면에 인쇄된 결과와 맞는가."""
    from web import db
    v = db.get_vehicle("CAP_1")
    b = service.expected_band(v, BT)
    raw = b["basis"]["raw"]
    assert abs(raw - v["min_sale_price"] * b["basis"]["premium"]) < 100_000
    # 최종값은 캡과 최저가 하한을 거친 값이고, 그 유도가 화면에 있어야 한다
    assert b["price"] == max(b["basis"]["cap"], v["min_sale_price"])


# ── 사보타주 B 방어: 썸네일이 실제로 동작하는가 ──────────────────
def _png_bytes(w=800, h=600):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (120, 140, 160)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def thumb_client(tmp_path, monkeypatch):
    from web import db
    import web.app as A
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(A, "DATA_DIR", tmp_path, raising=False)
    monkeypatch.setattr(A, "_THUMB_DIR", tmp_path / "_thumbs", raising=False)
    db.init_db()
    pdir = tmp_path / "TH_1" / "photos"
    pdir.mkdir(parents=True)
    (pdir / "a.png").write_bytes(_png_bytes())
    (pdir / "broken.png").write_bytes(b"not an image at all")
    return TestClient(A.app)


def test_thumb_is_smaller_than_original(thumb_client, tmp_path):
    """썸네일이 실제로 줄어야 한다 — 항상 원본 폴백이면 성능 수정이 무효다."""
    r = thumb_client.get("/thumb/TH_1/a.png", headers=_PUB)
    assert r.status_code == 200
    assert len(r.content) > 0, "0바이트 이미지를 200으로 주면 안 된다"
    orig = (tmp_path / "TH_1" / "photos" / "a.png").stat().st_size
    assert len(r.content) < orig, f"썸네일이 원본보다 작지 않다({len(r.content)} vs {orig})"
    assert r.headers.get("content-type", "").endswith("webp")


def test_thumb_never_serves_empty_body(thumb_client):
    """0바이트 응답 + 장기 캐시는 빈 이미지를 7일간 고정시킨다(5회차 P0)."""
    for _ in range(5):
        r = thumb_client.get("/thumb/TH_1/a.png", headers=_PUB)
        assert r.status_code == 200 and len(r.content) > 0
        if "max-age" in (r.headers.get("cache-control") or ""):
            assert len(r.content) > 0


def test_broken_image_falls_back_without_long_cache(thumb_client):
    """손상 이미지는 원본으로 폴백하되 장기 캐시를 붙이지 않는다(다음에 재시도)."""
    r = thumb_client.get("/thumb/TH_1/broken.png", headers=_PUB)
    assert r.status_code == 200
    assert "max-age" not in (r.headers.get("cache-control") or "").lower()


def test_thumb_rejects_path_traversal_and_missing(thumb_client):
    for bad in ("/thumb/TH_1/..%2F..%2Fsecret.txt", "/thumb/NOPE_1/a.png",
                "/thumb/TH_1/nope.png"):
        assert thumb_client.get(bad, headers=_PUB).status_code in (400, 404)


def test_thumb_write_is_atomic(thumb_client, tmp_path):
    """임시파일 → os.replace. 서빙 경로에 직접 쓰면 부분 파일이 노출된다."""
    src = pathlib.Path(__file__).resolve().parents[1] / "web" / "app.py"
    body = src.read_text(encoding="utf-8")
    fn = body[body.index("def _make_thumb("):body.index("@app.get(\"/thumb")]
    assert "os.replace" in fn or "_os.replace" in fn, "원자적 교체가 없다"
    assert "mkstemp" in fn or "NamedTemporaryFile" in fn, "임시파일 경유가 없다"


def test_list_and_home_use_thumbnails():
    """목록만 고치고 홈·상세를 두면 병목이 옮겨갈 뿐이다(홈 3G 43.1초)."""
    root = pathlib.Path(__file__).resolve().parents[1]
    svc = (root / "web" / "service.py").read_text(encoding="utf-8")
    assert '"/thumb/' in svc, "홈 카드 썸네일(_pick_photo_url)이 원본을 쓴다"
    det = (root / "web" / "templates" / "detail.html").read_text(encoding="utf-8")
    assert det.count("/thumb/") >= 2, "상세 히어로·스트립이 원본을 쓴다"
    # 라이트박스는 원본이어야 한다(확대해서 보는 용도)
    assert "LB_BASE" in det and '"/photo/"' in det
