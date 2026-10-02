"""운영 관리 명령(1회성·점검용) — 외부 요청 여부를 명령마다 밝힌다.

    python -m web.maint floor-refresh-plan [기간일수]   최저가 지연 재조회 계획만 출력(요청 0 · 쓰기 0)
    python -m web.maint rejudge-floor [기간일수]        최저가가 바뀐 물건 재판정(요청 0 · DB 쓰기)
    python -m web.maint regrade-accidents [--ids A,B] [--apply]
                                                        사고이력 파서 수정을 저장값에 반영(요청 0).
                                                        기본은 **미리보기**(쓰기 0) — 행별 전후(등급·감가·상한가·
                                                        입찰 상한선·판정)만 출력한다. --apply 일 때만 같은 행을 쓴다.
                                                        대상: 요항 파일이 있고, 직전 파서와 지금 파서의 보험이력이
                                                        다른 행만(service.regrade_accidents). --dry-run 은 기본과 같다.
    python -m web.maint reprice-accidents [--ids A,B] [--apply]
                                                        사고 근거 **규칙** 변경(REC-15)을 저장 산정에 반영(요청 0 ·
                                                        파일 I/O 0). 등급·보험이력은 그대로 두고 산정표의 사고감가율·
                                                        사고표기가 지금 규칙과 다른 행만 사고 감가 한 항을 다시 계산
                                                        → 상한가·판정(service.reprice_accidents). 기본은 **미리보기**
                                                        (쓰기 0). --apply 는 --ids 와 함께일 때만 쓴다. 매각이 끝난 행·
                                                        침수·전손 보류 행은 건드리지 않는다. --dry-run 은 기본과 같다.
    python -m web.maint floor-refresh [기간일수]        최저가 지연 재조회 실행 — config min_refresh_enabled 가
                                                        true 일 때만 법원에 요청한다(false 면 계획만 출력)
    python -m web.maint redetail-key [--ids A,B] [--apply]
                                                        상세 조회 키 정정(AUD-18) 뒤 **예전 키(item_no)로 받은 상세**가
                                                        남은 입찰예정 행을 다음 매일 갱신이 올바른 키(매각물건 번호)로
                                                        다시 받게 예약(요청 0 · 파일 I/O 0 — 상태만 '미분석').
                                                        기본은 **미리보기**(쓰기 0). --apply 는 --ids 와 함께일 때만 쓴다.
                                                        지난 기일·끝난 매각·키가 같은 행은 건드리지 않는다. 멱등.

REC-1(2026-09-29). 배포 뒤 순서: ⓪ regrade-accidents 로 바뀔 행을 보고(쓰기 0) → ① 오너 확인 뒤
regrade-accidents --apply(파서 수정 반영) ② rejudge-floor ③ floor-refresh-plan 으로
대상·예상 요청 수를 오너에게 보고 → 승인 후 config 를 켠다(C.4-6). ②는 다음 날 매일 갱신도 돈다.
REC-15(2026-10-01). 사고 근거 술어(service.accident_evidence) 배포 뒤 바로: ⓪ reprice-accidents(미리보기)로 대상·
skipped 를 보고 → ① 오너 확인 뒤 reprice-accidents --ids <대상 id> --apply. 배포와 ① 사이에는 화면 라벨·칩·입찰 상한선은
새 규칙인데 저장 판정('입찰 검토 가능')·상한가·산정표 표기는 옛 값이라 '지금 입찰 추천' 칸에 남는다 — 간격을 두지 않는다.
AUD-18(2026-10-02). 상세 조회 키 정정 배포 뒤 06:30 매일 갱신 **전에**: ⓪ redetail-key(미리보기)로 대상·skipped 를 보고
→ ① redetail-key --ids <대상 id> --apply. 다음 매일 갱신의 분석 단계가 그 행을 기존 상한·지연 안에서 다시 받는다.
⚠ 예전의 `regrade-accidents --force`(범위 없는 전체 재등급)는 없앴다 — 요항 파일이 없는 행을 매각물건명세만으로
  다시 매겨 무사고로 내렸다(qa 2026-09-29 F4). 2026-09-21 류의 전체 재산정이 필요하면
  service.backfill_accident_grades(force=True) 를 **미리보기부터** 따로 검토한다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web import db, service  # noqa: E402


def _within(argv, i=2, default=30) -> int:
    try:
        return int(argv[i]) if len(argv) > i and not argv[i].startswith("--") else default
    except ValueError:
        return default


def _ids(argv) -> "list | None":
    """--ids A,B 또는 --ids=A,B → ['A', 'B']. 없으면 None, 값이 비었으면 []."""
    for i, a in enumerate(argv):
        if a == "--ids":
            raw = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else ""
        elif a.startswith("--ids="):
            raw = a.split("=", 1)[1]
        else:
            continue
        return [x.strip() for x in raw.split(",") if x.strip()]
    return None


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    cmd = argv[1] if len(argv) > 1 else ""
    db.init_db()                      # floor_checked_at 등 새 열 마이그레이션(ALTER 가드)
    if cmd == "floor-refresh-plan":
        _print(service.refresh_lagged_floors(within_days=_within(argv), dry_run=True))
        return 0
    if cmd == "rejudge-floor":
        _print(service.rejudge_floor_changes(within_days=_within(argv)))
        return 0
    if cmd == "regrade-accidents":
        if "--force" in argv:
            print("regrade-accidents --force 는 없앴다 — 범위 없는 재등급은 요항 파일이 없는 행을 무사고로 내린다"
                  "(qa 2026-09-29 F4). 대상은 --ids 로 좁힌다.")
            return 2
        if "--apply" in argv and "--dry-run" in argv:
            print("--apply 와 --dry-run 을 함께 쓸 수 없다 — 쓸지 말지를 하나로 정한다")
            return 2
        ids = _ids(argv)
        if ids == []:
            print("--ids 뒤에 물건 id 를 쉼표로 적는다(예: --ids 2026타경30118_1,2026타경30178_1)")
            return 2
        _print(service.regrade_accidents(ids=ids, apply="--apply" in argv))
        return 0
    if cmd == "reprice-accidents":
        if "--apply" in argv and "--dry-run" in argv:
            print("--apply 와 --dry-run 을 함께 쓸 수 없다 — 쓸지 말지를 하나로 정한다")
            return 2
        ids = _ids(argv)
        if ids == []:
            print("--ids 뒤에 물건 id 를 쉼표로 적는다(예: --ids 2026타경50904_1,2026타경52708_1)")
            return 2
        if "--apply" in argv and ids is None:
            # 쓰기는 사람이 미리보기에서 고른 행에만 — 범위 없는 일괄 쓰기를 열어 두지 않는다(regrade --force 의 교훈).
            print("--apply 는 --ids 와 함께 쓴다 — 먼저 미리보기(인자 없이)로 대상을 보고, 그 id 를 --ids 로 넘긴다")
            return 2
        _print(service.reprice_accidents(ids=ids, apply="--apply" in argv))
        return 0
    if cmd == "redetail-key":
        if "--apply" in argv and "--dry-run" in argv:
            print("--apply 와 --dry-run 을 함께 쓸 수 없다 — 쓸지 말지를 하나로 정한다")
            return 2
        ids = _ids(argv)
        if ids == []:
            print("--ids 뒤에 물건 id 를 쉼표로 적는다(예: --ids 2025타경53697_4)")
            return 2
        if "--apply" in argv and ids is None:
            # 쓰기는 사람이 미리보기에서 고른 행에만 — reprice-accidents 와 같은 규칙.
            print("--apply 는 --ids 와 함께 쓴다 — 먼저 미리보기(인자 없이)로 대상을 보고, 그 id 를 --ids 로 넘긴다")
            return 2
        _print(service.redetail_key(ids=ids, apply="--apply" in argv))
        return 0
    if cmd == "floor-refresh":
        res = service.refresh_lagged_floors(within_days=_within(argv))
        res["rejudge_after"] = service.rejudge_floor_changes(within_days=_within(argv))
        _print(res)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
