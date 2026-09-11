"""보배드림 신차가격표 — 파서·후보 점수·(등급,연식) 캐시 수집 알고리즘 (네트워크 없음, 가짜 페이지)."""
import json

import pytest

from src.collect import bobae


def _page(select_id=None, opts=(), selected=None, price=None, release=None):
    html = "<html><body>"
    if select_id:
        html += f"<select id='{select_id}' name='{select_id}'><option value=''>선택</option>"
        for v, t in opts:
            html += f"<option value='{v}' {'selected' if v == selected else ''}>{t}</option>"
        html += "</select>"
    if release:
        html += f'<li class="item"><p class="title">출시일</p><p class="value"> {release}</p></li>'
    if price is not None:
        html += f'<header><h3>출시가격</h3></header><div class="price-area"><span>{price:,} 만원</span></div>'
    return html + "</body></html>"


# ── 파서 ──────────────────────────────────────────────────────────────────
def test_parse_options_single_quotes_and_selected():
    html = _page("year_no", [("2020", "2020"), ("2021", "2021")], selected="2021")
    assert bobae.parse_options(html, "year_no") == [("2020", "2020", False), ("2021", "2021", True)]
    assert bobae.parse_options(html, "level_no") == []


def test_parse_price_and_release():
    html = _page(price=3294, release="19.11~21.05")
    assert bobae.parse_price(html) == 3294
    assert bobae.parse_release(html) == "19.11~21.05"
    assert bobae.parse_price(_page(price=0)) is None        # 미선택 상태 '0 만원'은 가격 아님


def test_exclusion_tokens():
    assert bobae.is_excluded("3.0 LPi (렌터카용)") and bobae.is_excluded("택시형")
    assert not bobae.is_excluded("2.5") and not bobae.is_excluded("프리미엄")


# ── 모델 후보 점수 ────────────────────────────────────────────────────────
MODELS = [("1", "더 뉴 그랜저"), ("2", "더 뉴 그랜저 하이브리드"), ("3", "그랜저IG"), ("4", "그랜저HG"),
          ("5", "더 뉴 그랜저"), ("6", "쏘나타 DN8"), ("7", "디 올 뉴 그랜저")]


def test_rank_prefers_generation_name_then_group():
    ranked = bobae.rank_model_candidates(MODELS, ["더 뉴 그랜저 IG"], "그랜저")
    names = [n for _, n in ranked]
    assert names[:2] == ["더 뉴 그랜저", "더 뉴 그랜저"]         # 동명 2개 모두 상위(연식 검증으로 확정)
    assert "쏘나타 DN8" not in names                              # 그룹 불일치 제외
    exact = bobae.rank_model_candidates(MODELS, ["그랜저 IG"], "그랜저")
    assert exact[0][1] == "그랜저IG"                              # 정규화 완전일치 최우선


def test_rank_without_generation_falls_back_to_group():
    ranked = bobae.rank_model_candidates(MODELS, [], "그랜저")
    assert len(ranked) == 6 and all("그랜저" in n for _, n in ranked)


# ── 수집 알고리즘(가짜 fetch) ─────────────────────────────────────────────
@pytest.fixture
def dbmod(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    return db


class FakeSite:
    """URL 파라미터 → 페이지. 요청 수를 세어 캐시 효과를 검증한다."""
    def __init__(self):
        self.calls = 0
        self.levels = [("L1", "2.5"), ("L2", "3.0 LPi (렌터카용)")]
        self.grades = {"L1": [("G1", "프리미엄"), ("G2", "캘리그래피"), ("G3", "택시 전용")]}
        self.years = {"G1": ["2020", "2021"], "G2": ["2021"]}
        self.price = {("G1", "2020"): 3294, ("G1", "2021"): 3303, ("G2", "2021"): 4517}

    def __call__(self, session, budget, **p):
        budget.take(); self.calls += 1
        if "level2_no" in p:
            g = p["level2_no"]; yrs = self.years[g]
            sel = p.get("year_no") or yrs[0]
            return _page("year_no", [(y, y) for y in yrs], selected=sel,
                         price=self.price.get((g, sel), 0), release="19.11~21.05")
        if "level_no" in p:
            return _page("level2_no", self.grades[p["level_no"]])
        if "model_no" in p:
            return _page("level_no", self.levels)
        return _page("model_no", [("M1", "더 뉴 그랜저")])


def test_collect_model_year_excludes_and_caches(dbmod, monkeypatch):
    from web import service
    site = FakeSite()
    monkeypatch.setattr(bobae, "fetch", site)
    monkeypatch.setattr(bobae.time, "sleep", lambda s: None)
    b = bobae.Budget(50)
    res = service.newcar_collect_model_year(None, b, "49", "M1", 2021)
    # 렌터카용 세부모델·택시 등급 제외 → 프리미엄(3,303)·캘리그래피(4,517)만
    assert sorted(p for _, _, p in res["prices"]) == [3303, 4517]
    assert res["release"] == "19.11~21.05" and res["n_grades"] == 2
    first_calls = site.calls
    # 2020년식: 캘리그래피는 2020 없음 → 프리미엄만. 목록·등급·기본연식(2020) 가격이 모두 캐시라 요청 0회
    res2 = service.newcar_collect_model_year(None, b, "49", "M1", 2020)
    assert [p for _, _, p in res2["prices"]] == [3294]
    assert site.calls == first_calls
    # 같은 (모델,연식) 재수집은 요청 0
    calls = site.calls
    service.newcar_collect_model_year(None, b, "49", "M1", 2021)
    assert site.calls == calls


def test_budget_exhaustion_leaves_cache_for_resume(dbmod, monkeypatch):
    from web import service
    site = FakeSite()
    monkeypatch.setattr(bobae, "fetch", site)
    monkeypatch.setattr(bobae.time, "sleep", lambda s: None)
    with pytest.raises(bobae.BudgetExhausted):
        service.newcar_collect_model_year(None, bobae.Budget(2), "49", "M1", 2021)
    assert dbmod.nc_get("newcar_models", "model_no", "M1")["levels_json"]   # 첫 페이지는 캐시됨
    # 예산을 늘려 재개하면 이어서 완료
    res = service.newcar_collect_model_year(None, bobae.Budget(50), "49", "M1", 2021)
    assert len(res["prices"]) == 2


def test_block_status_stops(monkeypatch):
    class R:
        status_code = 429
        content = b""
        def raise_for_status(self): pass
    class S:
        def get(self, *a, **k): return R()
    monkeypatch.setattr(bobae.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError):
        bobae.fetch(S(), bobae.Budget(5), maker_no="49")
