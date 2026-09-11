"""차량목록 정렬 회귀 테스트 (2026-09-12 프로덕션 장애).

장애: `db.list_vehicles`의 정렬 폴백이 **컬럼식이 아니라 딕셔너리 키 이름**이었다.
    sql += f" ORDER BY {sort_cols.get(sort, 'recent')}"
기본값이 'sale_date'였을 땐 그게 우연히 실제 컬럼명이라 미지의 sort도 동작했는데,
'최근 등록순' 도입(3dc34ae)으로 'recent'가 되면서 sort_cols에 없는 값이 오면
`ORDER BY recent` → sqlite3.OperationalError: no such column: recent → **500**.

영향: 템플릿의 `sort=expected` 링크 7곳 전부(대시보드 '지금 입찰 추천' 포함) 500.
sort=expected는 예상낙찰가를 파이썬에서 계산해 정렬하므로 DB 정렬 키가 아니다.

이 테스트는 **템플릿을 실제로 스캔해서** 거기 쓰인 모든 sort 값을 호출한다.
새 링크에 지원되지 않는 정렬값을 넣어도 여기서 잡힌다.
"""
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

TEMPLATES = Path(__file__).resolve().parents[1] / "web" / "templates"


def template_sort_values():
    """템플릿에 실제로 쓰인 sort= 값 전부(중복 제거)."""
    found = set()
    for p in TEMPLATES.rglob("*.html"):
        found.update(re.findall(r"sort=([A-Za-z_]+)", p.read_text(encoding="utf-8")))
    return sorted(found)


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    for i, (mk, md, yr) in enumerate([("현대", "쏘나타", 2020), ("기아", "카니발", 2019)], 1):
        db.upsert_vehicle({
            "id": f"S{i}_1", "folder_key": f"S{i}_1", "case_no": f"2026타경{i}", "item_no": "1",
            "court": "수원지방법원", "maker": mk, "model": md, "year": yr,
            "min_sale_price": 10000000 + i, "appraisal_value": 15000000, "fail_count": i,
            "sale_date": "2999-01-01", "median_price": 13000000, "mileage_km": 50000 * i,
            "market_confidence": 72, "market_confidence_label": "높음",
            "judgment": "입찰 검토 가능", "status": "완료",
        })
    import web.app as A
    return TestClient(A.app)


def test_templates_actually_use_sort():
    """스캔이 0건이면 테스트가 아무것도 지키지 못한다 — 가드."""
    vals = template_sort_values()
    assert vals, "템플릿에서 sort= 를 하나도 못 찾음 (경로/정규식 확인)"
    assert "expected" in vals, "sort=expected 링크가 사라졌다면 이 테스트의 전제 확인 필요"


@pytest.mark.parametrize("sort", template_sort_values())
def test_every_template_sort_renders(app_client, sort):
    """템플릿이 거는 모든 정렬 링크는 200이어야 한다 (장애 재발 방지)."""
    r = app_client.get(f"/vehicles?sort={sort}")
    assert r.status_code == 200, f"sort={sort} → {r.status_code}"


@pytest.mark.parametrize("sort", ["", "recent", "nonexistent", "recent; DROP TABLE vehicles",
                                  "collected_at", "1"])
def test_unknown_sort_falls_back_not_500(app_client, sort):
    """미지·오염된 sort 값이 와도 기본 정렬로 떨어질 뿐 500이 나면 안 된다."""
    r = app_client.get("/vehicles", params={"sort": sort})
    assert r.status_code == 200, f"sort={sort!r} → {r.status_code}"


def test_sort_fallback_is_column_expression_not_key():
    """폴백이 '키 이름'이면 다시 `ORDER BY recent` 장애가 난다 — 소스 레벨 불변식."""
    from web import db
    src = Path(db.__file__).read_text(encoding="utf-8")
    m = re.search(r"ORDER BY \{sort_cols\.get\((.*?)\)", src)
    assert m, "정렬 폴백 표현식을 찾지 못함 (db.list_vehicles 구조 변경?)"
    expr = m.group(0)
    assert "'recent'" not in expr and '"recent"' not in expr, (
        "폴백에 키 이름 문자열이 그대로 들어 있다. sort_cols['recent'] 처럼 "
        f"**컬럼식**을 써야 한다: {expr}")


def test_expected_sort_orders_by_expected_win(app_client):
    """sort=expected는 DB가 아니라 파이썬에서 예상낙찰가 내림차순으로 정렬한다."""
    r = app_client.get("/vehicles?sort=expected")
    assert r.status_code == 200
    assert "2026타경1" in r.text or "2026타경2" in r.text
