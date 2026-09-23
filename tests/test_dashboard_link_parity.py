"""대시보드에 적힌 숫자 = 그 숫자를 누르면 나오는 목록 건수.

2026-09-12 2회차 패널(앱품질 지적 3) 실측 — 세 곳이 어긋나 있었다:
  헤더 "총 1320대 모니터링"  → 목록 1167건   (total_vehicles()가 COUNT(*)라 숨김 물건 포함)
  카드 "유찰 대기 387대"     → 목록 469건    (카드는 usepick을 뺐는데 링크는 안 뺌)
  링크 "기타·미분석 181대"   → 목록 1320건   (?all=1이 전체 목록이었음)

1회차에 count API만 고치고 대시보드 헤더를 안 고쳐 같은 거짓말이 남았다. 그래서 이번엔
**링크를 실제로 따라가 세는** 테스트를 만든다 — 숫자만 맞추는 수정으로는 통과하지 않는다.
"""
import re

import pytest
from starlette.testclient import TestClient


def _blk(n, err, fail_count, median, maker="현대", model="쏘나타"):
    """pred_pool 한 덩어리 — 블록 안에서는 오차가 일정하다(층 평균을 손으로 검산하려고)."""
    return [{"err_pct": err, "maker": maker, "model": model, "fail_count": fail_count,
             "median_price": median, "actual": 30_000_000} for _ in range(n)]


# ★ pred_pool 은 **층마다 다른 값**을 내야 한다 (PANEL-46).
#   예전 픽스처는 40행 전부 `median_price=40,000,000` · `fail_count=1` · 현대 쏘나타라
#   가격대·유찰횟수·제조사 **세 층이 전부 10.0** 이었다. 층값이 같으면 `accuracy_for` 가
#   어느 층을 고르든 결과가 같아서 **가격대 층 배선(service.accuracy_for 의 `("가격대", band)`
#   후보)을 끊어도 이 파일과 이 BT 를 빌려 쓰는 7개 모듈이 하나도 울지 않는다.**
#   실측(2026-09-23): 배선을 끊고 이 파일을 돌리면 **16건 전부 초록**이었고, 세 공허 파일을
#   함께 돌려도 45 passed / 0 failed 였다. 전체 스위트로는 12 failed 가 났는데 그 12건은
#   전부 PANEL-39 가 고친 `test_personal_use` 계열이고 이 파일 쪽은 **0건**이었다.
#
#   아래는 8행 블록 6개(=48행)로 축을 갈라 **일곱 층이 전부 다른 값**을 내게 한다. 손검산:
#     가격대 2,000만 이상   n=16  mae 10.0  ← 이 파일의 시세 4,000만 물건이 고르는 층
#     가격대 1,000~2,000만  n=16  mae 10.1  ← 시세 1,300만 물건이 고르는 층
#     가격대 500만 이하     n=16  mae  5.0
#     유찰 0~1회            n=16  mae  4.0     유찰 3회 이상  n=32  mae 10.6
#     제조사 국산           n=40  mae  8.6     제조사 수입    n=8   mae  7.0
#
#   ⚠ `2,000만 이상` 을 **10.0 에 맞춘 것은 의도**다. 고치기 전 `accuracy_for` 가 이 파일
#   물건들에 내주던 값이 10.0(세 층이 전부 10.0인 동점 → 첫 후보 '제조사')이라, 그대로 둬야
#   버킷 분류(usepick/wait/lowconf)와 이 BT 를 빌려 쓰는 7개 모듈의 오차 게이트 경계가
#   움직이지 않는다. 실측으로 확인했다 — 고치기 전후 `lifecycle_partition()` 이
#   total 66 / usepick 22 / wait 23 / lowconf 21 로 **동일**하다.
#   1,300만 층만 10.1 로 **일부러 0.1 벌려** 두 가격대 층끼리도 구분되게 했다(경계가 바뀌면
#   그 0.1 이 아니라 층 자체가 바뀌므로 아래 자기 유효성 검사가 먼저 운다).
#
#   ⚠ 행 수를 48 로 둔 것도 의도다. `_ACC_STRATA` 메모 키는 `(sample, len(pred_pool), mae_pct)`
#   인데 `test_personal_use.BT` 가 `(172, 40, 9.2)` 라 40행으로 두면 **키가 같은데 층값이 다른**
#   BT 가 둘이 된다(PANEL-39 가 conftest 로 막아 뒀지만, 애초에 성립하지 않게 해 둔다).
PRED_POOL = (_blk(8, 2.0, 1, 30_000_000) + _blk(8, 18.0, 3, 30_000_000)
             + _blk(8, 6.0, 1, 15_000_000) + _blk(8, 14.2, 3, 15_000_000)
             + _blk(8, 3.0, 3, 3_000_000) + _blk(8, 7.0, 3, 3_000_000, "BMW", "520d"))

# 층 → 기대 mae. 아래 자기 유효성 검사가 이 표와 대조한다(픽스처가 평평해지면 빨간불).
STRATA_EXPECTED = {("가격대", "2,000만 이상"): 10.0, ("가격대", "1,000~2,000만"): 10.1,
                   ("가격대", "500만 이하"): 5.0,
                   ("유찰횟수", "유찰 0~1회"): 4.0, ("유찰횟수", "유찰 3회 이상"): 10.6,
                   ("제조사", "국산"): 8.6, ("제조사", "수입"): 7.0}

# 대시보드 템플릿이 참조하는 키까지 채운다(실제 backtest_stats() 반환 키 기준).
BT = {"discount_median": 0.74, "mae_pct": 9.2, "sample": 172,
      "min_premium_median": 1.13, "min_premium_by_fail": {"0": 1.20, "1": 1.13, "2+": 1.06},
      "min_premium_p25": 1.05, "min_premium_p75": 1.22,
      "discount_p25": 0.62, "discount_p75": 0.86, "discount_by_fail": {}, "discount_by_model": {},
      "upper_hit_rate": None, "upper_n": 0, "within10_pct": 62, "within20_pct": 96,
      "actual_mae_pct": None, "actual_sample": 0, "mae_baseline_pct": 12.0,
      "history_n": 0, "model_learned": False, "pred_n": 40, "comp_pool": [],
      # accuracy_for()가 층별 오차를 내려면 실제 표본이 필요하다 — 빈 리스트면
      # 추천 게이트가 "오차를 모르면 추천하지 않는다"로 막아 픽스처가 전부 빠진다.
      # 층별로 다른 값을 내는 pool 이어야 하는 이유는 PRED_POOL 주석 참조(PANEL-46).
      "pred_pool": PRED_POOL,
      "won_total": 0}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db, service
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "d.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    base = {"court": "수원지방법원", "maker": "현대", "model": "쏘나타", "item_no": "1",
            "year": 2020, "sale_date": "2999-01-01", "status": "완료", "fail_count": 1}
    rows = [
        # 소매보다 싼 실사용 추천(유찰 대기지만 usepick으로 빠져야 함)
        dict(base, id="U1_1", case_no="2026타경11", min_sale_price=16000000,
             appraisal_value=30000000, median_price=40000000,
             market_confidence_label="높음", judgment="유찰 대기"),
        # '싸게 낙찰되면 이득'(2026-09-13 두 번째 갈래) — 카드 소계·링크 건수가 같아야 한다
        dict(base, id="C1_1", case_no="2026타경19", min_sale_price=28000000,
             appraisal_value=38000000, median_price=40000000,
             market_confidence_label="높음", judgment="유찰 대기"),
        # 순수 유찰 대기(비싸서 추천 아님)
        dict(base, id="W1_1", case_no="2026타경12", min_sale_price=39000000,
             appraisal_value=40000000, median_price=40000000,
             market_confidence_label="높음", judgment="유찰 대기"),
        dict(base, id="R1_1", case_no="2026타경13", min_sale_price=10000000,
             appraisal_value=12000000, median_price=13000000,
             market_confidence_label="높음", judgment="입찰 검토 가능"),
        dict(base, id="L1_1", case_no="2026타경14", min_sale_price=10000000,
             appraisal_value=12000000, median_price=13000000,
             market_confidence_label="낮음", judgment="시세 신뢰도 낮음, 수동 검토"),
        # 기일이 지난 '입찰 검토 가능' — 목록 필터는 빼는데 버킷이 안 빼면
        # 카드 34 / 링크 17처럼 갈린다(실제로 그렇게 갈렸다).
        dict(base, id="P1_1", case_no="2026타경18", min_sale_price=10000000,
             appraisal_value=12000000, median_price=13000000, sale_date="2020-01-01",
             market_confidence_label="높음", judgment="입찰 검토 가능"),
        # 시세 비교 대상 아님(건설기계) — 전에는 '신뢰도 낮음'에 섞여 보이지 않았다
        dict(base, id="NM1_1", case_no="2026타경20", model="굴착기",
             min_sale_price=10000000, appraisal_value=12000000,
             judgment="시세 신뢰도 낮음, 수동 검토"),
        dict(base, id="O1_1", case_no="2026타경15", min_sale_price=10000000,
             appraisal_value=12000000, judgment="입찰 보류", accident_grade="flood"),
        dict(base, id="O2_1", case_no="2026타경16", min_sale_price=10000000,
             appraisal_value=12000000, judgment="미분석", status="미분석"),
        dict(base, id="N1_1", case_no="2026타경17", min_sale_price=10000000,
             appraisal_value=12000000, median_price=13000000,
             market_confidence_label="높음", judgment="종결", auction_result="낙찰",
             winning_price=11000000),
    ]
    # 페이지네이션이 실제로 생기도록 '유찰 대기'를 페이지 크기 이상으로 채운다
    # (물건이 적으면 페이지 링크가 없어 아래 테스트가 조용히 공허해진다)
    for i in range(20):
        rows.append(dict(base, id=f"WB{i}_1", case_no=f"2026타경9{i:03d}",
                         min_sale_price=39000000, appraisal_value=40000000,
                         median_price=40000000, market_confidence_label="높음",
                         judgment="유찰 대기"))
        rows.append(dict(base, id=f"LB{i}_1", case_no=f"2026타경8{i:03d}",
                         min_sale_price=10000000, appraisal_value=12000000,
                         median_price=13000000, market_confidence_label="낮음",
                         judgment="시세 신뢰도 낮음, 수동 검토"))
        # 절감액이 층 오차를 넘어야 '실사용 추천'에 든다(5회차 유의성 게이트)
        rows.append(dict(base, id=f"UB{i}_1", case_no=f"2026타경7{i:03d}",
                         min_sale_price=16000000, appraisal_value=30000000,
                         median_price=40000000, market_confidence_label="높음",
                         judgment="유찰 대기"))
    for r in rows:
        db.upsert_vehicle(r)
    import web.app as A
    return TestClient(A.app)


_PUBLIC = {"x-forwarded-for": "203.0.113.7"}


def _list_count(client, href: str) -> int:
    """목록 페이지가 스스로 보고하는 총건수를 읽는다."""
    r = client.get(href, headers=_PUBLIC)
    assert r.status_code == 200, f"{href} → {r.status_code}"
    m = re.search(r'id="listCount"[^>]*>\s*([\d,]+)', r.text)
    if m:
        return int(m.group(1).replace(",", ""))
    m = re.search(r"총\s*<b[^>]*>([\d,]+)</b>\s*건", r.text)
    assert m, f"{href}: 목록 건수를 못 찾음"
    return int(m.group(1).replace(",", ""))


# ── ★ 픽스처 자기 유효성 검사 (PANEL-46) ──────────────────────────────
# 모범: tests/test_panel35_hero_tone_parity.py · tests/test_personal_use.py(PANEL-39) —
# 픽스처가 그 갈래를 **실제로 만들어 내는지**를 테스트가 스스로 검사한다. 다음 사람이
# pred_pool 을 조용히 평평하게 되돌리면 아래가 먼저 빨간불이 된다.

def test_픽스처의_층값이_표와_같고_층끼리_서로_다르다():
    """층끼리 같으면 accuracy_for 가 어느 층을 골라도 결과가 같다 — 공허 통과."""
    from web import service
    rows = {(r["group"], r["label"]): r for r in service.accuracy_strata(BT)}
    got = {k: rows[k]["mae"] for k in STRATA_EXPECTED if k in rows}
    assert got == STRATA_EXPECTED, f"층값이 표와 다르다 — pool 이나 층 경계가 바뀌었다: {got}"
    assert len(set(got.values())) == len(got), f"같은 값을 내는 층이 있다: {got}"


@pytest.mark.parametrize("vid,mae,label", [
    ("U1_1", 10.0, "시세 2,000만 이상"),     # 시세 4,000만 — usepick 갈래
    ("W1_1", 10.0, "시세 2,000만 이상"),     # 시세 4,000만 — wait 갈래
    ("R1_1", 10.1, "시세 1,000~2,000만"),    # 시세 1,300만 — review 갈래
])
def test_이_파일_물건의_오차를_좌우하는_것은_가격대_층이다(client, vid, mae, label):
    """★ 반증 장치 — `accuracy_for` 후보에서 가격대를 빼면 제조사 국산(8.6)으로 떨어진다.

    이 단언이 없으면 `service.accuracy_for` 의 `cands.append(rows.get(("가격대", band)))`
    한 줄을 지워도 이 파일은 전부 초록이다(실측 2026-09-23: 이 파일 16 passed·0 failed,
    이 BT 를 빌려 쓰는 7개 모듈까지 합쳐도 이 파일발 실패는 0건).
    """
    from web import db, service
    v = db.get_vehicle(vid)
    acc = service.accuracy_for(v, BT)
    assert acc and acc["group"] == "가격대" and acc["mae"] == mae, (
        f"{vid}: 가격대 층이 오차를 좌우하지 않는다 — 배선을 끊어도 안 울린다: {acc}")
    assert acc["label"] == label, f"{vid}: 축을 밝히는 라벨이 아니다: {acc['label']}"
    # 이 물건이 닿는 세 축이 전부 달라야 '가격대를 골랐다'가 의미를 갖는다
    rows = {(r["group"], r["label"]): r for r in service.accuracy_strata(BT)}
    axes = [rows[("제조사", "국산")]["mae"], rows[("유찰횟수", "유찰 0~1회")]["mae"], acc["mae"]]
    assert len(set(axes)) == 3, f"{vid}: 두 축 이상이 같은 값이다(PANEL-46): {axes}"


def test_오차가_이득을_덮으면_추천_버킷에_못_들어온다():
    """★ 자기검사가 아니라 **제품 동작** 가드다 (PANEL-46).

    이 파일의 기존 버킷 단언은 전부 `카드 숫자 == 링크를 눌러 센 수` 형태라, 분류가
    통째로 움직여도 양쪽이 같이 움직여 **구조적으로 오차에 둔감하다**. 그래서 오차
    게이트 자체를 여기서 한 건 고정한다.

    시세 4,000만 · 최저 2,950만 물건은 최저가 기준 이득이 있지만 그 이득이 **이 유형의
    실측 오차(가격대 층 10.0%)보다 작다.** 추천하지 않는 것이 맞다. 가격대 배선을 끊으면
    오차가 제조사 국산(8.6%)으로 **작아져** 같은 물건이 '싸게 낙찰되면 이득'으로 올라온다 —
    근거가 약해진 게 아니라 **근거를 덜 보게 된 것**인데 화면은 더 후하게 말한다.
    ⚠ 경계값이다. 뒤집히는 최저매각가 구간은 이 파일 BT 기준 실측
    29,320,000~29,710,000(폭 39만)이고 아래 값은 그 한가운데다. 같은 성격의 가드가
    `test_daily_picks_two_axes` 에도 있는데 거기는 2,975만이다 — BT 의
    `min_premium_by_fail` 이 달라 예상낙찰가가 다르기 때문이다(값을 서로 복사하지 말 것).
    """
    from web import service
    v = dict(court="수원지방법원", maker="현대", model="쏘나타", year=2020,
             sale_date="2999-01-01", status="완료", fail_count=1,
             min_sale_price=29_500_000, appraisal_value=40_000_000,
             median_price=40_000_000, market_confidence_label="높음",
             judgment="유찰 대기")
    assert service.accuracy_for(v, BT)["mae"] == 10.0, "전제: 이 물건의 오차는 가격대 층 10.0"
    assert service.personal_use_tier(v, BT) is None, (
        "오차보다 작은 이득을 '실사용 추천'으로 올렸다 — 가격대 층 배선이 끊겼는지 보라")
    assert service.lifecycle_bucket_of(v, BT) != "usepick"


def test_partition_sums_to_total(client):
    from web import service
    lc = service.lifecycle_partition()
    assert (lc["won"] + lc["review"] + lc["usepick"] + lc["wait"] + lc["nomarket"]
            + lc["lowconf"] + lc["other"]) == lc["total"]


@pytest.mark.parametrize("key,href", [
    ("usepick", "/vehicles?usepick=1"),
    ("usepick_now", "/vehicles?usepick=now"),
    ("usepick_cheap", "/vehicles?usepick=cheap"),
    ("wait", "/vehicles?bucket=wait"),
    ("nomarket", "/vehicles?bucket=nomarket"),
    ("lowconf", "/vehicles?bucket=lowconf"),
    ("other", "/vehicles?bucket=other"),
    # 2026-09-21: 카드는 bid_state 기준 버킷으로 세는데 링크가 judgment 컬럼으로 열어
    # 카드 10 / 목록 12 로 갈렸다. 링크도 같은 필터(bucket)를 타게 바꿨다.
    ("review", "/vehicles?bucket=review&sort=expected"),
])
def test_card_number_equals_what_the_link_opens(client, key, href):
    from web import service
    assert service.lifecycle_partition()[key] == _list_count(client, href), (
        f"카드 '{key}' 값과 링크 {href} 결과가 다르다")


def test_header_total_equals_default_list(client):
    from web import service
    assert service.lifecycle_partition()["total"] == _list_count(client, "/vehicles")


def test_count_api_agrees_with_the_list(client):
    """저장한 검색 알림이 쓰는 count API도 같은 모수를 써야 한다."""
    for href, api in (("/vehicles?bucket=wait", "/api/vehicles/count?bucket=wait"),
                      ("/vehicles?usepick=1", "/api/vehicles/count?usepick=1"),
                      ("/vehicles?usepick=cheap", "/api/vehicles/count?usepick=cheap"),
                      ("/vehicles", "/api/vehicles/count")):
        assert client.get(api, headers=_PUBLIC).json()["total"] == _list_count(client, href), api


def test_dashboard_header_number_matches_the_list(client):
    """대시보드 헤더에 렌더된 숫자 자체를 읽어 목록과 대조한다.

    lifecycle_partition()만 고치고 대시보드 라우트의 별도 total 변수를 안 고쳐
    화면에는 그대로 1320이 남아 있었다 — 측정이 아니라 **스크린샷을 눈으로 보고** 발견했다.
    그래서 이 테스트는 함수 반환값이 아니라 렌더된 HTML을 본다."""
    import re
    html = client.get("/", headers=_PUBLIC).text
    m = re.search(r"총\s*<b[^>]*>([\d,]+)</b>\s*대\s*모니터링", html)
    assert m, "헤더 총계를 못 찾음"
    assert int(m.group(1).replace(",", "")) == _list_count(client, "/vehicles")


@pytest.mark.parametrize("href", [
    "/vehicles?bucket=wait", "/vehicles?bucket=lowconf", "/vehicles?usepick=1",
])
def test_filters_survive_pagination(client, href):
    """2페이지로 넘어가도 필터가 유지돼야 한다.

    2026-09-12 디자인 검수 블로커: 실사용 추천 22건 목록에서 '2'를 누르면
    `/vehicles?sort=recent&page=2` — 필터가 통째로 빠져 전체 1167건이 나왔다.
    카드 숫자 = 목록 건수 규칙이 1페이지에서만 지켜지고 있었다."""
    import re
    html = client.get(href, headers=_PUBLIC).text
    links = re.findall(r'href="(/vehicles\?[^"]*page=\d+[^"]*)"', html)
    key = href.split("?", 1)[1].split("=")[0]
    assert links, f"{href}: 페이지 링크가 없어 이 테스트가 공허하다 — 픽스처를 늘려야 한다"
    for ln in links:
        assert key in ln, f"페이지 링크에서 {key}가 사라짐: {ln}"


def test_filter_form_keeps_bucket_and_usepick(client):
    """'적용' 버튼(폼 제출)으로도 필터가 풀리면 안 된다."""
    for href, name in (("/vehicles?bucket=wait", "bucket"), ("/vehicles?usepick=1", "usepick")):
        html = client.get(href, headers=_PUBLIC).text
        assert f'name="{name}"' in html, f"{href}: 폼에 {name} hidden input이 없다"
