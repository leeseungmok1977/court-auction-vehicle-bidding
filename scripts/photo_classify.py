# -*- coding: utf-8 -*-
"""차량 사진 비전 분류 파이프라인 (정면·측면·실내 순서 배치).

사용 흐름 (새 물건이 수집될 때마다 '미분류 건만' 처리):
  1) python scripts/photo_classify.py prep        # 미분류 물건 몽타주 생성 + args.json
  2) (Claude) classify-vehicle-photos 워크플로 실행 → results.json 저장
  3) python scripts/photo_classify.py apply        # 결과를 DB photo_order 에 반영 + 검수요약

작업 파일은 data/_photo_work/ (git 제외)에 만든다.
  manifest.json  : [{vid, model, folder_key, montage, files:[파일명…]}]  (셀 순서=files 순서)
  args.json      : 워크플로 args (=[{vid, model, n, montage}])
  results.json   : 워크플로 산출물 (=[{vid, front, side, interior, order, confident, note}])

'미분류'는 photo_count>0 이고 photo_order IS NULL 인 물건. 이미 분류된 건은 건드리지 않는다(증분).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.parse.photo_montage import DATA_DIR, build_montage, list_photos  # noqa: E402
from web import db  # noqa: E402

WORK = DATA_DIR / "_photo_work"
MANIFEST = WORK / "manifest.json"
ARGS = WORK / "args.json"
RESULTS = WORK / "results.json"


def _unclassified(status: str | None, limit: int | None):
    """photo_count>0 이고 photo_order 가 비어있는 물건."""
    conn = db.connect()
    sql = ("SELECT id, folder_key, model, status FROM vehicles "
           "WHERE COALESCE(photo_count,0) > 0 "
           "AND (photo_order IS NULL OR photo_order = '')")
    params: list = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY collected_at DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def cmd_prep(args) -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    # 이전 실행 잔여 몽타주 정리(인덱스 재사용 혼선 방지)
    for old in WORK.glob("*.png"):
        old.unlink()
    rows = _unclassified(args.status, args.limit)
    manifest = []
    skipped = 0
    for r in rows:
        vid = r["id"]
        fk = r["folder_key"] or vid
        if not list_photos(fk):
            skipped += 1
            continue
        idx = f"{len(manifest) + 1:04d}"             # 0001, 0002 … 순차(성공분만)
        built = build_montage(fk, WORK, name=idx)     # 파일명 = {idx}.png
        if not built:
            skipped += 1
            continue
        montage, files = built
        manifest.append({"idx": idx, "vid": vid, "model": r.get("model") or "-",
                         "folder_key": fk, "montage": montage, "files": files})
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    # 컴팩트 args: base + total 만. 몽타주 경로는 워크플로에서 `base/{idx}.png`로 재구성
    # (인덱스가 순차라 에이전트별 명시 경로 생성 가능 → 대용량 vid 인라인 불필요).
    base = str(WORK).replace("\\", "/")
    ARGS.write_text(json.dumps({"base": base, "total": len(manifest)}, ensure_ascii=False),
                    encoding="utf-8")
    print(f"미분류 대상 {len(rows)}건 중 몽타주 {len(manifest)}건 생성 (사진없음/실패 {skipped}건).")
    print(f"  manifest: {MANIFEST}")
    print(f"  args    : {ARGS.read_text(encoding='utf-8')}")
    if manifest:
        print("다음: classify-photos-bulk 워크플로에 위 args를 넘겨 실행 → results.json 저장 후 apply.")
    return 0


def cmd_apply(args) -> int:
    if not RESULTS.exists():
        print(f"results.json 이 없습니다: {RESULTS}", file=sys.stderr)
        return 1
    db.init_db()  # photo_order 등 컬럼 마이그레이션 보장
    mlist = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_idx = {m["idx"]: m for m in mlist}
    by_vid = {m["vid"]: m for m in mlist}
    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    applied, low = 0, []
    for r in results:
        m = by_idx.get(str(r.get("idx"))) or by_vid.get(r.get("vid"))  # idx 우선, vid 폴백
        if not m:
            continue
        files = m["files"]
        order = [c for c in r.get("order", []) if isinstance(c, int) and 1 <= c <= len(files)]
        seen = set(order)
        order += [i for i in range(1, len(files) + 1) if i not in seen]  # 누락 셀 보충
        photo_order = [files[c - 1] for c in order]
        db.update_fields(m["vid"], photo_order=photo_order)
        applied += 1
        if not r.get("confident", True):
            low.append((m["vid"], m.get("model"), r.get("note", "")))
    print(f"적용 완료: {applied}건")
    if low:
        print(f"검수 필요(저확신) {len(low)}건 — 대개 원본에 순수 측면/실내 컷이 없는 경우:")
        for vid, model, note in low:
            print(f"  - {vid} {model}: {note[:70]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="차량 사진 비전 분류 파이프라인")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep", help="미분류 물건 몽타주 + args.json 생성")
    p.add_argument("--status", default=None, help="특정 status만 (예: 검토가능). 기본=전체 미분류")
    p.add_argument("--limit", type=int, default=None, help="최대 건수(부하 통제)")
    p.set_defaults(func=cmd_prep)
    a = sub.add_parser("apply", help="results.json → DB photo_order 반영")
    a.set_defaults(func=cmd_apply)
    ns = ap.parse_args()
    return ns.func(ns)


if __name__ == "__main__":
    raise SystemExit(main())
