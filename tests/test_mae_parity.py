# -*- coding: utf-8 -*-
"""오차 수치가 **화면마다 다른 숫자로 인쇄되지 않는가** — 반올림 금지를 전 화면에 고정.

2026-09-22 에 같은 결함을 한 번 고쳤다. 그때는 `/landing` 만 반올림해
±9% vs ±9.3% 로 갈렸고(`tests/test_landing_parity.py`), `app.py:445` 에
`# round() 금지 — 적중률 페이지와 같은 표기여야 한다` 주석을 남겼다.

**그런데 그 테스트는 `/landing` 만 지켰다.** 그래서 같은 위반이 감시 밖에서 재발했다 —
2026-09-23 주간 패널 7회차에서 **4인 전원**이 독립적으로 같은 결함을 지적했다:

    상세   실측 오차 ±8.8%   /  같은 화면 실입찰 ±9%      (|round|int)
    리포트 실측 평균오차 ±9.5% /  같은 문서 예측 오차 ±10%  (|round|int)

원인은 값이 다른 게 아니라 **같은 값을 두 가지로 반올림한 것**이다. 실제로
`expected.mae` 와 `expected.acc.mae` 는 상세에서 같은 값이고(`app.py:781`),
`backtest.mae_pct` 는 `service.py:3249` 에서 이미 소수 1자리로 정리돼 나온다.

★ 이 파일은 **두 겹**으로 막는다.
  ① 렌더 검사 — 실제 화면에 반올림된 형태가 찍히지 않는지.
  ② 소스 검사 — 템플릿에서 오차 변수에 `|round` 를 붙이는 것 자체를 금지.
  ①만 두면 내가 열어 보지 않은 화면에서 또 샌다. 5회차 교훈이 그것이었다 —
  "468개가 전부 초록인 채로 사보타주 2건이 통과했다."
"""
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

TPL = Path(__file__).resolve().parents[1] / "web" / "templates"

# 소수 1자리 값을 일부러 쓴다 — 정수로 반올림되면 9.3 → 9 로 눈에 띄게 갈린다.
BT = {"discount_median": 0.74, "mae_pct": 9.3, "sample": 172, "pred_n": 249,
      "within10_pct": 61, "within20_pct": 95, "history_n": 244,
      "min_premium_median": 1.13, "min_premium_by_fail": {}, "discount_by_fail": {},
      "discount_by_model": {}, "upper_hit_rate": None, "upper_n": 0,
      "actual_mae_pct": None, "actual_sample": 0, "mae_baseline_pct": 12.0,
      "model_learned": False, "comp_pool": [], "pred_pool": [], "won_total": 0}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db, service
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "d.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    base = {"court": "수원지방법원", "maker": "현대", "model": "쏘나타", "item_no": "1",
            "year": 2020, "sale_date": "2999-01-01", "status": "완료", "fail_count": 1,
            "photo_count": 3, "mileage_km": 50_000}
    for r in [
        dict(base, id="A1", case_no="2026타경1", min_sale_price=16_000_000,
             median_price=40_000_000, market_confidence_label="높음", judgment="유찰 대기"),
        dict(base, id="A2", case_no="2026타경2", min_sale_price=20_000_000,
             median_price=30_000_000, market_confidence_label="높음",
             judgment="입찰 검토 가능"),
    ]:
        db.upsert_vehicle(r)
    from web.app import app
    # ★ with(lifespan) 를 쓰지 않는다 — 켜면 백필 데몬 스레드가 join 없이 살아남아
    #   monkeypatch 해제 뒤 운영 DB(data/auction.db) 에 쓴다(2026-09-23).
    #   이 파일은 startup 산출물에 의존하지 않는다(init_db 는 위에서 직접 호출).
    yield TestClient(app)


# 오차를 말하는 자리에 붙는 라벨. 이 라벨 주변의 ± 만 본다 —
# ⚠ 아무 ± 나 집으면 안 된다. 화면에는 저감률·표본편차 같은 다른 ± 가 있고,
#   2026-09-22 에 실제로 '±30%'를 오차로 잘못 집은 적이 있다.
_ROUNDED = re.compile(r"±\s*9\s*%")          # 9.3 이 정수로 뭉개진 형태
_EXACT = "±9.3%"

PAGES = ["/", "/vehicles", "/landing", "/accuracy", "/vehicle/A2", "/vehicle/A2/report"]


@pytest.mark.parametrize("path", PAGES)
def test_반올림된_오차가_화면에_찍히지_않는다(client, path):
    """±9.3% 를 ±9% 로 뭉개 찍으면 같은 값이 화면마다 다른 숫자가 된다."""
    r = client.get(path)
    assert r.status_code == 200, f"{path} 가 {r.status_code}"
    hit = _ROUNDED.search(r.text)
    assert not hit, (
        f"{path} 에 반올림된 오차 '{hit.group(0) if hit else ''}' 가 있다 — "
        f"실제 값은 {_EXACT} 다. 같은 값을 화면마다 다르게 말하면 안 된다")


def test_적중률_페이지는_정확한_값을_말한다(client):
    """기준이 되는 화면이 원값을 말하는지부터 고정한다."""
    acc = client.get("/accuracy").text
    m = re.search(r"평균 오차.{0,200}?±([\d.]+)", acc, re.S)
    assert m, "적중률 페이지에서 '평균 오차' 타일을 찾지 못했다"
    assert m.group(1) == str(BT["mae_pct"]), (
        f"적중률이 ±{m.group(1)}% 라고 한다 — 실제 {BT['mae_pct']}% 다")


# ── ② 소스 검사 — 렌더로 안 열어 본 화면까지 막는다 ────────────────────────
_MAE_VAR = re.compile(r"(?:mae_pct|expected\.mae|expected\.acc\.mae|report\.mae"
                      r"|actual_mae_pct|\bmae\b)\s*\|\s*round")


def test_템플릿이_오차에_round_필터를_붙이지_않는다():
    """★ 이게 재발을 막는 진짜 장치다.

    2026-09-22 에 `/landing` 하나를 고치고 테스트도 `/landing` 만 지켰더니,
    같은 위반이 detail·report·dashboard·vehicles 네 곳에서 감시 밖으로 재발했다
    (7회차 패널 4인 전원 지적). 화면을 하나씩 열어 보는 방식으로는 또 샌다.
    """
    bad = []
    for f in sorted(TPL.glob("*.html")):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if _MAE_VAR.search(line):
                bad.append(f"{f.name}:{i}")
    assert not bad, (
        "오차 변수에 |round 가 붙어 있다 — 화면마다 다른 숫자가 된다: " + ", ".join(bad)
        + "  (근거: app.py 의 'round() 금지 — 적중률 페이지와 같은 표기여야 한다')")


_FAKE_FALLBACK = re.compile(r"(?:mae|mae_pct|report\.mae)[^%{}]{0,40}else\s+30\b")


def test_오차가_없을_때_30이라는_숫자를_지어내지_않는다():
    """★ 표본이 없으면 '미산출'이 옳다 — 이 제품의 원칙이다.

    2026-09-23 주간 패널 7회차 지적(PANEL-07). `{{ report.mae if report.mae else 30 }}`
    같은 폴백이 리포트 음영 범례·참고 정확도·면책문과 목록 표 머리글에 있었다.
    값이 없을 때 **실측이 아닌 30%가 정확도인 양** 인쇄된다.

    ⚠ 렌더 검사로는 못 잡는다 — 그 분기는 시세가 없는 물건에서만 열리는데
      테스트 픽스처는 항상 시세를 준다. 그래서 **소스에서 금지**한다.
      실제로 나는 조사 결과가 준 목록(4곳)만 믿고 전수 검색을 건너뛰었다가
      한 곳을 놓칠 뻔했다. 사람이 세지 말고 테스트가 세게 한다.
    """
    bad = []
    for f in sorted(TPL.glob("*.html")):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if _FAKE_FALLBACK.search(line):
                bad.append(f"{f.name}:{i}")
    assert not bad, (
        "오차가 없을 때 30% 를 지어내 찍는 폴백이 있다: " + ", ".join(bad)
        + "  — 값이 없으면 '미산출'로 적는다(표본이 없으면 미산출이 옳다)")
