# -*- coding: utf-8 -*-
"""밖에서 앱으로 들어오는 문 — robots.txt · sitemap.xml.

2026-09-22 실측. 이 앱에는 **외부에서 들어올 문이 사실상 없었다.**

    og 태그            0건  → 링크를 카톡에 붙여도 제목·썸네일이 안 뜬다
    robots.txt         404
    sitemap.xml        404  → 물건 페이지 1,278개가 검색에 한 건도 안 잡힌다
    공유 기능          0건
    12일간 외부 유입   34건 (하루 2.8건)

특히 데스크톱에서는 `base.html`이 900px 이상·pointer:fine 환경을 `/static/frame.html`로
넘긴다(폰 프레임). 크롤러가 그 경로를 집으면 **본문 67자짜리 껍데기**를 색인한다
(같은 날 내 측정 도구가 정확히 그 함정에 빠졌다). 그래서 robots 로 프레임을 막는다.

사이트맵에 넣는 것은 **기일이 남아 있고 아직 안 끝난 물건**뿐이다(실측 354건).
끝난 경매를 검색에 흘리면 들어온 사람이 입찰할 수 없는 차를 보게 된다.
"""
import re

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "s.db")
    db.init_db()
    base = {"court": "수원지방법원", "maker": "현대", "model": "쏘나타", "item_no": "1",
            "year": 2020, "status": "완료", "photo_count": 3, "mileage_km": 50_000,
            "median_price": 14_000_000, "min_sale_price": 9_000_000, "fail_count": 1}
    rows = [
        dict(base, id="LIVE1", case_no="2026타경1", sale_date="2999-01-01"),
        dict(base, id="LIVE2", case_no="2026타경2", sale_date="2999-02-01"),
        # 끝난 경매 — 사이트맵에 들어가면 안 된다
        dict(base, id="DONE1", case_no="2026타경3", sale_date="2020-01-01",
             auction_result="낙찰", winning_price=10_000_000),
        # 상세 없는 물건 — 목록에도 안 나온다
        {"id": "HID1", "case_no": "(중복)_9", "item_no": "1", "status": "상세없음",
         "court": "수원지방법원", "sale_date": "2999-01-01"},
    ]
    for r in rows:
        db.upsert_vehicle(r)
    from web.app import app
    with TestClient(app) as c:
        yield c


def test_robots가_있고_사이트맵을_알려준다(client):
    r = client.get("/robots.txt")
    assert r.status_code == 200, f"robots.txt 가 {r.status_code}"
    body = r.text
    assert re.search(r"(?im)^sitemap:\s*https?://\S+/sitemap\.xml", body), (
        "robots 가 사이트맵 위치를 알려주지 않는다 — 검색엔진이 목록을 못 찾는다")
    assert "User-agent" in body


def test_폰_프레임_껍데기를_색인에서_막는다(client):
    """★ 데스크톱 크롤러가 이 경로를 집으면 본문 67자짜리 빈 페이지가 색인된다."""
    body = client.get("/robots.txt").text
    assert "/static/frame.html" in body, "폰 프레임 경로가 robots 에 없다"
    assert re.search(r"(?im)^disallow:\s*/static/frame\.html", body), (
        "프레임 경로가 Disallow 로 막혀 있지 않다")


def test_사이트맵은_아직_입찰할_수_있는_물건만_담는다(client):
    """끝난 경매를 검색에 흘리면 들어온 사람이 입찰할 수 없는 차를 본다."""
    r = client.get("/sitemap.xml")
    assert r.status_code == 200, f"sitemap.xml 이 {r.status_code}"
    assert "xml" in r.headers.get("content-type", ""), r.headers.get("content-type")
    xml = r.text
    assert "/vehicle/LIVE1" in xml and "/vehicle/LIVE2" in xml, "기일이 남은 물건이 빠졌다"
    assert "/vehicle/DONE1" not in xml, "끝난 경매가 사이트맵에 들어갔다"
    assert "/vehicle/HID1" not in xml, "목록에 없는 물건이 사이트맵에 들어갔다"


def test_사이트맵에_주요_화면이_들어간다(client):
    xml = client.get("/sitemap.xml").text
    for path in ("/vehicles", "/calendar", "/accuracy", "/landing"):
        assert f"<loc>" in xml and path in xml, f"{path} 가 사이트맵에 없다"


def test_사이트맵_주소가_절대주소다(client):
    """상대 주소를 넣으면 검색엔진이 무시한다."""
    xml = client.get("/sitemap.xml").text
    locs = re.findall(r"<loc>([^<]+)</loc>", xml)
    assert locs, "사이트맵이 비어 있다"
    for u in locs[:20]:
        assert u.startswith("http"), f"절대 주소가 아니다: {u}"
