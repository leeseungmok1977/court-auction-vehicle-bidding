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

'미분류'는 photo_count>0 이고 photo_order IS NULL 인 물건 + 로컬 모델 자동 정렬(photo_order_src='auto',
src/parse/photo_autosort.py — 일일 갱신이 채움)된 물건. 비전 분류(src='vision')는 건드리지 않는다(증분).
apply 는 src='vision'으로 기록해 VM 패치 주입 시 auto를 덮어쓰게 한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.collect import encar  # noqa: E402
from src.parse.photo_montage import DATA_DIR, build_montage, list_photos  # noqa: E402
from web import db  # noqa: E402

WORK = DATA_DIR / "_photo_work"
MANIFEST = WORK / "manifest.json"
ARGS = WORK / "args.json"
RESULTS = WORK / "results.json"
PATCH = DATA_DIR / "photo_order_patch.json"   # data/ 최상위(VM scp 편의)


_NEEDS_VISION = "(photo_order IS NULL OR photo_order = '' OR photo_order_src = 'auto')"


def _unclassified(status: str | None, limit: int | None):
    """photo_count>0 이고 photo_order 가 비어있거나 자동 정렬(auto)만 된 물건."""
    db.init_db()
    conn = db.connect()
    sql = ("SELECT id, folder_key, model, status FROM vehicles "
           "WHERE COALESCE(photo_count,0) > 0 "
           f"AND {_NEEDS_VISION}")
    params: list = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY collected_at DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _truck_form_unknown(status: str | None, limit: int | None):
    """포터·봉고인데 **적재함 형식을 아직 모르는** 물건.

    법원 차명에 형식이 안 적힌 물건이 많다(2026-09-20 실측 23건 중 16건). 형식을 모르면
    카고와 탑차가 섞인 시세가 나오므로 조회 자체를 포기하고 있었고, 그래서 이 물건들은
    영원히 '동급 시세 없음'이었다. 사진에는 적재함이 그대로 찍혀 있으니 비전에 물어본다.

    이 선택자는 `_NEEDS_VISION` 과 **겹치지 않게 별도로** 둔다. 그쪽 조건(미분류 또는 auto)은
    이미 비전 분류가 끝난 물건을 제외하는데, 형식 미상 물건 대부분이 거기 해당해 재분류
    대상에서 빠진다(16건 중 14건). 그렇다고 조건을 풀면 사진 보유 물건 전체가 대상이 돼
    비전 요청이 수백 건 나가고 이미 맞는 정렬까지 흔든다 — 그래서 **대상을 좁혀서** 부른다.
    """
    db.init_db()
    conn = db.connect()
    sql = ("SELECT id, folder_key, model, status FROM vehicles "
           "WHERE COALESCE(photo_count,0) > 0 "
           "AND (truck_form IS NULL OR truck_form = '') "
           # 이미 끝난 물건(종결·낙찰·상세없음)은 제외한다. 시세를 새로 내봐야 쓸 데가 없고
           # 비전 요청만 태운다 — 로컬 실측 65건 중 17건이 여기 해당했다.
           "AND COALESCE(status,'') NOT IN ('종결','상세없음') "
           "AND COALESCE(auction_result,'') NOT IN ('낙찰','종결')")
    params: list = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY collected_at DESC"
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    # 차명으로 형식을 읽을 수 있으면 물어볼 필요가 없다 — 비전 요청을 아낀다.
    rows = [r for r in rows
            if encar.is_truck_model(r.get("model")) and not encar.truck_form(r.get("model"))]
    return rows[:int(limit)] if limit else rows


def cmd_prep(args) -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    # 이전 실행 잔여 몽타주 정리(인덱스 재사용 혼선 방지)
    for old in WORK.glob("*.png"):
        old.unlink()
    rows = _unclassified(args.status, args.limit)
    extra = 0
    if getattr(args, "truck_form", False):
        # 형식만 새로 묻는 물건을 **더한다**(대체가 아니다). 비전은 한 번에 순서와 형식을 함께
        # 답하므로, 미분류 배치가 대기 중인데 그걸 버리고 형식용으로 새로 돌릴 이유가 없다.
        seen = {r["id"] for r in rows}
        add = [r for r in _truck_form_unknown(args.status, None) if r["id"] not in seen]
        rows += add
        extra = len(add)
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
    what = f"미분류 {len(rows) - extra}건" + (f" + 형식 미상 화물차 {extra}건" if extra else "")
    print(f"대상 {what} 중 몽타주 {len(manifest)}건 생성 (사진없음/실패 {skipped}건).")
    print(f"  manifest: {MANIFEST}")
    print(f"  args    : {ARGS.read_text(encoding='utf-8')}")
    if manifest:
        print("다음: classify-photos-bulk 워크플로에 위 args를 넘겨 실행 → results.json 저장 후 apply.")
    return 0


def cmd_apply(args) -> int:
    if not RESULTS.exists():
        print(f"results.json 이 없습니다: {RESULTS}", file=sys.stderr)
        return 1
    # ⚠ 옛 결과를 새 배치에 적용하지 않는다. idx 는 배치마다 0001부터 다시 매겨지고 결과에는
    #   vid 가 없어 **idx 로만** 맞춘다 — 남아 있던 옛 results 를 새 manifest 에 적용하면
    #   엉뚱한 차량에 남의 사진 순서가 조용히 덮인다(2026-09-20 실측: 9일 지난 결과 90건의
    #   idx 0001~0023 이 그날 새 배치 23건과 완전히 겹쳐 있었다).
    if (MANIFEST.exists() and RESULTS.stat().st_mtime < MANIFEST.stat().st_mtime
            and not getattr(args, "force", False)):
        print("results.json 이 manifest 보다 오래됐습니다 — 이전 배치의 결과로 보입니다.\n"
              "  idx 는 배치마다 다시 매겨지므로 그대로 적용하면 다른 차량에 붙습니다.\n"
              f"  이번 배치를 다시 분류해 ingest 하거나, 확신하면 --force 로 실행하세요.\n"
              f"  results: {RESULTS}\n  manifest: {MANIFEST}", file=sys.stderr)
        return 1
    db.init_db()  # photo_order 등 컬럼 마이그레이션 보장
    mlist = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_idx = {m["idx"]: m for m in mlist}
    by_vid = {m["vid"]: m for m in mlist}
    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    applied, low, forms, unsure = 0, [], 0, 0
    for r in results:
        m = by_idx.get(str(r.get("idx"))) or by_vid.get(r.get("vid"))  # idx 우선, vid 폴백
        if not m:
            continue
        files = m["files"]
        order = [c for c in r.get("order", []) if isinstance(c, int) and 1 <= c <= len(files)]
        seen = set(order)
        order += [i for i in range(1, len(files) + 1) if i not in seen]  # 누락 셀 보충
        photo_order = [files[c - 1] for c in order]
        fields = {"photo_order": photo_order, "photo_order_src": "vision"}
        # 적재함 형식은 **답이 있을 때만** 쓴다. 비전이 생략했다는 건 사진으로 알 수 없다는 뜻이고,
        # 그때 추측해서 채우면 틀린 형식 → 틀린 시세가 된다(모르는 채로 두는 편이 낫다).
        form = (r.get("truck_form") or "").strip()
        if form and not r.get("confident", True):
            # 저확신 몽타주의 형식은 쓰지 않는다. 2026-09-20 실측에서 저확신 건은 대개
            # **한 몽타주에 여러 차량이 섞였거나**(계기판 4종·싼타페+포터+세단) 외관 컷이
            # 한 장뿐이었다 — 거기 보이는 적재함이 이 차의 것이라는 보장이 없다.
            # 순서는 틀려도 사진을 다시 보면 되지만, 틀린 형식은 곧 틀린 시세가 된다.
            unsure += 1
        elif form in encar.TRUCK_FORMS:
            fields["truck_form"] = form
            forms += 1
        elif form:
            print(f"  ! 알 수 없는 형식 값 무시: {m['vid']} {form!r}", file=sys.stderr)
        db.update_fields(m["vid"], **fields)
        applied += 1
        if not r.get("confident", True):
            low.append((m["vid"], m.get("model"), r.get("note", "")))
    print(f"적용 완료: {applied}건" + (f" (적재함 형식 {forms}건 확인)" if forms else "")
          + (f" · 저확신이라 형식 보류 {unsure}건" if unsure else ""))
    if low:
        print(f"검수 필요(저확신) {len(low)}건 — 대개 원본에 순수 측면/실내 컷이 없는 경우:")
        for vid, model, note in low:
            print(f"  - {vid} {model}: {note[:70]}")
    return 0


def cmd_status(args) -> int:
    """미분류 건수 확인(루틴 진입점). 'MICLASSIFIED=n' 도 출력해 파싱 편의 제공."""
    db.init_db()
    conn = db.connect()
    tot = conn.execute("SELECT COUNT(*) FROM vehicles WHERE COALESCE(photo_count,0)>0").fetchone()[0]
    unc = conn.execute(
        "SELECT COUNT(*) FROM vehicles WHERE COALESCE(photo_count,0)>0 "
        "AND (photo_order IS NULL OR photo_order='')").fetchone()[0]
    auto = conn.execute(
        "SELECT COUNT(*) FROM vehicles WHERE COALESCE(photo_count,0)>0 "
        "AND photo_order IS NOT NULL AND photo_order!='' AND photo_order_src='auto'").fetchone()[0]
    conn.close()
    print(f"사진보유 {tot} · 비전분류 {tot - unc - auto} · 자동정렬(검수 대기) {auto} · 미분류 {unc}")
    print(f"UNCLASSIFIED={unc + auto}")
    return 0


def cmd_ingest(args) -> int:
    """워크플로 출력(JSON)에서 results 배열을 뽑아 results.json 저장.
    래퍼 형태 {result:{results:[…]}} / {results:[…]} / [ … ] 모두 처리."""
    obj = json.loads(Path(args.path).read_text(encoding="utf-8"))
    if isinstance(obj, dict) and isinstance(obj.get("result"), dict):
        obj = obj["result"]
    results = obj["results"] if isinstance(obj, dict) and "results" in obj else obj
    if not isinstance(results, list):
        print("results 배열을 찾지 못했습니다.", file=sys.stderr)
        return 1
    RESULTS.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    print(f"results.json 저장: {len(results)}건")
    return 0


def cmd_export_patch(args) -> int:
    """이번 배치(manifest)에서 분류된 photo_order 를 VM 이관용 패치로 추출."""
    if not MANIFEST.exists():
        print(f"manifest 가 없습니다: {MANIFEST}", file=sys.stderr)
        return 1
    mlist = json.loads(MANIFEST.read_text(encoding="utf-8"))
    patch = {}
    for m in mlist:
        v = db.get_vehicle(m["vid"])
        if not v or not v.get("photo_order"):
            continue
        # 적재함 형식이 있으면 **순서와 함께** 나른다(구형 패치는 리스트, 새 패치는 dict — 양쪽 다 읽힌다).
        if v.get("truck_form"):
            patch[m["vid"]] = {"order": v["photo_order"], "truck_form": v["truck_form"]}
        else:
            patch[m["vid"]] = v["photo_order"]
    PATCH.write_text(json.dumps(patch, ensure_ascii=False), encoding="utf-8")
    print(f"패치 생성: {PATCH} ({len(patch)}건)")
    print("→ 이 파일을 VM으로 복사 후, VM에서 python scripts/apply_photo_order_patch.py 실행")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="차량 사진 비전 분류 파이프라인")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep", help="미분류 물건 몽타주 + args.json 생성")
    p.add_argument("--status", default=None, help="특정 status만 (예: 검토가능). 기본=전체 미분류")
    p.add_argument("--limit", type=int, default=None, help="최대 건수(부하 통제)")
    p.add_argument("--truck-form", action="store_true", dest="truck_form",
                   help="'포터·봉고인데 적재함 형식 미상' 물건을 대상에 **추가**한다"
                        " (이미 비전 분류가 끝난 물건도 포함 — 순서는 그대로 두고 형식만 새로 묻는다)")
    p.set_defaults(func=cmd_prep, truck_form=False)
    s = sub.add_parser("status", help="미분류 건수 확인(루틴 진입점)")
    s.set_defaults(func=cmd_status)
    a = sub.add_parser("apply", help="results.json → DB photo_order 반영")
    a.add_argument("--force", action="store_true",
                   help="results 가 manifest 보다 오래돼도 적용(위험: idx 는 배치마다 다시"
                        " 매겨지므로 다른 차량에 붙을 수 있다)")
    a.set_defaults(func=cmd_apply, force=False)
    ig = sub.add_parser("ingest", help="워크플로 출력 JSON → results.json 추출")
    ig.add_argument("path", help="워크플로 출력 파일 경로(task .output)")
    ig.set_defaults(func=cmd_ingest)
    e = sub.add_parser("export-patch", help="분류된 photo_order → VM 이관용 패치(json)")
    e.set_defaults(func=cmd_export_patch)
    ns = ap.parse_args()
    return ns.func(ns)


if __name__ == "__main__":
    raise SystemExit(main())
