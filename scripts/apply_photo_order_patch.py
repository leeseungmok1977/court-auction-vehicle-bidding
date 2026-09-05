# -*- coding: utf-8 -*-
"""photo_order 패치를 DB에 주입 (로컬에서 비전분류한 순서를 VM DB로 이관).

로컬에서 scripts/photo_classify.py apply 로 분류를 마친 뒤,
  python scripts/photo_classify.py export-patch   # data/_photo_work/photo_order_patch.json 생성
로 패치를 만들고, 이 파일을 VM으로 복사한 다음 VM에서:
  python scripts/apply_photo_order_patch.py            # 미분류(순서 없는) 물건만 채움(안전)
  python scripts/apply_photo_order_patch.py --force    # 기존 순서도 덮어씀

패치는 {vehicle_id: [파일명,...]} 형태. 사진 파일은 로컬=VM 동일(같은 대법원 원본)이므로
파일명 순서 리스트를 그대로 이관해도 유효하다. VM에 없는 물건은 건너뛴다.
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


PATCH = _resolve_patch()


def main() -> int:
    force = "--force" in sys.argv
    if not PATCH.exists():
        print(f"패치 파일이 없습니다: {PATCH}", file=sys.stderr)
        return 1
    db.init_db()  # photo_order 컬럼 보장
    patch = json.loads(PATCH.read_text(encoding="utf-8"))
    applied = skipped = missing = 0
    for vid, order in patch.items():
        if not isinstance(order, list) or not order:
            continue
        v = db.get_vehicle(vid)
        if not v:
            missing += 1
            continue
        if v.get("photo_order") and not force:
            skipped += 1
            continue
        db.update_fields(vid, photo_order=order)
        applied += 1
    print(f"적용 {applied} · 스킵(기존 순서 보존) {skipped} · VM에 없는 물건 {missing} "
          f"(총 패치 {len(patch)}건, force={force})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
