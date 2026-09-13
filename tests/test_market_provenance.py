"""시세 근거 공개(F) — 표본 수·수집 시점·집계 방식은 밝히고, 출처명·매물 링크는 막는다.

배경: 18인 패널 재평가에서 F("시세를 어디서 어떻게 구했는지 알 수 없다")가 5→15로
**악화**했다. 그전까지는 계약 범위가 불확실해 표본 수까지 통째로 가리고 있었다.
2026-09-13 권리자 조건 확인 결과 **금지 대상은 출처명과 매물 링크뿐**이다.

그래서 여는 것과 계속 막는 것을 이 파일이 갈라놓는다:
  열림  표본 수 · 원표본/이상치 제외 건수 · 수집 시점 · 경과일 · 집계 방식 · 매칭 조건 · 편차
  막힘  플랫폼 이름(엔카·SK엔카·케이카·보배드림) · 개별 매물 · 매물 링크

설계상 중요한 것: `public_view`의 PRIVATE_FIELDS 차단은 **그대로 둔다.** 근거는
원본 v에서 뽑아 별도 인자(prov)로 넘긴다 — 차단을 느슨하게 푸는 대신 담을 것만
담는 통로를 따로 낸다. 그래서 아래 두 가지를 같이 검사한다.
"""
import re

import pytest
from starlette.testclient import TestClient

from web import service

_PUBLIC = {"x-forwarded-for": "203.0.113.7"}
_TUNNEL = {"host": "127.0.0.1"}
_SOURCE_TOKENS = ("엔카", "SK엔카", "케이카", "보배드림", "encar", "kcar", "bobae")

_BASE = {
    "id": "P1_1", "folder_key": "P1_1", "case_no": "2026타경7001", "item_no": "1",
    "court": "수원지방법원", "maker": "현대", "model": "쏘나타", "year": 2020,
    "min_sale_price": 10_000_000, "appraisal_value": 15_000_000, "fail_count": 1,
    "sale_date": "2999-01-01", "status": "완료", "judgment": "입찰 검토 가능",
    "median_price": 13_000_000, "market_confidence": 72, "market_confidence_label": "높음",
    "market_platform": "encar", "sample_count": 21, "market_cv": 0.137,
    "match_label": "동급 (연식±1·주행±30%)·가솔린·동세대·이상치2건제외",
    "analyzed_at": "2026-09-01 10:00:00",
    "comps": [{"year": 2020, "mileage_km": 50000, "price_won": 7_770_000, "badge": "ZZLEAKZZ"}],
    "encar_total": 99999, "mean_price": 13_100_000, "min_price": 9_000_000,
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "prov.db")
    db.init_db()
    db.upsert_vehicle(dict(_BASE))
    import web.app as A
    return TestClient(A.app)


# ── 함수 계약 ────────────────────────────────────────────────────
def test_provenance_reports_what_actually_made_the_number():
    p = service.market_provenance(dict(_BASE))
    assert p["n"] == 21, "중앙값 산출에 실제 쓴 표본 수"
    assert p["outliers"] == 2 and p["n_raw"] == 23, "처음 모은 건수 = 남은 것 + 버린 것"
    assert p["cv_pct"] == 14
    assert p["as_of"] == "2026-09-01" and p["days"] is not None
    assert "이상치" not in p["match"], "이상치 건수는 별도 필드로 뺐는데 문구에도 남았다"
    assert "연식±1" in p["match"] and "주행±30%" in p["match"]
    assert "중앙값" in p["method"]


def test_provenance_never_carries_a_source_name():
    """수집기가 라벨 문구를 바꿔 출처명이 섞여도 데이터 계층에서 막힌다."""
    for tok in _SOURCE_TOKENS:
        v = dict(_BASE, match_label=f"동급 (연식±1)·{tok} 기준")
        p = service.market_provenance(v)
        blob = " ".join(str(x) for x in p.values())
        assert tok.lower() not in blob.lower(), f"근거에 출처명 '{tok}' 누출"


def test_provenance_has_no_field_for_individual_listings():
    """개별 매물·링크는 담을 자리 자체가 없어야 한다(구조적 차단)."""
    p = service.market_provenance(dict(_BASE))
    assert "comps" not in p and "url" not in p and "link" not in p
    blob = " ".join(str(x) for x in p.values())
    assert "ZZLEAKZZ" not in blob and "http" not in blob


def test_cross_source_count_matches_what_the_blend_actually_used():
    """화면이 '2차 소스 N건 반영'이라 적으면 그 N건이 실제로 반영돼 있어야 한다."""
    used = dict(_BASE, kcar_median=12_500_000, kcar_sample=5)
    assert service.market_provenance(used)["cross_n"] == 5
    assert service.effective_median(used) != used["median_price"], "블렌드가 실제로 걸려야"
    # 표본 부족(<2) · 극단 괴리(2배 밖) 는 반영하지 않으므로 0으로 적어야 한다
    for bad in (dict(_BASE, kcar_median=12_500_000, kcar_sample=1),
                dict(_BASE, kcar_median=40_000_000, kcar_sample=9)):
        assert service.market_provenance(bad)["cross_n"] == 0
        assert service.effective_median(bad) == bad["median_price"]


def test_stale_flag_matches_the_encar_block_reality():
    """수집이 멈춘 물건은 '오래됨'으로 스스로 밝혀야 한다(엔카 차단 2026-09-07~)."""
    from datetime import date, timedelta
    old = (date.today() - timedelta(days=30)).isoformat() + " 10:00:00"
    fresh = (date.today() - timedelta(days=3)).isoformat() + " 10:00:00"
    assert service.market_provenance(dict(_BASE, analyzed_at=old))["stale"] is True
    assert service.market_provenance(dict(_BASE, analyzed_at=fresh))["stale"] is False


def test_no_market_no_provenance():
    assert service.market_provenance(dict(_BASE, median_price=None)) is None
    assert service.market_provenance(None) is None


# ── 렌더된 화면 ──────────────────────────────────────────────────
@pytest.mark.parametrize("path", ["/vehicle/P1_1", "/vehicle/P1_1/report"])
def test_public_screens_now_show_the_evidence(client, path):
    r = client.get(path, headers=_PUBLIC)
    assert r.status_code == 200
    assert "21건" in r.text, "표본 수가 안 보인다 — F가 안 풀렸다"
    assert "2026-09-01" in r.text, "수집 시점이 안 보인다"
    assert "중앙값" in r.text, "집계 방식이 안 보인다"
    assert "±14%" in r.text, "표본 편차가 안 보인다"


@pytest.mark.parametrize("path", ["/vehicle/P1_1", "/vehicle/P1_1/report", "/vehicles"])
def test_opening_the_evidence_did_not_open_the_source(client, path):
    """근거를 열면서 출처명·개별 매물까지 새면 계약 위반이다."""
    r = client.get(path, headers=_PUBLIC)
    assert r.status_code == 200
    for tok in _SOURCE_TOKENS:
        assert tok not in r.text, f"출처명 '{tok}' 공개 노출: {path}"
    assert "ZZLEAKZZ" not in r.text, f"개별 매물 누출: {path}"
    assert "동급 매물" not in r.text, f"동급 매물 섹션 누출: {path}"


def test_private_fields_are_still_stripped(client):
    """근거를 별도 통로로 낸 것이지 PRIVATE_FIELDS 차단을 푼 것이 아니다."""
    u = service.public_view(dict(_BASE), is_admin=False)
    for k in ("comps", "encar_total", "sample_count", "mean_price",
              "min_price", "market_cv", "match_label"):
        assert u.get(k) is None, f"PRIVATE 누출: {k}"


def test_admin_screen_is_unchanged(client):
    """관리자는 원자료를 계속 봐야 한다 — 근거 공개가 관리자 기능을 지우지 않았는지."""
    r = client.get("/vehicle/P1_1", headers=_TUNNEL)
    assert r.status_code == 200
    assert "ZZLEAKZZ" in r.text and "엔카" in r.text


def test_public_evidence_block_is_not_duplicated_for_admin(client):
    """관리자 화면에는 바로 아래 원자료 카드가 있으므로 근거 카드를 겹쳐 쓰지 않는다."""
    r = client.get("/vehicle/P1_1", headers=_TUNNEL)
    assert "이 시세의 근거" not in r.text


def test_stale_notice_reaches_the_screen(client, monkeypatch):
    from datetime import date, timedelta
    from web import db
    old = (date.today() - timedelta(days=40)).isoformat() + " 09:00:00"
    db.upsert_vehicle(dict(_BASE, analyzed_at=old))
    for path in ("/vehicle/P1_1", "/vehicle/P1_1/report"):
        t = client.get(path, headers=_PUBLIC).text
        assert "3주 넘게 갱신되지 않았습니다" in t, path
        assert "40일 전" in t, path


# ── 디자인 검수 반영분 ────────────────────────────────────────────
def test_conclusions_are_not_filed_under_method():
    """'집계 방식'에 결론·중복이 섞여 6줄짜리 회색 덩어리가 됐다(디자인 검수 지적 1)."""
    v = dict(_BASE, sample_count=1, match_label=(
        "확장 (연식±2·주행±50%)·동세대·표본1건(부족)·감정가 대비 괴리 큼 — 트림·사고 확인"))
    p = service.market_provenance(v)
    assert p["match"] == "확장 (연식±2·주행±50%)·동세대"
    assert "표본1건" not in p["match"], "표본 수 행과 글자 그대로 중복된다"
    assert p["caution"].startswith("감정가 대비"), p["caution"]


def test_a_wide_spread_is_flagged_even_when_the_sample_is_big():
    """표본 47건·편차 ±30% 물건이 경고 하나 없는 카드로 나갔다(디자인 검수 지적 2).

    앵커가 ±30% 흔들린다는 건 입찰가 전체가 그만큼 흔들린다는 뜻이다.
    """
    wide = dict(_BASE, sample_count=47, market_cv=0.30,
                analyzed_at=service.date.today().isoformat() + " 10:00:00")
    p = service.market_provenance(wide)
    assert p["weak_n"] is False and p["stale"] is False, "표본·신선도는 멀쩡한 케이스여야"
    assert p["weak_cv"] is True and p["grade"] == "weak", "그런데도 근거는 약해야 한다"


@pytest.mark.parametrize("path,head,tail", [
    ("/vehicle/W1_1", "이 시세의 근거", "낙찰 전 점검 포인트"),
    ("/vehicle/W1_1/report", "소매 시세 근거", "</table>"),
])
def test_wide_spread_reaches_the_screen_in_warning_colour(client, path, head, tail):
    """근거 블록 **안에서** 위험이 보여야 한다 — 범위를 넓게 잡으면 다른 곳의 앰버를
    보고 통과해 버린다(실제로 사보타주 H가 그렇게 빠져나갔다)."""
    from web import db
    db.upsert_vehicle(dict(_BASE, id="W1_1", folder_key="W1_1", case_no="2026타경7002",
                           sample_count=47, market_cv=0.30, match_label="동급 (연식±1)·동세대",
                           analyzed_at=service.date.today().isoformat() + " 10:00:00"))
    t = client.get(path, headers=_PUBLIC).text
    seg = t[t.index(head):]
    seg = seg[:seg.index(tail)]
    assert "±30%" in seg
    assert ("text-amber-700" in seg or "tag estimated" in seg), \
        "표본 47건·편차 ±30% 인데 근거 블록에 위험 표시가 하나도 없다"


def test_report_tags_do_not_reuse_the_confirmed_green(client):
    """§02 안에 '확정=초록' 범례가 있다. 같은 초록을 근거 태그에 쓰면 두 뜻이 된다."""
    t = client.get("/vehicle/P1_1/report", headers=_PUBLIC).text
    tbl = t[t.index("소매 시세 근거"):]
    tbl = tbl[:tbl.index("</table>")]
    assert "tag confirmed" not in tbl, "근거 태그가 '확정'과 같은 초록을 쓴다"
    assert "tag basis" in tbl, "중립 태그가 안 쓰였다"


def test_detail_card_carries_one_status_chip(client):
    """경고색은 헤더 칩 1개 + 약한 항목의 숫자에만 — 설명 문단을 통째로 칠하지 않는다."""
    t = client.get("/vehicle/P1_1", headers=_PUBLIC).text
    card = t[t.index("이 시세의 근거"):]
    card = card[:card.index("낙찰 전 점검 포인트")]
    assert ("근거 충분" in card or "근거 보통" in card or "근거 약함" in card), "등급 칩이 없다"
    assert card.count("text-amber-700") <= 3, "앰버가 너무 많다 — 경고색이 희석된다"


def test_no_bare_numbers_without_a_unit_in_evidence(client):
    """'21' 처럼 단위 없는 숫자만 던지지 않는다 — 근거는 읽혀야 근거다."""
    t = client.get("/vehicle/P1_1/report", headers=_PUBLIC).text
    block = t[t.index("소매 시세 근거"):]
    block = block[:block.index("</table>")]
    assert re.search(r"21건", block) and re.search(r"±14%", block)
    assert "표본 수" in block and "수집 시점" in block and "집계 방식" in block
