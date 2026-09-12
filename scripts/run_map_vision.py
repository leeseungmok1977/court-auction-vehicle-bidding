"""비전 LLM으로 지도의 인쇄된 보관장소 주소를 읽는 배치 — **로컬 PC에서 실행**.

운영 서버(t3.micro, RAM 911MB)에서 돌리지 않는다:
  · API 키를 서버에 두지 않기 위해(docs/.env 는 gitignore라 서버에 없다)
  · 앞서 OCR 배치를 서버에서 3.8시간 돌렸다가 홈 응답이 0.68초 → 1.4초가 됐다

끝나면 결과를 JSON으로 뽑는다. 운영에는 그 파일만 옮겨 apply_storage_patch 로 반영한다.

사용:
  python scripts/run_map_vision.py            # 전량
  python scripts/run_map_vision.py 50         # 50건만
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from web import db, service  # noqa: E402

PATCH = ROOT / "data" / "storage_patch.json"


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100000
    db.init_db()
    targets = [v for v in db.list_vehicles(hide_incomplete=False)
               if not (v.get("storage_addr") or "").strip() and (v.get("map_photos") or [])]
    n = min(limit, len(targets))
    print(f"대상 {len(targets)}건 중 {n}건 실행 · 6초 간격 · 예상 {n * 9 / 3600:.1f}시간",
          flush=True)

    t0 = time.time()
    r = service.backfill_map_vision(limit=n, delay=6.0)
    dt = time.time() - t0

    cost = r["tokens_in"] / 1e6 * 0.15 + r["tokens_out"] / 1e6 * 0.60
    print(f"\n완료 {dt / 60:.0f}분 · 시도 {r['tried']} · 채택 {r['found']} · "
          f"거부 {r['rejected']} · 비용 ${cost:.2f}", flush=True)
    if r.get("aborted"):
        print(f"⚠ 중단: {r['aborted']}", flush=True)
    for why, cnt in sorted(r["why"].items(), key=lambda x: -x[1]):
        print(f"   {cnt:>4}건  {why}", flush=True)

    got = service.export_storage_patch(str(PATCH))
    print(f"\n결과 {got}건 → {PATCH}", flush=True)
    print("운영 반영:  .venv/bin/python -c \"import sys;sys.path.insert(0,'.');"
          "from web import db,service;db.init_db();"
          "print(service.apply_storage_patch('data/storage_patch.json'))\"", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
