# -*- coding: utf-8 -*-
"""AUD-18 — 상세 조회 키 바로잡기(지시서 2026-10-02-15 · 오너 승인 10-02).

배경(Steward 라이브 검증 10-02, 법원 요청 4회 — 이 파일은 그 응답을 **복사하지 않고** 같은 모양의 합성 값만 쓴다):
  법원 상세는 csNo=saNo · cortOfcCd=boCd · **dspslGdsSeq=maemulSer(매각물건 번호)** 로 묻는다(수집URL정의서 L3).
  재조회 경로들은 item_no(= 목적물 번호 mokmulSer)를 보냈다. doc_id 끝 두 자리가 (매각물건, 목적물)이고, 두 번호가 다른
  물건은 ⑴ 빈 응답 → '상세없음'으로 숨겨지거나 ⑵ **옆 매각물건의 상세**로 채워졌다 — 운영 DB 의 벤츠 CLS350(doc 끝 '34')에
  스타렉스(매각물건 4 · 목적물 5)의 2,497cc·디젤·'뒤바퀴 부식' 비고와 기일내역(최저가 171.5만, 실제 253.8만)이 붙어 있었다.

고정하는 것:
  ① 모든 상세 요청 경로가 매각물건 번호를 보낸다(저장값 → doc_id → item_no). 두 번호가 같은 행은 예전과 바이트까지 같다.
  ② 받은 상세가 보낸 키의 물건(사건·법원·매각물건 같고, 목적물 번호 == item_no)일 때만 저장한다. 아니면 아무것도 안 쓰고
     감사기록(detail-mismatch)·실행 기록 ⚠ 조각. [0] 고정 대신 목적물 번호로 고른다(일괄매각).
  ③ 감정요항 '기호N' 은 목적물 번호로 고른다.
  ④ 이미 옆 물건 상세로 채워진 입찰예정 행은 `redetail-key` 예약 → 다음 매일 갱신이 기존 상한 안에서 올바른 키로 받는다.
     '상세없음' 행은 목록 재등장 복구(mark_disappeared)로 같은 런에서 다시 묻는다.
  ⑤ C.4-5: 불일치는 비정상 응답 연속 카운터를 올리지도 0 으로 되돌리지도 않는다(예전보다 약해지지 않는다).
외부 요청 0 — 법원·엔카 요청 함수는 대역, 루프백 밖 소켓 연결은 막는다.
"""
import json
import re
import socket
from datetime import date, timedelta
from pathlib import Path

import pytest

from src.collect import courtauction_detail as cad
from src.parse import list_parser as lp
from src.parse.detail_parser import parse_detail
from web import db, service

ROOT = Path(__file__).resolve().parents[1]
TODAY = date.today()
SD = (TODAY + timedelta(days=10)).isoformat()
PAST = (TODAY - timedelta(days=3)).isoformat()

# 합성 사건 — 운영 53697 사건과 같은 **모양**(doc 끝 '34'·'45')이지만 번호·값은 지어낸 것이다.
COURT, COURT_NAME = "B000999", "가상지원"
CASE, SA = "2025타경90697", "20250130090697"
BENZ, STAREX = f"{CASE}_4", f"{CASE}_5"
DOC_BENZ, DOC_STAREX = f"{COURT}{SA}34", f"{COURT}{SA}45"
# 다물건 감정요항(사건 단위 글) — 기호는 목적물 번호다.
AEE_MULTI = ("기호1 자동차: 2019년식 화물로서 차량계기판상 주행거리는 303,000km임. "
             "기호3 자동차: 2011년식 승용으로서 자동차등록원부 주행거리는 237,000km임. "
             "기호4 자동차: 2012년식 승용으로서 차량계기판상 주행거리는 254,000km임. "
             "기호5 자동차: 2017년식 승합.")


# ── 외부 요청 0 ────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    real, real_ex = socket.socket.connect, socket.socket.connect_ex

    def _lo(addr):
        h = addr[0] if isinstance(addr, tuple) and addr else addr
        return str(h) in ("127.0.0.1", "::1", "localhost")

    def deny(self, addr, *a, **k):
        if _lo(addr):
            return real(self, addr, *a, **k)
        raise AssertionError(f"외부 연결 시도 {addr!r} — AUD-18 테스트는 외부 요청 0 이어야 한다(C.4)")

    def deny_ex(self, addr, *a, **k):
        if _lo(addr):
            return real_ex(self, addr, *a, **k)
        raise AssertionError(f"외부 연결 시도 {addr!r} — AUD-18 테스트는 외부 요청 0 이어야 한다(C.4)")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_ex)

    def _no_court(*a, **k):
        raise AssertionError("법원 요청 함수를 대역 없이 불렀다")
    for name in ("new_session", "warmup", "fetch_detail", "fetch_list_page"):
        monkeypatch.setattr(service, name, _no_court)
    monkeypatch.setattr(service.encar, "new_session", lambda: object())
    monkeypatch.setattr(service, "_resolve_encar", lambda *a, **k: None)     # 시세 없음 경로(엔카 요청 0)


# ── 합성 응답 ────────────────────────────────────────────────────────
def _obj(seq, gds, maker, model, year, cc, fuel, km, cs=SA, court=COURT):
    return {"csNo": cs, "cortOfcCd": court, "dspslGdsSeq": gds, "dspslObjctSeq": seq,
            "gdsVendNm": maker, "carMdlNm": model, "carDelvYr": year, "carDsplcCtt": cc,
            "fuelKndCd": fuel, "drvnDistIndctCtt": km,
            "carVidCtt": f"TESTVIN0000000{seq:03d}", "objctRegNo": "00가0000"}     # 합성(실제 값 아님)


def _resp(gds, objs, *, cs=SA, court=COURT, spec="", aee=(AEE_MULTI,), pics=3, dxdy=(), appraisal=7_400_000,
          fails=3):
    return {"data": {"dma_result": {
        "dspslGdsDxdyInfo": {"csNo": cs, "cortOfcCd": court, "dspslGdsSeq": gds, "aeeEvlAmt": appraisal,
                             "flbdNcnt": fails, "dspslDxdyYmd": SD.replace("-", ""), "gdsSpcfcRmk": spec},
        "gdsDspslObjctLst": list(objs),
        "csPicLst": [{"csNo": cs, "cortOfcCd": court, "picTitlNm": f"{court}{cs}{i}.jpg", "picFile": None}
                     for i in range(1, pics + 1)],
        "aeeWevlMnpntLst": [{"csNo": cs, "cortOfcCd": court, "aeeWevlMnpntCtt": t} for t in aee],
        "gdsDspslDxdyLst": [{"auctnDxdyKndCd": "01", "dxdyYmd": d.replace("-", ""), "auctnDxdyRsltCd": c,
                             "tsLwsDspslPrc": p, "dspslAmt": 0} for d, c, p in dxdy]}}}


# 매각물건 3 = 목적물 4(벤츠) — 올바른 키로 받는 응답
BENZ_DXDY = (("2026-04-20", "002", 7_400_000), ("2026-05-22", "002", 5_180_000),
             ("2026-09-07", "002", 3_626_000), (SD, "", 2_538_000))
BENZ_RESP = _resp(3, [_obj(4, 3, "벤츠", "CLS350", 2012, 3498, "0001001", 254_000)],
                  spec="전반적인 사용 흠집 있고 관리상태 보통", dxdy=BENZ_DXDY)
# 매각물건 4 = 목적물 5(스타렉스) — 예전 키(item_no 4)로 물으면 벤츠 행이 이걸 받았다
STAREX_DXDY = (("2026-04-20", "002", 5_000_000), ("2026-05-22", "002", 3_500_000),
               ("2026-09-07", "002", 2_450_000), (SD, "", 1_715_000))
STAREX_RESP = _resp(4, [_obj(5, 4, "현대", "그랜드 스타렉스", 2017, 2497, "0001002", 188_000)],
                    spec="조수석쪽 뒤바퀴 주변에 부식이 있음", dxdy=STAREX_DXDY, appraisal=5_000_000)
BY_SEQ = {"3": BENZ_RESP, "4": STAREX_RESP}       # 매각물건 5 는 없다 → 빈 응답


class _R:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def _court(monkeypatch, by_seq=None, sent=None):
    """법원 상세·세션 대역 — (saNo, 법원, 매각물건) 을 sent 에 적고 by_seq[매각물건] 을 돌려준다(없으면 빈 응답)."""
    by_seq = BY_SEQ if by_seq is None else by_seq
    sent = [] if sent is None else sent

    def fd(cs, sa, bo, seq="1"):
        sent.append((sa, bo, str(seq)))
        return _R(by_seq.get(str(seq), {}))
    monkeypatch.setattr(service, "new_session", lambda: object())
    monkeypatch.setattr(service, "warmup", lambda *a, **k: None)
    monkeypatch.setattr(service, "fetch_detail", fd)
    return sent


@pytest.fixture
def saved(monkeypatch, tmp_path):
    """save_item_folder 를 임시 폴더로 — 실제 함수를 그대로 쓰되 저장소 data/ 에 쓰지 않는다."""
    out = []
    real = cad.save_item_folder

    def f(resp, fk, cfg=None):
        out.append(fk)
        return real(resp, fk, cfg, base_dir=str(tmp_path / "data"))
    monkeypatch.setattr(service, "save_item_folder", f)
    out_dir = tmp_path / "data"
    return out, out_dir


def V(**kw) -> dict:
    """운영 DB 의 벤츠 행 모양(10-02 사본) — 상태 '완료'인데 옆 물건 상세로 채워져 있다."""
    base = {"id": BENZ, "folder_key": BENZ, "case_no": CASE, "item_no": "4", "court": COURT_NAME,
            "court_code": COURT, "doc_id": DOC_BENZ, "maker": "벤츠", "model": "CLS350", "year": 2012,
            "mileage_km": 254_000, "displacement_cc": 2497, "fuel_code": "0001002",
            "spec_remark": "조수석쪽 뒤바퀴 주변에 부식이 있음", "appraisal_value": 7_400_000,
            "min_sale_price": 1_715_000, "fail_count": 3, "sale_date": SD, "status": "완료",
            "judgment": "시세 신뢰도 낮음, 수동 검토", "market_platform": "encar", "photo_count": 3,
            "accident_grade": "accident", "collected_at": "2026-08-24 06:30:30",
            "analyzed_at": "2026-08-24 06:30:36"}
    base.update(kw)
    return base


def STAREX_ROW(**kw) -> dict:
    base = {"id": STAREX, "folder_key": STAREX, "case_no": CASE, "item_no": "5", "court": COURT_NAME,
            "court_code": COURT, "doc_id": DOC_STAREX, "maker": "현대자동차", "model": "그랜드 스타렉스",
            "year": 2017, "appraisal_value": 5_000_000, "min_sale_price": 2_450_000, "fail_count": 3,
            "sale_date": SD, "status": "상세없음", "photo_count": 0}
    base.update(kw)
    return base


def _list_row(v: dict, maemul: str) -> dict:
    """법원 목록 행(tests/fixtures/list_sample.json 과 같은 키) — 합성."""
    sa = v["doc_id"][7:21]
    return {"printCsNo": f"{v['court']}<br/>{v['case_no']}", "saNo": sa, "boCd": v["court_code"],
            "jiwonNm": v["court"], "mokmulSer": v["item_no"], "maemulSer": maemul, "docid": v["doc_id"],
            "carNm": v["model"], "jejosaNm": v["maker"], "maeGiil": v["sale_date"].replace("-", ""),
            "minmaePrice": str(v["min_sale_price"]), "gamevalAmt": str(v["appraisal_value"]),
            "yuchalCnt": str(v["fail_count"]), "carYrtype": str(v["year"]), "mulStatcd": "01",
            "printSt": "사용본거지 : 서울 중구"}


def _stub_list(monkeypatch, rows):
    monkeypatch.setattr(service, "fetch_list_page", lambda cs, page_no=1, page_size=40, **kw: _R(
        {"data": {"dlt_srchResult": rows[(page_no - 1) * 40: page_no * 40],
                  "dma_pageInfo": {"groupTotalCount": len(rows)}}}))


def _stub_daily_rest(monkeypatch):
    monkeypatch.setattr(service, "refresh_lagged_floors", lambda **k: {})
    monkeypatch.setattr(service, "encar_health", lambda *a, **k: {"state": "ok", "code": 200})
    monkeypatch.setattr(service, "requery_missing_market", lambda **k: {"targets": 0, "updated": 0})
    monkeypatch.setattr(service, "reuse_market_prices", lambda **k: {})
    monkeypatch.setattr(service, "photo_autosort_run", lambda **k: {"sorted": 0})
    monkeypatch.setattr(service, "update_results", lambda **k: 0)
    monkeypatch.setattr(service, "review_daily_anomalies",
                        lambda *a, **k: {"found": 0, "reviewed": 0, "resolved": 0, "quarantined": 0})
    monkeypatch.setattr(service, "newcar_collect", lambda **k: {"matched": 0, "remaining": 0})


def _anoms(action=None):
    conn = db.connect()
    q = "SELECT * FROM anomaly_log" + (" WHERE action=?" if action else "") + " ORDER BY id"
    rows = [dict(r) for r in conn.execute(q, (action,) if action else ()).fetchall()]
    conn.close()
    return rows


def _snapshot(vid):
    conn = db.connect()
    r = conn.execute("SELECT * FROM vehicles WHERE id=?", (vid,)).fetchone()
    conn.close()
    return tuple(r) if r else None


# ═════════════════════════════════════════════════════════════════════
# ① 키 해석 — 저장값 → doc_id → item_no
# ═════════════════════════════════════════════════════════════════════
def test_사건번호에서_saNo_를_만든다_역함수():
    assert lp.sano_from_case_no("2025타경53697") == "20250130053697"
    assert lp.sano_from_case_no("2026타경101080") == "20260130101080"
    assert lp.case_no_from_sano(lp.sano_from_case_no(CASE)) == CASE
    for bad in ("(중복)", "(병합)", "2025타경1234567", "", None, "2025가단1"):
        assert lp.sano_from_case_no(bad) is None, bad


def test_doc_id_끝_두_자리는_매각물건_목적물_순서다():
    """라이브 2건과 같은 모양: '34' → 매각물건 3, '12' → 매각물건 1."""
    assert service.detail_request_seq(V()) == ("3", "doc_id")
    assert service.detail_request_seq(STAREX_ROW()) == ("4", "doc_id")
    v = {"case_no": "2026타경90080", "item_no": "2", "court_code": "B000210",
         "doc_id": "B000210" + "20260130090080" + "12"}
    assert service.detail_request_seq(v) == ("1", "doc_id")


def test_목록에서_저장한_매각물건_번호가_먼저다():
    assert service.detail_request_seq(V(maemul_ser="3")) == ("3", "stored")
    assert service.detail_request_seq(V(maemul_ser=" 3 ")) == ("3", "stored")
    # 저장값이 숫자가 아니면 쓰지 않는다 → doc_id
    assert service.detail_request_seq(V(maemul_ser="x")) == ("3", "doc_id")


@pytest.mark.parametrize("kw", [
    {"court_code": "B000998"},                                # 앞 7자 ≠ 법원코드
    {"case_no": "2025타경90698"},                              # 가운데 14자 ≠ 이 사건
    {"case_no": "(중복)"},                                     # 사건번호 형식 밖
    {"doc_id": DOC_BENZ[:22]},                                 # 22자
    {"doc_id": DOC_BENZ[:21] + "3x"},                          # 끝이 숫자 아님
    {"doc_id": DOC_BENZ[:21] + "04"},                          # 매각물건 0
    {"item_no": "3"},                                          # 둘째 자리 ≠ item_no — 해석이 이 물건과 안 맞는다
])
def test_doc_id_형식_검사를_하나라도_못_넘으면_item_no_로(kw):
    v = V(**kw)
    assert service.detail_request_seq(v) == (v["item_no"], "item_no")


def test_item_no_대체값은_예전_식_그대로():
    assert service.detail_request_seq({"item_no": None, "doc_id": ""}) == ("1", "item_no")
    assert service.detail_request_seq({"item_no": "2", "doc_id": ""}) == ("2", "item_no")


# ═════════════════════════════════════════════════════════════════════
# ① 모든 상세 요청 경로가 매각물건 번호를 보낸다
# ═════════════════════════════════════════════════════════════════════
def test_단건_분석은_매각물건_번호로_묻고_올바른_상세를_저장한다(monkeypatch, saved):
    db.upsert_vehicle(V())
    sent = _court(monkeypatch)
    out = service.analyze_single(BENZ)
    assert sent == [(SA, COURT, "3")], "item_no(4)가 아니라 매각물건 번호(3)로 물어야 한다"
    assert (out["displacement_cc"], out["fuel_code"]) == (3498, "0001001"), "옆 물건(스타렉스) 값이 남았다"
    assert out["min_sale_price"] == 2_538_000 and out["spec_remark"] == "전반적인 사용 흠집 있고 관리상태 보통"
    assert out["detail_seq"] == "3"
    folders, data_dir = saved
    assert folders == [BENZ]
    dj = json.loads((data_dir / BENZ / "detail.json").read_text(encoding="utf-8"))
    assert (dj["model"], dj["object_seq"], dj["item_seq"]) == ("CLS350", "4", "3")


def test_재분석은_매각물건_번호로_묻는다(monkeypatch, saved):
    db.upsert_vehicle(STAREX_ROW())          # 상세없음 → _reanalyze 대상
    sent = _court(monkeypatch)
    rid = db.create_run(target=5)
    service._active["running"] = True
    service._reanalyze(max_items=5, repair_cost=500_000, run_id=rid)
    assert sent == [(SA, COURT, "4")], "목적물 5 가 아니라 매각물건 4 로 물어야 한다"
    v = db.get_vehicle(STAREX)
    assert v["status"] == "완료" and v["displacement_cc"] == 2497 and v["detail_seq"] == "4"


def test_최종_검토_재확인은_매각물건_번호로_묻는다(monkeypatch, saved):
    # 이상 낙찰(낙찰인데 기일 미도래) → 재확인 대상
    db.upsert_vehicle(V(auction_result="낙찰", winning_price=100, status="종결", judgment="종결"))
    sent = _court(monkeypatch)
    out = service.review_daily_anomalies(object(), object(), service.load_config())
    assert sent == [(SA, COURT, "3")]
    assert out["reviewed"] == 1 and out.get("mismatch", 0) == 0


def test_매일_갱신_분석은_매각물건_번호로_묻는다(monkeypatch, saved):
    db.upsert_vehicle(V(status="미분석"))
    _stub_list(monkeypatch, [])
    _stub_daily_rest(monkeypatch)
    sent = _court(monkeypatch)
    out = service.daily_update(run_id=db.create_run(target=0))
    assert sent == [(SA, COURT, "3")]
    v = db.get_vehicle(BENZ)
    assert (v["status"], v["displacement_cc"], v["min_sale_price"]) == ("완료", 3498, 2_538_000)
    assert out["detail_mismatch"] == 0


def _seed_lagging(**kw):
    """최저가 지연(목록 값이 한 회차 늦음) 벤츠 — 최저가 재조회 대상."""
    v = V(min_sale_price=3_626_000, judgment="입찰 검토 가능", median_price=9_000_000, sample_count=10,
          market_confidence_label="높음", upper_bid=4_000_000, lower_bound=3_626_000,
          displacement_cc=3498, fuel_code="0001001", spec_remark="", dxdy_history=None, **kw)
    db.upsert_vehicle(v)
    return v


def _floor_on():
    return {**service.load_config(), "min_refresh_enabled": True, "min_refresh_daily_cap": 10}


def test_최저가_재조회는_매각물건_번호로_묻고_옆_물건_최저가를_쓰지_않는다(monkeypatch):
    _seed_lagging()
    monkeypatch.setattr(service.time, "sleep", lambda s: None)
    sent = _court(monkeypatch)
    res = service.refresh_lagged_floors(config=_floor_on())
    assert sent == [(SA, COURT, "3")], "예전엔 item_no(4)로 물어 스타렉스(매각물건 4)의 기일내역을 받았다"
    v = db.get_vehicle(BENZ)
    assert v["min_sale_price"] == 2_538_000, "벤츠의 이번 회차 최저가(253.8만)여야 한다 — 171.5만은 옆 물건"
    assert res["changed"] == 1 and res["mismatch"] == 0


def test_최저가_재조회도_옆_물건_응답이면_섞지_않고_기록한다(monkeypatch):
    """키가 어긋난 경우(저장값이 틀린 등)에도 응답 확인이 막는다 — 기일내역·최저가를 쓰지 않는다."""
    _seed_lagging(maemul_ser="4")          # 일부러 틀린 저장값 → 매각물건 4(목적물 5) 응답
    monkeypatch.setattr(service.time, "sleep", lambda s: None)
    sent = _court(monkeypatch)
    res = service.refresh_lagged_floors(config=_floor_on())
    assert sent == [(SA, COURT, "4")]
    v = db.get_vehicle(BENZ)
    assert v["min_sale_price"] == 3_626_000 and not v.get("dxdy_history"), "옆 물건 최저가가 섞였다"
    assert v["floor_checked_at"], "헛걸음도 백오프 기준이 된다(법원 불일치와 같은 처리)"
    assert res["mismatch"] == 1 and res["changed"] == 0
    a = _anoms("detail-mismatch")
    assert len(a) == 1 and a[0]["vehicle_id"] == BENZ and "최저가 재조회" in a[0]["note"]


def test_수동_수집_경로는_목록_행의_매각물건_번호를_그대로(monkeypatch, saved):
    """/run(_run_collection)은 예전부터 목록 행을 그대로 넘긴다 — 바뀌지 않았는지 + 목록 값 저장."""
    v = V()
    _stub_list(monkeypatch, [_list_row(v, "3")])
    sent = _court(monkeypatch)
    rid = db.create_run(target=1)
    service._active["running"] = True
    service._run_collection(max_items=1, scan_limit=1, repair_cost=500_000, run_id=rid)
    assert sent == [(SA, COURT, "3")]
    got = db.get_vehicle(BENZ)
    assert (got["displacement_cc"], got["maemul_ser"], got["detail_seq"]) == (3498, "3", "3")


def test_상세_요청_경로_전수_그리고_item_no_를_보내는_식이_남지_않았다():
    """fetch_detail 을 부르는 곳은 이 넷뿐이다. 새 경로가 생기면 키(_detail_raw/목록 행)와 응답 확인(detail_identity)을
    거치는지 보고 여기에 더한다. 감사 당시 네 곳 + 최저가 재조회가 `maemulSer: item_no` 를 보냈다."""
    calls = set()
    for p in sorted(list((ROOT / "web").glob("*.py")) + list((ROOT / "src").rglob("*.py"))):
        src = p.read_text(encoding="utf-8")
        assert not re.search(r"""["']maemulSer["']\s*:\s*v\.get\(\s*["']item_no""", src), p
        for m in re.finditer(r"(?<!def )\bfetch_detail\(", src):
            fn = re.findall(r"^def (\w+)", src[:m.start()], re.M)[-1]
            calls.add((p.relative_to(ROOT).as_posix(), fn))
            body = src[src.rindex("\ndef " + fn, 0, m.start()):]
            body = body[:body.find("\ndef ", 5) if body.find("\ndef ", 5) > 0 else len(body)]
            assert "detail_identity(" in body, f"{p.name}:{fn} 가 받은 상세를 확인하지 않는다"
    assert calls == {("src/collect/courtauction_detail.py", "main"), ("src/pipeline.py", "run"),
                     ("web/service.py", "_analyze_item"), ("web/service.py", "refresh_lagged_floors")}, calls


# ═════════════════════════════════════════════════════════════════════
# ① 두 번호가 같은 행은 예전과 바이트까지 같다
# ═════════════════════════════════════════════════════════════════════
class _Sess:
    """requests.Session 대역 — 실제 fetch_detail()·_check_block() 이 이 객체를 부른다(요청 0)."""

    def __init__(self, payload):
        self.bodies, self._payload = [], payload

    def post(self, url, data=None, headers=None, timeout=None):
        self.bodies.append(data)
        p = self._payload

        class R:
            status_code = 200
            headers = {"Content-Type": "application/json;charset=UTF-8"}
            text = json.dumps(p)

            def json(self):
                return p
        return R()


@pytest.mark.parametrize("row", [
    dict(id="2026타경90001_1", case_no="2026타경90001", item_no="1", doc_id="B000210" + "20260130090001" + "11"),
    dict(id="2026타경90001_2", case_no="2026타경90001", item_no="2", doc_id="B000210" + "20260130090001" + "22",
         maemul_ser="2"),
    dict(id="(중복)_7", case_no="(중복)", item_no="7", doc_id="B000210" + "20260130090002" + "27"),
])
def test_두_번호가_같거나_해석을_못_하는_행은_요청_바이트가_예전과_같다(monkeypatch, saved, row):
    v = {"court": "가상법원", "court_code": "B000210", "maker": "현대", "model": "아반떼", "year": 2020,
         "sale_date": SD, "status": "완료", "min_sale_price": 5_000_000, **row}
    v["folder_key"] = v["id"]
    db.upsert_vehicle(v)
    sess = _Sess({})
    monkeypatch.setattr(service, "new_session", lambda: sess)
    monkeypatch.setattr(service, "warmup", lambda *a, **k: None)
    monkeypatch.setattr(service, "fetch_detail", cad.fetch_detail)
    monkeypatch.setattr(cad.time, "sleep", lambda s: None)
    service.analyze_single(v["id"])
    head = json.dumps({"dma_srchGdsDtlSrch": {"csNo": v["doc_id"][7:21], "cortOfcCd": "B000210",
                                              "dspslGdsSeq": v["item_no"], "pgmId": "PGJ154M03",
                                              "srchInfo": {}}})       # 예전 식(item_no)으로 만든 요청
    assert sess.bodies == [head]


# ═════════════════════════════════════════════════════════════════════
# ② 응답 확인 · 목적물 고르기
# ═════════════════════════════════════════════════════════════════════
def test_응답_확인_같은_사건_매각물건_목적물이면_통과():
    from src.parse.detail_parser import detail_identity
    r = detail_identity(BENZ_RESP, SA, COURT, "3", "4")
    assert r["ok"] and r["obj_index"] == 0 and r["pick"] == "matched"
    assert r["got"]["objects"] == [["4", "벤츠 CLS350 2012"]]


@pytest.mark.parametrize("args,why", [
    ((STAREX_RESP, SA, COURT, "4", "4"), "목적물 4 없음"),          # 예전 키로 받은 옆 물건 — 벤츠 행에 스타렉스
    ((BENZ_RESP, SA, COURT, "3", "3"), "목적물 3 없음"),
    ((BENZ_RESP, "20250130090698", COURT, "3", "4"), "사건"),
    ((BENZ_RESP, SA, "B000998", "3", "4"), "법원"),
    ((BENZ_RESP, SA, COURT, "4", "4"), "매각물건 3≠4"),
])
def test_응답_확인_하나라도_다르면_불일치(args, why):
    from src.parse.detail_parser import detail_identity
    r = detail_identity(*args)
    assert not r["ok"] and r["obj_index"] is None
    assert any(why in x for x in r["reasons"]), r["reasons"]


def test_일괄매각은_0번이_아니라_목적물_번호로_고른다(saved):
    """매각물건 1 에 목적물 1·2 — 예전 `_vehicle_obj` 는 [0](목적물 1)을 집어 _2 행에 남의 차를 붙였다."""
    from src.parse.detail_parser import detail_identity, narrow_to_object
    bulk = _resp(1, [_obj(1, 1, "기아", "봉고3", 2015, 2497, "0001002", 120_000),
                     _obj(2, 1, "현대", "포터2", 2018, 2497, "0001002", 80_000)], appraisal=9_000_000)
    assert parse_detail(bulk, item_no="2").model == "포터2"
    assert parse_detail(bulk, item_no="1").model == "봉고3"
    assert parse_detail(bulk).model == "", "목적물 번호를 모르면 여럿 중 아무것도 집지 않는다"
    r = detail_identity(bulk, SA, COURT, "1", "2")
    assert r["ok"] and r["obj_index"] == 1
    narrowed = narrow_to_object(bulk, r["obj_index"])
    assert parse_detail(narrowed).model == "포터2" and parse_detail(narrowed).object_seq == "2"
    assert len(bulk["data"]["dma_result"]["gdsDspslObjctLst"]) == 2, "원본을 바꾸면 안 된다"


def test_목적물_번호가_없는_옛_응답은_하나뿐이고_두_번호가_같을_때만():
    from src.parse.detail_parser import detail_identity
    old = _resp(1, [{k: v for k, v in _obj(1, 1, "현대", "아반떼", 2020, 1598, "0001001", 50_000).items()
                     if k != "dspslObjctSeq"}])
    assert detail_identity(old, SA, COURT, "1", "1")["ok"], "축소 픽스처 모양 — 두 번호가 같으면 갈릴 여지가 없다"
    assert not detail_identity(old, SA, COURT, "1", "2")["ok"]
    two = _resp(1, [{k: v for k, v in o.items() if k != "dspslObjctSeq"}
                    for o in (_obj(1, 1, "현대", "아반떼", 2020, 1598, "0001001", 1),
                              _obj(2, 1, "기아", "K5", 2020, 1999, "0001001", 2))])
    assert not detail_identity(two, SA, COURT, "1", "1")["ok"], "목적물이 여럿이면 번호 없이 고르지 않는다"


def test_빈_응답은_불일치가_아니라_기존_상세없음_규칙으로():
    from src.parse.detail_parser import detail_identity
    assert detail_identity({}, SA, COURT, "5", "5")["ok"]
    assert detail_identity({"data": {"dma_result": {}}}, SA, COURT, "5", "5")["ok"]


def test_옆_물건_응답이면_매일_갱신은_아무것도_쓰지_않고_경고를_남긴다(monkeypatch, saved):
    """저장값이 틀려(가상) 매각물건 4 를 물었고 스타렉스가 왔다 — 벤츠 행은 바이트 하나 안 바뀐다."""
    from web import ops_health
    db.upsert_vehicle(V(status="미분석", maemul_ser="4"))
    before = _snapshot(BENZ)
    _stub_list(monkeypatch, [])
    _stub_daily_rest(monkeypatch)
    sent = _court(monkeypatch)
    rid = db.create_run(target=0)
    out = service.daily_update(run_id=rid)
    assert sent == [(SA, COURT, "4")]
    assert _snapshot(BENZ) == before, "옆 물건 상세가 벤츠 행에 쓰였다"
    assert saved[0] == [], "사진·감정서 폴더도 쓰지 않는다"
    assert out["detail_mismatch"] == 1 and out["analyzed"] == 0
    msg = db.latest_run()["message"]
    assert msg.startswith("입찰예정 0 · 분석 0 · ⚠상세 불일치 1 보류 · "), msg
    assert "⚠상세 불일치 1 보류" in ops_health.warn_parts(msg)
    a = _anoms("detail-mismatch")
    assert len(a) == 1 and a[0]["vehicle_id"] == BENZ
    assert "목적물 4 없음" in a[0]["note"] and "5=현대 그랜드 스타렉스 2017" in a[0]["note"]
    assert "TESTVIN" not in a[0]["note"] and "00가0000" not in a[0]["note"], "차대번호·등록번호를 적지 않는다"


def test_불일치가_없으면_실행_기록에_조각이_없다(monkeypatch, saved):
    db.upsert_vehicle(V(status="미분석"))
    _stub_list(monkeypatch, [])
    _stub_daily_rest(monkeypatch)
    _court(monkeypatch)
    service.daily_update(run_id=db.create_run(target=0))
    assert "상세 불일치" not in db.latest_run()["message"]


def test_단건_분석_불일치는_행을_그대로_두고_안내한다(monkeypatch, saved):
    from fastapi.testclient import TestClient
    import web.app as A
    db.upsert_vehicle(V(maemul_ser="4"))
    before = _snapshot(BENZ)
    _court(monkeypatch)
    r = TestClient(A.app).post(f"/vehicle/{BENZ}/analyze", headers={"host": "127.0.0.1"}, follow_redirects=False)
    assert r.status_code == 303 and "an=" in r.headers["location"]
    from urllib.parse import unquote
    assert "법원 상세가 이 물건과 달라 저장하지 않았습니다" in unquote(r.headers["location"])
    assert _snapshot(BENZ) == before, "상태(오류: …)든 값이든 아무것도 바뀌면 안 된다"


def test_재분석_불일치는_쓰지_않고_기록만(monkeypatch, saved):
    db.upsert_vehicle(STAREX_ROW(maemul_ser="3"))       # 틀린 저장값 → 매각물건 3(목적물 4 벤츠) 응답
    before = _snapshot(STAREX)
    _court(monkeypatch)
    service._active["running"] = True
    service._reanalyze(max_items=5, repair_cost=500_000, run_id=db.create_run(target=5))
    assert _snapshot(STAREX) == before
    assert [a["vehicle_id"] for a in _anoms("detail-mismatch")] == [STAREX]


def test_최종_검토_불일치는_쓰지_않고_따로_센다(monkeypatch, saved):
    db.upsert_vehicle(V(auction_result="낙찰", winning_price=100, status="종결", judgment="종결", maemul_ser="4"))
    before = _snapshot(BENZ)
    _court(monkeypatch)
    out = service.review_daily_anomalies(object(), object(), service.load_config())
    assert out["mismatch"] == 1 and out["resolved"] == 0 and out["reviewed"] == 0
    assert _snapshot(BENZ) == before


# ═════════════════════════════════════════════════════════════════════
# ⑤ C.4-5 — 불일치는 비정상 응답 카운터를 되돌리지 않는다(예전보다 약해지지 않는다)
# ═════════════════════════════════════════════════════════════════════
def test_불일치는_연속_실패_카운터를_0으로_되돌리지_않는다(monkeypatch, saved):
    """[비정상, 불일치, 비정상, 비정상] — 예전엔 불일치 응답을 '성공'으로 저장하고 카운터를 0 으로 되돌려 멈추지 않았다.
    이제 불일치는 카운터를 건드리지 않으므로 비정상 3번째에서 멈춘다(C.4-5)."""
    rows = []
    for i, (case, sa) in enumerate((("2026타경90011", "20260130090011"), ("2026타경90012", "20260130090012"),
                                     ("2026타경90013", "20260130090013"), ("2026타경90014", "20260130090014"))):
        rows.append(sa)
        db.upsert_vehicle({"id": f"{case}_1", "folder_key": f"{case}_1", "case_no": case, "item_no": "1",
                           "court_code": COURT, "doc_id": f"{COURT}{sa}11", "maker": "현대", "model": "아반떼",
                           "year": 2020, "sale_date": (TODAY + timedelta(days=3 + i)).isoformat(),
                           "status": "미분석", "min_sale_price": 5_000_000})
    _stub_list(monkeypatch, [])
    _stub_daily_rest(monkeypatch)
    calls = []

    def fd(cs, sa, bo, seq="1"):
        calls.append(sa)
        if sa == rows[1]:                     # 두 번째 물건: 정상 JSON 이지만 다른 목적물
            return _R(_resp(1, [_obj(2, 1, "기아", "K5", 2019, 1999, "0001001", 1)], cs=sa))
        raise ValueError("응답 형식 이상")      # 비정상(JSON 깨짐 등)
    monkeypatch.setattr(service, "new_session", lambda: object())
    monkeypatch.setattr(service, "warmup", lambda *a, **k: None)
    monkeypatch.setattr(service, "fetch_detail", fd)
    with pytest.raises(RuntimeError, match="3회 연속"):
        service.daily_update(run_id=db.create_run(target=0))
    assert calls == rows, "네 번째 비정상에서 멈춰야 한다(그 뒤 요청 없음)"


def test_불일치_메시지는_차단으로_읽히지_않는다():
    e = service.DetailMismatch({"saNo": SA}, {"reasons": ["목적물 4 없음"]})
    assert not service._is_block(e) and "차단" not in str(e)


# ═════════════════════════════════════════════════════════════════════
# ③ 감정요항 '기호N' 은 목적물 번호
# ═════════════════════════════════════════════════════════════════════
def test_구조화_주행거리가_없으면_목적물_번호의_기호에서_찾는다():
    """매각물건 3 · 목적물 4(벤츠). 예전엔 매각물건 번호(3)를 기호로 넘겨 기호3(기아 237,000km)을 집었다."""
    r = _resp(3, [_obj(4, 3, "벤츠", "CLS350", 2012, 3498, "0001001", None)])
    assert parse_detail(r).mileage_km == 254_000
    assert parse_detail(r, item_no="4").mileage_km == 254_000


def test_목적물_번호를_모르면_다물건_글에서_값을_만들지_않는다():
    o = {k: v for k, v in _obj(4, 3, "벤츠", "CLS350", 2012, 3498, "0001001", None).items() if k != "dspslObjctSeq"}
    assert parse_detail(_resp(3, [o])).mileage_km is None
    one = _resp(1, [{**o, "dspslGdsSeq": 1}], aee=("계기판상 주행거리는 52,900㎞임.",))
    assert parse_detail(one).mileage_km == 52_900, "단일 물건 글은 예전처럼 읽는다"


# ═════════════════════════════════════════════════════════════════════
# 저장 — 목록 행의 매각물건 번호(신규·갱신), 확인된 상세 키 보존, 마이그레이션
# ═════════════════════════════════════════════════════════════════════
def test_목록_파서가_매각물건_번호를_싣는다():
    it = lp.parse_row(_list_row(V(), "3"))
    assert (it.item_no, it.maemul_ser) == ("4", "3")
    assert lp.parse_row({**_list_row(V(), "3"), "maemulSer": None}).maemul_ser == ""


def test_목록_갱신이_매각물건_번호를_신규_갱신_모두_저장하고_빈_값으로_지우지_않는다(monkeypatch):
    v = V()
    _stub_list(monkeypatch, [_list_row(v, "3")])
    monkeypatch.setattr(service, "new_session", lambda: object())
    monkeypatch.setattr(service, "warmup", lambda *a, **k: None)
    service.collect_upcoming(within_days=30)
    assert db.get_vehicle(BENZ)["maemul_ser"] == "3", "신규 행"
    db.update_fields(BENZ, maemul_ser="9", detail_seq="3", status="완료")
    service.collect_upcoming(within_days=30)
    got = db.get_vehicle(BENZ)
    assert got["maemul_ser"] == "3", "갱신 행 — 목록 값이 권위"
    assert got["detail_seq"] == "3" and got["status"] == "완료", "분석 쪽 열은 목록 갱신이 덮지 않는다"
    _stub_list(monkeypatch, [{**_list_row(v, "3"), "maemulSer": ""}])
    service.collect_upcoming(within_days=30)
    assert db.get_vehicle(BENZ)["maemul_ser"] == "3", "목록에 값이 없으면 저장값을 지우지 않는다"
    assert "detail_seq" in db._LISTING_KEEP and "maemul_ser" not in db._LISTING_KEEP


def test_마이그레이션은_옛_DB_에_열만_더한다(tmp_path, monkeypatch):
    import sqlite3
    p = tmp_path / "old.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE vehicles (id TEXT PRIMARY KEY, case_no TEXT, item_no TEXT, doc_id TEXT, status TEXT)")
    c.execute("INSERT INTO vehicles VALUES (?,?,?,?,?)", (BENZ, CASE, "4", DOC_BENZ, "완료"))
    c.commit()
    c.close()
    monkeypatch.setattr(db, "DB_PATH", p)
    db.init_db()
    db.init_db()                                           # 두 번 돌려도 된다(ALTER 가드)
    v = db.get_vehicle(BENZ)
    assert "maemul_ser" in v and "detail_seq" in v and v["maemul_ser"] is None and v["detail_seq"] is None
    assert (v["case_no"], v["item_no"], v["status"]) == (CASE, "4", "완료")


# ═════════════════════════════════════════════════════════════════════
# ④ 복구 — redetail-key 예약 → 다음 매일 갱신이 기존 상한 안에서 다시 받는다
# ═════════════════════════════════════════════════════════════════════
def test_복구_미리보기는_입찰예정의_예전_키_행만_고르고_쓰지_않는다():
    db.upsert_vehicle(V())                                                    # target_wrong
    db.upsert_vehicle(STAREX_ROW())                                           # target_missing
    db.upsert_vehicle(V(id="P_4", folder_key="P_4", sale_date=PAST))          # 지난 기일
    db.upsert_vehicle(V(id="C_4", folder_key="C_4", auction_result="낙찰"))   # 끝난 매각
    db.upsert_vehicle(V(id="Q_4", folder_key="Q_4", status="미분석"))          # 이미 분석 대기
    db.upsert_vehicle(V(id="S_1", folder_key="S_1", item_no="1", doc_id=f"{COURT}{SA}11"))  # 키가 같다
    db.upsert_vehicle(V(id="K_4", folder_key="K_4", doc_id=""))               # 받을 키가 없다
    db.upsert_vehicle(V(id="D_4", folder_key="D_4", detail_seq="3"))          # 새 키로 확인한 상세
    before = {v["id"]: _snapshot(v["id"]) for v in db.list_vehicles()}
    out = service.redetail_key()
    assert sorted((r["id"], r["why"], r["key"], r["key_src"]) for r in out["rows"]) == sorted([
        (BENZ, "target_wrong", ["4", "3"], "doc_id"), (STAREX, "target_missing", ["5", "4"], "doc_id")])
    assert out["skipped"] == {"past": 1, "closed": 1, "no_key": 1, "same_key": 1, "queued": 1, "verified": 1}
    benz = next(r for r in out["rows"] if r["id"] == BENZ)
    assert benz["stored"]["displacement_cc"] == 2497, "의심 값(옆 물건 배기량)을 함께 보여 준다"
    assert out["applied"] == 0 and {v["id"]: _snapshot(v["id"]) for v in db.list_vehicles()} == before
    assert _anoms() == []


def test_복구_적용_다음_매일_갱신이_올바른_키로_다시_받고_멱등이다(monkeypatch, saved):
    """운영 사본의 두 경우 그대로: 옆 물건 상세로 채워진 '완료' 행(벤츠) + 예전 키로 빈 응답을 받은 '상세없음' 행(스타렉스)."""
    db.upsert_vehicle(V(dxdy_history=[{"ymd": SD, "result_code": "", "result": "", "lws_price": 1_715_000,
                                       "dspsl_amt": 0}], floor_checked_at=f"{TODAY.isoformat()} 06:49:45"))
    db.upsert_vehicle(STAREX_ROW())
    out = service.redetail_key(ids=[BENZ, STAREX], apply=True)
    assert out["applied"] == 2
    assert {db.get_vehicle(i)["status"] for i in (BENZ, STAREX)} == {"미분석"}
    assert [a["action"] for a in _anoms()] == ["requeued", "requeued"]
    again = service.redetail_key()
    assert again["targets"] == 0 and again["skipped"]["queued"] == 2, "예약한 행은 다시 고르지 않는다"
    # 다음 매일 갱신 — 목록에 두 물건이 그대로 있다(목록 행엔 매각물건 번호가 있다)
    _stub_list(monkeypatch, [_list_row(V(), "3"), _list_row(STAREX_ROW(), "4")])
    _stub_daily_rest(monkeypatch)
    sent = _court(monkeypatch)
    res = service.daily_update(run_id=db.create_run(target=0))
    assert sorted(sent) == sorted([(SA, COURT, "3"), (SA, COURT, "4")]), "물건마다 한 번 — 추가 요청 없음"
    b, s = db.get_vehicle(BENZ), db.get_vehicle(STAREX)
    assert (b["status"], b["displacement_cc"], b["fuel_code"], b["min_sale_price"]) == ("완료", 3498, "0001001",
                                                                                        2_538_000)
    assert [h["lws_price"] for h in b["dxdy_history"]][-1] == 2_538_000, "벤츠 매각물건의 기일내역"
    assert (b["maemul_ser"], b["detail_seq"]) == ("3", "3")
    assert (s["status"], s["displacement_cc"], s["detail_seq"]) == ("완료", 2497, "4"), "숨겨졌던 스타렉스가 돌아온다"
    assert res["detail_mismatch"] == 0 and res["analyzed"] == 2
    final = service.redetail_key()
    assert final["targets"] == 0 and final["skipped"]["verified"] == 2, "다시 받은 뒤에도 다시 고르지 않는다(멱등)"


def test_상세없음_행은_예약_없이도_다음_매일_갱신에서_다시_묻는다(monkeypatch, saved):
    """목록 재등장 복구(mark_disappeared: 상세없음 → 미분석) → 같은 런의 분석 단계. 예전엔 목적물 번호(5)로 물어
    빈 응답 → 다시 상세없음(10-02 06:37 운영 기록과 같은 순환). 이제 매각물건 번호(4)로 물어 돌아온다."""
    db.upsert_vehicle(STAREX_ROW())
    _stub_list(monkeypatch, [_list_row(STAREX_ROW(), "4")])
    _stub_daily_rest(monkeypatch)
    sent = _court(monkeypatch)
    service.daily_update(run_id=db.create_run(target=0))
    assert sent == [(SA, COURT, "4")]
    assert db.get_vehicle(STAREX)["status"] == "완료"


def test_복구_명령_인자_규칙(capsys):
    from web import maint
    db.upsert_vehicle(V())
    assert maint.main(["m", "redetail-key", "--apply"]) == 2, "--apply 는 --ids 와 함께만"
    assert maint.main(["m", "redetail-key", "--ids"]) == 2
    assert maint.main(["m", "redetail-key", "--apply", "--dry-run", "--ids", BENZ]) == 2
    assert db.get_vehicle(BENZ)["status"] == "완료", "거부된 명령은 아무것도 쓰지 않는다"
    capsys.readouterr()
    assert maint.main(["m", "redetail-key"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["targets"] == 1 and printed["apply"] is False
    assert maint.main(["m", "redetail-key", "--ids", BENZ, "--apply"]) == 0
    assert db.get_vehicle(BENZ)["status"] == "미분석"
