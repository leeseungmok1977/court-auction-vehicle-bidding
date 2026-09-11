"""사진 자동 정렬(로컬 모델) — 순서 규칙·DB 반영·비전 패치 우선순위 불변식.

모델 파일 없이 검증한다(FakeSorter). 실제 정확도는 src/parse/photo_autosort.py 머리말의 교차검증 수치 참조.
"""
import numpy as np
import pytest
from PIL import Image

from src.parse import photo_autosort as PA


def test_order_from_probs_priority_then_confidence():
    files = ["a", "b", "c", "d", "e"]
    P = np.array([[.1, .1, .1, .6, .1],      # a: other
                  [.7, .1, .1, .05, .05],    # b: front .7
                  [.05, .05, .05, .05, .8],  # c: back(지도·서류) → 맨 뒤
                  [.2, .6, .1, .05, .05],    # d: side
                  [.8, .1, .05, .05, .0]])   # e: front .8 → 1순위
    order, labels, conf = PA.order_from_probs(files, P)
    assert order == ["e", "b", "d", "a", "c"]
    assert sorted(order) == sorted(files) and labels[2] == "back"


class FakeSorter:
    """파일명 접두어로 확률을 만든다(모델 없이 파이프라인 검증)."""
    def sort(self, files, paths):
        P = []
        for f in files:
            row = [0.05] * 5
            row[{"front": 0, "side": 1, "rear": 2, "map": 4}.get(f.split("_")[0], 3)] = 0.8
            P.append(row)
        order, labels, conf = PA.order_from_probs(files, np.array(P))
        first = dict(zip(files, zip(labels, conf)))[order[0]]
        return {"order": order, "labels": labels, "conf": conf, "first_label": first[0], "first_conf": first[1]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    monkeypatch.setattr(PA, "DATA_DIR", tmp_path)

    def mk(vid, names, order=None, src=None):
        d = tmp_path / vid / "photos"
        d.mkdir(parents=True)
        for n in names:
            Image.new("RGB", (8, 8)).save(d / n)
        db.upsert_vehicle({"id": vid, "folder_key": vid, "case_no": vid, "item_no": "1", "court": "x",
                           "maker": "현대", "model": "쏘나타", "year": 2020, "min_sale_price": 1, "appraisal_value": 1,
                           "fail_count": 0, "sale_date": "2999-01-01", "status": "미분석", "photo_count": len(names)})
        if order:
            db.update_fields(vid, photo_order=order, photo_order_src=src)
    return db, mk


def test_autosort_new_sets_order_and_source_only_for_unclassified(env):
    db, mk = env
    mk("N1", ["map_1.gif", "side_2.gif", "front_3.gif", "x_4.gif"])
    mk("V1", ["map_1.gif", "front_2.gif"], order=["front_2.gif", "map_1.gif"], src="vision")
    st = PA.autosort_new(limit=10, sorter=FakeSorter())
    assert st["candidates"] == 1 and st["sorted"] == 1 and st["low_conf"] == 0
    v = db.get_vehicle("N1")
    assert v["photo_order"] == ["front_3.gif", "side_2.gif", "x_4.gif", "map_1.gif"]
    assert v["photo_order_src"] == "auto"
    assert db.get_vehicle("V1")["photo_order_src"] == "vision"      # 기분류는 건드리지 않음
    # 두 번째 실행: 후보 0 (auto도 '순서 있음'으로 취급 — 매일 재정렬로 흔들리지 않게)
    assert PA.autosort_new(limit=10, sorter=FakeSorter())["candidates"] == 0


def test_autosort_dry_run_and_low_conf(env):
    db, mk = env
    mk("N2", ["map_1.gif", "x_2.gif"])                 # 정면 없음 → 저확신 집계
    st = PA.autosort_new(limit=10, sorter=FakeSorter(), dry_run=True)
    assert st["sorted"] == 1 and st["low_conf"] == 1
    assert db.get_vehicle("N2")["photo_order"] is None  # dry-run은 DB 미반영


def test_missing_model_is_nonfatal(env, monkeypatch):
    db, mk = env
    mk("N3", ["a.gif"])
    monkeypatch.setattr(PA, "MODEL_PATH", PA.MODEL_PATH.with_name("nope.onnx"))
    st = PA.autosort_new(limit=10)
    assert st["sorted"] == 0 and "모델 로드 실패" in st["error"]


def test_vision_patch_overwrites_auto_but_keeps_vision(env):
    db, mk = env
    mk("A1", ["a.gif", "b.gif"], order=["b.gif", "a.gif"], src="auto")
    mk("V1", ["a.gif", "b.gif"], order=["b.gif", "a.gif"], src="vision")
    mk("U1", ["a.gif", "b.gif"])
    from scripts.apply_photo_order_patch import apply_patch
    c = apply_patch({"A1": ["a.gif", "b.gif"], "V1": ["a.gif", "b.gif"], "U1": ["a.gif", "b.gif"], "Z9": ["a.gif"]})
    assert c == {"applied": 2, "overwrote_auto": 1, "skipped": 1, "missing": 1}
    a = db.get_vehicle("A1")
    assert a["photo_order"] == ["a.gif", "b.gif"] and a["photo_order_src"] == "vision"
    assert db.get_vehicle("V1")["photo_order"] == ["b.gif", "a.gif"]   # 비전 순서는 force 없이 보존
    assert db.get_vehicle("U1")["photo_order_src"] == "vision"


def test_probe_weights_match_classes():
    z = np.load(PA.PROBE_PATH)
    assert tuple(z["classes"]) == PA.CLASSES and z["W"].shape == (5, 512) and z["b"].shape == (5,)
