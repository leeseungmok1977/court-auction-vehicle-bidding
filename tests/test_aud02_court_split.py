"""AUD-02 · AUD-04 — 다른 법원의 같은 사건번호를 버리지 않고 법원 구분 id 로 저장한다.

배경(운영 DB 백업 2026-10-01 · anomaly_log): 물건 id 가 `사건번호_물건번호` 뿐이라 법원 코드가 없다.
다른 법원이 같은 사건번호 id 를 먼저 쓰고 있으면 `collect_upcoming` 이 새 물건을 '기존 유지 · 신규 반영 안 함'
으로 **버렸다** — 09-30 하루 41건(실사건번호 27쌍 + '(중복)' 14건), 14일 누적 505건. 사용자는 법원 사이트에
있는 차를 앱에서 볼 수 없었고, 같은 사건번호로 검색하면 다른 법원의 끝난 차가 대신 나왔다.

고정하는 것:
  ① 기존 행은 바이트 하나 바뀌지 않는다(id·즐겨찾기 키·사진 폴더·낙찰 이력이 그 id 에 묶여 있다).
  ② 충돌한 새 물건만 `사건번호_물건번호@법원코드` 로 저장 — URL·파일 이름에 안전, 예전 id 와 겹치지 않음.
  ③ 같은 물건을 다시 수집하면 같은 id(멱등) — 감사기록은 처음 한 번만.
  ④ 재분석 경로(_rebuild_item → _analyze_item)가 **그 행의 id·폴더**에 쓴다(다른 법원 행을 덮지 않는다).
  ⑤ '(중복)'·'(병합)' 은 saNo 로 진짜 사건번호를 복원한다(AUD-04) — 예전 행은 doc_id 로 제자리를 찾는다.
  ⑥ 화면은 id 가 아니라 행의 사건번호·법원을 보여 준다. 새 id 의 상세·리포트·관심 목록이 200.
외부 요청 0 — 법원 목록은 합성 응답(파서 픽스처 모양)으로 대역한다.
"""
from datetime import date, timedelta

import pytest

from src.parse.detail_parser import DetailInfo
from src.parse.list_parser import (COURT_SEP, VehicleItem, case_no_from_sano, court_qualified_key,
                                   is_court_qualified, parse_row)
from web import db, service

A_COURT, A_NAME = "B000250", "수원지방법원"
B_COURT, B_NAME = "B250826", "수원지방법원 안산지원"


def _sale(days=5) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _row(serial: int, court: str, court_name: str, model: str, *, year: int = 2026, mok: str = "1",
         sale: str = None, price: int = 10_000_000, printed: str = None, sano: str = None,
         maker: str = "현대") -> dict:
    """법원 목록 행(tests/fixtures/list_sample.json 과 같은 키) — 합성."""
    sa = sano or f"{year}0130{serial:06d}"
    return {"printCsNo": printed if printed is not None else f"{court_name}<br/>{year}타경{serial}",
            "saNo": sa, "boCd": court, "jiwonNm": court_name, "mokmulSer": mok, "maemulSer": "1",
            "docid": f"{court}{sa}1{mok}", "carNm": model, "jejosaNm": maker,
            "maeGiil": (sale or _sale()).replace("-", ""), "minmaePrice": str(price),
            "gamevalAmt": str(price * 2), "yuchalCnt": "1", "carYrtype": "2020", "mulStatcd": "01",
            "printSt": "사용본거지 : 서울 중구"}


class _Resp:
    def __init__(self, data):
        self._d = data

    def json(self):
        return self._d


def _stub_list(monkeypatch, rows, page_size=40):
    """collect_upcoming 의 법원 요청을 합성 응답으로 바꾼다. 요청 수를 센다(외부 요청 0)."""
    calls = {"list": 0}

    def fake_fetch(cs, page_no=1, page_size=page_size, **kw):
        calls["list"] += 1
        chunk = rows[(page_no - 1) * page_size: page_no * page_size]
        return _Resp({"data": {"dlt_srchResult": chunk,
                               "dma_pageInfo": {"groupTotalCount": len(rows)}}})

    monkeypatch.setattr(service, "new_session", lambda: object())
    monkeypatch.setattr(service, "warmup", lambda *a, **k: None)
    monkeypatch.setattr(service, "fetch_list_page", fake_fetch)

    def no_detail(*a, **k):
        raise AssertionError("목록 수집은 상세를 부르지 않는다")
    monkeypatch.setattr(service, "fetch_detail", no_detail)
    return calls


def _snapshot(vid):
    conn = db.connect()
    r = conn.execute("SELECT * FROM vehicles WHERE id=?", (vid,)).fetchone()
    conn.close()
    return tuple(r) if r else None


def _anoms(action=None):
    conn = db.connect()
    q = "SELECT * FROM anomaly_log" + (" WHERE action=?" if action else "") + " ORDER BY id"
    rows = [dict(r) for r in conn.execute(q, (action,) if action else ()).fetchall()]
    conn.close()
    return rows


def _seed_blocker(vid="2026타경50279_1", court=B_COURT, court_name=B_NAME, **kw):
    """다른 법원이 먼저 쓰고 있는 행(분석·사용자 값까지 있는 '끝난 경매')."""
    rec = {"id": vid, "folder_key": vid, "case_no": vid.rsplit("_", 1)[0], "item_no": "1",
           "court": court_name, "court_code": court, "maker": "현대", "model": "그랜저",
           "year": 2019, "min_sale_price": 9_000_000, "sale_date": "2026-09-21", "status": "종결",
           "median_price": 15_000_000, "judgment": "종결", "auction_result": "낙찰",
           "winning_price": 11_000_000, "doc_id": f"{court}2026013005027911",
           "photo_count": 4, "photo_order": ["a.jpg"], "starred": 1, "memo": "현장 확인",
           "collected_at": "2026-09-01 06:30:00", "analyzed_at": "2026-09-01 06:40:00"}
    rec.update(kw)
    db.upsert_vehicle(rec)
    return rec


# ═════════════════════════════════════════════════════════════════════
# ② id 형식 — URL·파일 이름에 안전, 예전 id 와 겹치지 않음
# ═════════════════════════════════════════════════════════════════════
def test_법원_구분_id_형식():
    q = court_qualified_key("2026타경50279_1", A_COURT)
    assert q == "2026타경50279_1@B000250"
    assert is_court_qualified(q) and not is_court_qualified("2026타경50279_1")
    for ch in '/?#%\\:*"<>| ':
        assert ch not in q, f"URL·파일 이름에 위험한 문자 {ch!r}"
    assert court_qualified_key("2026타경1_1", "") is None, "법원코드가 없으면 구분할 수 없다"
    assert court_qualified_key("2026타경1_1", " B0/00:250 ") == "2026타경1_1@B000250"


def test_예전_규칙_id_는_골뱅이를_만들지_못한다_두_형식은_겹치지_않는다():
    it = VehicleItem(case_no="2026타경@1/ 2", item_no="1", court="", court_code="", maker="", model="",
                     year=None, fuel_code="", fuel_name=None, transmission_code="", appraisal_value=None,
                     min_sale_price=None, fail_count=None, sale_date=None, sale_time=None, sale_place="",
                     usage_name="", location="", status_code="", doc_id="")
    assert COURT_SEP not in it.base_key and "/" not in it.base_key and " " not in it.base_key
    assert it.folder_key == it.base_key == "2026타경12_1"


def test_정상_목록_행의_id_는_예전과_같다():
    it = parse_row(_row(103470, "B000210", "서울중앙지방법원", "제네시스", year=2025, mok="2"))
    assert it.case_no == "2025타경103470" and it.folder_key == "2025타경103470_2"
    assert it.key is None


# ═════════════════════════════════════════════════════════════════════
# ⑤ '(중복)'·'(병합)' — saNo 로 진짜 사건번호(AUD-04)
# ═════════════════════════════════════════════════════════════════════
def test_saNo_규칙():
    assert case_no_from_sano("20260130030526") == "2026타경30526"
    assert case_no_from_sano("20230130552581") == "2023타경552581"
    assert case_no_from_sano("20260199000001") is None, "타경(0130) 밖은 지어내지 않는다"
    assert case_no_from_sano("") is None and case_no_from_sano(None) is None


@pytest.mark.parametrize("tail", ["(중복)", "(병합)"])
def test_중복_병합은_saNo_로_사건번호를_복원한다(tail):
    r = _row(30526, "B000520", "전주지방법원", "BMW X3",
             printed=f"전주지방법원<br/>2026타경30526<br/>{tail}")
    it = parse_row(r)
    assert it.case_no == "2026타경30526" and it.folder_key == "2026타경30526_1"


def test_saNo_도_규칙_밖이면_예전_그대로다():
    r = _row(1, "B000520", "전주지방법원", "X", printed="전주지방법원<br/>(중복)", sano="XYZ")
    assert parse_row(r).case_no == "(중복)"


def test_픽스처의_정상_행은_끝_조각과_saNo_규칙이_같다():
    import json
    from pathlib import Path
    d = json.loads((Path(__file__).parent / "fixtures" / "list_sample.json").read_text(encoding="utf-8"))
    for r in d["data"]["dlt_srchResult"]:
        assert parse_row(r).case_no == case_no_from_sano(r["saNo"])


# ═════════════════════════════════════════════════════════════════════
# 해석 규칙(db.resolve_listing_id) — 순서 ①~④
# ═════════════════════════════════════════════════════════════════════
def test_해석_빈_DB_면_예전_규칙_id():
    assert db.resolve_listing_id("2026타경1_1", A_COURT, "D1") == ("2026타경1_1", None)


def test_해석_같은_법원이면_예전처럼_같은_행():
    _seed_blocker("2026타경1_1", court=A_COURT, court_name=A_NAME, doc_id="OLD")
    assert db.resolve_listing_id("2026타경1_1", A_COURT, "NEW") == ("2026타경1_1", None)


def test_해석_다른_법원이면_법원_구분_id_와_막은_법원():
    _seed_blocker("2026타경1_1")
    assert db.resolve_listing_id("2026타경1_1", A_COURT, "DA") == ("2026타경1_1@B000250", B_COURT)


def test_해석_법원_구분_행이_있으면_그_id_감사기록_없음():
    _seed_blocker("2026타경1_1")
    db.upsert_vehicle({"id": "2026타경1_1@B000250", "court_code": A_COURT, "doc_id": "DA"})
    assert db.resolve_listing_id("2026타경1_1", A_COURT, "DX") == ("2026타경1_1@B000250", None)


def test_해석_doc_id_가_같으면_예전_행_제자리():
    db.upsert_vehicle({"id": "(중복)_1", "case_no": "(중복)", "court_code": "B000520",
                       "doc_id": "B0005202026013003052611"})
    assert db.resolve_listing_id("2026타경30526_1", "B000520",
                                 "B0005202026013003052611") == ("(중복)_1", None)


def test_해석_doc_id_가_같아도_법원이_다르면_쓰지_않는다():
    db.upsert_vehicle({"id": "X_1", "court_code": B_COURT, "doc_id": "SAME"})
    rid, blocked = db.resolve_listing_id("2026타경7_1", A_COURT, "SAME")
    assert rid == "2026타경7_1" and blocked is None


@pytest.mark.parametrize("old, new", [("", A_COURT), (B_COURT, "")])
def test_해석_한쪽_법원_미상이면_예전처럼_같은_행(old, new):
    db.upsert_vehicle({"id": "2026타경9_1", "court_code": old or None})
    assert db.resolve_listing_id("2026타경9_1", new, "") == ("2026타경9_1", None)


# ═════════════════════════════════════════════════════════════════════
# ①②③ collect_upcoming — 버리지 않는다 · 기존 행 불변 · 멱등
# ═════════════════════════════════════════════════════════════════════
def test_충돌한_새_물건을_법원_구분_id_로_저장하고_기존_행은_그대로(monkeypatch):
    _seed_blocker()
    before = _snapshot("2026타경50279_1")
    calls = _stub_list(monkeypatch, [_row(50279, A_COURT, A_NAME, "K7", maker="기아")])
    stored = service.collect_upcoming(within_days=30)
    assert stored == 1
    assert _snapshot("2026타경50279_1") == before, "기존 행이 바뀌었다(바이트 비교)"
    v = db.get_vehicle("2026타경50279_1@B000250")
    assert v and v["court_code"] == A_COURT and v["court"] == A_NAME and v["model"] == "K7"
    assert v["case_no"] == "2026타경50279" and v["item_no"] == "1"
    assert v["folder_key"] == v["id"], "사진 폴더는 새 id 이름으로 따로 — 기존 행 폴더를 덮지 않는다"
    assert v["status"] == "미분석", "새 행은 다음 분석 단계의 대상"
    assert calls["list"] == 1
    got = _anoms()
    assert [a["action"] for a in got] == ["stored-as"], got
    assert got[0]["vehicle_id"] == "2026타경50279_1@B000250" and got[0]["case_no"] == "2026타경50279"
    assert "기존 2026타경50279_1(B250826) 유지" in got[0]["note"] and "B000250" in got[0]["note"]
    assert "법원구분 신규 1건" in db.get_setting("last_case_collisions")


def test_다시_수집해도_같은_id_감사기록은_한_번(monkeypatch):
    _seed_blocker()
    row = _row(50279, A_COURT, A_NAME, "K7", maker="기아", price=10_000_000)
    _stub_list(monkeypatch, [row])
    service.collect_upcoming(within_days=30)
    first = {r["id"] for r in db.list_vehicles()}
    row2 = dict(row, minmaePrice="8000000")         # 다음 날 — 최저가만 바뀜
    _stub_list(monkeypatch, [row2])
    service.collect_upcoming(within_days=30)
    assert {r["id"] for r in db.list_vehicles()} == first == {"2026타경50279_1", "2026타경50279_1@B000250"}
    assert db.get_vehicle("2026타경50279_1@B000250")["min_sale_price"] == 8_000_000, "같은 행이 갱신돼야 한다"
    assert len(_anoms("stored-as")) == 1 and not _anoms("skipped")
    assert service._LAST_COLLECT == {"court_split_new": 0, "court_split_seen": 1, "collided": 0}


def test_법원_구분_행의_분석값은_목록_갱신이_보존한다(monkeypatch):
    _seed_blocker()
    row = _row(50279, A_COURT, A_NAME, "K7", maker="기아")
    _stub_list(monkeypatch, [row])
    service.collect_upcoming(within_days=30)
    db.update_fields("2026타경50279_1@B000250", status="완료", median_price=12_000_000,
                     judgment="입찰 검토 가능", photo_count=5)
    service.collect_upcoming(within_days=30)
    v = db.get_vehicle("2026타경50279_1@B000250")
    assert (v["status"], v["median_price"], v["judgment"], v["photo_count"]) == \
        ("완료", 12_000_000, "입찰 검토 가능", 5), "_LISTING_KEEP 규칙이 새 id 에도 같아야 한다"


def test_같은_법원_같은_사건은_예전처럼_갱신(monkeypatch):
    _seed_blocker("2026타경50279_1", court=A_COURT, court_name=A_NAME, status="미분석",
                  auction_result=None, judgment=None, sale_date=_sale(), doc_id="OLD")
    _stub_list(monkeypatch, [_row(50279, A_COURT, A_NAME, "K7", price=7_000_000)])
    service.collect_upcoming(within_days=30)
    assert [r["id"] for r in db.list_vehicles()] == ["2026타경50279_1"]
    v = db.get_vehicle("2026타경50279_1")
    assert v["min_sale_price"] == 7_000_000 and v["memo"] == "현장 확인" and v["starred"] == 1
    assert not _anoms()


def test_같은_런에_새로_들어온_두_법원도_갈린다(monkeypatch):
    _stub_list(monkeypatch, [_row(77, A_COURT, A_NAME, "아반떼"), _row(77, B_COURT, B_NAME, "쏘렌토")])
    assert service.collect_upcoming(within_days=30) == 2
    a, b = db.get_vehicle("2026타경77_1"), db.get_vehicle("2026타경77_1@B250826")
    assert a["court_code"] == A_COURT and a["model"] == "아반떼"
    assert b["court_code"] == B_COURT and b["model"] == "쏘렌토"
    # 순서가 바뀐 다음 날에도 각자 제 id(doc_id 로 찾는다)
    _stub_list(monkeypatch, [_row(77, B_COURT, B_NAME, "쏘렌토"), _row(77, A_COURT, A_NAME, "아반떼")])
    service.collect_upcoming(within_days=30)
    assert {r["id"]: r["court_code"] for r in db.list_vehicles()} == {
        "2026타경77_1": A_COURT, "2026타경77_1@B250826": B_COURT}


def test_목록이탈_판정은_그_물건이_저장된_id_로_센다(monkeypatch):
    """예전엔 예전 규칙 id 를 '봤다'로 넣어서, B법원 물건이 목록에 있으면 A법원 행도 본 것으로 셌다."""
    _seed_blocker("2026타경50279_1", court=B_COURT, court_name=B_NAME, sale_date=_sale(3),
                  status="완료", judgment="입찰 검토 가능", auction_result=None, winning_price=None)
    _stub_list(monkeypatch, [_row(50279, A_COURT, A_NAME, "K7")])       # B법원 물건은 목록에서 빠졌다
    service.collect_upcoming(within_days=30)
    assert db.get_vehicle("2026타경50279_1")["status"] == "상세없음", "B법원 행이 빠진 걸 못 봤다"
    assert db.get_vehicle("2026타경50279_1@B000250")["status"] == "미분석"


def test_예전_중복_행은_doc_id_로_제자리를_찾고_사건번호가_고쳐진다(monkeypatch):
    db.upsert_vehicle({"id": "(중복)_6", "folder_key": "(중복)_6", "case_no": "(중복)", "item_no": "6",
                       "court": "창원지방법원", "court_code": "B000420", "status": "상세없음",
                       "doc_id": "B0004202026013001048416", "model": "G80", "starred": 1})
    # 같은 사건번호를 다른 법원도 쓰고 있다(실측: 2026타경10484 는 B000521 에도 있다)
    db.upsert_vehicle({"id": "2026타경10484_6", "folder_key": "2026타경10484_6", "case_no": "2026타경10484",
                       "item_no": "6", "court_code": "B000521", "doc_id": "B0005212026013001048416"})
    r = _row(10484, "B000420", "창원지방법원", "G80", mok="6",
             printed="창원지방법원<br/>2026타경10484<br/>(중복)")
    r["docid"] = "B0004202026013001048416"
    _stub_list(monkeypatch, [r])
    service.collect_upcoming(within_days=30)
    v = db.get_vehicle("(중복)_6")
    assert v["case_no"] == "2026타경10484", "진짜 사건번호로 고쳐져야 목록 GLOB 가드를 통과한다"
    assert v["folder_key"] == "(중복)_6" and v["starred"] == 1, "id·폴더·사용자 값은 그대로"
    assert db.get_vehicle("2026타경10484_6@B000420") is None, "같은 물건을 두 번 저장하면 안 된다"
    assert len(db.list_vehicles()) == 2 and not _anoms()


def test_여러_법원의_중복_물건이_한_자리를_두고_다투지_않는다(monkeypatch):
    db.upsert_vehicle({"id": "(중복)_1", "case_no": "(중복)", "item_no": "1", "court_code": "B000520",
                       "doc_id": "B0005202026013003052611", "sale_date": "2026-09-21", "status": "종결"})
    rows = [_row(s, c, n, m, printed=f"{n}<br/>(중복)") for s, c, n, m in (
        (101, "B000281", "강릉지원", "렉스턴스포츠"), (102, "B000283", "원주지원", "BMW M2"),
        (103, "B000320", "대구지방법원", "ARKANA"))]
    _stub_list(monkeypatch, rows)
    assert service.collect_upcoming(within_days=30) == 3
    got = {r["id"]: (r["court_code"], r["case_no"]) for r in db.list_vehicles() if r["id"] != "(중복)_1"}
    assert got == {"2026타경101_1": ("B000281", "2026타경101"), "2026타경102_1": ("B000283", "2026타경102"),
                   "2026타경103_1": ("B000320", "2026타경103")}
    assert not _anoms("skipped")


def test_마지막_방어선은_그대로_남는다():
    """조회표가 낡아 법원 구분 id 자리를 다른 법원이 먼저 차지했다면 병합하지 않고 예외."""
    db.upsert_vehicle({"id": "2026타경5_1@B000250", "court_code": B_COURT})
    with pytest.raises(db.CaseCollision):
        db.upsert_listing({"id": "2026타경5_1@B000250", "court_code": A_COURT, "case_no": "2026타경5"})


def test_완료_실행_기록에_법원구분_신규_수(monkeypatch):
    _seed_blocker()
    _stub_list(monkeypatch, [_row(50279, A_COURT, A_NAME, "K7")])
    rid = db.create_run(target=0)
    service.collect_upcoming(within_days=30, run_id=rid, finalize=True)
    assert db.latest_run()["message"].endswith("· 법원구분 신규 1건")


# ═════════════════════════════════════════════════════════════════════
# ④ 재분석 경로 — 그 행의 id·폴더에 쓴다
# ═════════════════════════════════════════════════════════════════════
def test_rebuild_item_은_행_id_를_싣는다():
    q = service._rebuild_item({"id": "2026타경1_1@B000250", "case_no": "2026타경1", "item_no": "1",
                               "court_code": A_COURT})
    assert q.folder_key == "2026타경1_1@B000250"
    legacy = service._rebuild_item({"id": "2026타경1_1", "case_no": "2026타경1", "item_no": "1"})
    assert legacy.folder_key == "2026타경1_1" == legacy.base_key


def _detail(**kw):
    d = dict(case_no="20260130050279", court_code=A_COURT, item_seq="1", maker="기아", model="K7",
             year=2018, displacement_cc=2400, mileage_km=88_000, fuel_code="", fuel_name=None,
             transmission_code="", reg_no="", vin="", storage_addr="", appraisal_value=20_000_000,
             fail_count=1, sale_date=_sale(), appraisal_text="주행거리 88,000km", photo_count=3)
    d.update(kw)
    return DetailInfo(**d)


def test_단건_분석은_법원_구분_행에_쓰고_다른_법원_행과_폴더를_건드리지_않는다(monkeypatch):
    _seed_blocker()
    before = _snapshot("2026타경50279_1")
    qid = "2026타경50279_1@B000250"
    db.upsert_vehicle({"id": qid, "folder_key": qid, "case_no": "2026타경50279", "item_no": "1",
                       "court": A_NAME, "court_code": A_COURT, "maker": "기아", "model": "K7", "year": 2018,
                       "min_sale_price": 10_000_000, "sale_date": _sale(), "status": "미분석",
                       "doc_id": f"{A_COURT}2026013005027911"})
    sent, saved = [], []
    monkeypatch.setattr(service, "new_session", lambda: object())
    monkeypatch.setattr(service, "warmup", lambda *a, **k: None)
    monkeypatch.setattr(service.encar, "new_session", lambda: object())
    monkeypatch.setattr(service, "fetch_detail",
                        lambda cs, sa, bo, seq: sent.append((sa, bo, seq)) or _Resp({}))
    monkeypatch.setattr(service, "parse_detail", lambda resp, cfg=None: _detail())
    monkeypatch.setattr(service, "save_item_folder", lambda resp, fk, cfg=None: saved.append(fk))
    monkeypatch.setattr(service, "_resolve_encar", lambda *a, **k: None)     # 시세 없음 경로(엔카 0)
    out = service.analyze_single(qid)
    assert sent == [("20260130050279", A_COURT, "1")], "법원 요청은 행의 법원코드·doc_id 로"
    assert saved == [qid], "사진·감정서는 새 id 폴더에"
    assert out["id"] == qid and out["mileage_km"] == 88_000
    assert _snapshot("2026타경50279_1") == before, "다른 법원 행이 바뀌었다"


def _stub_manual(monkeypatch, rows, fail=False):
    """수동 검색 수집(/run → _run_collection) 대역 — 목록·상세·저장 모두 가짜(외부 요청 0)."""
    saved, sent = [], []
    _stub_list(monkeypatch, rows)
    monkeypatch.setattr(service.encar, "new_session", lambda: object())

    def fake_detail(cs, sa, bo, seq):
        sent.append((sa, bo, seq))
        if fail:
            raise ValueError("응답 형식 이상")
        return _Resp({})
    monkeypatch.setattr(service, "fetch_detail", fake_detail)
    monkeypatch.setattr(service, "parse_detail", lambda resp, cfg=None: _detail())
    monkeypatch.setattr(service, "save_item_folder", lambda resp, fk, cfg=None: saved.append(fk))
    monkeypatch.setattr(service, "_resolve_encar", lambda *a, **k: None)
    return saved, sent


@pytest.mark.parametrize("fail", [False, True])
def test_수동_수집도_다른_법원_행을_덮지_않는다(monkeypatch, fail):
    """예전 `_run_collection` 은 upsert_vehicle 로 예전 규칙 id 에 바로 썼다 — 가드가 없어 다른 법원 행을 덮었다."""
    _seed_blocker()
    before = _snapshot("2026타경50279_1")
    saved, sent = _stub_manual(monkeypatch, [_row(50279, A_COURT, A_NAME, "K7")], fail=fail)
    rid = db.create_run(target=1)
    service._active["running"] = True
    try:
        service._run_collection(max_items=1, scan_limit=1, repair_cost=500_000, run_id=rid)
    finally:
        service._active["running"] = False
    assert _snapshot("2026타경50279_1") == before, "다른 법원 행이 바뀌었다"
    v = db.get_vehicle("2026타경50279_1@B000250")
    assert v and v["court_code"] == A_COURT and v["court"] == A_NAME
    assert sent == [("20260130050279", A_COURT, "1")]
    assert saved == ([] if fail else ["2026타경50279_1@B000250"])
    assert [a["action"] for a in _anoms()] == ["stored-as"]


def test_낙찰결과는_각_행의_법원_결과에서만_찾는다(monkeypatch):
    """AUD-07 'ⓒ 충돌 id' 가설과 같은 뿌리 — 사건번호만으로 찾으면 두 법원 결과가 섞인다.
    update_results 는 행의 court_code 로 법원별 결과를 받아 (saNo, 물건번호)로 맞춘다 — 새 id 행도 같다."""
    from src.collect import courtauction_result as cr
    past = (date.today() - timedelta(days=3)).isoformat()
    _seed_blocker(sale_date=past, auction_result=None, winning_price=None, status="완료",
                  judgment="입찰 검토 가능")
    qid = "2026타경50279_1@B000250"
    db.upsert_vehicle({"id": qid, "folder_key": qid, "case_no": "2026타경50279", "item_no": "1",
                       "court_code": A_COURT, "sale_date": past, "status": "완료", "min_sale_price": 9_000_000,
                       "doc_id": f"{A_COURT}2026013005027911"})
    asked = []

    def fake_results(s, bo, max_pages=15):
        asked.append(bo)
        base = {"saNo": "20260130050279", "mokmulSer": "1", "minmaePrice": "9000000", "yuchalCnt": "1",
                "maeGiil": past.replace("-", "")}
        return [dict(base, mulStatcd="04", maeAmt="11000000")] if bo == B_COURT \
            else [dict(base, mulStatcd="03", maeAmt="0")]
    monkeypatch.setattr(cr, "fetch_all_results", fake_results)
    monkeypatch.setattr(service, "new_session", lambda: object())
    monkeypatch.setattr(service, "warmup", lambda *a, **k: None)
    assert service.update_results(finalize=False) == 2
    assert sorted(asked) == sorted([A_COURT, B_COURT]), "법원마다 한 번씩"
    b, a = db.get_vehicle("2026타경50279_1"), db.get_vehicle(qid)
    assert (b["auction_result"], b["winning_price"]) == ("낙찰", 11_000_000)
    assert (a["auction_result"], a["winning_price"]) == ("유찰", None), "다른 법원 낙찰가가 새 id 행에 붙었다"


# ═════════════════════════════════════════════════════════════════════
# 같은 사건 = 같은 법원 + 같은 사건번호 — '사진 혼재?' 칩
# ═════════════════════════════════════════════════════════════════════
def test_다물건_판정은_법원까지_같아야_한다():
    for vid, cc, case in (("2026타경1_1", B_COURT, "2026타경1"), ("2026타경1_1@B000250", A_COURT, "2026타경1"),
                          ("2026타경2_1", A_COURT, "2026타경2"), ("2026타경2_2", A_COURT, "2026타경2")):
        db.upsert_vehicle({"id": vid, "court_code": cc, "case_no": case, "photo_count": 2})
    assert service.multi_lot_ids(refresh=True) == {"2026타경2_1", "2026타경2_2"}


# ═════════════════════════════════════════════════════════════════════
# 매일 갱신 실행 기록 — 요약 머리('입찰예정 N · 분석 N')를 깨지 않는다
# ═════════════════════════════════════════════════════════════════════
def _stub_daily_rest(monkeypatch):
    monkeypatch.setattr(service, "refresh_lagged_floors", lambda **k: {})
    monkeypatch.setattr(service, "encar_health", lambda *a, **k: {"state": "blocked", "code": 407})
    monkeypatch.setattr(service, "reuse_market_prices", lambda **k: {})
    monkeypatch.setattr(service, "photo_autosort_run", lambda **k: {"sorted": 0})
    monkeypatch.setattr(service, "update_results", lambda **k: 0)
    monkeypatch.setattr(service, "review_daily_anomalies",
                        lambda *a, **k: {"found": 0, "reviewed": 0, "resolved": 0, "quarantined": 0})
    monkeypatch.setattr(service, "newcar_collect", lambda **k: {"matched": 0, "remaining": 0})
    monkeypatch.setattr(service, "new_session", lambda: object())
    monkeypatch.setattr(service, "warmup", lambda *_a, **_k: None)
    monkeypatch.setattr(service.encar, "new_session", lambda: object())


def test_배포_뒤_첫_매일_갱신_목록에서_분석까지_새_id_행에서만(monkeypatch):
    """배포 뒤 첫 06:30 런의 실제 경로: 목록이 새 id 로 넣고 → 같은 런의 분석 단계가 그 행을 분석한다.
    법원 요청은 행의 법원코드로, 사진은 새 id 폴더로, 다른 법원 행은 바이트 그대로."""
    _seed_blocker()
    before = _snapshot("2026타경50279_1")
    qid = "2026타경50279_1@B000250"
    _stub_list(monkeypatch, [_row(50279, A_COURT, A_NAME, "K7", maker="기아")])
    _stub_daily_rest(monkeypatch)
    monkeypatch.setattr(service, "encar_health", lambda *a, **k: {"state": "ok", "code": 200})
    monkeypatch.setattr(service, "requery_missing_market", lambda **k: {"targets": 0, "updated": 0})
    sent, saved = [], []
    monkeypatch.setattr(service, "fetch_detail",
                        lambda cs, sa, bo, seq: sent.append((sa, bo, seq)) or _Resp({}))
    monkeypatch.setattr(service, "parse_detail", lambda resp, cfg=None: _detail())
    monkeypatch.setattr(service, "save_item_folder", lambda resp, fk, cfg=None: saved.append(fk))
    monkeypatch.setattr(service, "_resolve_encar", lambda *a, **k: None)
    rid = db.create_run(target=0)
    out = service.daily_update(run_id=rid)
    assert out["stored"] == 1 and out["analyzed"] == 1
    assert sent == [("20260130050279", A_COURT, "1")] and saved == [qid]
    v = db.get_vehicle(qid)
    assert v["status"] == "완료" and v["mileage_km"] == 88_000 and v["court_code"] == A_COURT
    assert _snapshot("2026타경50279_1") == before, "다른 법원 행이 바뀌었다"
    assert " · 법원구분 신규 1 · " in db.latest_run()["message"]


def test_버린_물건이_있으면_매일_갱신_기록에_경고(monkeypatch):
    """마지막 방어선에 걸려 버린 물건은 0 이어야 한다. 0 이 아니면 ⚠ — 실행 기록 신호가 경고로 읽는다."""
    from web import ops_health
    monkeypatch.setattr(service, "collect_upcoming", lambda **k: (
        service._LAST_COLLECT.update({"court_split_new": 0, "court_split_seen": 4, "collided": 2}) or 7))
    _stub_daily_rest(monkeypatch)
    rid = db.create_run(target=0)
    service.daily_update(run_id=rid)
    msg = db.latest_run()["message"]
    assert msg.startswith("입찰예정 7 · 분석 0 · ⚠사건번호 충돌 2 보류 · "), msg
    assert "⚠사건번호 충돌 2 보류" in ops_health.warn_parts(msg)


def test_매일_갱신_기록에_법원구분_신규_조각(monkeypatch):
    def fake_collect(**k):
        service._LAST_COLLECT.update({"court_split_new": 3, "court_split_seen": 3, "collided": 0})
        return 5
    monkeypatch.setattr(service, "collect_upcoming", fake_collect)
    _stub_daily_rest(monkeypatch)
    rid = db.create_run(target=0)
    service.daily_update(run_id=rid)
    msg = db.latest_run()["message"]
    assert msg.startswith("입찰예정 5 · 분석 0 · 법원구분 신규 3 · "), msg
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "daily_ops_report", Path(__file__).resolve().parents[1] / "tools" / "daily_ops_report.py")
    R = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(R)
    assert R.is_daily_summary(msg), "일일 리포트가 요약 문장으로 알아보지 못한다"
    p = R.parse_daily_message(msg)
    assert p["stored"] == 5 and p["analyzed"] == 0 and "법원구분 신규 3" in p["unknown"]


# ═════════════════════════════════════════════════════════════════════
# ⑥ 화면 — 새 id 라우트 200, 화면에는 사건번호·법원
# ═════════════════════════════════════════════════════════════════════
_PUB = {"x-forwarded-for": "203.0.113.7"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    import web.app as A
    from starlette.testclient import TestClient
    data = tmp_path / "data"
    monkeypatch.setattr(A, "DATA_DIR", data)
    _seed_blocker()
    qid = "2026타경50279_1@B000250"
    db.upsert_vehicle({"id": qid, "folder_key": qid, "case_no": "2026타경50279", "item_no": "1",
                       "court": A_NAME, "court_code": A_COURT, "maker": "기아", "model": "K7", "year": 2018,
                       "min_sale_price": 10_000_000, "appraisal_value": 20_000_000, "sale_date": _sale(),
                       "status": "완료", "median_price": 14_000_000, "market_confidence": 78,
                       "market_confidence_label": "높음", "sample_count": 12, "photo_count": 1,
                       "mileage_km": 88_000, "judgment": "입찰 검토 가능", "upper_bid": 12_000_000,
                       "doc_id": f"{A_COURT}2026013005027911"})
    (data / qid / "photos").mkdir(parents=True)
    (data / qid / "photos" / "a.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 64)
    return TestClient(A.app), qid


@pytest.mark.parametrize("suffix", ["", "/report", "/appraisal"])
def test_새_id_상세_리포트_감정서안내_200(client, suffix):
    c, qid = client
    r = c.get(f"/vehicle/{qid}{suffix}", headers=_PUB)
    assert r.status_code == 200 and "Traceback" not in r.text
    assert "2026타경50279" in r.text and A_NAME in r.text, "화면은 행의 사건번호·법원을 보여 준다"
    assert f">{qid}<" not in r.text, "새 id 가 글자로 노출됐다"


def test_새_id_사진_서빙(client):
    c, qid = client
    assert c.get(f"/photo/{qid}/a.jpg", headers=_PUB).status_code == 200
    assert c.get(f"/photo/2026타경50279_1/a.jpg", headers=_PUB).status_code == 404, "다른 법원 폴더와 섞이면 안 된다"


def test_관심_목록은_두_법원_물건을_각자_찾는다(client):
    c, qid = client
    from urllib.parse import quote
    r = c.get("/watchlist?ids=" + quote(f"{qid},2026타경50279_1"), headers=_PUB)
    assert r.status_code == 200
    assert r.text.count('data-vid="2026타경50279_1@B000250"') >= 1
    assert r.text.count('data-vid="2026타경50279_1"') >= 1


def test_사건번호로_검색하면_두_법원_물건이_법원명과_함께_나온다(client):
    """감사 검증 A: 법원 사이트에서 본 사건번호로 검색하면 찾는 차 대신 **다른 법원의 끝난 차**가 나왔다."""
    c, qid = client
    from urllib.parse import quote
    r = c.get("/vehicles?q=" + quote("2026타경50279"), headers=_PUB)
    assert r.status_code == 200
    assert f'data-vid="{qid}"' in r.text and 'data-vid="2026타경50279_1"' in r.text
    assert "2026타경50279 · 수원지법 · 2018" in r.text, "목록 줄은 '사건번호 · 법원' 을 보여 준다(새 행)"
    assert "2026타경50279 · 수원지법 안산지원 · 2019" in r.text, "기존 행도 제 법원으로"


def test_사이트맵은_새_id_를_인코딩한다(client):
    c, qid = client
    r = c.get("/sitemap.xml", headers=_PUB)
    assert r.status_code == 200 and "/vehicle/2026%ED%83%80%EA%B2%BD50279_1%40B000250" in r.text
