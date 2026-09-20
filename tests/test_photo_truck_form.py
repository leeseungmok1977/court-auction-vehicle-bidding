# -*- coding: utf-8 -*-
"""사진 비전이 읽은 적재함 형식이 DB와 운영 서버까지 닿는지 고정(파이프라인 3구간).

2026-09-20. 형식 미상 포터·봉고 16건을 살리려고 비전에게 적재함을 묻기로 했는데,
조사해 보니 **주간 검수가 다시 보는 것은 2건뿐**이었다. 나머지 14건은 이미 비전 분류가
끝나 `_NEEDS_VISION`(미분류 또는 auto)에 걸리지 않기 때문이다. 그래서 세 군데가 필요했다.

  ① 대상 선정 — 형식만 새로 묻는 **별도 선택자**(`_truck_form_unknown`)
  ② 저장      — `cmd_apply` 가 **답이 있을 때만** 형식을 쓴다
  ③ 이관      — VM 패치가 **순서를 보존하면서 형식만** 채운다

③이 특히 함정이다. 재분류 대상은 전부 src='vision'이라 패치 주입의 '기존 순서 보존' 가지로
떨어진다 — 거기서 같이 건너뛰면 형식이 영원히 운영 DB에 닿지 않는다.
"""
import json
import os

import pytest

from scripts import photo_classify as pc
from scripts.apply_photo_order_patch import apply_patch
from web import db


@pytest.fixture
def dbmod(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    return db


def _v(vid, model, **kw):
    row = {"id": vid, "folder_key": vid, "case_no": f"2026타경{abs(hash(vid)) % 9000 + 1000}",
           "item_no": "1", "maker": "현대", "model": model, "photo_count": 4}
    row.update(kw)
    db.upsert_vehicle(row)


# ── ① 대상 선정 ────────────────────────────────────────────────────────
def test_이미_비전분류된_물건도_형식이_없으면_대상이다(dbmod):
    """이게 이번 작업의 핵심이다 — 기존 조건이라면 14건이 통째로 빠진다."""
    _v("V1", "포터Ⅱ", photo_order=["a.jpg"], photo_order_src="vision")
    assert [r["id"] for r in pc._truck_form_unknown(None, None)] == ["V1"]


def test_차명으로_형식을_읽을_수_있으면_묻지_않는다(dbmod):
    """비전 요청은 비싸다 — 감정 문서에 이미 적힌 것을 다시 묻지 않는다."""
    _v("V2", "포터Ⅱ 냉동탑차")
    assert pc._truck_form_unknown(None, None) == []


def test_이미_형식을_채운_물건은_다시_묻지_않는다(dbmod):
    _v("V3", "포터Ⅱ", truck_form="카고(화물)트럭")
    assert pc._truck_form_unknown(None, None) == []


def test_포터봉고가_아닌_물건은_대상이_아니다(dbmod):
    """사진 보유 물건 전체로 번지면 수백 건 비전 요청이 나가고 맞는 정렬까지 흔든다."""
    for i, m in enumerate(("쏘나타", "굴착기", "덤프트럭", "지게차")):
        _v(f"N{i}", m)
    assert pc._truck_form_unknown(None, None) == []


def test_사진이_없으면_물어볼_것이_없다(dbmod):
    _v("V4", "봉고Ⅲ", photo_count=0)
    assert pc._truck_form_unknown(None, None) == []


@pytest.mark.parametrize("kw", [{"status": "종결"}, {"status": "상세없음"},
                                {"auction_result": "낙찰"}, {"auction_result": "종결"}])
def test_이미_끝난_물건은_묻지_않는다(dbmod, kw):
    """끝난 물건에 시세를 새로 내봐야 쓸 데가 없다 — 비전 요청만 태운다.

    로컬 실측 65건 중 17건이 종결·낙찰이었다. 9/20 에 같은 실수를 한 적이 있다
    (새로 만든 버킷에 종결 53건이 딸려 들어갔고, 운영 데이터에 적용해 보고서야 드러났다)."""
    _v("F1", "포터Ⅱ", **kw)
    assert pc._truck_form_unknown(None, None) == []


# ── ② 저장 ────────────────────────────────────────────────────────────
def _run_apply(tmp_path, monkeypatch, vid, result):
    monkeypatch.setattr(pc, "MANIFEST", tmp_path / "manifest.json")
    monkeypatch.setattr(pc, "RESULTS", tmp_path / "results.json")
    pc.MANIFEST.write_text(json.dumps(
        [{"idx": "0001", "vid": vid, "model": "포터Ⅱ", "folder_key": vid,
          "montage": "x.png", "files": ["a.jpg", "b.jpg"]}], ensure_ascii=False), encoding="utf-8")
    pc.RESULTS.write_text(json.dumps([result], ensure_ascii=False), encoding="utf-8")
    assert pc.cmd_apply(None) == 0
    return db.get_vehicle(vid)


def test_형식_답이_있으면_저장한다(dbmod, tmp_path, monkeypatch):
    _v("A1", "포터Ⅱ")
    v = _run_apply(tmp_path, monkeypatch, "A1",
                   {"idx": "0001", "order": [2, 1], "confident": True,
                    "truck_form": "윙바디/탑"})
    assert v["truck_form"] == "윙바디/탑"
    assert v["photo_order"] == ["b.jpg", "a.jpg"], "순서 반영은 기존대로 유지"


def test_형식_답이_없으면_비워_둔다(dbmod, tmp_path, monkeypatch):
    """비전이 생략했다는 건 사진으로 알 수 없다는 뜻이다 — 추측해 채우면 틀린 시세가 된다."""
    _v("A2", "포터Ⅱ")
    v = _run_apply(tmp_path, monkeypatch, "A2",
                   {"idx": "0001", "order": [1, 2], "confident": False})
    assert not v["truck_form"]


def test_저확신_몽타주의_형식은_쓰지_않는다(dbmod, tmp_path, monkeypatch):
    """실측에서 저확신 건은 대개 **한 몽타주에 여러 차량이 섞인** 경우였다.

    2026-09-20 비전 결과에 '계기판 4종·차량 여러 대 혼재', '싼타페·포터·검정세단 섞임'
    같은 건이 형식을 답해 왔다. 거기 보이는 적재함이 이 차의 것이라는 보장이 없다 —
    순서가 틀리면 사진을 다시 보면 되지만, 틀린 형식은 그대로 틀린 시세가 된다."""
    _v("A4", "포터Ⅱ")
    v = _run_apply(tmp_path, monkeypatch, "A4",
                   {"idx": "0001", "order": [1, 2], "confident": False,
                    "truck_form": "카고(화물)트럭"})
    assert not v["truck_form"]
    assert v["photo_order"] == ["a.jpg", "b.jpg"], "순서는 저확신이어도 기존대로 반영한다"


def test_엔카_표기가_아닌_형식_값은_저장하지_않는다(dbmod, tmp_path, monkeypatch):
    """'카고'는 그럴듯하지만 엔카 표기가 아니다 — 그대로 실리면 0건이 나온다."""
    _v("A3", "포터Ⅱ")
    v = _run_apply(tmp_path, monkeypatch, "A3",
                   {"idx": "0001", "order": [1, 2], "confident": True, "truck_form": "카고"})
    assert not v["truck_form"]


def test_옛_결과를_새_배치에_적용하지_않는다(dbmod, tmp_path, monkeypatch):
    """작업 폴더에 실제로 놓여 있던 지뢰(2026-09-20 발견).

    결과 JSON 에는 vid 가 없어 `apply` 는 **idx 로만** 차량을 찾는다. 그런데 idx 는 배치마다
    0001부터 다시 매겨진다 — 9일 지난 결과 90건의 idx 0001~0023 이 그날 새로 만든 배치 23건과
    완전히 겹쳐 있었다. 그대로 적용했다면 모하비·렉서스·G90 에 남의 사진 순서가 조용히 덮인다.
    화면에는 아무 오류도 안 뜬다 — 사용자만 엉뚱한 사진을 본다."""
    _v("G1", "포터Ⅱ")
    monkeypatch.setattr(pc, "MANIFEST", tmp_path / "m.json")
    monkeypatch.setattr(pc, "RESULTS", tmp_path / "r.json")
    pc.RESULTS.write_text(json.dumps([{"idx": "0001", "order": [2, 1], "confident": True}]),
                          encoding="utf-8")
    pc.MANIFEST.write_text(json.dumps(
        [{"idx": "0001", "vid": "G1", "model": "포터Ⅱ", "folder_key": "G1",
          "montage": "x.png", "files": ["a.jpg", "b.jpg"]}], ensure_ascii=False), encoding="utf-8")
    os.utime(pc.RESULTS, (1, 1))          # 결과가 배치보다 확실히 오래된 상태
    assert pc.cmd_apply(None) == 1, "오래된 결과를 거부해야 한다"
    assert not db.get_vehicle("G1")["photo_order"], "거부했으면 DB 를 건드리지 않아야 한다"


# ── ③ 운영 서버 이관 ───────────────────────────────────────────────────
def test_비전_순서는_보존하면서_형식만_채운다(dbmod):
    """재분류 대상은 전부 src='vision' — '기존 순서 보존' 가지에서 형식도 건너뛰면 안 된다."""
    _v("P1", "포터Ⅱ", photo_order=["원래1.jpg", "원래2.jpg"], photo_order_src="vision")
    c = apply_patch({"P1": {"order": ["새1.jpg"], "truck_form": "카고(화물)트럭"}})
    v = db.get_vehicle("P1")
    assert v["truck_form"] == "카고(화물)트럭"
    assert v["photo_order"] == ["원래1.jpg", "원래2.jpg"], "순서는 건드리지 않는다"
    assert c["forms"] == 1 and c["skipped"] == 1


def test_구형_패치_형식도_그대로_읽는다(dbmod):
    """패치 형태를 바꿨다 — 예전 리스트 패치가 깨지면 이관 경로가 통째로 멈춘다."""
    _v("P2", "포터Ⅱ")
    apply_patch({"P2": ["a.jpg", "b.jpg"]})
    assert db.get_vehicle("P2")["photo_order"] == ["a.jpg", "b.jpg"]


def test_이미_형식이_있으면_패치가_덮지_않는다(dbmod):
    _v("P3", "포터Ⅱ", truck_form="윙바디/탑", photo_order=["a.jpg"], photo_order_src="vision")
    apply_patch({"P3": {"order": ["a.jpg"], "truck_form": "카고(화물)트럭"}})
    assert db.get_vehicle("P3")["truck_form"] == "윙바디/탑"
