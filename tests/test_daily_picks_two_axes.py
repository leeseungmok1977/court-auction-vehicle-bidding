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

BT_POOL = [{"err_pct": 8.0 + (i % 5), "maker": "현대", "model": "쏘나타",
            "fail_count": 1, "median_price": 40_000_000, "actual": 30_000_000}
           for i in range(40)]
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
