# -*- coding: utf-8 -*-
"""사진 자동 정렬 — 로컬 모델(생성형 AI API 없음). 정면→측면→후면→기타 외관→실내→지도·서류.

구성: CLIP ViT-B/32 이미지 인코더(ONNX int8, Xenova/clip-vit-base-patch32 — data/models/ 에 1회 다운로드)
      + 자체 학습 선형 프로브(src/parse/models/photo_probe.npz, 512→5 클래스).
프로브 정답 = Claude 비전 분류 photo_order 1,243건·13,510장(2026-09-11). 물건 단위 5-fold 교차검증:
      1번=비전1번 75.9% · 1번∈비전 top3 87.6% · 썸네일 3장에 지도·서류 유입 1.4%
      (법원 원본순: 32.1% · 36.0%). 비전보다 정확도가 낮으므로 photo_order_src='auto'로 표시하고,
      주간 /classify-photos(Claude 비전)가 'auto'를 덮어써 보정한다(scripts/apply_photo_order_patch.py).
메모리: int8 모델 로드 ~150MB, 배치 8 추론 ~175MB → 일일 갱신에서는 별도 프로세스로 실행(EC2 RAM 1GB).

사용:
  python -m src.parse.photo_autosort --download          # 모델 1회 다운로드(sha256 검증)
  python -m src.parse.photo_autosort --new --limit 150   # 미분류(photo_order 없음) 신규 물건 정렬
  python -m src.parse.photo_autosort --vid <id> --dry-run # 단건 확인(DB 미반영)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path
from typing import Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.parse.photo_montage import DATA_DIR  # noqa: E402

MODEL_URL = "https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/onnx/vision_model_quantized.onnx"
MODEL_SHA256 = "583fd1110a514667812fee7d684952aaf82a99b959760c8d7dca7e0ab9839299"
MODEL_PATH = DATA_DIR / "models" / "clip-vit-b32-vision-int8.onnx"
PROBE_PATH = Path(__file__).with_name("models") / "photo_probe.npz"

CLASSES = ("front", "side", "rear", "other", "back")
PRIO = {"front": 0, "side": 1, "rear": 2, "other": 3, "back": 9}   # 정렬 우선순위(낮을수록 앞)
SRC_AUTO = "auto"       # photo_order_src: 로컬 모델 자동 정렬
SRC_VISION = "vision"   # photo_order_src: Claude 비전 분류(정답 취급, auto를 덮어씀)
PHOTO_EXT = (".gif", ".jpg", ".jpeg", ".png", ".webp")
BATCH = 8               # 메모리 상한(≈175MB)용 배치
LOW_CONF = 0.5          # 1순위 사진의 정면 확률이 이 미만이면 저확신 집계
_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_model(download: bool = False) -> Path:
    """모델 파일 존재·무결성 보장. download=True면 없을 때 받는다(단일 HTTPS GET, 1회)."""
    if MODEL_PATH.exists() and _sha256(MODEL_PATH) == MODEL_SHA256:
        return MODEL_PATH
    if not download:
        raise FileNotFoundError(f"모델 없음: {MODEL_PATH} (python -m src.parse.photo_autosort --download)")
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = MODEL_PATH.with_suffix(".part")
    req = urllib.request.Request(MODEL_URL, headers={"User-Agent": "naechaget-photo-autosort/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        for chunk in iter(lambda: r.read(1 << 20), b""):
            f.write(chunk)
    if _sha256(tmp) != MODEL_SHA256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("모델 sha256 불일치 — 다운로드 중단")
    tmp.replace(MODEL_PATH)
    return MODEL_PATH


def _preprocess(path: Path) -> np.ndarray:
    """CLIP 표준 전처리: 짧은 변 224 리사이즈 → 중앙 224 크롭 → 정규화, CHW float32."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = 224 / min(w, h)
    im = im.resize((max(224, round(w * s)), max(224, round(h * s))), Image.BICUBIC)
    w, h = im.size
    l, t = (w - 224) // 2, (h - 224) // 2
    a = (np.asarray(im.crop((l, t, l + 224, t + 224)), dtype=np.float32) / 255.0 - _MEAN) / _STD
    return a.transpose(2, 0, 1)


def order_from_probs(files: list, P) -> tuple:
    """클래스 확률(P: n×5) → (정렬된 파일 목록, 파일별 라벨, 파일별 확신). 우선순위 → 확신 내림차순 → 원순서.
    모든 파일이 정확히 한 번씩 포함된다."""
    P = np.asarray(P, dtype=np.float32)
    cls = P.argmax(1)
    conf = P.max(1)
    idx = sorted(range(len(files)), key=lambda i: (PRIO[CLASSES[cls[i]]], -float(conf[i]), i))
    return [files[i] for i in idx], [CLASSES[c] for c in cls], [float(c) for c in conf]


class Sorter:
    """ONNX 이미지 인코더 + 선형 프로브. 프로세스당 1회 로드."""

    def __init__(self, threads: int = 2):
        import onnxruntime as ort
        ensure_model(download=False)
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(str(MODEL_PATH), so, providers=["CPUExecutionProvider"])
        z = np.load(PROBE_PATH)
        if tuple(z["classes"]) != CLASSES:
            raise RuntimeError("프로브 클래스 불일치")
        self.W, self.b = z["W"].astype(np.float32), z["b"].astype(np.float32)

    def _probs(self, arrays: list) -> np.ndarray:
        out = []
        for i in range(0, len(arrays), BATCH):
            X = np.stack(arrays[i:i + BATCH]).astype(np.float32)
            E = self.sess.run(None, {"pixel_values": X})[0]
            E = E / np.linalg.norm(E, axis=1, keepdims=True)
            L = E @ self.W.T + self.b
            L -= L.max(1, keepdims=True)
            Pb = np.exp(L)
            Pb /= Pb.sum(1, keepdims=True)
            out.append(Pb)
        return np.concatenate(out) if out else np.zeros((0, len(CLASSES)), np.float32)

    def sort(self, files: list, paths: list) -> dict:
        """한 물건의 사진 정렬. 열 수 없는 파일은 맨 뒤(정렬 실패로 전체를 버리지 않는다)."""
        arrays, ok, bad = [], [], []
        for i, p in enumerate(paths):
            try:
                arrays.append(_preprocess(Path(p)))
                ok.append(i)
            except Exception:  # noqa: BLE001 — 손상 파일
                bad.append(i)
        ok_files = [files[i] for i in ok]
        order, labels, conf = order_from_probs(ok_files, self._probs(arrays)) if ok else ([], [], [])
        by_file = dict(zip(ok_files, zip(labels, conf)))
        first = by_file.get(order[0]) if order else None
        return {"order": order + [files[i] for i in bad], "labels": labels, "conf": conf,
                "first_label": first[0] if first else None, "first_conf": first[1] if first else None}


def _photo_files(fk: str) -> list:
    d = DATA_DIR / fk / "photos"
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_file() and p.suffix.lower() in PHOTO_EXT)


def autosort_new(limit: int = 150, only_ids: Optional[list] = None, dry_run: bool = False,
                 sorter=None, threads: int = 2) -> dict:
    """미분류(photo_order 없음) 물건을 자동 정렬해 photo_order + photo_order_src='auto' 저장.
    이미 순서가 있는 물건(비전·auto 모두)은 건드리지 않는다 — 비전 결과 퇴행 방지."""
    from web import db
    db.init_db()
    conn = db.connect()
    if only_ids:
        q = f"SELECT id, folder_key FROM vehicles WHERE id IN ({','.join('?' * len(only_ids))})"
        rows = [dict(r) for r in conn.execute(q, list(only_ids)).fetchall()]
    else:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, folder_key FROM vehicles WHERE COALESCE(photo_count,0)>0 "
            "AND (photo_order IS NULL OR photo_order='') ORDER BY collected_at DESC LIMIT ?",
            (int(limit),)).fetchall()]
    conn.close()
    stats = {"candidates": len(rows), "sorted": 0, "no_photos": 0, "errors": 0, "low_conf": 0, "dry_run": dry_run}
    if not rows:
        return stats
    if sorter is None:
        try:
            sorter = Sorter(threads=threads)
        except Exception as e:  # noqa: BLE001 — 모델 미설치 등: 갱신 전체를 막지 않는다
            stats["error"] = f"모델 로드 실패: {str(e)[:120]}"
            return stats
    for r in rows:
        fk = r.get("folder_key") or r["id"]
        files = _photo_files(fk)
        if not files:
            stats["no_photos"] += 1
            continue
        try:
            res = sorter.sort(files, [DATA_DIR / fk / "photos" / f for f in files])
        except Exception:  # noqa: BLE001
            stats["errors"] += 1
            continue
        if res["first_label"] != "front" or (res["first_conf"] or 0) < LOW_CONF:
            stats["low_conf"] += 1
        if not dry_run:
            db.update_fields(r["id"], photo_order=res["order"], photo_order_src=SRC_AUTO)
        stats["sorted"] += 1
        if only_ids:
            stats.setdefault("detail", {})[r["id"]] = {"order": res["order"],
                                                       "labels": dict(zip(files, zip(res["labels"], [round(c, 2) for c in res["conf"]])))}
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="사진 자동 정렬(로컬 모델)")
    ap.add_argument("--download", action="store_true", help="모델 파일 다운로드(1회)")
    ap.add_argument("--new", action="store_true", help="미분류 신규 물건 정렬")
    ap.add_argument("--limit", type=int, default=150)
    ap.add_argument("--vid", nargs="*", help="특정 물건만")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--json", action="store_true", help="마지막 줄에 JSON 요약 출력(일일 갱신 파싱용)")
    ns = ap.parse_args()
    if ns.download:
        p = ensure_model(download=True)
        print(f"모델 준비 완료: {p} ({p.stat().st_size / 1e6:.1f} MB)")
    stats = None
    if ns.new or ns.vid:
        stats = autosort_new(limit=ns.limit, only_ids=ns.vid, dry_run=ns.dry_run, threads=ns.threads)
        if ns.json:
            print(json.dumps(stats, ensure_ascii=False))
        else:
            print(f"후보 {stats['candidates']} · 정렬 {stats['sorted']} · 사진없음 {stats['no_photos']} · 오류 {stats['errors']}"
                  f" · 저확신 {stats['low_conf']}" + (f" · {stats['error']}" if stats.get("error") else ""))
            for vid, d in (stats.get("detail") or {}).items():
                print(f"  {vid}: {d['order'][:3]} …")
                for f, (lab, c) in d["labels"].items():
                    print(f"     {f}: {lab} {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
