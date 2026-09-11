# -*- coding: utf-8 -*-
"""photo_order 패치를 DB에 주입 (로컬에서 비전분류한 순서를 VM DB로 이관).

로컬에서 scripts/photo_classify.py apply 로 분류를 마친 뒤,
  python scripts/photo_classify.py export-patch   # data/_photo_work/photo_order_patch.json 생성
로 패치를 만들고, 이 파일을 VM으로 복사한 다음 VM에서:
  python scripts/apply_photo_order_patch.py            # 미분류 + 자동정렬(photo_order_src='auto') 물건을 채움/덮어씀
  python scripts/apply_photo_order_patch.py --force    # 비전 분류(vision) 기존 순서도 덮어씀

패치는 {vehicle_id: [파일명,...]} 형태. 사진 파일은 로컬=VM 동일(같은 대법원 원본)이므로
파일명 순서 리스트를 그대로 이관해도 유효하다. VM에 없는 물건은 건너뛴다.
비전 분류는 로컬 모델 자동 정렬(auto)보다 정확하므로 auto는 기본으로 덮어쓰고 src='vision'으로 승격한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from web import db  # noqa: E402

# 패치 위치: CLI 인자 > data/photo_order_patch.json > data/_photo_work/photo_order_patch.json
def _resolve_patch() -> Path:
    for a in sys.argv[1:]:
        if a.endswith(".json"):
            return Path(a)
    for p in (ROOT / "data" / "photo_order_patch.json",
              ROOT / "data" / "_photo_work" / "photo_order_patch.json"):
        if p.exists():
            return p
    return ROOT / "data" / "photo_order_patch.json"


def apply_patch(patch: dict, force: bool = False) -> dict:
    """패치 주입. 순서 없음 → 채움, src='auto'(로컬 모델) → 비전으로 덮어씀, src='vision' → force일 때만."""
    db.init_db()  # photo_order·photo_order_src 컬럼 보장
    c = {"applied": 0, "overwrote_auto": 0, "skipped": 0, "missing": 0}
    for vid, order in patch.items():
        if not isinstance(order, list) or not order:
            continue
        v = db.get_vehicle(vid)
        if not v:
            c["missing"] += 1
            continue
        if v.get("photo_order") and not force:
            if (v.get("photo_order_src") or "") == "auto":
                c["overwrote_auto"] += 1
            else:
                c["skipped"] += 1
                continue
        db.update_fields(vid, photo_order=order, photo_order_src="vision")
        c["applied"] += 1
    return c


def main() -> int:
    force = "--force" in sys.argv
    patch_path = _resolve_patch()
    if not patch_path.exists():
        print(f"패치 파일이 없습니다: {patch_path}", file=sys.stderr)
        return 1
    patch = json.loads(patch_path.read_text(encoding="utf-8"))
    c = apply_patch(patch, force=force)
    print(f"적용 {c['applied']}(자동정렬 덮어씀 {c['overwrote_auto']}) · 스킵(비전 순서 보존) {c['skipped']} "
          f"· VM에 없는 물건 {c['missing']} (총 패치 {len(patch)}건, force={force})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
