# -*- coding: utf-8 -*-
"""등급이 내려가면 **감가율도 따라 내려가야** 한다 — 사고판정 재산정 정합.

2026-09-21 실측. 침수 오판을 고쳐 등급이 `flood` → `none` 으로 내려갔는데,
breakdown 의 `사고감가율` 은 **1.0(시세 전액)** 그대로였다. 그 결과 상한가가 음수로
잠겨 그 차는 **어떤 금액을 써도 손해**로 표시됐다(C220d: 시세 1,400만 · 상한가 −561만).

원인은 `backfill_accident_grades` 가 새 등급을 `fields` 에만 담고, 감가율을 정하는
`apply_accident_rate` 에는 **갱신 전 행 `v`** 를 넘긴 것이다 — `use_accident_rate` 는
`v["accident_grade"]` 를 보므로 옛 'flood' 를 읽어 1.0 을 돌려준다.
**등급만 바뀌고 값은 안 바뀌는** 상태였고, breakdown 의 `사고표기: 침수의심` 이 그 흔적이었다.

더 나쁜 건 고칠 기회조차 없었다는 것이다. skip 조건이 "등급·이력이 그대로면 건너뜀"인데
이미 `none` 으로 내려가 있어 **다시 돌려도 영영 건너뛴다.** `force` 를 둔 이유다.

⚠ 이 계열의 버그는 "판정은 맞는데 값이 틀린" 형태라 **화면만 보면 안 보인다.**
   등급·라벨은 정상으로 보이고 숫자만 조용히 틀린다.
"""
import json

import pytest

from web import db, service

# 운영 원문 그대로 — "전손, 도난, 침수 … 없음"(부정문). 침수가 아니다.
NOT_FLOOD_TEXT = (
    "2)보험개발원 제공 중고차 사고이력정보 보고서에 의하면 전손 보험사고,도난 보험사고,침수\n"
    "  보험사고, 특수용도 이력, 내차피해, 상대차 피해, 소유자변경, 차량번호변경 없음.\n"
    "외관 및 유리 등 전체적으로 미세한 스크래치 등이 있음."
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr("src.paths.DATA_DIR", tmp_path)
    db.init_db()

    def mk(vid, **kw):
        folder = tmp_path / vid
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "appraisal.txt").write_text(NOT_FLOOD_TEXT, encoding="utf-8")
        row = {"id": vid, "folder_key": vid, "case_no": "2026타경9001", "item_no": "1",
               "maker": "현대", "model": "쏘나타", "year": 2020, "sale_date": "2999-01-01",
               "status": "완료", "median_price": 14_000_000, "min_sale_price": 9_000_000,
               "sample_count": 19, "market_confidence_label": "높음", "photo_count": 3}
        row.update(kw)
        db.upsert_vehicle(row)
        return db.get_vehicle(vid)

    return mk


def _rate(v) -> float:
    """저장된 breakdown 에서 사고감가율을 읽는다(dict/JSON 양쪽 대응)."""
    bd = v.get("breakdown")
    if isinstance(bd, str):
        bd = json.loads(bd)
    assert isinstance(bd, dict), f"breakdown 을 읽을 수 없다: {type(bd)}"
    return float(bd.get("사고감가율", -1))


def test_등급이_내려가면_감가율도_따라_내려간다(env):
    """★ 이 테스트가 없어서 '등급은 맞는데 값이 틀린' 상태가 운영에 나갔다."""
    env("V1", accident_grade="flood")
    assert service.backfill_accident_grades() >= 1

    v = db.get_vehicle("V1")
    assert v["accident_grade"] != "flood", "부정문인데 침수로 남았다"
    assert _rate(v) != 1.0, (
        f"등급은 {v['accident_grade']} 로 내려갔는데 감가율이 1.0 그대로다 — "
        f"시세 전액이 깎여 상한가가 음수로 잠긴다")
    assert v["upper_bid"] > 0, f"상한가가 {v['upper_bid']} — 어떤 금액을 써도 손해가 된다"


def test_감가_표기도_옛_등급을_말하지_않는다(env):
    """breakdown 의 '사고표기' 가 옛 v 를 본 흔적이었다 — 화면 근거로 인쇄되는 값이다."""
    env("V2", accident_grade="flood")
    service.backfill_accident_grades()
    bd = db.get_vehicle("V2").get("breakdown")
    if isinstance(bd, str):
        bd = json.loads(bd)
    assert bd.get("사고표기") != "침수의심", "등급이 내려갔는데 표기는 침수 그대로다"


def test_이미_잘못_박힌_행은_force_로만_고쳐진다(env):
    """skip 조건 때문에 **다시 돌려도 건너뛰는** 상태가 실제로 있었다.

    등급은 이미 내려가 있고(none) 이력도 그대로라 `grade == 기존` 이 참이 된다.
    그러면 breakdown 에 박힌 옛 감가율(1.0)은 영영 손댈 수 없다."""
    v = env("V3", accident_grade="none",
            breakdown=json.dumps({"사고감가율": 1.0, "사고표기": "침수의심"},
                                 ensure_ascii=False),
            upper_bid=-5_610_000)

    # 평소 실행: 등급·이력이 그대로라 건너뛴다 → 잘못된 값이 남는다
    service.backfill_accident_grades()
    assert _rate(db.get_vehicle("V3")) == 1.0, "이 전제가 깨지면 이 테스트의 의미가 없다"

    # 강제 실행: 건너뛰지 않고 다시 산정한다
    assert service.backfill_accident_grades(force=True) >= 1
    after = db.get_vehicle("V3")
    assert _rate(after) != 1.0, "force 인데도 옛 감가율이 남았다"
    assert after["upper_bid"] > 0, f"상한가가 {after['upper_bid']} 로 여전히 잠겨 있다"


def test_진짜_침수는_감가율_1_0_을_유지한다(env):
    """고치면서 반대쪽을 지우면 안 된다 — 침수차는 그대로 전액 감가다."""
    folder_text = ("별첨 '사진용지'내 '작업지시현황'상 정비내역중 침수차량으로 입고되어 "
                   "시동이 불능상태 인 바, 관리상태 등은 불량시 됨.")
    env("V4", accident_grade="none")
    from src.paths import DATA_DIR          # 픽스처가 tmp_path 로 바꿔 끼운 경로
    (DATA_DIR / "V4" / "appraisal.txt").write_text(folder_text, encoding="utf-8")

    service.backfill_accident_grades(force=True)
    after = db.get_vehicle("V4")
    assert after["accident_grade"] == "flood", "진짜 침수를 놓쳤다"
    assert _rate(after) == 1.0, "침수인데 전액 감가가 아니다"
