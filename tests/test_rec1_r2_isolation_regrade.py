# -*- coding: utf-8 -*-
"""REC-1 2회차(지시서 2026-09-29-27) — qa 1회차 F3·F4 수정 · 가드 상태의 입찰 상한선 · judge 경계.

F3  매일 갱신에서 최저가 재조회의 **비차단 오류**(연결 끊김 등)가 갱신 전체를 멈췄다. 0표본 재조회·⑤ 최종
    검토처럼 격리한다 — 차단(RuntimeError·403/429)·비정상 3연속은 **그대로 전파**한다(C.4-5, 완화 금지).
F4  `python -m web.maint regrade-accidents` 가 범위 없이 돌아, 요항 파일이 없는 행을 매각물건명세만으로 다시
    매겨 무사고로 내렸다(로컬 사본: 직전 파서로도 23행, 그중 20행이 요항 없음). 이제 ① 요항 파일이 있고
    ② 직전 파서와 지금 파서의 보험이력이 다른 행만 ③ 기본은 미리보기, --apply 일 때만 쓴다.

외부 요청 0 — 루프백 밖 connect·connect_ex·DNS 와 법원 요청 함수를 막고 **시도를 기록**한다(TEST-1).
기록은 테스트가 끝날 때 검사한다: 매일 갱신이 예외를 격리(except Exception)해도 시도 자체는 잡힌다.
"""
import json
import socket
from datetime import date, timedelta

import pytest
import requests

from src.bidcalc.calculator import Judgment, judge
from src.collect import courtauction_detail as cad, courtauction_list as cal
from src.parse import detail_parser
from src.parse.detail_parser import HIST_PATTERNS_BASELINE, parse_insurance_history
from web import db, service

TODAY = date.today()
SD = (TODAY + timedelta(days=10)).isoformat()


# ── 외부 요청 0(시도 기록) ─────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    attempts: list = []
    real, real_ex, real_gai = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo

    def _lo(h) -> bool:
        return h is None or str(h) in ("127.0.0.1", "::1", "localhost")

    def _host(addr):
        return addr[0] if isinstance(addr, tuple) and addr else addr

    def deny(self, addr, *a, **k):
        if _lo(_host(addr)):
            return real(self, addr, *a, **k)
        attempts.append(("connect", addr))
        raise AssertionError(f"외부 연결 시도 {addr!r}")

    def deny_ex(self, addr, *a, **k):
        if _lo(_host(addr)):
            return real_ex(self, addr, *a, **k)
        attempts.append(("connect_ex", addr))
        raise AssertionError(f"외부 연결 시도 {addr!r}")

    def deny_dns(host, *a, **k):
        if _lo(host):
            return real_gai(host, *a, **k)
        attempts.append(("dns", host))
        raise AssertionError(f"DNS 조회 시도 {host!r}")

    def no_court(*a, **k):
        attempts.append(("court", a[:1]))
        raise AssertionError("모킹 없이 법원 요청 함수를 불렀다")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_ex)
    monkeypatch.setattr(socket, "getaddrinfo", deny_dns)
    for name in ("new_session", "warmup", "fetch_detail"):
        monkeypatch.setattr(service, name, no_court)
    yield attempts
    assert not attempts, f"외부 요청 시도 {attempts} — 이 파일은 외부 요청 0 이어야 한다(C.4)"


def V(i=0, **kw) -> dict:
    """기일 남은 유찰 3회 물건 — 최저가 980만 = 감정가 2,000만 × 0.7²(한 회차 지연)."""
    base = {"id": f"L_{i}", "case_no": f"2026타경{30118 + i}", "item_no": "1", "court": "전주지방법원",
            "court_code": "B000520", "doc_id": "B000520" + f"{20260130030118 + i}" + "11",
            "appraisal_value": 20_000_000, "min_sale_price": 9_800_000, "fail_count": 3,
            "sale_date": (TODAY + timedelta(days=5 + i)).isoformat(), "status": "완료",
            "judgment": "유찰 대기", "median_price": 20_795_000, "sample_count": 14,
            "market_confidence_label": "높음", "accident_grade": "none", "upper_bid": 8_000_000,
            "lower_bound": 9_800_000, "breakdown": {"현재최저매각가": 9_800_000}}
    base.update(kw)
    return base


def _enable(monkeypatch):
    real = service.load_config
    monkeypatch.setattr(service, "load_config",
                        lambda *a, **k: {**real(*a, **k), "min_refresh_enabled": True})


def _stub_rest(monkeypatch, seen: list):
    """재조회 뒤 단계들을 가짜로 — 어디까지 도달했는지 seen 에 남긴다."""
    monkeypatch.setattr(service, "collect_upcoming", lambda **k: 0)
    monkeypatch.setattr(service, "encar_health", lambda *a, **k: {"state": "blocked", "code": 407})
    monkeypatch.setattr(service, "reuse_market_prices", lambda **k: {})
    monkeypatch.setattr(service, "photo_autosort_run", lambda **k: {"sorted": 0})
    monkeypatch.setattr(service, "update_results", lambda **k: seen.append("update_results") or 0)
    monkeypatch.setattr(service, "review_daily_anomalies",
                        lambda *a, **k: seen.append("review") or
                        {"found": 0, "reviewed": 0, "resolved": 0, "quarantined": 0})
    monkeypatch.setattr(service, "newcar_collect", lambda **k: seen.append("newcar") or
                        {"matched": 0, "remaining": 0})
    monkeypatch.setattr(service.encar, "new_session", lambda: object())
    # ⑤ 최종 검토 앞에서 법원 세션을 연다 — 기본은 가짜(요청 0). 재조회 경로를 보는 테스트가 덮어쓴다.
    monkeypatch.setattr(service, "new_session", lambda: object())
    monkeypatch.setattr(service, "warmup", lambda _s: None)


class _Resp:
    def __init__(self, status=200, text="{}", ctype="application/json;charset=UTF-8"):
        self.status_code, self.text = status, text
        self.headers = {"Content-Type": ctype}

    def json(self):
        return json.loads(self.text)


class _Sess:
    """requests.Session 대역 — 실제 warmup()·fetch_detail() 이 이 객체를 부른다(요청 0)."""
    def __init__(self, responder):
        self.gets, self.posts, self.responder, self.headers = [], [], responder, {}

    def get(self, url, **k):
        self.gets.append(url)
        return _Resp(200, "<html></html>", "text/html")

    def post(self, url, data=None, **k):
        self.posts.append(url)
        return self.responder(len(self.posts))


def _wire_real(monkeypatch, responder) -> _Sess:
    sess = _Sess(responder)
    monkeypatch.setattr(service, "new_session", lambda: sess)
    monkeypatch.setattr(service, "warmup", cal.warmup)
    monkeypatch.setattr(service, "fetch_detail", cad.fetch_detail)
    for mod in (cal.time, cad.time, service.time):
        monkeypatch.setattr(mod, "sleep", lambda s: None)
    return sess


# ═════════════════════════════════════════════════════════════════════
# F3 — 재조회 비차단 오류는 격리, 차단·비정상 3연속은 전파
# ═════════════════════════════════════════════════════════════════════
def test_재조회_세션_연결오류_하나가_매일_갱신_전체를_멈추는가(monkeypatch):
    """qa 재현 테스트(scratchpad/qa_rec1fix/tests_adv)를 옮긴 것 — 1회차엔 빨강(ConnectionError 로 끝남)."""
    for i in range(2):
        db.upsert_vehicle(V(i))
    seen: list = []
    _stub_rest(monkeypatch, seen)
    monkeypatch.setattr(service, "new_session", lambda: object())

    def wu(_s):
        raise requests.exceptions.ConnectionError("일시 연결 끊김")
    monkeypatch.setattr(service, "warmup", wu)
    _enable(monkeypatch)
    rid = db.create_run(target=0)
    try:
        out = service.daily_update(run_id=rid)
        outcome = "continued"
    except Exception as e:  # noqa: BLE001
        out, outcome = None, f"raised {type(e).__name__}: {e}"
    assert outcome == "continued" and "update_results" in seen, f"{outcome} — 낙찰결과 단계 도달 {seen}"
    # 뒤 단계 전부(낙찰결과 → ⑤ 최종 검토 → ⑥ 출시가)까지 갔고, 오류는 기록에 남았다
    assert seen == ["update_results", "newcar"], seen    # ⑤ 는 warmup 에서 같은 오류로 기존 격리(pass)
    assert out["floor"]["error_type"] == "ConnectionError"
    run = db.latest_run()
    assert run["status"] == "done"
    assert run["message"].startswith("입찰예정 0 · 분석 0"), "일일 리포트 파서가 읽는 머리가 깨졌다"
    assert " · ⚠최저가 재조회 오류 ConnectionError" in run["message"]
    last = json.loads(db.get_setting("last_min_refresh"))
    assert last["stopped"].startswith("오류 — 중단: ConnectionError"), last["stopped"]
    assert last["requests"] == 0, "warmup 에서 끊겼으니 센 요청이 없다"


def test_재조회_오류_뒤에도_최저가_재판정은_돈다(monkeypatch):
    seen: list = []
    _stub_rest(monkeypatch, seen)
    db.upsert_vehicle(V(0))
    # 재판정 대상: 최저가가 내려갔는데 판정은 옛 최저가(980만)로 남은 행 — 지연 아님(유찰 2회 = 0.7²)
    db.upsert_vehicle(V(9, id="R1", fail_count=2, judgment="유찰 대기", upper_bid=8_000_000))
    monkeypatch.setattr(service, "new_session", lambda: object())
    monkeypatch.setattr(service, "warmup",
                        lambda _s: (_ for _ in ()).throw(requests.exceptions.Timeout("읽기 시간 초과")))
    _enable(monkeypatch)
    out = service.daily_update(run_id=db.create_run(target=0))
    assert out["floor"]["error_type"] == "Timeout"
    assert "error" not in out["rejudge"] and out["rejudge"]["checked"] >= 2


@pytest.mark.parametrize("status", [403, 429])
def test_재조회_차단은_여전히_매일_갱신_전체를_멈춘다(monkeypatch, status):
    """C.4-5 — 격리를 넣으면서 차단 전파가 약해지지 않았는지. 실제 fetch_detail·_check_block 경로."""
    for i in range(3):
        db.upsert_vehicle(V(i))
    seen: list = []
    _stub_rest(monkeypatch, seen)
    sess = _wire_real(monkeypatch, lambda n: _Resp(status))
    _enable(monkeypatch)
    with pytest.raises(RuntimeError, match="차단"):
        service.daily_update(run_id=db.create_run(target=0))
    assert len(sess.posts) == 1, "차단 뒤 요청을 더 보냈다"
    assert seen == [], f"차단 뒤 단계가 돌았다 {seen}"
    assert "차단" in json.loads(db.get_setting("last_min_refresh"))["stopped"]


def test_캡차_소프트_차단도_여전히_멈춘다(monkeypatch):
    for i in range(2):
        db.upsert_vehicle(V(i))
    seen: list = []
    _stub_rest(monkeypatch, seen)
    _wire_real(monkeypatch, lambda n: _Resp(200, "<html>보안문자</html>", "text/html"))
    _enable(monkeypatch)
    with pytest.raises(RuntimeError, match="차단"):
        service.daily_update(run_id=db.create_run(target=0))
    assert seen == []


def test_비정상_응답_3회_연속도_여전히_멈춘다(monkeypatch):
    for i in range(4):
        db.upsert_vehicle(V(i))
    seen: list = []
    _stub_rest(monkeypatch, seen)
    sess = _wire_real(monkeypatch, lambda n: _Resp(200, "{not json"))
    _enable(monkeypatch)
    with pytest.raises(RuntimeError, match="3회 연속"):
        service.daily_update(run_id=db.create_run(target=0))
    assert len(sess.posts) == 3 and seen == []


def test_RuntimeError_가_아닌_상태코드_차단도_전파한다(monkeypatch):
    """requests.HTTPError(403) 처럼 RuntimeError 가 아니어도 `_is_block` 이면 멈춘다 — 격리는 좁게."""
    db.upsert_vehicle(V(0))
    seen: list = []
    _stub_rest(monkeypatch, seen)
    monkeypatch.setattr(service, "new_session", lambda: object())

    class _R:
        status_code = 403

    def wu(_s):
        raise requests.exceptions.HTTPError("403 Forbidden", response=_R())
    monkeypatch.setattr(service, "warmup", wu)
    _enable(monkeypatch)
    with pytest.raises(requests.exceptions.HTTPError):
        service.daily_update(run_id=db.create_run(target=0))
    assert seen == []
    assert json.loads(db.get_setting("last_min_refresh"))["stopped"].startswith("차단 감지 — 중단")


def test_재판정_단계_오류는_기록하고_계속한다(monkeypatch):
    import sqlite3
    seen: list = []
    _stub_rest(monkeypatch, seen)

    def boom(**k):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(service, "rejudge_floor_changes", boom)
    out = service.daily_update(run_id=db.create_run(target=0))
    assert "update_results" in seen and out["rejudge"]["error_type"] == "OperationalError"
    assert " · ⚠최저가 재판정 오류 OperationalError" in db.latest_run()["message"]


def test_꺼져_있으면_격리_경로를_타지_않는다(monkeypatch):
    """꺼짐이면 요청 0 — 오류 조각도 없다. 저장소 config 는 09-30 오너 승인으로 켜졌으므로 메모리에서 끄고 본다."""
    real = service.load_config
    monkeypatch.setattr(service, "load_config", lambda *a, **k: {**real(*a, **k), "min_refresh_enabled": False})
    for i in range(2):
        db.upsert_vehicle(V(i))
    seen: list = []
    _stub_rest(monkeypatch, seen)
    monkeypatch.setattr(service, "new_session", lambda: object())      # ⑤ 최종 검토의 세션(가짜)
    monkeypatch.setattr(service, "warmup", lambda _s: None)
    out = service.daily_update(run_id=db.create_run(target=0))
    assert "error_type" not in out["floor"] and out["floor"]["requests"] == 0
    assert "오류" not in db.latest_run()["message"]


# ═════════════════════════════════════════════════════════════════════
# F4 — 사고 재등급 범위: 요항 파일이 있고 파서 결과가 달라진 행만 · 기본 미리보기 · --apply · --ids
# ═════════════════════════════════════════════════════════════════════
NEW_FORM = "중고차 사고 이력정보보고서는 내차 8회 및 상대차 2회의 사고 기록이 있습니다."


def test_기준선_패턴은_직전_파서다_내차_상대차_두_줄만_다르다():
    cur = detail_parser._HIST_PATTERNS
    assert set(HIST_PATTERNS_BASELINE) == set(cur)
    assert {k for k in cur if cur[k] != HIST_PATTERNS_BASELINE[k]} == {"own_damage", "opp_damage"}
    assert parse_insurance_history(NEW_FORM, HIST_PATTERNS_BASELINE) == {}
    assert parse_insurance_history(NEW_FORM) == {"own_damage": 8, "opp_damage": 2}
    assert parse_insurance_history("내차 피해 : 6건", HIST_PATTERNS_BASELINE) == {"own_damage": 6}


def _seed_regrade(tmp_path, monkeypatch) -> dict:
    """F4 재현 픽스처 — 파서 수정 대상 1행 + qa 가 본 '범위 없는 재등급'이 건드리던 표류 4꼴."""
    monkeypatch.setattr("src.paths.DATA_DIR", tmp_path)

    def appr(fk, text):
        (tmp_path / fk).mkdir()
        (tmp_path / fk / "appraisal.txt").write_text(text, encoding="utf-8")

    rows = {
        # A: 요항에 새 꼴 '내차 8회' — 파서 수정의 진짜 대상(2026타경30118_1 BMW 520d)
        "A": V(0, id="A", folder_key="A", accident_grade="accident", accident_hits=["사고"],
               insurance_history={}, judgment="입찰 검토 가능", upper_bid=10_645_200,
               breakdown={"사고감가율": 0.15, "현재최저매각가": 9_800_000}, photo_count=15),
        # B: 요항 파일 없음 + 명세에 새 꼴 — 파서 결과는 달라도 명세만으로 다시 매기지 않는다(2026타경100593_1 꼴)
        "B": V(1, id="B", folder_key="B", accident_grade="none", insurance_history={},
               spec_remark="보험사고이력 내차 3회(8,038,135원), 상대차 1회(6,162,733원)"),
        # C: 요항 파일 없음 + 저장은 침수(요항에서 읽었던 근거) — 범위 없는 재등급은 무사고로 내렸다(2025타경34408_1 꼴)
        "C": V(2, id="C", folder_key="C", accident_grade="flood", accident_hits=[],
               insurance_history={}, judgment="입찰 보류", upper_bid=-13_321_000,
               spec_remark="특이사항 없음"),
        # D: 요항은 있으나 옛 꼴 '내차 피해 : 2건'(두 파서가 같게 읽음) — 저장 등급이 표류해 있어도 건드리지 않는다
        "D": V(3, id="D", folder_key="D", accident_grade="none", accident_hits=[], insurance_history={}),
        # E: 요항 파일 없음 + 저장은 사고 — 범위 없는 재등급은 사고→무사고로 내렸다(2026타경15189_1 꼴)
        "E": V(4, id="E", folder_key="E", accident_grade="accident", accident_hits=["판금"],
               insurance_history={"owner_changes": 3}, spec_remark="소유자 변경 3회"),
    }
    appr("A", NEW_FORM)
    appr("D", "보험사고이력 내차 피해 : 2건, 상대차 피해 : 0건")
    for r in rows.values():
        db.upsert_vehicle(r)
    return rows


def _snapshot() -> dict:
    return {v["id"]: v for v in db.list_vehicles()}


def test_재등급은_요항이_있고_파서_결과가_달라진_행만_고른다(tmp_path, monkeypatch):
    _seed_regrade(tmp_path, monkeypatch)
    # 대조: 범위 없는 옛 경로는 표류 행까지 바꾼다(qa F4 재현)
    wide: list = []
    service.backfill_accident_grades(preview=wide)
    assert {r["id"] for r in wide} == {"A", "B", "C", "D", "E"}, \
        "픽스처가 F4 표류를 재현하지 못한다(공허 통과 방지)"
    res = service.regrade_accidents()
    assert [r["id"] for r in res["rows"]] == ["A"]
    assert res["skipped"] == {"no_appraisal": 3, "same_parse": 1, "already": 0}
    assert res["apply"] is False and res["applied"] == 0 and res["baseline"] == "8073a3d"


def test_직전_파서로는_재등급_대상이_0이다(tmp_path, monkeypatch):
    """qa F4: 로컬 사본에서 HEAD 파서로도 23행(요항 없음 20행)이 바뀌었다 — 파서가 같으면 0 이어야 한다."""
    _seed_regrade(tmp_path, monkeypatch)
    monkeypatch.setattr(detail_parser, "_HIST_PATTERNS", dict(HIST_PATTERNS_BASELINE))   # = HEAD 파서
    wide: list = []
    assert service.backfill_accident_grades(preview=wide) >= 2, "대조군: 범위 없는 경로는 여전히 바꾼다"
    res = service.regrade_accidents()
    assert res["targets"] == 0 and res["rows"] == []


def test_미리보기_행은_등급_감가_상한가_입찰상한선_판정의_전후를_보인다(tmp_path, monkeypatch):
    _seed_regrade(tmp_path, monkeypatch)
    r = service.regrade_accidents()["rows"][0]
    assert r["parse"] == [{}, {"own_damage": 8, "opp_damage": 2}]
    assert r["grade"] == ["accident", "accident"]
    assert r["insurance_history"] == [{}, {"own_damage": 8, "opp_damage": 2}]
    assert r["rate"] == [0.15, 0.30]
    assert r["upper_bid"][1] < r["upper_bid"][0] == 10_645_200
    assert r["judgment"] == ["입찰 검토 가능", "유찰 대기"]
    # 입찰 상한선(실사용 손익분기)도 감가 15%→30% 를 따라 내려간다(design-critic 확인 요청)
    assert r["max_bid"][0] and r["max_bid"][1] and r["max_bid"][1] < r["max_bid"][0]


def test_관리_명령은_기본이_미리보기이고_쓰지_않는다(tmp_path, monkeypatch, capsys):
    from web import maint
    _seed_regrade(tmp_path, monkeypatch)
    before = _snapshot()
    for argv in (["maint", "regrade-accidents"], ["maint", "regrade-accidents", "--dry-run"]):
        assert maint.main(argv) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["apply"] is False and out["targets"] == 1 and out["rows"][0]["id"] == "A"
        assert _snapshot() == before, f"{argv} 가 DB 를 썼다"


def test_apply_일_때만_같은_행을_쓰고_다시_돌리면_0이다(tmp_path, monkeypatch, capsys):
    from web import maint
    _seed_regrade(tmp_path, monkeypatch)
    before = _snapshot()
    assert maint.main(["maint", "regrade-accidents", "--apply"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["apply"] is True and out["applied"] == 1 and [r["id"] for r in out["rows"]] == ["A"]
    after = _snapshot()
    assert {k for k in after if after[k] != before[k]} == {"A"}, "A 밖의 행을 썼다"
    a = after["A"]
    assert a["insurance_history"] == {"own_damage": 8, "opp_damage": 2}
    assert a["breakdown"]["사고감가율"] == 0.30 and a["judgment"] == "유찰 대기"
    assert after["C"]["accident_grade"] == "flood" and after["C"]["judgment"] == "입찰 보류", \
        "요항 없는 침수 행이 무사고로 내려갔다(F4)"
    assert maint.main(["maint", "regrade-accidents", "--apply"]) == 0
    again = json.loads(capsys.readouterr().out)
    assert again["targets"] == 0 and again["skipped"]["already"] == 1, "멱등이 아니다"


def test_ids_는_범위를_좁히고_요항_없는_행은_지정해도_건너뛴다(tmp_path, monkeypatch, capsys):
    from web import maint
    _seed_regrade(tmp_path, monkeypatch)
    before = _snapshot()
    assert maint.main(["maint", "regrade-accidents", "--ids", "B,C", "--apply"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["checked"] == 2 and out["targets"] == 0 and out["skipped"]["no_appraisal"] == 2
    assert _snapshot() == before
    assert maint.main(["maint", "regrade-accidents", "--ids=A,없는_id"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [r["id"] for r in out["rows"]] == ["A"] and out["not_found"] == ["없는_id"]


@pytest.mark.parametrize("argv", [["--force"], ["--force", "--apply"], ["--ids"], ["--ids="],
                                  ["--apply", "--dry-run"]])
def test_범위_없는_재등급과_모호한_인자는_거절한다(tmp_path, monkeypatch, capsys, argv):
    from web import maint
    _seed_regrade(tmp_path, monkeypatch)
    before = _snapshot()
    assert maint.main(["maint", "regrade-accidents", *argv]) == 2
    capsys.readouterr()
    assert _snapshot() == before


def test_끝난_매각의_판정은_재등급이_되살리지_않는다(tmp_path, monkeypatch):
    monkeypatch.setattr("src.paths.DATA_DIR", tmp_path)
    (tmp_path / "W").mkdir()
    (tmp_path / "W" / "appraisal.txt").write_text(NEW_FORM, encoding="utf-8")
    db.upsert_vehicle(V(0, id="W", folder_key="W", sale_date=(TODAY - timedelta(days=20)).isoformat(),
                        auction_result="낙찰", winning_price=11_000_000, judgment="종결",
                        accident_grade="none", insurance_history={}))
    res = service.regrade_accidents(apply=True)
    assert res["applied"] == 1 and res["rows"][0]["judgment"] == ["종결", "종결"]
    w = db.get_vehicle("W")
    assert w["judgment"] == "종결" and w["accident_grade"] == "accident"


# ═════════════════════════════════════════════════════════════════════
# frontend 재료 — 가드 상태에서도 bid_state 는 입찰 상한선을 준다(design-critic 지적 2 의 '값은 backend 확인')
# 화면 재료(이번 기일 추정 최저가·근거)는 frontend 가 app.py `_floor_guard` 에서 service 원시 함수로 만든다.
# ═════════════════════════════════════════════════════════════════════
BT = {"min_premium_pool": [round(1.00 + i * 0.004, 4) for i in range(60)],
      "discount_median": 0.74, "mae_pct": 9.2, "sample": 172, "within10_pct": 62,
      "min_premium_median": 1.13, "min_premium_by_fail": {"0": 1.20, "1": 1.13, "2+": 1.06},
      "min_premium_p25": 1.05, "min_premium_p75": 1.22}


def test_가드_상태에서도_입찰_상한선은_bid_state_에_있고_최저가와_무관하다():
    v = V(0)
    assert service.floor_lagging(v), "픽스처가 가드 상태가 아니다(공허 통과 방지)"
    st = service.bid_state(v, BT)
    assert st["state"] == "wait" and st["exp"] is None
    assert st["max_bid"] and st["max_bid"] == service.personal_use_max_bid(v)
    # 최저가를 이번 기일 추정값으로 바꿔도(가드 해제) 상한선은 같다 — 최저가와 무관한 값이다
    st2 = service.bid_state({**v, "min_sale_price": 6_860_000}, BT)
    assert st2["max_bid"] == st["max_bid"]


# ═════════════════════════════════════════════════════════════════════
# qa 1회차 §4 — judge 경계 변이(`<` → `<=`)가 살아남았다: 고정 기대값으로 묶는다
# ═════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("upper,mn,n,flood,want", [
    (10_000_000, 10_000_000, 14, False, Judgment.OK),          # 상한 = 최저가 → 써낼 수 있다
    (9_999_999, 10_000_000, 14, False, Judgment.WAIT_FAIL),    # 1원 모자라면 유찰 대기
    (10_000_001, 10_000_000, 14, False, Judgment.OK),
    (10_000_000, 9_000_000, 4, False, Judgment.LOW_CONFIDENCE),  # 표본 4 < min_sample_count 5
    (10_000_000, 9_000_000, 5, False, Judgment.OK),              # 표본 5 = 경계 → 통과
    (10_000_000, 9_000_000, 14, True, Judgment.HOLD_FLOOD),      # 침수가 가장 앞선다
    (-1, 9_000_000, 3, True, Judgment.HOLD_FLOOD),
])
def test_judge_경계는_고정값이다(upper, mn, n, flood, want):
    cfg = service.load_config()
    assert cfg["min_sample_count"] == 5, "기준 값이 바뀌었다 — 이 표도 함께 검토할 것"
    assert judge(upper, mn, n, flood, cfg) == want.value
