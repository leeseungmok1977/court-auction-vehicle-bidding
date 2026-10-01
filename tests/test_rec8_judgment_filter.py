# -*- coding: utf-8 -*-
"""REC-8 ⑴(지시서 2026-10-01-03) — `/vehicles?judgment=입찰 검토 가능` 은 홈 '지금 입찰 추천' 칸(`?bucket=review`)이다.

2026-09-29 12:00(09-29 백업 사본, backend r4 §4.1 ②): 판정 필터가 **저장 문자열** judgment 로 소속·'총 N건'을 정해
'총 4건' 중 2대가 칸 밖이었다 — E300(2026타경50522_1, 이번 회차 최저가 미확인 → 판정 '다음 기일 최저가 공고 대기')과
체로키(50005_1, 기일 경과). 같은 시각 `?bucket=review` 는 2건이다. 진입점 6곳(홈 '✅ 검토 가능' 칩·캐러셀 '더보기'·
랜딩 2·목록 2)과 사용자가 저장·공유한 옛 링크가 이 값을 쓴다. 저장 문자열로 판정을 말하는 길의 다섯 번째 자리다.

처방: 판정 값이 칸으로 읽히면(service.JUDGMENT_FILTER_BUCKETS) SQL 에 저장 문자열을 넘기지 않고 `?bucket=` 과 **같은
함수**(service.in_lifecycle_bucket)로 거른다. SQL 이 같은 질의라 결과·순서·총수·페이지·축별 건수가 같다.
다른 판정 값('유찰 대기' 등)은 이번에 바꾸지 않는다.

외부 요청 0 — tests/test_rec1_r3_picks_gate_block.py 의 `_no_network`(루프백 밖 connect·connect_ex·DNS 와 법원 요청 함수를
막고 시도를 기록, 끝에서 비었는지 본다).
"""
import inspect
from urllib.parse import quote

import pytest
from starlette.testclient import TestClient

from tests.test_daily_picks_two_axes import BT
from tests.test_rec1_r3_picks_gate_block import _d, _ge300, _no_network, mk  # noqa: F401 — 픽스처(외부 요청 0 · 물건 생성)
from tests.test_rec7_carousel_resale_state import _b520_after_refresh
from web import db, service

_PUB = {"x-forwarded-for": "203.0.113.7"}   # XFF 가 없으면 이 앱은 요청을 관리자(SSH 터널)로 본다
J = "입찰 검토 가능"
JQ = quote(J)
SORTS = ("recent", "sale_date", "expected", "min_sale_price", "fail_count", "upper_bid", "mileage", "inspection")
# 저장 판정은 '입찰 검토 가능'인데 칸은 review 가 아닌 것 — 옛 규칙이면 전부 이 목록에 섰다
OUTSIDE = ("GE300", "ELAP", "STOP", "FLDR", "LOWC")


def _resale(mk, vid, **kw):
    """되팔이 판정(bid_state resale)이 서는 '지금 입찰 추천' 물건 — REC-7 ⑺ 대조군(RSL)과 같은 값."""
    base = dict(maker="기아", model="K5", appraisal_value=30_000_000, min_sale_price=10_000_000, fail_count=1,
                judgment=J, median_price=30_000_000, upper_bid=19_000_000)
    base.update(kw)
    return mk(vid, **base)


@pytest.fixture
def cars(mk):
    """칸 안 2갈래(되팔이·지금 사면 이득) + 저장 문자열만 '입찰 검토 가능'인 칸 밖 5갈래 + 대조군."""
    out = {
        "RSL": _resale(mk, "RSL", maker="현대", model="쏘나타", min_sale_price=9_000_000, mileage_km=80_000,
                       sale_date=_d(9), inspection_to=_d(200)),
        "RSL2": _resale(mk, "RSL2", maker="기아", model="K5", min_sale_price=11_000_000, fail_count=2,
                        sale_date=_d(9), mileage_km=30_000),
        "B520R": _b520_after_refresh(mk),                                    # 판정 usepick '지금 사면 이득' — 칸 안
        "GE300": _ge300(mk),                                                 # 이번 회차 최저가 미확인(가드) — 칸 밖
        "ELAP": _resale(mk, "ELAP", sale_date=_d(0), sale_time="00:00"),      # 오늘 기일, 입찰 시각 경과 — 칸 밖
        "STOP": _resale(mk, "STOP", runnable="no"),                          # 시동·운행 불가 — 칸 밖
        "FLDR": _resale(mk, "FLDR", accident_grade="flood"),                 # 침수 등급이 뒤에 붙은 물건 — 칸 밖
        "LOWC": _resale(mk, "LOWC", market_confidence_label="낮음", market_confidence=30),   # 시세 신뢰도 낮음 — 칸 밖
        "PAST": _resale(mk, "PAST", sale_date=_d(-3)),                       # 지난 기일 — 옛 SQL 도 뺐다
        "WAIT1": mk("WAIT1", judgment="유찰 대기", appraisal_value=30_000_000, min_sale_price=29_000_000,
                    median_price=30_000_000),
        "DUP": _resale(mk, "DUP", case_no="(중복)2026타경DUP"),               # 칸 안이지만 목록 모수(hide_incomplete)가 숨긴다
    }
    return out


@pytest.fixture
def get(monkeypatch):
    """(컨텍스트, HTML) — 라우트가 템플릿에 넘긴 값을 그대로 본다."""
    import web.app as A
    cap = []
    orig = A.templates.TemplateResponse

    def _cap(name, ctx, *a, **k):
        cap.append(ctx)
        return orig(name, ctx, *a, **k)
    monkeypatch.setattr(A.templates, "TemplateResponse", _cap)
    c = TestClient(A.app)

    def _get(url):
        cap.clear()
        r = c.get(url, headers=_PUB)
        assert r.status_code == 200, (url, r.status_code)
        return cap[-1], r.text
    _get.client = c
    return _get


def _pages(get, url):
    """모든 페이지의 id(순서 그대로)와 1페이지 컨텍스트."""
    ctx, _ = get(url)
    ids = [r["id"] for r in ctx["rows"]]
    for p in range(2, ctx["total_pages"] + 1):
        c2, _ = get(f"{url}&page={p}")
        ids += [r["id"] for r in c2["rows"]]
    return ctx, ids


def _axes(ctx):
    return ([b["count"] for b in ctx["price_bands"]], [o["count"] for o in ctx["year_options"]],
            [o["count"] for o in ctx["km_options"]], ctx["km_unknown_excluded"])


# ── 전제 — 픽스처가 그 갈래를 실제로 만든다(공허 통과 방지) ─────────────────────
def test_전제_칸_안과_칸_밖이_의도대로_갈린다(cars):
    bucket = {k: service.lifecycle_bucket_of(v, BT) for k, v in cars.items()}
    state = {k: service.bid_state(v, BT)["state"] for k, v in cars.items()}
    assert bucket["RSL"] == bucket["RSL2"] == "review" and state["RSL"] == state["RSL2"] == "resale"
    assert bucket["B520R"] == "review" and state["B520R"] == "usepick", "지금 사면 이득도 '지금 입찰 추천' 칸이다"
    assert bucket["DUP"] == "review", "DUP 은 칸 안인데 목록이 숨기는 물건이어야 한다"
    assert service.floor_unconfirmed(cars["GE300"]) and bucket["GE300"] == "wait"
    assert service.bid_state(cars["ELAP"], BT)["label"] == "기일 경과 — 결과 확인 전" and bucket["ELAP"] == "wait"
    assert bucket["STOP"] == "lowconf" and bucket["LOWC"] == "lowconf"
    assert state["FLDR"] == "blocked" and bucket["FLDR"] == "wait"
    # 옛 규칙(저장 문자열 SQL)이면 칸 밖 5대가 전부 '입찰 검토 가능' 목록에 섰다
    old = {v["id"] for v in db.list_vehicles(judgment=J, hide_incomplete=True)}
    assert set(OUTSIDE) <= old and "PAST" not in old and "DUP" not in old, old


# ── 결과·총수·순서·페이지 ────────────────────────────────────────────────
@pytest.mark.parametrize("sort", SORTS)
def test_판정_필터는_지금_입찰_추천_칸과_같은_목록이다(cars, get, sort):
    cj, ij = _pages(get, f"/vehicles?judgment={JQ}&sort={sort}")
    cb, ib = _pages(get, f"/vehicles?bucket=review&sort={sort}")
    assert ij == ib, f"{sort}: 판정 필터 {ij} ≠ 칸 {ib}"
    assert cj["total"] == cb["total"] == 3 and cj["total_pages"] == cb["total_pages"]
    assert set(ij) == {"RSL", "RSL2", "B520R"}
    assert cj["sale_split"] == cb["sale_split"]
    assert _axes(cj) == _axes(cb), "가격대·연식·주행거리 셀렉트의 건수도 같은 모수여야 한다"


def test_가드_기일경과_시동불가_침수_신뢰도낮음은_나오지_않는다(cars, get):
    ctx, html = get(f"/vehicles?judgment={JQ}&sort=expected")        # 홈 '✅ 검토 가능' 칩의 옛 링크 그대로
    ids = {r["id"] for r in ctx["rows"]}
    assert not ids & set(OUTSIDE), ids & set(OUTSIDE)
    for vid in OUTSIDE:
        assert f"/vehicle/{vid}" not in html, f"{vid} 카드가 그려졌다"
    assert ctx["total"] == 3


def test_옛_규칙과_달리_총수가_칸_수와_같다(cars, get):
    """홈 '지금 입찰 추천' 숫자 = 이 목록의 '총 N건' — 카드 수와 목록 수가 같아야 한다(2026-09-21 카드 10 / 목록 12 사건)."""
    ctx, _ = get(f"/vehicles?judgment={JQ}")
    lc = service.lifecycle_partition()
    assert ctx["total"] == lc["review"] == 3


def test_페이지까지_같다(mk, get):
    """12건 한 페이지를 넘겨도 페이지마다 같은 물건이 같은 순서로 선다(칸 밖 물건이 끼어 페이지 경계를 밀지 않는다)."""
    for i in range(14):
        _resale(mk, f"R{i:02d}", min_sale_price=9_000_000 + i * 100_000, sale_date=_d(5 + i % 4))
        if i % 3 == 0:
            _resale(mk, f"X{i:02d}", runnable="no", sale_date=_d(5 + i % 4))    # 칸 밖 — 옛 규칙이면 끼었다
    _ge300(mk)
    for sort in ("recent", "sale_date", "min_sale_price"):
        for page in (1, 2):
            cj, _ = get(f"/vehicles?judgment={JQ}&sort={sort}&page={page}")
            cb, _ = get(f"/vehicles?bucket=review&sort={sort}&page={page}")
            assert [r["id"] for r in cj["rows"]] == [r["id"] for r in cb["rows"]], (sort, page)
            assert (cj["total"], cj["total_pages"], cj["page"]) == (cb["total"], cb["total_pages"], cb["page"]) == (14, 2, page)


# ── 다른 필터와 겹칠 때 · 저장한 검색 건수 ──────────────────────────────────
@pytest.mark.parametrize("extra", ["", "&maker=기아", "&price=1000-2000", "&price=500-1000", "&year_min=2018",
                                   "&km_max=100000", "&upcoming=30", "&q=K5", "&all=1", "&sort=expected"])
def test_다른_필터와_겹쳐도_칸과_같다(cars, get, extra):
    cj, ij = _pages(get, f"/vehicles?judgment={JQ}{extra}")
    cb, ib = _pages(get, f"/vehicles?bucket=review{extra}")
    assert ij == ib and cj["total"] == cb["total"], (extra, ij, ib)
    assert _axes(cj) == _axes(cb), extra
    if extra == "&all=1":
        assert "DUP" in ij, "숨김 해제(all=1)면 목록 모수가 숨기던 칸 안 물건도 같이 선다"


@pytest.mark.parametrize("extra", ["", "&maker=기아", "&price=1000-2000", "&all=1", "&upcoming=30"])
def test_저장한_검색_건수도_같다(cars, get, extra):
    c = get.client
    n_j = c.get(f"/api/vehicles/count?judgment={JQ}{extra}", headers=_PUB).json()["total"]
    n_b = c.get(f"/api/vehicles/count?bucket=review{extra}", headers=_PUB).json()["total"]
    ctx, _ = get(f"/vehicles?judgment={JQ}{extra}")
    assert n_j == n_b == ctx["total"], (extra, n_j, n_b, ctx["total"])


def test_다른_판정_값은_이번에_바꾸지_않았다(cars, get):
    """'유찰 대기' 등은 저장 문자열 그대로다 — 드롭다운의 뜻(저장 판정)은 Steward 결정 사항(REC-8 선택지)."""
    for j in ("유찰 대기", "시세 신뢰도 낮음, 수동 검토", "입찰 보류", "종결"):
        ctx, _ = get(f"/vehicles?judgment={quote(j)}")
        assert ctx["total"] == len(db.list_vehicles(judgment=j, hide_incomplete=True)), j
    ctx, _ = get(f"/vehicles?judgment={quote('유찰 대기')}")
    assert ctx["total"] >= 1 and {r["id"] for r in ctx["rows"]} >= {"WAIT1"}


def test_판정_필터와_칸을_같이_걸면_교집합이다(cars, get):
    same, _ = get(f"/vehicles?judgment={JQ}&bucket=review")
    none, _ = get(f"/vehicles?judgment={JQ}&bucket=wait")
    assert same["total"] == 3 and none["total"] == 0, "'지금 입찰 추천' ∩ '유찰 대기' 는 비어 있다"


# ── 사전 확인이 답을 바꾸지 않는다 · 구조 ──────────────────────────────────
def test_칸_소속_사전확인은_답을_바꾸지_않는다(cars):
    """in_lifecycle_bucket 은 저장 문자열 '입찰 검토 가능'을 review 의 필요조건으로 먼저 본다 — 칸 판정 그대로와 같아야 한다."""
    for v in cars.values():
        b = service.lifecycle_bucket_of(v, BT)
        for k in service.LIFECYCLE_BUCKETS:
            assert service.in_lifecycle_bucket(v, k, BT) == (b == k), (v["id"], k, b)
        assert service.in_judgment_filter(v, J, BT) == (b == "review"), v["id"]
        assert service.in_judgment_filter(v, "유찰 대기", BT) == (v.get("judgment") == "유찰 대기"), v["id"]


def test_구조_판정_필터는_칸과_같은_함수를_부른다():
    import web.app as A
    assert service.JUDGMENT_FILTER_BUCKETS == {J: "review"}, "칸으로 읽는 판정 값이 말없이 늘지 않게 고정한다"
    assert service.judgment_filter_bucket(J) == "review" and service.judgment_filter_bucket("유찰 대기") is None
    assert service.judgment_filter_bucket("") is None and service.judgment_filter_bucket(None) is None
    assert "in_lifecycle_bucket(" in inspect.getsource(service.in_judgment_filter)
    for fn in (A.vehicles, A.vehicles_count):
        src = inspect.getsource(fn)
        assert "judgment_filter_bucket(" in src and "in_judgment_filter(" in src, fn.__name__
        assert "_jbucket or usepick" in src, f"{fn.__name__}: 칸으로 읽는 판정 값은 파이썬 경로(축별 건수 포함)여야 한다"
    # /vehicles 는 저장 문자열을 SQL 에 넘기지 않는다(?bucket=review 와 같은 질의 → 같은 순서·페이지)
    assert "judgment=(None if _jbucket else (judgment or None))" in inspect.getsource(A.vehicles)
