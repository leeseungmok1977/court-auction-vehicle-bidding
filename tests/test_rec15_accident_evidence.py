"""REC-15(2026-10-01) — '무사고' 근거 강화. 오너 승인: "무사고 권고기준을 강화합니다."

근거 = accident_hits 가 있거나, 보험이력에 **일반 사고 항목**(own_damage 내차피해 · opp_damage 상대차피해 키 — 값이 0 이어도)이
있을 때만(service.accident_evidence). 소유자·차량번호 변경, 특수사고(전손·도난·침수)·특수용도 카운트만 있는 보험이력은
근거가 아니다 — 2026타경50904_1 은 보험이력이 {"owner_changes": 3, "plate_changes": 1} 뿐인데(감정 요항 원문 "…전손보험사고,
도난보험사고, 침수보험사고, 특수용도 이력 없음.") 초록 '무사고'·사고 감가 0% 로 '입찰 검토 가능'에 있었다.

① 술어 단위 — 근거 아님 / 근거
② 같은 술어를 따르는 곳이 함께 움직인다: 라벨 · 감가율 · 산정표 표기(apply_accident_rate) · 실사용 상한선 · 육각형 사고축 ·
   리포트 신뢰도 패널 '사고·이력'(insurance_accident_known — 칸이 올라가는 물건은 없다)
③ calculator.reprice_accident 는 calculate() 를 새 감가율로 다시 부른 값과 같다(사고 감가 한 항만 바뀐다)
④ 재산정(service.reprice_accidents · `python -m web.maint reprice-accidents`) — 미리보기는 쓰지 않는다 · --apply 는 --ids 와
   함께만 · 매각 끝난 행·침수 행·산정 없는 행은 건드리지 않는다 · 멱등 · 외부 요청 0 · 요항 파일 I/O 0
⑤ 2026타경50904_1(10-01 백업 저장값) — 상한가 7,680,000 → 5,730,000 · '입찰 검토 가능' → '유찰 대기'
"""
import copy
import json
import socket
from datetime import date, timedelta

import pytest

from src.bidcalc.calculator import BidInput, calculate, load_config, reprice_accident
from tests.test_render_smoke import BT
from web import db, maint, service

CFG = load_config()            # 저장소 루트 config.yaml(절대 경로) — 모듈 임포트가 현재 디렉터리에 기대지 않게
ASSUMED = float(CFG["accident_depreciation_rate"]["accident"])      # 이력 미확인 → 사고 가정 감가율(설정값)
LBL_ASSUMED, LBL_CLEAN = "이력 미확인 — 사고차 가정", "무사고(이력 확인됨)"

NOT_EVIDENCE = [
    None,
    {},
    {"owner_changes": 3, "plate_changes": 1},          # 2026타경50904_1 그대로
    {"owner_changes": 1},                              # 2026타경50311_1 · 60319_1
    {"owner_changes": 5, "plate_changes": 0},          # 2026타경52708_1
    {"plate_changes": 1},
    {"total_loss": 0, "theft": 0, "flood": 0},         # 2026타경503268_1 — 특수사고만
    {"special_use": 0},
    {"내차피해": 0},                                    # 파서가 만들지 않는 키(옛 테스트 픽스처)
    '{"owner_changes": 3}',                            # JSON 문자열로 와도 같다
    {"own_damage": "모름"},                             # 값을 읽을 수 없으면 '모른다'(accident_hit_count None)
]
EVIDENCE = [
    {"own_damage": 0},                                 # 0건이라도 '조회했다'
    {"opp_damage": 0},
    {"own_damage": 0, "opp_damage": 0},
    {"own_damage": 0, "opp_damage": 2, "owner_changes": 3},
    {"own_damage": 0, "opp_damage": 0, "total_loss": 0, "theft": 0, "flood": 0},
    '{"own_damage": 0}',
]


def _car(ih, **kw):
    base = {"accident_grade": "none", "median_price": 13_000_000, "min_sale_price": 6_860_000,
            "market_confidence_label": "높음", "market_confidence": 80, "judgment": "유찰 대기",
            "year": 2020, "mileage_km": 60_000, "inspection_to": "2099-01-01"}
    if ih is not None:
        base["insurance_history"] = ih
    base.update(kw)
    return base


# ── ① 술어 단위 ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ih", NOT_EVIDENCE, ids=lambda x: f"no:{x}")
def test_insurance_without_general_accident_items_is_not_evidence(ih):
    v = _car(ih)
    assert service.insurance_accident_known(v) is False
    assert service.accident_evidence(v) is False, f"일반 사고 항목 없는 보험이력을 근거로 쳤다: {ih!r}"


@pytest.mark.parametrize("ih", EVIDENCE, ids=lambda x: f"yes:{x}")
def test_general_accident_item_key_is_evidence_even_when_zero(ih):
    v = _car(ih)
    assert service.insurance_accident_known(v) is True
    assert service.accident_evidence(v) is True


def test_accident_hits_alone_are_evidence():
    assert service.accident_evidence({"accident_grade": "none", "accident_hits": ["내차피해2회"]}) is True
    assert service.accident_evidence({"accident_grade": "none", "accident_hits": []}) is False
    # hits 는 근거지만 '보험이력 조회'는 아니다(패널 칸은 insurance_accident_known 만 본다 — ② 참조)
    assert service.insurance_accident_known({"accident_hits": ["판금"]}) is False


# ── ② 같은 술어를 따르는 곳 ─────────────────────────────────────────────────────
def _panel(v):
    cats = {c["name"]: c for c in service.report_data(v, CFG, BT)["cats"]}
    return cats["사고·이력"]["score"], cats["사고·이력"]["tag"]


@pytest.mark.parametrize("ih,ev", [(x, False) for x in NOT_EVIDENCE] + [(x, True) for x in EVIDENCE],
                         ids=lambda x: str(x))
def test_label_rate_stored_label_ceiling_hexagon_panel_follow_one_predicate(ih, ev):
    v = _car(ih)
    assert service.accident_evidence(v) is ev
    # 라벨
    assert service.accident_label(v) == ("무사고" if ev else "이력 미확인")
    # 감가율 — 근거가 없으면 사고차 가정(설정의 accident 율)
    assert service.use_accident_rate(v, CFG) == ((0.0, False) if ev else (ASSUMED, True))
    # 저장 산정표 표기 — 분석 경로가 쓰는 apply_accident_rate 가 같은 값을 싣는다
    bi = service.apply_accident_rate(BidInput(median_price=0, min_sale_price=0, sample_count=0), v, CFG)
    assert (bi.accident_rate, bi.accident_label) == ((0.0, LBL_CLEAN) if ev else (ASSUMED, LBL_ASSUMED))
    # 육각형 사고·상태 축 — 근거 없으면 미산출
    ax = {a["key"]: a for a in service.hexagon_scores(v, date(2026, 10, 1), newcar_ok=False)["axes"]}
    assert ax["cond"]["score"] == (100 if ev else None)
    # 리포트 신뢰도 패널 — 등급 none 에서는 근거와 같은 말(한 화면에서 '이력 미확인'과 '검증 90'이 갈리지 않는다)
    assert _panel(v) == ((90, "verified") if ev else (60, "estimated"))


def test_ceiling_with_owner_only_history_equals_unknown_not_clean():
    """실사용 상한선(입찰 상한선)은 소유자·번호 변경만 있는 보험이력을 '이력 미확인'과 같게 본다."""
    owner = service.personal_use_max_bid(_car({"owner_changes": 3, "plate_changes": 1}), BT, CFG)
    unknown = service.personal_use_max_bid(_car(None), BT, CFG)
    clean = service.personal_use_max_bid(_car({"own_damage": 0, "opp_damage": 0}), BT, CFG)
    assert owner == unknown < clean


def test_panel_never_rises_and_keyword_only_accident_stays_estimated():
    """패널 칸은 예전 기준('보험이력 dict 가 비지 않음')의 부분집합 — 올라가는 물건은 없다.

    등급 accident 인데 감정서 낱말로만 잡힌 물건(10-01 백업 306대)은 사고가 **있다**는 것만 안다 — '검증'으로 올리지 않는다.
    소유자 변경만 있는 보험이력의 사고차(10-01 백업 10대)는 90 → 60 으로 내려온다."""
    kw_only = _car(None, accident_grade="accident", accident_hits=["판금"])
    assert service.accident_evidence(kw_only) is True            # 라벨·감가에는 근거(등급 accident 라 쓰이지 않는다)
    assert _panel(kw_only) == (60, "estimated")
    owner_acc = _car({"owner_changes": 2, "plate_changes": 1}, accident_grade="accident", accident_hits=["사고"])
    assert _panel(owner_acc) == (60, "estimated")
    counted = _car({"own_damage": 2, "opp_damage": 0}, accident_grade="accident", accident_hits=["내차피해2회"])
    assert _panel(counted) == (90, "verified")


def test_every_consumer_routes_through_accident_hit_count(monkeypatch):
    """술어는 한 곳(accident_hit_count → insurance_accident_known → accident_evidence) — 바꾸면 모두가 따라온다.

    보험이력이 아예 없는 행에서 그 한 곳만 '0건'으로 바꾸면 라벨·감가·패널이 함께 '확인됨'으로 움직여야 한다 —
    어느 하나라도 보험이력 dict 를 직접 보면(예전 패널) 여기서 갈린다."""
    v = _car(None)
    assert service.accident_label(v) == "이력 미확인" and _panel(v) == (60, "estimated")
    monkeypatch.setattr(service, "accident_hit_count", lambda _v: 0)
    assert service.accident_label(v) == "무사고"
    assert service.use_accident_rate(v, CFG) == (0.0, False)
    assert _panel(v) == (90, "verified")


# ── ③ calculator.reprice_accident == calculate() ───────────────────────────────
_TEXTS = ["", "차량 외관에 경미한 긁힘이 있음.", "앞범퍼 파손, 라이트 깨짐, 부식 심함", "시동 불가, 운행 불가"]


@pytest.mark.parametrize("r0,r1", [(0.0, 0.15), (0.15, 0.0), (0.10, 0.30), (0.15, 0.22)])
def test_reprice_accident_equals_calculate_with_new_rate(r0, r1):
    """시세 5 × 요항(상태 비용 0·30만·70만·150만) 4 × 사진(미상·0장·5장) 3 = 60 조합마다 calculate() 와 같다."""
    n = 0
    for med in (13_000_000, 12_345_000, 9_995_000, 31_900_000, 109_000_000):
        for text in _TEXTS:
            for photos in (None, 0, 5):
                def calc(rate, label):
                    return calculate(BidInput(median_price=med, min_sale_price=6_860_000, sample_count=17,
                                              platform="encar", accident_grade="none", repair_cost=500_000,
                                              appraisal_text=text, photo_count=photos,
                                              accident_rate=rate, accident_label=label), CFG)
                old, new = calc(r0, LBL_CLEAN), calc(r1, LBL_ASSUMED)
                got = reprice_accident(old.breakdown, old.upper_bid, r1, LBL_ASSUMED)
                case = (med, text, photos)
                assert got == (new.upper_bid, new.breakdown), case
                # 사고 감가 항 말고는 하나도 바뀌지 않는다
                assert {k for k in old.breakdown if old.breakdown[k] != got[1][k]} <= \
                    {"사고표기", "사고감가율", "사고감가"}, case
                n += 1
    assert n == 60


def test_reprice_accident_leaves_flood_and_missing_inputs_alone():
    fl = calculate(BidInput(median_price=13_000_000, min_sale_price=6_860_000, sample_count=17,
                            appraisal_text="침수 흔적 있음", accident_rate=0.0), CFG)
    assert fl.breakdown["사고등급"] == "flood"
    assert reprice_accident(fl.breakdown, fl.upper_bid, 0.15, LBL_ASSUMED) is None
    assert reprice_accident(None, 1, 0.15) is None
    assert reprice_accident({"기준시세": 1}, 1, 0.15) is None          # 사고감가율 없음
    assert reprice_accident({"사고감가율": 0.0}, 1, 0.15) is None      # 기준시세 없음
    assert reprice_accident({"기준시세": 1, "사고감가율": 0.0}, None, 0.15) is None


# ── ④⑤ 재산정 — 2026타경50904_1 과 주변 행 ─────────────────────────────────────
# 10-01 09:10 백업 사본의 저장값 그대로(산정표 포함).
BD_50904 = {"기준시세": 13000000, "플랫폼": "encar", "플랫폼가중": 1.0, "예상수리비": 500000, "사고등급": "none",
            "사고표기": LBL_CLEAN, "사고감가율": 0.0, "사고감가": 0, "리스크프리미엄": 910000, "취득세": 910000,
            "고정부대비": 500000, "마진": 1950000, "상태정비추가": 550000,
            "상태사유": ["외관 경미 손상", "자동차검사 유효기간 경과"], "표본수": 17, "현재최저매각가": 6860000}


def _row(vid, **kw):
    base = {"id": vid, "case_no": vid.split("_")[0], "court_code": "000210", "maker": "르노삼성코리아", "model": "XM3",
            "year": 2020, "item_no": "1", "status": "완료",
            "sale_date": (date.today() + timedelta(days=5)).isoformat(),
            "median_price": 13_000_000, "min_sale_price": 6_860_000, "sample_count": 17,
            "market_confidence": 80, "market_confidence_label": "높음", "market_platform": "encar",
            "upper_bid": 7_680_000, "lower_bound": 6_860_000, "judgment": "입찰 검토 가능",
            "accident_grade": "none", "accident_hits": [], "insurance_history": {"owner_changes": 3, "plate_changes": 1},
            "breakdown": copy.deepcopy(BD_50904), "repair_cost": 500_000, "photo_count": 12}
    base.update(kw)
    return base


@pytest.fixture
def rows():
    rs = {
        "2026타경50904_1": _row("2026타경50904_1"),
        # 매각 끝난 같은 꼴 — 건드리지 않는다(2026타경10294_1 꼴)
        "CLOSED_1": _row("CLOSED_1", auction_result="낙찰", judgment="종결", status="종결"),
        # 침수 보류 — 감가율은 flood 율 고정
        "FLOOD_1": _row("FLOOD_1", accident_grade="flood", judgment="입찰 보류", upper_bid=-561_000,
                        breakdown={**BD_50904, "사고등급": "flood", "사고표기": "침수의심", "사고감가율": 1.0}),
        # 이미 지금 규칙과 같다(일반 사고 항목 0건 — 근거 있음)
        "OK_1": _row("OK_1", insurance_history={"own_damage": 0, "opp_damage": 0}),
        # 산정 없음(시세 없음) — 저장할 상한가·산정표가 없다(2026타경60319_1 꼴: 라벨만 바뀐다)
        "NOBD_1": _row("NOBD_1", upper_bid=None, breakdown=None, median_price=None,
                       judgment="시세 신뢰도 낮음, 수동 검토", insurance_history={"owner_changes": 1}),
        # 상한가는 있지만 판정이 judge() 가 상한가로 가르는 둘이 아니다 — 상한가·산정표만 고치고 판정은 둔다.
        #   신뢰도 '보통'·표본 17 이라 judge() 를 다시 부르면 '유찰 대기'가 나온다 — 그래도 바꾸지 않는다(재산정이
        #   다른 이유로 저장된 판정을 움직이는 길을 열지 않는다. 판정 범위는 rejudge_floor 와 같다).
        "LOWCONF_1": _row("LOWCONF_1", judgment="시세 신뢰도 낮음, 수동 검토", market_confidence_label="보통"),
    }
    for r in rs.values():
        db.upsert_vehicle(r)
    return rs


def _snap():
    return {v["id"]: v for v in db.list_vehicles()}


@pytest.fixture
def no_io(monkeypatch):
    """외부 요청 0 · 요항 파일 I/O 0 — 닿으면 테스트가 깨진다."""
    def boom(*a, **k):
        raise AssertionError("REC-15 재산정이 외부 요청·요항 파일에 닿았다")
    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    for name in ("new_session", "warmup", "fetch_detail", "fetch_list_page", "_read_appraisal"):
        monkeypatch.setattr(service, name, boom)
    monkeypatch.setattr(service.encar, "new_session", boom)
    monkeypatch.setattr(service.kcar, "new_session", boom, raising=False)


def test_50904_fields_from_backup_values():
    f, why = service._reprice_accident_plan(_row("2026타경50904_1"), CFG)
    assert why == "target"
    assert f["upper_bid"] == 5_730_000                    # 7,680,000 − 13,000,000 × 15%
    assert f["judgment"] == "유찰 대기"                    # 상한가 < 최저가 6,860,000 (judge 한 곳)
    assert "lower_bound" not in f                          # 최저가는 그대로
    bd = f["breakdown"]
    assert (bd["사고감가율"], bd["사고감가"], bd["사고표기"]) == (ASSUMED, 1_950_000, LBL_ASSUMED)
    assert {k for k in BD_50904 if BD_50904[k] != bd[k]} == {"사고표기", "사고감가율", "사고감가"}
    # 같은 입력으로 calculate() 를 새로 부른 것과 같은 상한가 — 상태정비 550,000(요항 기반)은 저장값 그대로 쓴다
    assert bd["상태정비추가"] == 550_000


def test_dry_run_writes_nothing_and_targets_only_stale_open_rows(rows, no_io):
    before = _snap()
    out = service.reprice_accidents(config=CFG)
    assert _snap() == before, "미리보기가 DB 를 썼다"
    assert out["apply"] is False and out["applied"] == 0
    assert out["checked"] == len(rows)
    got = {r["id"]: r for r in out["rows"]}
    assert set(got) == {"2026타경50904_1", "LOWCONF_1"}
    assert out["skipped"] == {"closed": 1, "flood": 1, "no_breakdown": 1, "already": 1}
    r = got["2026타경50904_1"]
    assert r["evidence"] is False
    assert r["label"] == [LBL_CLEAN, LBL_ASSUMED] and r["rate"] == [0.0, ASSUMED]
    assert r["upper_bid"] == [7_680_000, 5_730_000] and r["judgment"] == ["입찰 검토 가능", "유찰 대기"]
    assert r["max_bid"][0] == r["max_bid"][1], "입찰 상한선은 화면이 매번 지금 규칙으로 계산한다 — 저장값과 무관"
    assert got["LOWCONF_1"]["judgment"] == ["시세 신뢰도 낮음, 수동 검토"] * 2


def test_apply_with_ids_writes_only_those_rows_and_is_idempotent(rows, no_io):
    before = _snap()
    out = service.reprice_accidents(ids=["2026타경50904_1", "없는_1"], apply=True, config=CFG)
    assert out["applied"] == 1 and out["not_found"] == ["없는_1"]
    after = _snap()
    a = after["2026타경50904_1"]
    assert (a["upper_bid"], a["judgment"]) == (5_730_000, "유찰 대기")
    assert a["breakdown"]["사고감가율"] == ASSUMED and a["breakdown"]["사고표기"] == LBL_ASSUMED
    # 바꾸지 않는 열: 등급·보험이력·분석 시각·최저가·시세
    for k in ("accident_grade", "insurance_history", "analyzed_at", "min_sale_price", "median_price", "lower_bound"):
        assert a.get(k) == before["2026타경50904_1"].get(k), k
    # 다른 행은 한 글자도 안 바뀐다(--ids 밖의 LOWCONF_1 포함)
    for vid in rows:
        if vid != "2026타경50904_1":
            assert after[vid] == before[vid], vid
    # 다시 돌리면 대상 0(멱등)
    again = service.reprice_accidents(ids=["2026타경50904_1"], apply=True, config=CFG)
    assert again["targets"] == 0 and again["applied"] == 0 and _snap() == after


def test_closed_flood_nobd_and_already_consistent_rows_are_never_touched(rows, no_io):
    before = _snap()
    out = service.reprice_accidents(ids=list(rows), apply=True, config=CFG)
    assert {r["id"] for r in out["rows"]} == {"2026타경50904_1", "LOWCONF_1"}
    after = _snap()
    for vid in ("CLOSED_1", "FLOOD_1", "OK_1", "NOBD_1"):
        assert after[vid] == before[vid], vid
    lc = after["LOWCONF_1"]
    assert lc["judgment"] == "시세 신뢰도 낮음, 수동 검토"              # 판정은 그대로
    assert lc["upper_bid"] == 5_730_000 and lc["breakdown"]["사고표기"] == LBL_ASSUMED


def test_after_reprice_the_stored_breakdown_agrees_with_the_live_rule(rows, no_io):
    """재산정 뒤에는 저장 산정표의 표기·감가율이 화면이 매번 계산하는 값과 같다 — 같은 화면에서 두 말을 하지 않는다."""
    service.reprice_accidents(ids=["2026타경50904_1"], apply=True, config=CFG)
    v = db.get_vehicle("2026타경50904_1")
    rate, assumed = service.use_accident_rate(v, CFG)
    assert (v["breakdown"]["사고감가율"], assumed) == (rate, True)
    assert service.accident_label(v) == "이력 미확인"
    assert v["breakdown"]["사고표기"] == LBL_ASSUMED


# ── CLI(web.maint reprice-accidents) ──────────────────────────────────────────
def test_cli_refuses_unscoped_apply_and_bad_flags(rows, no_io, capsys):
    before = _snap()
    assert maint.main(["web.maint", "reprice-accidents", "--apply"]) == 2
    assert "--apply 는 --ids 와 함께 쓴다" in capsys.readouterr().out
    assert maint.main(["web.maint", "reprice-accidents", "--apply", "--dry-run", "--ids", "2026타경50904_1"]) == 2
    assert "함께 쓸 수 없다" in capsys.readouterr().out
    assert maint.main(["web.maint", "reprice-accidents", "--ids"]) == 2
    assert "--ids 뒤에 물건 id" in capsys.readouterr().out
    assert _snap() == before


def test_cli_dry_run_default_then_apply_with_ids(rows, no_io, capsys):
    before = _snap()
    assert maint.main(["web.maint", "reprice-accidents"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["apply"] is False and {r["id"] for r in out["rows"]} == {"2026타경50904_1", "LOWCONF_1"}
    assert _snap() == before, "인자 없는 실행(미리보기)이 DB 를 썼다"
    assert maint.main(["web.maint", "reprice-accidents", "--ids", "2026타경50904_1", "--dry-run"]) == 0
    capsys.readouterr()
    assert _snap() == before
    assert maint.main(["web.maint", "reprice-accidents", "--ids=2026타경50904_1", "--apply"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["applied"] == 1
    assert db.get_vehicle("2026타경50904_1")["judgment"] == "유찰 대기"
    assert db.get_vehicle("LOWCONF_1") == before["LOWCONF_1"]
