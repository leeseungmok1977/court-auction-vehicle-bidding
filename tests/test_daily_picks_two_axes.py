# -*- coding: utf-8 -*-
"""홈 캐러셀은 **두 축**을 담되 섞지 않는다 — 보여줄 것을 늘리되 기준은 안 낮춘다.

2026-09-22 사용자 지적: "이 정도의 추천 매물 수준이면 앱 사용자 수를 늘릴 수 없습니다."

원인을 실측했다. 캐러셀 모수가 `judgment == '입찰 검토 가능'` 하나뿐이었고 그게 5대라
**캐러셀이 2장에서 끝났다.** 그런데 '실사용 추천'은 판정과 **별개의 축**이다 —
되팔아 남는가(재판매)와 내가 타면 싼가(실사용)는 서로 다른 질문의 답이고,
후자는 judgment 가 '유찰 대기'인 물건에도 붙는다. 두 축을 합치면 후보가 33대였다.

그래서 모수만 넓혔다. **자격은 그대로다** — `_promising`(시세 신뢰도 '높음' + 오매칭 제외)를
두 축에 똑같이 적용한다. 추천 수를 늘리려고 게이트를 푸는 것은 이 제품이 파는 정직을
스스로 깨는 일이다.

이 파일이 지키는 것:
  (1) 실사용 추천만 있어도 캐러셀이 빈손이 아니다(예전엔 0장이었다)
  (2) 카드마다 **어느 축인지** 실려 있다(섞어 놓고 한 이름으로 부르지 않는다)
  (3) 신뢰도가 '높음'이 아니면 두 축 어디로도 못 들어온다
  (4) 아침에 고른 뒤 축이 바뀐 물건은 화면에서 빠진다
"""
import json

import pytest

from web import db, service

def _blk(n, err, fail_count, median, maker="현대", model="쏘나타"):
    """pred_pool 한 덩어리 — 블록 안에서는 오차가 일정하다(층 평균을 손으로 검산하려고)."""
    return [{"err_pct": err, "maker": maker, "model": model, "fail_count": fail_count,
             "median_price": median, "actual": 30_000_000} for _ in range(n)]


# ★ pred_pool 은 **층마다 다른 값**을 내야 한다 (PANEL-46).
#   예전 픽스처는 40행 전부 `median_price=40,000,000` · `fail_count=1` · 현대 쏘나타라
#   가격대·유찰횟수·제조사 **세 층이 전부 10.0** 이었다. 층값이 같으면 `accuracy_for` 가
#   어느 층을 고르든 결과가 같아서 **가격대 층 배선을 끊어도 이 파일이 울지 않았다**
#   (실측 2026-09-23: 배선 절단 시 0 failed).
#
#   아래는 8행 블록 5개(=40행)로 축을 갈라 **여섯 층이 전부 다른 값**을 내게 한다. 손검산:
#     가격대 2,000만 이상   n=16  mae 10.0  ← 이 파일 물건(시세 3,000만·4,000만)이 고르는 층
#     가격대 1,000~2,000만  n=16  mae 10.1
#     가격대 500만 이하     n=8   mae  3.0
#     유찰 0~1회            n=16  mae  4.0     유찰 3회 이상  n=24  mae 11.7
#     제조사 국산           n=40  mae  8.6
#
#   ⚠ `2,000만 이상` 을 **10.0 에 맞춘 것은 의도**다. 고치기 전 이 파일 물건들이 받던 값이
#   10.0 이라, 그대로 둬야 `personal_use_tier`·`bid_state` 의 오차 게이트 경계가 움직이지
#   않는다(캐러셀에 무엇이 오르는지가 이 파일의 전부다). 가격대 배선을 끊으면 국산(8.6)으로
#   떨어진다 — 그게 반증 장치다.
BT_POOL = (_blk(8, 2.0, 1, 30_000_000) + _blk(8, 18.0, 3, 30_000_000)
           + _blk(8, 6.0, 1, 15_000_000) + _blk(8, 14.2, 3, 15_000_000)
           + _blk(8, 3.0, 3, 3_000_000))

# 층 → 기대 mae. 아래 자기 유효성 검사가 이 표와 대조한다(픽스처가 평평해지면 빨간불).
STRATA_EXPECTED = {("가격대", "2,000만 이상"): 10.0, ("가격대", "1,000~2,000만"): 10.1,
                   ("가격대", "500만 이하"): 3.0,
                   ("유찰횟수", "유찰 0~1회"): 4.0, ("유찰횟수", "유찰 3회 이상"): 11.7,
                   ("제조사", "국산"): 8.6}
BT = {"discount_median": 0.74, "mae_pct": 9.3, "sample": 172, "pred_n": 249,
      "within10_pct": 61, "within20_pct": 95, "history_n": 244,
      "min_premium_median": 1.13, "min_premium_by_fail": {}, "discount_by_fail": {},
      "discount_by_model": {}, "upper_hit_rate": None, "upper_n": 0,
      "actual_mae_pct": None, "actual_sample": 0, "mae_baseline_pct": 12.0,
      "model_learned": False, "comp_pool": [], "pred_pool": BT_POOL, "won_total": 0}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "p.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()

    def mk(vid, **kw):
        row = {"id": vid, "folder_key": vid, "case_no": f"2026타경{vid}", "item_no": "1",
               "court": "수원지방법원", "maker": "현대", "model": "쏘나타", "year": 2020,
               "sale_date": "2999-01-01", "status": "완료", "photo_count": 3,
               "mileage_km": 50_000, "fail_count": 1,
               "market_confidence_label": "높음", "market_confidence": 81}
        row.update(kw)
        db.upsert_vehicle(row)
        return db.get_vehicle(vid)

    return mk


def _kinds(picks):
    return {p.get("pick_kind") for p in picks}


# ── ★ 픽스처 자기 유효성 검사 (PANEL-46) ──────────────────────────────
# 모범: tests/test_panel35_hero_tone_parity.py · tests/test_personal_use.py(PANEL-39) —
# 픽스처가 그 갈래를 **실제로 만들어 내는지**를 테스트가 스스로 검사한다.

def test_픽스처의_층값이_표와_같고_층끼리_서로_다르다():
    """층끼리 같으면 accuracy_for 가 어느 층을 골라도 결과가 같다 — 공허 통과."""
    rows = {(r["group"], r["label"]): r for r in service.accuracy_strata(BT)}
    got = {k: rows[k]["mae"] for k in STRATA_EXPECTED if k in rows}
    assert got == STRATA_EXPECTED, f"층값이 표와 다르다 — pool 이나 층 경계가 바뀌었다: {got}"
    assert len(set(got.values())) == len(got), f"같은 값을 내는 층이 있다: {got}"


@pytest.mark.parametrize("med", [40_000_000, 30_000_000])
def test_이_파일_물건의_오차를_좌우하는_것은_가격대_층이다(env, med):
    """★ 반증 장치 — `accuracy_for` 후보에서 가격대를 빼면 10.0 → 제조사 국산 8.6 으로 떨어진다.

    이 단언이 없으면 `service.accuracy_for` 의 `cands.append(rows.get(("가격대", band)))`
    한 줄을 지워도 이 파일이 전부 초록이다(실측 2026-09-23: 배선 절단 시 0 failed).
    """
    v = env("ACC", min_sale_price=16_000_000, median_price=med,
            appraisal_value=30_000_000, judgment="유찰 대기")
    acc = service.accuracy_for(v, BT)
    assert acc and acc["group"] == "가격대" and acc["mae"] == 10.0, (
        f"시세 {med}: 가격대 층이 오차를 좌우하지 않는다 — 배선을 끊어도 안 울린다: {acc}")
    assert acc["label"] == "시세 2,000만 이상", f"축을 밝히는 라벨이 아니다: {acc['label']}"
    rows = {(r["group"], r["label"]): r for r in service.accuracy_strata(BT)}
    axes = [rows[("제조사", "국산")]["mae"], rows[("유찰횟수", "유찰 0~1회")]["mae"], acc["mae"]]
    assert len(set(axes)) == 3, f"두 축 이상이 같은 값이다(PANEL-46): {axes}"


def test_실사용_추천만_있어도_캐러셀이_빈손이_아니다(env):
    """★ 이것이 '추천 4대' 문제의 실체였다 — 검토 가능이 0이면 캐러셀도 0장이었다."""
    v = env("U1", min_sale_price=16_000_000, median_price=40_000_000,
            appraisal_value=30_000_000, judgment="유찰 대기")
    tier = service.personal_use_tier(v, BT)
    assert tier, "픽스처가 실사용 추천이 아니다 — 이 테스트의 전제가 깨졌다"

    picks = service.compute_daily_picks(5)
    assert picks, "실사용 추천이 있는데 캐러셀이 비었다"
    assert picks[0]["kind"] in ("now", "cheap"), f"축이 잘못 실렸다: {picks[0]}"


def test_카드마다_어느_축인지_실린다(env):
    """되팔아 남는 물건과 내가 타면 싼 물건은 **다른 질문**의 답이다. 한 이름으로 부르지 않는다."""
    env("R1", min_sale_price=10_000_000, median_price=30_000_000,
        appraisal_value=30_000_000, judgment="입찰 검토 가능", maker="기아")
    env("U1", min_sale_price=16_000_000, median_price=40_000_000,
        appraisal_value=30_000_000, judgment="유찰 대기", maker="현대")

    out = service.get_daily_picks(5)
    assert out, "픽이 하나도 없다"
    for d in out:
        assert d.get("pick_kind") in service.PICK_LABELS, (
            f"축 라벨이 없거나 모르는 값이다: {d.get('pick_kind')}")


def test_신뢰도가_높음이_아니면_두_축_어디로도_못_들어온다(env):
    """★ 보여줄 것을 늘리되 기준은 1mm도 낮추지 않는다."""
    env("LOW", min_sale_price=16_000_000, median_price=40_000_000,
        appraisal_value=30_000_000, judgment="유찰 대기",
        market_confidence_label="보통", market_confidence=52)

    picks = service.compute_daily_picks(5)
    assert not picks, f"신뢰도 '보통'인 물건이 캐러셀에 올라왔다: {picks}"


def test_오차보다_작은_이득은_캐러셀에_못_올라온다(env):
    """★ 자기검사가 아니라 **제품 동작** 가드다 (PANEL-46). 이 파일의 주제 그대로 —
    보여줄 것을 늘리되 기준은 1mm도 낮추지 않는다.

    시세 4,000만 · 최저 2,975만 물건은 최저가 기준 이득이 있지만 그 이득이 **이 유형의
    실측 오차(가격대 층 10.0%)보다 작다.** `accuracy_for` 후보에서 가격대를 빼면 오차가
    제조사 국산(8.6%)으로 작아져 같은 물건이 캐러셀 첫 화면에 올라온다 — 데이터가 좋아진
    게 아니라 **덜 본 것**인데 추천 수만 늘어난다.
    ⚠ 경계값이다. 뒤집히는 최저매각가 구간은 이 파일 BT 기준 실측 29,600,000~29,950,000
    (폭 35만)이고 아래 값은 그 한가운데다. 같은 성격의 가드가 `test_dashboard_link_parity`
    에도 있는데 거기는 2,950만이다 — BT 의 `min_premium_by_fail` 이 달라 예상낙찰가가
    다르기 때문이다(그 파일 값을 여기 복사하지 말 것).
    """
    v = env("BRD", min_sale_price=29_750_000, median_price=40_000_000,
            appraisal_value=40_000_000, judgment="유찰 대기")
    assert service.accuracy_for(v, BT)["mae"] == 10.0, "전제: 이 물건의 오차는 가격대 층 10.0"
    assert service.personal_use_tier(v, BT) is None, (
        "오차보다 작은 이득을 '실사용 추천'으로 올렸다 — 가격대 층 배선이 끊겼는지 보라")
    assert not service.compute_daily_picks(5), (
        "오차를 못 넘는 물건이 홈 첫 화면 캐러셀에 올라왔다")


def test_아침에_고른_뒤_축이_바뀌면_화면에서_빠진다(env):
    """판정은 한 곳에서만 한다 — 저장된 id를 그대로 믿고 띄우면 화면이 옛말을 한다."""
    env("R1", min_sale_price=10_000_000, median_price=30_000_000,
        appraisal_value=30_000_000, judgment="입찰 검토 가능")
    db.set_setting("daily_picks_ids", json.dumps([{"id": "R1", "kind": "resale"}]))
    import datetime
    db.set_setting("daily_picks_date", datetime.date.today().isoformat())
    assert service.get_daily_picks(5), "정상 상태인데 픽이 비었다"

    db.upsert_vehicle({"id": "R1", "judgment": "유찰 대기"})     # 축이 바뀌었다
    assert not service.get_daily_picks(5), "재판매 축이 아닌데 '되팔아도 남음'으로 남아 있다"


def test_사지_말라고_판정한_물건은_캐러셀에_없다(env):
    """★ 실제로 홈 첫 화면에 올라 있었다 — 시동 불가 카니발이 '되팔아도 남음'으로.

    judgment 는 '입찰 검토 가능'인데 bid_state 는 stop 이었다. `_promising` 이 시세
    신뢰도만 보고 판정을 안 봤기 때문이다. 더 나쁜 건 코드가 **이미 알고 있었다**는 점이다 —
    `_pick_dict` 는 tone=stop 이면 할인 배지를 안 붙이므로, 같은 카드가 "추천"이라 말하면서
    "싸다"는 말은 삼키는 모순 상태로 진열됐다.

    같은 날 '지금 입찰 추천' 칸에서 고친 것과 같은 계열이고, 경매는 취소가 안 된다.
    """
    v = env("STOP1", min_sale_price=10_000_000, median_price=30_000_000,
            appraisal_value=30_000_000, judgment="입찰 검토 가능", runnable="no")
    tone = (service.bid_state(v, BT) or {}).get("tone")
    assert tone == "stop", f"픽스처가 stop 이 아니다(tone={tone}) — 이 테스트의 전제가 깨졌다"

    picks = service.compute_daily_picks(5)
    assert not any(p["id"] == "STOP1" for p in picks), (
        "사지 말라고 판정한 물건이 홈 첫 화면 캐러셀에 올라왔다")


def test_아침에_저장된_것이라도_stop_이면_화면에_안_띄운다(env):
    """★ 게이트를 고르는 쪽에만 걸면 **저장분이 하루를 버틴다.**

    2026-09-22 실측: 새로 계산하면 시동 불가 카니발이 빠지는데, 오늘 아침 저장분을 읽는
    경로에는 그대로 3번에 남아 있었다. 고치고 배포해도 캐시가 만료될 때까지 첫 화면에
    계속 떴을 것이다 — 두 경로에 같은 게이트를 건다.
    """
    import datetime
    v = env("STOP2", min_sale_price=10_000_000, median_price=30_000_000,
            appraisal_value=30_000_000, judgment="입찰 검토 가능", runnable="no")
    assert (service.bid_state(v, BT) or {}).get("tone") == "stop", "픽스처 전제가 깨졌다"

    db.set_setting("daily_picks_ids", json.dumps([{"id": "STOP2", "kind": "resale"}]))
    db.set_setting("daily_picks_date", datetime.date.today().isoformat())

    assert not service.get_daily_picks(5), (
        "아침에 저장된 stop 물건이 캐시 경로로 첫 화면에 올라왔다")


def test_예상가가_상한을_넘으면_카드가_그_사실을_말한다(env):
    """★ '싸게 낙찰되면 이득'은 **조건부** 판정이다 — 상한만 적으면 카드가 자기모순이 된다.

    2026-09-22 운영 실측: 쏘렌토가 상한 770만인데 예상낙찰가가 820만이었다. 카드는
    "770만까지 쓰면 이득"이라 말하면서 바로 아래에서 "예상낙찰가 8,200,000"을 보여주고,
    우상단엔 "시세보다 −25%" 배지까지 붙어 있었다. 세 표시가 한 카드에서 서로 다른 말을 한다.

    목록 카드는 title 로 "예상 경쟁가는 그 위라 낙찰 가능성은 낮습니다"를 말한다. 그런데
    캐러셀을 스와이프하는 사람은 툴팁을 열지 않는다 — 첫 화면에서도 관계를 말해야 한다.
    """
    from pathlib import Path
    tpl = (Path(__file__).resolve().parents[1] / "web" / "templates" / "dashboard.html"
           ).read_text(encoding="utf-8")
    assert "expected_win > v.max_bid" in tpl, (
        "예상가와 상한을 비교하는 조건이 사라졌다 — 조건부 판정이 확정 추천처럼 읽힌다")
    assert "예상가는 그 위" in tpl, "상한을 넘는다는 사실이 카드에서 사라졌다"
    assert "낙찰 가능성은 낮습니다" in tpl, "목록과 같은 설명이 캐러셀에서 사라졌다"


def test_옛_저장형식도_읽는다(env):
    """형식을 바꾸기 전 저장분은 id 문자열 리스트다 — 배포 직후 하루치가 깨지면 안 된다."""
    env("R1", min_sale_price=10_000_000, median_price=30_000_000,
        appraisal_value=30_000_000, judgment="입찰 검토 가능")
    import datetime
    db.set_setting("daily_picks_ids", json.dumps(["R1"]))       # 옛 형식
    db.set_setting("daily_picks_date", datetime.date.today().isoformat())

    out = service.get_daily_picks(5)
    assert len(out) == 1, "옛 형식을 못 읽어 픽이 사라졌다"
    assert out[0]["pick_kind"] == "resale", "옛 저장분은 재판매 축으로 봐야 한다"
