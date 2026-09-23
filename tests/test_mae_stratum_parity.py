# -*- coding: utf-8 -*-
"""리포트가 **이 물건 유형**의 오차를 말하는가 — 전체 평균을 물건에 붙이지 않는가 (PANEL-01).

`accuracy_for` 독스트링이 이미 금지한 행위다:

    이 물건 **유형**의 실측 오차. 표본이 부족하면 None — 전체 평균으로 대신하지 않는다.
    전체 MAE 하나를 모든 물건에 붙이면, 표본에 없는 유형에도 정확도를 전이시키는
    과대주장이 된다(3회차 경매·중고차 지적).

그런데 리포트 라우트의 `expected` 에 `acc` 키가 없어 `report.html:892·900` 의
`{% if expected.acc %}` 두 자리가 **한 번도 안 열리는 죽은 가지**였고, 늘
`{% elif backtest.mae_pct %}`(전체평균)로 떨어졌다. 상세는 ±10.6%, 리포트는 ±8.9%.

★ 이 파일이 필요한 이유: **기존 테스트는 이 변경을 막지도 보호하지도 않는다.**
  `test_mae_parity.py` 가 지키는 불변식은 '같은 값'이 아니라 **반올림 금지**뿐이고,
  리포트를 유형별로 바꿔도 전부 초록이다. 감시 밖의 변경이었다.

★ 공허 통과 함정: `test_mae_parity.py` 픽스처는 `pred_pool: []` 이라 `accuracy_for` 가
  **항상 None** 이다. 그 상태로는 오차 문구가 아예 렌더되지 않고 그래도 통과한다.
  그래서 여기서는 pool 을 **실제로 채운다**(층 8건 이상, `ACCURACY_STRATUM_MIN_N`).
  그리고 층값(12.8)과 전체평균(9.3)을 **일부러 다르게** 둔다 — 같으면 이 테스트는
  아무것도 증명하지 못한다(오늘 `soft_cap` 에서 그 함정을 한 번 밟았다).

★ 반드시 지킬 예외: **§실측 검증 타일(`report.html:1075`)은 전체평균이 맞다.**
  그 섹션은 이 물건이 아니라 예측 전체를 말한다("예측이 실제 낙찰을 얼마나 맞혔는가").
  (섹션 이름은 2026-09-23 에 '모델 검증 실적' → '실측 검증' 으로 홈과 통일됐다 —
   이 앱에서 `모델`의 1차 의미는 예측모델이 아니라 **차명**이라 제목이 오독됐다.)
  예외 없이 '한 문서 한 값'을 강요하면 **옳은 표기를 깨뜨리는 테스트**가 된다.

⚠ ± 를 전수로 긁지 않는다. 화면에는 `동급 (연식±1·주행±30%)`(매칭 허용범위)와
  표본 편차 `±38%` 가 함께 있다. `test_landing_parity.py:93-94` 가 경고하는 함정이고,
  2026-09-23 하루에 **두 번** 밟았다. 반드시 **라벨 뒤**만 본다.
"""
import re

import pytest
from starlette.testclient import TestClient

GLOBAL_MAE = 9.3        # 전체평균 — 물건별 자리에 나오면 안 된다
STRATUM_MAE = 12.8      # 이 물건 유형(수입) — 물건별 자리에 나와야 한다

# 수입차 8건(= ACCURACY_STRATUM_MIN_N). 오차를 전부 12.8 로 둬 층 평균이 정확히 12.8.
_POOL = [{"err_pct": STRATUM_MAE, "median_price": 30_000_000, "fail_count": 0,
          "maker": "BMW", "model": "520d", "actual": 30_000_000,
          "sale_date": f"2026-08-{i:02d}"} for i in range(1, 9)]

BT = {"discount_median": 0.74, "mae_pct": GLOBAL_MAE, "sample": 172, "pred_n": 249,
      "within10_pct": 61, "within20_pct": 95, "history_n": 244,
      "min_premium_median": 1.13, "min_premium_by_fail": {}, "discount_by_fail": {},
      "discount_by_model": {}, "upper_hit_rate": None, "upper_n": 0,
      "actual_mae_pct": None, "actual_sample": 0, "mae_baseline_pct": 12.0,
      "model_learned": False, "comp_pool": [], "pred_pool": _POOL, "won_total": 0}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db, service
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "d.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    # ⚠ conftest 의 자동 픽스처가 _bt_cache·_reduction_cache·_multi_lot_cache 는 비우지만
    #   **_ACC_STRATA 는 목록에 없다.** accuracy_strata 는 (sample, len(pool), mae_pct) 로
    #   메모하므로 다른 테스트의 층이 그대로 넘어올 수 있다. 여기서 직접 끊는다.
    monkeypatch.setattr(service, "_ACC_STRATA", {"key": None, "data": None}, raising=False)
    db.init_db()
    base = {"court": "수원지방법원", "maker": "BMW", "model": "520d", "item_no": "1",
            "year": 2020, "sale_date": "2999-01-01", "status": "완료", "fail_count": 1,
            "photo_count": 3, "mileage_km": 50_000}
    db.upsert_vehicle(dict(base, id="X1", case_no="2026타경9001",
                           min_sale_price=20_000_000, median_price=30_000_000,
                           market_confidence_label="높음", judgment="입찰 검토 가능"))
    from web.app import app
    # ★ with(lifespan) 를 쓰지 않는다 — 켜면 백필 데몬 스레드가 join 없이 살아남아
    #   monkeypatch 해제 뒤 운영 DB(data/auction.db) 에 쓴다(2026-09-23).
    #   이 파일은 startup 산출물에 의존하지 않는다(init_db 는 위에서 직접 호출).
    yield TestClient(app)


def _text(html: str) -> str:
    html = re.sub(r"<(script|style).*?</\1>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


# 물건별 오차를 말하는 라벨. 라벨 **뒤**의 ± 만 본다.
_PER_VEHICLE = re.compile(r"(?:실측\s*오차|실측\s*평균오차|참고\s*정확도)\s*±\s*([\d.]+)\s*%")
# 전체 표본을 말하는 타일은 숫자가 **앞**에 온다: "±8.9% 전체 평균 오차".
# ⚠ 라벨은 2026-09-23 에 '예측 오차' → '전체 평균 오차' 로 통일됐다 — 같은 숫자(backtest.mae_pct)를
#   부르는 이름이 홈('예상낙찰가 오차')·리포트('예측 오차')·정확도('전체 평균 오차') 3종이었다.
#   또 갈리면 이 정규식이 **조용히 0건**이 되는데, 아래 테스트가 빈 집합을 실패로 잡는다.
_MODEL_WIDE = re.compile(r"±\s*([\d.]+)\s*%\s*전체\s*평균\s*오차")


def _per_vehicle(txt):
    return {float(x) for x in _PER_VEHICLE.findall(txt)}


def test_전제_층값과_전체평균이_다르다():
    """이 전제가 깨지면 아래 테스트들이 **아무것도 증명하지 못한다.**

    값이 같으면 배선이 끊겨도 전부 통과한다 — 오늘 soft_cap 테스트에서 실제로 밟은 함정이다.
    """
    assert STRATUM_MAE != GLOBAL_MAE, "층값과 전체평균이 같으면 이 파일 전체가 공허 통과다"


def test_픽스처가_유형별_오차를_실제로_만든다(client):
    """pool 이 비면 accuracy_for 가 None 이라 문구가 아예 안 뜨고 테스트가 공허해진다."""
    from web import db, service
    acc = service.accuracy_for(db.get_vehicle("X1"), BT)
    assert acc is not None, "pred_pool 을 채웠는데도 층이 안 만들어졌다 — 픽스처를 고쳐야 한다"
    assert acc["mae"] == STRATUM_MAE, f"층 오차가 {acc['mae']} — {STRATUM_MAE} 여야 한다"


def test_상세와_리포트가_같은_유형_오차를_말한다(client):
    """★ PANEL-01 의 본체. 같은 물건인데 화면마다 다른 정확도를 말하면 안 된다."""
    detail = _text(client.get("/vehicle/X1").text)
    report = _text(client.get("/vehicle/X1/report").text)
    d, r = _per_vehicle(detail), _per_vehicle(report)
    assert d, "상세에 물건별 오차 표기가 없다"
    assert r, "리포트에 물건별 오차 표기가 없다"
    assert d == r, f"상세 {sorted(d)} · 리포트 {sorted(r)} — 같은 물건인데 다른 정확도를 말한다"


def test_리포트가_물건별_자리에_전체평균을_붙이지_않는다(client):
    """`accuracy_for` 독스트링이 '과대주장'이라 못 박은 바로 그 행위."""
    report = _text(client.get("/vehicle/X1/report").text)
    vals = _per_vehicle(report)
    assert GLOBAL_MAE not in vals, (
        f"리포트가 물건별 자리에 전체평균 ±{GLOBAL_MAE}% 를 붙였다 — 이 유형은 ±{STRATUM_MAE}% 다. "
        "표본에 없는 유형에 정확도를 전이시키는 과대주장이다(service.accuracy_for 독스트링)")
    assert vals == {STRATUM_MAE}, f"물건별 오차가 {sorted(vals)} — {STRATUM_MAE} 하나여야 한다"


def test_실측_검증_타일은_전체평균이_맞다(client):
    """★ 예외 조항. 이 섹션은 이 물건이 아니라 **예측 전체**를 말한다.

    '한 문서 한 값'을 예외 없이 강요하면 **옳은 표기를 깨뜨리는 테스트**가 된다 —
    패널 처방을 그대로 따랐을 때의 개악이 정확히 그 모양이다.
    """
    report = _text(client.get("/vehicle/X1/report").text)
    wide = {float(x) for x in _MODEL_WIDE.findall(report)}
    assert wide == {GLOBAL_MAE}, (
        f"§실측 검증이 ±{sorted(wide)}% 라고 한다 — 전체평균 ±{GLOBAL_MAE}% 여야 한다. "
        "이 타일까지 유형별로 바꾸면 '예측이 실제 낙찰을 얼마나 맞혔는가'가 거짓이 된다")


def test_추정치가_없으면_오차_수치를_말하지_않는다(client):
    """없는 추정치의 정밀도를 말하지 않는다.

    2026-09-23 실측: 예상낙찰가가 안 뜨는 물건 **22건 전부**가 면책문에서
    '오차(±8.9%)가 있고' 라고 말하고 있었다. 가드가 `report.mae`(모델 전체 값)라
    이 물건에 추정치가 없어도 참이었기 때문이다.
    """
    from web import db
    db.upsert_vehicle({"id": "X2", "case_no": "2026타경9002", "court": "수원지방법원",
                       "maker": "BMW", "model": "520d", "item_no": "1", "year": 2020,
                       "sale_date": "2999-01-01", "status": "완료", "fail_count": 1,
                       "photo_count": 3, "mileage_km": 50_000,
                       "min_sale_price": 20_000_000, "median_price": None,
                       "judgment": "시세 미산출"})
    report = _text(client.get("/vehicle/X2/report").text)
    m = re.search(r"중심 추정치로 오차(\(±[\d.]+%\))?", report)
    if m:
        assert not m.group(1), (
            f"예상낙찰가가 없는 물건의 면책문이 오차 {m.group(1)} 를 말한다 — "
            "있지도 않은 추정치의 정밀도를 주장하는 것이다")
    assert not _per_vehicle(report), (
        f"예상낙찰가가 없는데 물건별 오차 {sorted(_per_vehicle(report))} 가 찍혔다")


def test_리포트_템플릿이_물건별_자리에_전체값_변수를_쓰지_않는다():
    """★ 소스 가드 — 렌더 검사만으로는 내가 안 열어 본 분기에서 재발한다.

    `report.mae` 는 `report_data()` 가 `bt["mae_pct"]`(전체평균)를 그대로 담은 값이다
    (`service.py` report_data 반환부). 물건별 오차 자리에서 이 변수를 다시 쓰면
    PANEL-01 이 그대로 되살아난다. 전체평균이 필요한 곳은 §모델 검증 실적 하나뿐이고,
    그 자리는 `backtest.mae_pct` 를 쓴다.
    """
    from pathlib import Path
    tpl = Path(__file__).resolve().parents[1] / "web" / "templates" / "report.html"
    src = tpl.read_text(encoding="utf-8")
    assert "report.mae" not in src, (
        "report.html 에 report.mae 가 돌아왔다 — 그 값은 전체평균이라 물건별 자리에 쓰면 "
        "과대주장이 된다. 물건별은 expected.acc.mae, 모델 전체는 backtest.mae_pct 를 쓴다")
