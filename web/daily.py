"""일일 갱신 CLI — Windows 작업 스케줄러 등록용.

    python -m web.daily [기간일수] [분석상한]
      기간일수: 매각기일 이내 (기본 30)
      분석상한: 국산차 시세 분석 최대 건수 (0=전체, 기본 0)

목록 수집 후 국산차 시세 분석까지 이어서 진행한다.
앱(run_web.py)이 꺼져 있어도 이 스크립트를 매일 실행하면 DB가 갱신된다.
run_daily.bat 을 작업 스케줄러에 등록하면 편하다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web import db, service  # noqa: E402


def main() -> None:
    within = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    db.init_db()
    print(f"[일일 갱신] 입찰예정(≤{within}일) 목록 수집 + 시세 분석 시작…")
    r = service.daily_update(within_days=within, analyze=True, analyze_limit=limit)
    print(f"[일일 갱신] 완료: 입찰예정 {r['stored']}건 · 시세 분석 {r['analyzed']}건 ({service._now()})")


if __name__ == "__main__":
    main()
