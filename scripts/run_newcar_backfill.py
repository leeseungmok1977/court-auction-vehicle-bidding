"""출시가(보배드림) 백필 1회 실행 — 일일 갱신 06:30을 기다리지 않고 지금 채운다.

당시 출시가는 과거 값이라 변하지 않으므로 이 작업은 본질적으로 **1회성 백필**이다.
평소에는 일일 갱신 ②-2가 알아서 처리하고, 이 스크립트는 백필을 앞당길 때만 쓴다.

C.4 준수:
  · 실행 전 **대상·건수·예상 요청 수**를 출력하고, `--yes` 없이는 실행하지 않는다(C.4-6).
  · 요청 간 5초 지연·물건당 45요청·403/429 즉시 중단은 수집기 쪽에 그대로 있다(C.4-2/5).
  · `--limit`으로 런당 하드캡을 반드시 건다(C.4-1). 기본값은 서비스 상한.

사용:
    python scripts/run_newcar_backfill.py                 # 계획만 출력(안전)
    python scripts/run_newcar_backfill.py --yes           # 기본 상한으로 실행
    python scripts/run_newcar_backfill.py --yes --limit 600
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web import db, service  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="실제 실행(없으면 계획만 출력)")
    ap.add_argument("--limit", type=int, default=service.NEWCAR_DAILY_CAP, help="런당 요청 하드캡")
    ap.add_argument("--within-days", type=int, default=30, help="입찰예정 범위(일)")
    a = ap.parse_args()

    cutoff = (datetime.date.today()
              - datetime.timedelta(days=service.NEWCAR_RECHECK_DAYS)).isoformat()
    pool = service.newcar_pool(db.list_vehicles(upcoming_days=a.within_days), cutoff)
    dom = [v for v in pool if service.newcar_is_domestic(v)]
    rec = [v for v in pool if v.get("judgment") == "입찰 검토 가능"]

    print("=" * 62)
    print("출시가 백필 계획 (C.4-6 사전 보고)")
    print(f"  대상        : 입찰예정 {a.within_days}일 이내, 수집 대기 {len(pool)}건")
    print(f"                (추천 {len(rec)} · 국산 {len(dom)} · 수입 {len(pool) - len(dom)})")
    print(f"  요청 하드캡 : {a.limit}회")
    print(f"  예상 소요   : 최대 약 {a.limit * 5 // 60}분 (요청 간 5초 고정)")
    print(f"  중단 조건   : 403/429 즉시 중단 · 물건당 {service.NEWCAR_MAX_REQ_PER_VEHICLE}요청 상한")
    print(f"  연식 하한   : {service.NEWCAR_MIN_YEAR}년 이상만")
    print("=" * 62)
    if not a.yes:
        print("계획만 출력했다. 실제로 실행하려면 --yes 를 붙일 것.")
        return 0

    t0 = time.time()
    print(f"[{datetime.datetime.now():%H:%M:%S}] 시작")
    out = service.newcar_collect(max_requests=a.limit, within_days=a.within_days)
    el = int(time.time() - t0)
    print(f"[{datetime.datetime.now():%H:%M:%S}] 종료 ({el // 60}분 {el % 60}초)")
    print(f"  시도 {out.get('vehicles', 0)}건 · 매칭 {out.get('matched', 0)}건 "
          f"· 실패 {out.get('unmatched', 0)}건 · 남은 대기 {out.get('remaining', 0)}건")
    print(f"  실제 요청 {out.get('requests', 0)}회 · 종료사유 {out.get('stopped') or '대기열 소진'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
