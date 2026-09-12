"""모든 판정 상태에서 상세·리포트가 실제로 렌더되는지 — 템플릿 500 방지.

2026-09-12 4회차: 전략 밴드에 `backtest.pred_n`을 참조했는데 그 변수는 리포트
컨텍스트에만 있었다. 결과는 **전략 밴드가 렌더되는 모든 상세가 HTTP 500** —
홈 추천 1번, 실사용 추천 1·2·3번이 전부 죽었다. 살아 있는 페이지는 "입찰하지
마세요"뿐이라, 이 앱이 하겠다고 한 단 하나의 일이 되는 물건만 골라서 죽은 셈이다.

기존 테스트가 못 잡은 이유는 픽스처의 backtest 표본이 비어 `win_probability`가
None을 돌려주고 템플릿이 **else 분기만** 탔기 때문이다. 그래서 이 파일은
**분기별 픽스처를 명시적으로 만들어** 전 상태를 한 번씩 렌더한다.
"""
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
      "history_n": 0, "model_learned": False, "pred_n2": 0, "pred_pool": [], "comp_pool": []}

_BASE = {"court": "수원지방법원", "maker": "현대", "model": "쏘나타", "year": 2020,
         "item_no": "1", "sale_date": "2999-01-01", "status": "완료", "fail_count": 1,
         "market_confidence": 78, "market_confidence_label": "높음", "sample_count": 12,
         "photo_count": 3}

# 상태 → 그 상태를 실제로 만들어내는 필드. 하나라도 렌더가 깨지면 실패한다.
CASES = {
    "resale":      dict(min_sale_price=10_000_000, appraisal_value=12_000_000,
                        median_price=13_000_000, upper_bid=14_000_000),
    "usepick":     dict(min_sale_price=28_000_000, appraisal_value=30_000_000,
                        median_price=40_000_000),
    "over_market": dict(min_sale_price=14_000_000, appraisal_value=16_000_000,
                        median_price=16_600_000),
    "blocked":     dict(min_sale_price=16_000_000, appraisal_value=20_000_000,
                        median_price=16_600_000),
    "flood":       dict(min_sale_price=9_000_000, appraisal_value=12_000_000,
                        median_price=13_000_000, accident_grade="flood",
                        judgment="입찰 보류"),
    "lowconf":     dict(min_sale_price=9_000_000, appraisal_value=12_000_000,
                        median_price=13_000_000, market_confidence_label="낮음",
                        market_confidence=31),
    "no_market":   dict(min_sale_price=9_000_000, appraisal_value=12_000_000,
                        median_price=None),
    "stale_floor": dict(min_sale_price=20_000_000, appraisal_value=20_000_000,
                        median_price=18_000_000),
    "past_date":   dict(min_sale_price=10_000_000, appraisal_value=12_000_000,
                        median_price=15_000_000, sale_date="2020-01-01"),
    "not_runnable": dict(min_sale_price=10_000_000, appraisal_value=12_000_000,
                         median_price=15_000_000, runnable="no"),
    "accident_many": dict(min_sale_price=10_000_000, appraisal_value=12_000_000,
                          median_price=15_000_000, accident_grade="accident",
                          insurance_history={"own_damage": 8, "opp_damage": 5}),
    "kcar_blend":  dict(min_sale_price=9_000_000, appraisal_value=11_000_000,
                        median_price=9_670_000, kcar_median=13_000_000, kcar_sample=9),
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "smoke.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    for i, (name, extra) in enumerate(CASES.items()):
        db.upsert_vehicle({**_BASE, "id": f"{name}_1", "folder_key": f"{name}_1",
                           "case_no": f"2026타경9{i:03d}", "judgment": "유찰 대기", **extra})
    import web.app as A
    return TestClient(A.app)


_PUB = {"x-forwarded-for": "203.0.113.7"}
_TUNNEL = {"host": "127.0.0.1"}


@pytest.mark.parametrize("name", list(CASES))
@pytest.mark.parametrize("suffix", ["", "/report"])
def test_detail_and_report_render(client, name, suffix):
    r = client.get(f"/vehicle/{name}_1{suffix}", headers=_PUB)
    assert r.status_code == 200, f"{name}{suffix} → {r.status_code}"
    assert "Traceback" not in r.text


@pytest.mark.parametrize("name", list(CASES))
def test_admin_view_renders_too(client, name):
    """관리자 화면은 가려진 블록이 더 많아 별도로 렌더해야 한다."""
    r = client.get(f"/vehicle/{name}_1", headers=_TUNNEL)
    assert r.status_code == 200, f"{name}(admin) → {r.status_code}"


@pytest.mark.parametrize("path", [
    "/", "/vehicles", "/vehicles?usepick=1", "/vehicles?bucket=wait",
    "/vehicles?sort=expected", "/calendar", "/courts", "/accuracy", "/watchlist",
    "/landing", "/privacy",
])
def test_all_pages_render(client, path):
    r = client.get(path, headers=_PUB)
    assert r.status_code == 200, f"{path} → {r.status_code}"


def test_every_case_actually_hits_its_state(client):
    """픽스처가 의도한 상태를 실제로 만드는지 — 아니면 이 파일 전체가 공허하다."""
    from web import db
    got = {n: service.bid_state(db.get_vehicle(f"{n}_1"), BT)["state"] for n in CASES}
    assert got["blocked"] == "blocked", got
    assert got["usepick"] in ("usepick", "resale"), got
    assert got["flood"] == "blocked", got
    assert got["lowconf"] == "lowconf", got
    assert got["past_date"] == "wait", got
    assert len(set(got.values())) >= 4, f"상태가 너무 몰려 있다: {got}"


def test_probability_branch_is_actually_rendered(client):
    """'낙찰 확률' 분기가 실제로 렌더돼야 이 파일이 500을 잡는다.

    4회차에 바로 이 분기가 렌더된 적이 없어 프로덕션 500이 나갔다."""
    html = client.get("/vehicle/usepick_1", headers=_PUB).text
    assert "낙찰 확률" in html, "확률 분기가 렌더되지 않아 500을 못 잡는다"


# ── 한글에 monospace를 걸지 않는다 (5회차 디자인 P0) ──────────────
# JetBrains Mono에는 한글 글리프가 없다. 한글이 들어간 요소에 mono를 걸면
# 글자마다 폴백이 일어나 "소 매 로  사 는  편 이  쌉 니 다"로 자간이 벌어진다.
# 큰글씨 모드에서 가장 심했다 — 접근성 옵션이 접근성을 떨어뜨렸다.
# CSS 계산값은 브라우저가 필요하므로, 여기서는 **템플릿 소스**에서 잡는다.
import pathlib
import re as _re

_TPL = pathlib.Path(__file__).resolve().parents[1] / "web" / "templates"
_HANGUL = _re.compile(r"[가-힣]")


# 한글을 담을 수 있는 변수들 — 런타임에 mono 안으로 들어가면 자간이 벌어진다
_HANGUL_VARS = ("case_no", "court", "model", "maker", "judgment", "sale_place",
                "storage_addr", "label")
_MONO_TAG = _re.compile(r"<(\w+)([^>]*?(?:font-mono|var\(--mono\))[^>]*?)>", _re.S)
_JINJA = _re.compile(r"\{\{.*?\}\}|\{%.*?%\}", _re.S)


def _mono_elements_with_hangul(path: pathlib.Path):
    """mono가 걸린 **그 요소 안**에 한글(리터럴 또는 한글 변수)이 있는지.

    요소 밖의 한글까지 세면 오탐이 쏟아진다(숫자 옆 '건'·'원' 라벨 등).
    여는 태그부터 다음 태그 시작까지의 직계 텍스트만 본다.
    """
    src = path.read_text(encoding="utf-8")
    bad = []
    for m in _MONO_TAG.finditer(src):
        inner = src[m.end():].split("<", 1)[0]
        line = src[:m.start()].count(chr(10)) + 1
        literal = _JINJA.sub("", inner)
        if _HANGUL.search(literal):
            bad.append((line, "리터럴 한글: " + literal.strip()[:40]))
            continue
        for var in _HANGUL_VARS:
            if _re.search(r"\{\{[^}]*\b" + var + r"\b", inner):
                bad.append((line, "한글 변수 " + var))
                break
    return bad

def test_case_number_is_not_monospaced():
    """사건번호는 '2026타경'이라 한글이 섞인다 — mono면 '2026타 경 30903'이 된다."""
    for f in sorted(_TPL.glob("*.html")):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if "case_no" not in line:
                continue
            if "font-mono" in line:
                raise AssertionError(f"{f.name}:{i} 사건번호에 font-mono가 걸렸다")
