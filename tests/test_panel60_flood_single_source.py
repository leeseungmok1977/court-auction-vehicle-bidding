# -*- coding: utf-8 -*-
"""PANEL-60 — 침수 판정의 원천은 accident_grade(grade_accident) 하나다.

배경(2026-09-25 Steward 실측): 2025타경53062_1 이 라이브에선 accident_grade='none' 인데
condition_flags=["침수","탈거"] 이고, 로컬 사본(9/23)에선 같은 행이 accident_grade='flood' 였다.
조사 결과(reports/2026-09-26-panel60.md):
  · 그 차의 감정요항 원문은 "전손, 도난, 침수 보험사고 이력 … **없는 것으로 조회되었음**" —
    침수차가 아니다. 로컬의 'flood' 는 2026-09-21 파서 수정 이전의 부정문 오독이고, 라이브의
    'none' 이 맞다. 라이브 플래그의 "침수" 는 재파싱되지 않고 남은 옛 파서의 산물이다.
  · 로컬 사본에서 플래그 '침수' 18행을 현재 파서로 다시 읽으면 11행이 none/accident(전부 부정문 또는
    "침수차량 여부도 재확인 바랍니다") — "플래그 침수 = 침수" 로 판정하면 이 11대가 거짓 STOP 을 받는다.
  · 반대로 2026타경10406_1 은 "전손 사고 이력 : 보험사고 이력(… 수리비 39,080,000원) 존재함" 인데
    grade_accident 가 보험이력 카운트가 있으면 자유서술을 건너뛰어 accident 로 내렸다(진짜 전손 미탐).

고정하는 계약:
  1. 부정문 침수는 어느 원천에서도 침수가 아니다(등급·판정·플래그·bid_state).
  2. 진짜 침수는 등급·판정이 함께 flood 이고 bid_state 가 stop 이다. 플래그는 침수를 말하지 않는다.
  3. 보험이력 카운트가 있어도 자유서술의 전손·침수를 놓치지 않는다(게이트 제거 — 강화).
  4. 낡은 '침수' 플래그는 기동 백필이 level 이 있어도 다시 읽어 지운다(멱등).
  5. bid_state 는 condition_flags 를 판정 원천으로 쓰지 않는다(오너 결정 대기 항목 — 맨 아래 docstring).

★ 아래 원문은 전부 운영 감정요항에서 그대로 가져온 것이다(지어낸 문장은 실제 표현을 못 잡는다).
"""
from datetime import date, timedelta

import pytest

from src.bidcalc.calculator import BidInput, _is_flood
from src.parse import appraisal as ap
from src.parse.detail_parser import grade_accident, parse_insurance_history
from web import db, service

# 2025타경53062_1 — 번호판 탈거(상태 poor) + 침수 '없음'
NEGATED = ("본 건 조사 당시 전면 번호판은 탈거된 상태이며, 연식 및 주행거리 대비 자동차의 외부 및 내부, "
           "타이어 등의 전반적인 관리상태는 보통임.\n"
           "중고차사고이력정보보고서(카히스토리)상 소유자변경은 '2회', 내차피해 및 상대차피해 내역 없으며, "
           "영업용도(대여, 일반) 및 관용용도 사용이력이 없고, 전손, 도난, 침수 보험사고 이력 및 특수용도 이력은 "
           "없는 것으로 조회되었음.")
# 2025타경34408_1 — 진짜 침수(정비내역상 침수차량 입고)
FLOOD = ("본건 차량은 현장조사 당시 시동작동불능으로 인한 주행성능 및 운행유무 등은 확인이 곤란하였으며, "
         "별첨 '사진용지'내 '작업지시현황'상 정비내역중 침수차량으로 입고되어 시동이 불능상태 인 바, "
         "관리상태 등은 불량시 됨.")
# 2026타경10406_1 — 보험이력 카운트(차량번호 변경 1회)가 있는데 자유서술에 진짜 전손
TOTAL_LOSS_WITH_REPORT = ("차량번호 변경 1회이며, 자기차량손해담보 미가입기간은 2019년04월 ~ 2019년07월로 조사됨.\n"
                          "- 전손 사고 이력 : 보험사고 이력(2019-03-19, 수리비 39,080,000원) 존재함.")
# 2025타경16105_1 — 보험이력 카운트 + 부정문(게이트를 풀어도 침수가 되면 안 된다)
REPORT_AND_NEGATION = ("중고차 사고이력정보 보고서 상에는 전손, 도난, 침수 보험사고, 특수용도이력은 없으나, "
                       "내차 피해 3회, 상대차 피해 1회로 조회되었음.")


def _cfg():
    return service.load_config()


def _flood_in_calc(text, grade):
    return _is_flood(BidInput(median_price=0, min_sale_price=0, sample_count=0,
                              accident_grade=grade, appraisal_text=text), _cfg())


def _future():
    return (date.today() + timedelta(days=10)).isoformat()


# ── 1. 부정문 침수는 어느 원천에서도 침수가 아니다 ──────────────────────────────
def test_negated_flood_is_not_flood_in_any_source():
    grade, _, flood_hits, _ = grade_accident(NEGATED, "", _cfg())
    assert grade == "none" and flood_hits == [], (grade, flood_hits)
    assert _flood_in_calc(NEGATED, grade) is False
    cond = ap.parse_appraisal(NEGATED)["condition"]
    assert "침수" not in cond["damage"] and "탈거" in cond["damage"], cond
    assert cond["level"] == "poor"                       # 번호판 탈거는 여전히 poor
    sig = service._appraisal_signals(NEGATED, item_no="1")
    assert "침수" not in (sig["condition_flags"] or [])
    v = {"id": "N1", "accident_grade": grade, "condition_flags": sig["condition_flags"],
         "condition_level": "poor", "sale_date": _future(), "min_sale_price": 21_000_000}
    st = service.bid_state(v)
    assert st["state"] != "blocked" and "침수" not in st["label"], st


# ── 2. 진짜 침수는 등급·판정·bid_state 가 한목소리로 stop, 플래그는 침수를 말하지 않는다 ──
def test_real_flood_agrees_everywhere_and_bid_state_stops():
    grade, _, flood_hits, _ = grade_accident(FLOOD, "", _cfg())
    assert grade == "flood" and "침수" in flood_hits
    assert _flood_in_calc(FLOOD, grade) is True
    cond = ap.parse_appraisal(FLOOD)["condition"]
    assert "침수" not in cond["damage"], cond            # 원천은 하나 — 플래그가 따로 주장하지 않는다
    assert cond["level"] == "poor"                       # 등급 신호로는 그대로 반영(완화 아님)
    v = {"id": "F1", "accident_grade": grade, "condition_level": cond["level"],
         "condition_flags": cond["damage"] or None, "sale_date": _future(),
         "median_price": 12_000_000, "min_sale_price": 5_000_000, "sample_count": 20,
         "market_confidence_label": "높음"}
    st = service.bid_state(v)
    assert (st["state"], st["tone"]) == ("blocked", "stop"), st
    assert st["label"] == "침수·전손 의심 — 입찰 보류"


def test_condition_flags_never_assert_flood_structurally():
    """반증: '침수'를 _DAMAGE_MAJOR 로 되돌리면 여기와 위 두 테스트가 같이 빨개진다."""
    assert "침수" not in ap._DAMAGE_MAJOR and "침수" not in ap._DAMAGE_MINOR
    assert "침수" in ap._LEVEL_ONLY_KW


# ── 3. 보험이력 카운트가 있어도 자유서술의 전손·침수를 본다(게이트 제거 = 강화) ────────
def test_total_loss_in_free_text_survives_insurance_report():
    assert parse_insurance_history(TOTAL_LOSS_WITH_REPORT)          # 카운트가 실제로 있다(옛 게이트 조건)
    grade, _, flood_hits, _ = grade_accident(TOTAL_LOSS_WITH_REPORT, "", _cfg())
    assert grade == "flood" and "전손" in flood_hits, (grade, flood_hits)
    assert _flood_in_calc(TOTAL_LOSS_WITH_REPORT, grade) is True   # calculator 와 같은 답


def test_gate_removal_does_not_revive_negation_false_positives():
    """게이트를 풀어도 부정문은 그대로 — 9/21 수정(20대 중 14대 오독)을 되살리면 안 된다."""
    assert parse_insurance_history(REPORT_AND_NEGATION)
    grade, acc_hits, flood_hits, _ = grade_accident(REPORT_AND_NEGATION, "", _cfg())
    assert grade == "accident" and flood_hits == [], (grade, acc_hits, flood_hits)


# ── 4. 낡은 '침수' 플래그는 기동 백필이 다시 읽어 지운다 ──────────────────────────
@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("src.paths.DATA_DIR", tmp_path)
    return tmp_path


def _seed(vid, **fields):
    db.upsert_vehicle({"id": vid, "folder_key": vid, "item_no": "1", "court_code": "B000000",
                       "status": "완료", **fields})
    return vid


def _put_text(data_dir, vid, text):
    (data_dir / vid).mkdir()
    (data_dir / vid / "appraisal.txt").write_text(text, encoding="utf-8")


def test_backfill_resweeps_stale_flood_flag(data_dir):
    _put_text(data_dir, "S1", NEGATED)
    _put_text(data_dir, "S2", "좌측 전면에 일부 스크레치가 목측되었으나.")
    _seed("S1", accident_grade="none", condition_level="poor", condition_flags=["침수", "탈거"])
    _seed("S2", accident_grade="none", condition_level="fair", condition_flags=["스크레치"])
    _seed("S3", accident_grade="none", condition_level="poor", condition_flags=["침수"])   # 원문 없음

    assert service.backfill_appraisal_signals() == 1          # S1 만 (S2 는 level 있음, S3 는 원문 없음)
    s1 = db.get_vehicle("S1")
    assert s1["condition_flags"] == ["탈거"] and s1["condition_level"] == "poor", s1
    assert s1["accident_grade"] == "none"                     # 이 백필은 등급을 건드리지 않는다
    assert db.get_vehicle("S2")["condition_flags"] == ["스크레치"]
    assert db.get_vehicle("S3")["condition_flags"] == ["침수"]  # 원문이 없으면 주장을 바꾸지 않는다
    assert service.backfill_appraisal_signals() == 0          # 멱등 — 두 번째 기동엔 다시 걸리지 않는다


def test_backfill_still_skips_rows_that_already_have_a_level(data_dir):
    """반증: _stale_flood_flag 조건을 지우면 위 테스트가 0 을 돌려주며 빨개진다. 이쪽은 예전 동작 보존."""
    _put_text(data_dir, "K1", FLOOD)
    _seed("K1", accident_grade="flood", condition_level="poor", condition_flags=["파손"])
    assert service.backfill_appraisal_signals() == 0


def test_backfill_reads_from_data_dir_not_cwd(data_dir, monkeypatch):
    """상대경로 "data" 를 쓰던 시절엔 작업 디렉터리가 바뀌면 조용히 0건이었다."""
    _put_text(data_dir, "D1", NEGATED)
    _seed("D1")                                                # condition_level NULL → 원래 대상
    monkeypatch.chdir(data_dir)                                # cwd 에 "data" 폴더가 없다
    assert service.backfill_appraisal_signals() == 1
    assert db.get_vehicle("D1")["condition_level"] == "poor"


# ── 5. bid_state 의 침수 원천은 accident_grade 다 — condition_flags 가 아니다 ───────────
def test_bid_state_reads_flood_from_accident_grade_not_condition_flags():
    """지시서 대안 (a) "condition_flags 의 '침수'도 flood 로 본다" 를 **채택하지 않은** 근거 고정.

    플래그의 '침수'는 (i) 현재 파서에선 만들어지지 않고 (ii) 남아 있는 것은 옛 파서의 부정문 오독이다
    (로컬 사본 18행 중 11행 — 2025타경53062_1 포함). 그것을 침수로 판정하면 감정요항이 "침수 없음"
    이라고 적은 차에 '침수·전손 의심 — 입찰 보류' 가 붙는다. 이 계약을 바꾸는 것은 오너 승인 항목이다."""
    v = {"id": "A1", "accident_grade": "none", "condition_flags": ["침수", "탈거"],
         "condition_level": "poor", "sale_date": _future(), "min_sale_price": 21_000_000}
    st = service.bid_state(v)
    assert st["state"] != "blocked" and "침수" not in st["label"], st
