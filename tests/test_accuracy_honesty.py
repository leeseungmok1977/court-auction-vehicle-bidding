# -*- coding: utf-8 -*-
"""±10% 적중률이 왜 그 수준인지 화면이 말하는가 — 정직성 고정.

2026-09-22 사용자 지적: "10프로 이내 적중율이 너무 낮습니다."

조사 결과 이것은 산식 결함이 아니었다. 후보 예측식 11종(연속 회귀 5·2D 셀·전역
프리미엄·시세 블렌드 4·단독경쟁 혼합·최빈값)을 운영 241건에 정직한 LOO로 돌렸으나
**쌍대 부트스트랩에서 현재식을 유의하게 이긴 것이 하나도 없었다.** 자기 표본을 포함하는
반칙(과적합 상한)을 해도 ±10%는 65.6~72.6%가 한계였다.

원인은 예측 대상 자체다. 낙찰가/최저가 배수가 1.00~1.45에 퍼져 있고, ±10%를 빗나간
91건 중 **89%가 양 끝**(최저가 근처 낙찰 36건 · 경쟁 과열 45건)이었다. 그 갈림은
**응찰자 수**로 정해지는데, 법원 매각결과 응답에는 낙찰가·매각여부·최저가·유찰횟수만
오고 화면정의 8종 어디에도 응찰자수 필드가 없다(2026-09-22 실측).

그래서 숫자를 꾸미는 대신 **이유를 화면에 적었다.** 이 테스트가 지키는 것:
  (1) 이유에 쓰는 수치는 전부 실측에서 나온다 — 템플릿에 박은 숫자가 아니다
  (2) 표본이 없으면 아무 말도 하지 않는다(모르면 멈춘다)
"""
import re
from pathlib import Path

import pytest

from web import db, service

TPL = Path(__file__).resolve().parents[1] / "web" / "templates" / "accuracy.html"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("src.paths.DATA_DIR", tmp_path)
    db.init_db()
    service._bt_cache.update({"data": None, "t": 0.0, "key": None})   # 통계 캐시 무효화
    yield
    service._bt_cache.update({"data": None, "t": 0.0, "key": None})


def _won(vid, min_sale, winning, median, fail=1):
    db.upsert_vehicle({
        "id": vid, "folder_key": vid, "case_no": f"2026타경{vid}", "item_no": "1",
        "maker": "현대", "model": "쏘나타", "year": 2020, "sale_date": "2026-08-01",
        "status": "완료", "auction_result": "낙찰", "winning_price": winning,
        "median_price": median, "min_sale_price": min_sale, "fail_count": fail,
        "sample_count": 19, "market_confidence_label": "높음",
    })


def test_이유_수치는_실측에서_나온다(env):
    """배수가 한쪽에 모이지 않는다는 사실을 표본에서 직접 센다.

    단독 4건(1.00배) · 경쟁 4건(1.40배) · 가운데 4건(1.15배)을 넣으면
    solo_pct 와 compete_pct 는 각각 33% 부근이어야 한다."""
    for i in range(4):
        _won(f"S{i}", 10_000_000, 10_000_000, 14_000_000)      # 배수 1.00 — 단독
    for i in range(4):
        _won(f"C{i}", 10_000_000, 14_000_000, 20_000_000)      # 배수 1.40 — 경쟁
    for i in range(4):
        _won(f"M{i}", 10_000_000, 11_500_000, 16_000_000)      # 배수 1.15 — 가운데

    bt = service.backtest_stats()
    assert bt["pred_n"] == 12
    assert 25 <= bt["solo_pct"] <= 42, f"단독 비율이 실측과 다르다: {bt['solo_pct']}"
    assert 25 <= bt["compete_pct"] <= 42, f"경쟁 비율이 실측과 다르다: {bt['compete_pct']}"
    assert bt["solo_pct"] + bt["compete_pct"] < 100, "가운데가 사라졌다 — 경계가 잘못됐다"


def test_빗나간_건의_양끝_비율을_센다(env):
    """±10%를 벗어난 건 중 양 끝이 몇 %인지 — 화면이 주장하는 바로 그 숫자다."""
    for i in range(5):
        _won(f"S{i}", 10_000_000, 10_000_000, 14_000_000)
    for i in range(5):
        _won(f"C{i}", 10_000_000, 14_500_000, 20_000_000)

    bt = service.backtest_stats()
    assert bt["miss_n"] >= 1, "이 표본은 양 끝뿐이라 반드시 빗나간 건이 있다"
    assert bt["miss_edge_pct"] == 100, (
        f"전부 양 끝인 표본인데 {bt['miss_edge_pct']}% 로 셌다")


def test_표본이_없으면_아무_말도_하지_않는다(env):
    """낙찰 표본이 없으면 이유도 주장하지 않는다 — 템플릿이 통째로 숨는 조건이다."""
    bt = service.backtest_stats()
    assert not bt.get("miss_edge_pct"), "표본이 없는데 이유를 말하고 있다"


def test_화면이_수치를_박아두지_않는다():
    """★ 이 블록의 존재 이유가 '정직'이므로, 숫자가 하드코딩되면 의미가 반전된다."""
    html = TPL.read_text(encoding="utf-8")
    m = re.search(r"±10%를 벗어나는 건 왜 생기나.*?\{% endif %\}", html, re.S)
    assert m, "이유 블록이 사라졌다"
    block = m.group(0)
    for key in ("bt.solo_pct", "bt.compete_pct", "bt.miss_n", "bt.miss_edge_pct"):
        assert key in block, f"{key} 를 서버 실측이 아니라 다른 데서 가져온다"
    # 경계값(1.05·1.3)은 설명용 문구라 허용하되, 비율·건수로 읽히는 리터럴은 금지
    for bad in re.findall(r">\s*(\d{1,3})\s*<span[^>]*>%", block):
        pytest.fail(f"비율 {bad}% 가 화면에 박혀 있다 — 실측이어야 한다")


def test_적중_건수를_올려_말하지_않는다():
    """★ 95%를 반올림하면 '10건 중 약 10건' — **만점**이 된다(2026-09-22 디자인 검수).

    한계를 밝히는 블록 바로 위에서 과장하면 정직한 쪽이 변명처럼 보인다.
    타일 둘 다 내림이어야 한다."""
    html = TPL.read_text(encoding="utf-8")
    for pct in ("within10_pct", "within20_pct"):
        assert f"(bt.{pct}/10)|round" not in html, (
            f"{pct} 를 반올림한다 — 95%가 '약 10건'으로 부풀어 만점처럼 읽힌다")
        assert f"(bt.{pct}/10)|int" in html, f"{pct} 적중 건수 표기가 사라졌다"


def test_두_비율의_모집단을_밝힌다():
    """16%+22%(전체 기준)와 88%(빗나간 건 기준)는 분모가 다르다.

    모집단을 안 적으면 38과 88이 같은 대상으로 읽혀 '숫자가 안 맞는다'가 된다."""
    html = TPL.read_text(encoding="utf-8")
    m = re.search(r"±10%를 벗어나는 건 왜 생기나.*?\{% endif %\}", html, re.S)
    assert m, "이유 블록이 사라졌다"
    block = m.group(0)
    assert "bt.pred_n" in block, "두 비율이 '무엇 중'인지 밝히지 않는다"
    assert block.index("bt.pred_n") < block.index("bt.solo_pct"), (
        "모집단은 두 카드보다 **먼저** 나와야 한다")


def test_응찰자수를_안다고_말하지_않는다():
    """법원은 응찰자 수를 공개하지 않는다. 화면이 그걸 아는 척하면 거짓이 된다."""
    html = TPL.read_text(encoding="utf-8")
    # 어미까지 고정하면 문장을 다듬을 때마다 깨진다 — 사실이 남아 있는지만 본다
    assert "알려주지 않" in html or "공개되지 않" in html, (
        "응찰자 수를 모른다는 사실이 화면에서 사라졌다")
    assert "응찰자 수를 반영" not in html and "경쟁률을 예측" not in html
