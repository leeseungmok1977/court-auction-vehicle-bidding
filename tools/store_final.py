# -*- coding: utf-8 -*-
"""스토어 최종 산출 파이프라인 — 촬영 → 대조 → 오버레이(B-1) → `final/` 검사를 **한 명령**으로 잇는다.

    python tools/store_final.py                 # (a) 촬영 --all → (b) --audit → (c) B-1 8장 → (d)(e)(f)
    python tools/store_final.py --dry-run       # (a) 를 건너뛰고 지금 screenshots/store/ 의 8장으로 (b)~(f)
    python tools/store_final.py --hero-detail /vehicle/A --hero-report /vehicle/B
                                                # 촬영 대상 덮어쓰기(기본은 capture_store_shots.SUBMIT_TARGETS)

## 왜 이 파일이 생겼나

`docs/STORE_LISTING.md` §재촬영 절차 가 정한 단계(촬영 `--all` → `--audit` → 오버레이 → 바뀐 장만
오너에게)를 잇는 도구가 없었다. `tools/capture_store_shots.py`(촬영·감사)와 `tools/store_overlay.py`(띠)가
따로 있고, **캡션·기준월·대상 물건이 사람 손에 달려 있었다.** 손으로 적는 것은 다음 재촬영 때 낡는다 —
`store_overlay.py --basis` 기본값 `2026년 9월 기준` 이 바로 그것이다. 여기서는 기준월을 **손으로 적지 않는다**:
`screenshots/store/HEAD.json` 의 촬영 시각(가장 최근 장)에서 `YYYY년 M월 기준` 을 만들어 넘긴다.

## 순서와 종료코드

  (a) `capture_store_shots.py --all [--hero-detail …] [--hero-report …]` 를 서브프로세스로 돈다.
      **`--dry-run` 이면 건너뛴다** — 배포 전에는 외부 요청을 보내지 않는다(C.4). 실패(rc≠0)면 중단.
  (b) `capture_store_shots.py --audit` — 8장 md5·규격·기준 커밋 대조. rc 1 이면 중단(일부만 보는 대조는 대조가 아니다).
  (c) `store_overlay.main()` 으로 8장 B-1(띠 250 · 캡션 아래 가운데 기준월) → `screenshots/store/final/NN_name__B1.png`.
      오버레이가 스스로 내는 rc(캡션이 카드보다 넓음·md5 중복)도 그대로 받는다.
  (d) `final/HEAD.json` — 장별 `{slide, source, source_md5, source_commit, source_at, final_md5, size, alt_text}`.
      `source_*` 는 촬영 도구의 `HEAD.json` 에서 온다(PANEL-45: 한 줄 HEAD 로는 못 적는 것이 있다).
      원본의 실제 md5 가 그 기록과 다르면 **어느 커밋에서 나온 장인지 모르는 것**이라 위반이다.
  (e) `final/ALT_TEXT.txt` — 제출 순서대로 8줄. `docs/STORE_LISTING.md` "제출할 8장" 표의 캡션을 **문서에서 읽어**
      그대로 쓴다(대시 포함 확정본 — 그림에서는 06 의 대시를 줄바꿈이 대신하지만 alt text 는 확정본 그대로).
      Play 의 alt text 상한 140자를 줄마다 검사한다. 표와 `store_overlay.CAPTIONS` 가 갈리면 위반이다
      (그림의 캡션과 스크린리더가 읽는 캡션이 달라지는 것이다).
  (f) `final/` 8장 규격 1080×1920·RGB(알파 없음)·md5 전부 상이 검사. **하나라도 걸리면 종료코드 1 과 위반 목록.**

## 원칙

  · 원본 `screenshots/store/NN_*.png` 은 절대 덮어쓰지 않는다. 출력은 `final/` 아래에만 쓴다.
  · 임포트 부작용이 없다(stdout 재설정은 `main()` 안에서만). 테스트가 함수를 직접 부른다.
  · 검사에 걸리면 **조용히 넘어가지 않는다** — 위반 목록을 찍고 1 을 돌려준다. 잘못된 자산이
    조용히 제출되는 것이 최악이다(4·5번이 같은 파일이었던 2026-09-23 사고).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
CAPTURE = TOOLS / "capture_store_shots.py"
SRC_DIR = ROOT / "screenshots" / "store"
FINAL_DIR = SRC_DIR / "final"
LISTING = ROOT / "docs" / "STORE_LISTING.md"
MANIFEST_NAME = "HEAD.json"         # 촬영 도구가 장별 {commit, at, md5, size} 를 적는 파일(capture_store_shots.MANIFEST)
ALT_TEXT_NAME = "ALT_TEXT.txt"
FINAL_MANIFEST_NAME = "HEAD.json"

CANVAS = (1080, 1920)               # Play 휴대전화 세로 스크린샷 규격(원본·최종 동일)
ALT_TEXT_MAX = 140                  # Play: "Include alt text with each screenshot … 140 characters or less"
LISTING_HEADING = "### 제출할 8장"   # docs/STORE_LISTING.md 의 표 제목(앵커 문자열 — 줄 번호를 쓰지 않는다)
VARIANT = "B1"                      # 오너 확정(2026-09-24 "모두 진행해"): B-1, 띠 250, 기준월은 캡션 아래 가운데
BAND_H = 250

# `tools/` 는 패키지가 아니다 — 오버레이는 상수·함수뿐이라(부작용 없음) 경로로 끌어온다.
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import store_overlay  # noqa: E402


def md5(p: pathlib.Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              cwd=str(ROOT), check=True).stdout.strip()
    except Exception as e:                                   # noqa: BLE001
        return f"unknown ({e})"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ──────────────────────────────────────────────────────────────────────────
# (e) 캡션 — 문서에서 읽는다. 여기 적어 두면 표가 바뀔 때 조용히 갈린다.
# ──────────────────────────────────────────────────────────────────────────
_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*`([^`]+\.png)`\s*\|\s*(.+?)\s*\|\s*$")


def listing_captions(text: str | None = None) -> list[tuple[int, str, str]]:
    """`docs/STORE_LISTING.md` "제출할 8장" 표를 읽어 `(순서, 파일, 캡션)` 을 표 순서대로 돌려준다.

    표 제목(`LISTING_HEADING`)을 찾고 그 아래 첫 표의 행만 읽는다. 표가 끝나면(빈 줄·비표 줄) 멈춘다.
    8행이 아니거나 순서가 1..8 이 아니면 SystemExit — 문서가 깨진 채로 alt text 를 만들지 않는다.
    """
    if text is None:
        text = LISTING.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.strip().startswith(LISTING_HEADING)), None)
    if start is None:
        raise SystemExit(f"{LISTING.name} 에 '{LISTING_HEADING}' 제목이 없다 — 캡션 원천을 찾을 수 없다")
    rows: list[tuple[int, str, str]] = []
    in_table = False
    for ln in lines[start + 1:]:
        s = ln.strip()
        if s.startswith("|"):
            in_table = True
            m = _ROW.match(s)
            if m:
                rows.append((int(m.group(1)), m.group(2), m.group(3)))
            continue
        if in_table:
            break
    if [r[0] for r in rows] != list(range(1, 9)):
        raise SystemExit(f"'{LISTING_HEADING}' 표가 1..8 순서의 8행이 아니다: {[r[0] for r in rows]}")
    return rows


def check_captions_against_overlay(rows) -> list[str]:
    """표(alt text 원천)와 `store_overlay.CAPTIONS`(그림에 그리는 캡션)가 같은가. 갈리면 위반 목록."""
    bad = []
    stems = [pathlib.Path(f).stem for _, f, _ in rows]
    if stems != list(store_overlay.CAPTIONS):
        bad.append(f"표의 순서/파일 {stems} 가 store_overlay.CAPTIONS 순서 {list(store_overlay.CAPTIONS)} 와 다르다")
    for _, f, cap in rows:
        stem = pathlib.Path(f).stem
        drawn = store_overlay.CAPTIONS.get(stem)
        if drawn != cap:
            bad.append(f"{f}: 표 캡션 {cap!r} ≠ 그림 캡션 {drawn!r} — 스크린리더와 그림이 다른 말을 한다")
    return bad


def write_alt_text(out: pathlib.Path, rows) -> list[str]:
    """제출 순서대로 8줄, LF, utf-8(BOM 없음). 140자 초과 줄은 위반으로 돌려준다(파일은 그래도 쓴다 — 보고용)."""
    bad = [f"{f}: alt text {len(cap)}자 > {ALT_TEXT_MAX}" for _, f, cap in rows if len(cap) > ALT_TEXT_MAX]
    body = "\n".join(cap for _, _, cap in rows) + "\n"
    (out / ALT_TEXT_NAME).write_bytes(body.encode("utf-8"))
    return bad


# ──────────────────────────────────────────────────────────────────────────
# 기준월 — 손으로 적지 않는다. 촬영 시각(가장 최근 장)에서 만든다.
# ──────────────────────────────────────────────────────────────────────────
def read_manifest(src: pathlib.Path) -> dict:
    p = src / MANIFEST_NAME
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                        # noqa: BLE001
        return {}


def _parse_at(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        t = datetime.fromisoformat(s)
    except ValueError:
        return None
    return t if t.tzinfo else t.astimezone()   # 시간대 없는 옛 기록은 로컬로 본다(같은 종류끼리 비교)


def basis_from_manifest(man: dict, names) -> tuple[str, datetime, list[str]]:
    """`(기준월 문구, 가장 최근 촬영 시각, 경고 목록)`. 촬영 월이 갈리면 경고하고 **가장 최근 월**을 쓴다.

    한 장이라도 촬영 시각이 없으면 SystemExit — 기준월을 지어낼 수 없다.
    """
    ats: dict[str, datetime] = {}
    missing = []
    for n in names:
        t = _parse_at((man.get(n) or {}).get("at"))
        if t is None:
            missing.append(n)
        else:
            ats[n] = t
    if missing:
        raise SystemExit(f"촬영 시각이 없는 장 {missing} — {MANIFEST_NAME} 없이 기준월을 만들 수 없다(손으로 적지 않는다)")
    latest_name, latest = max(ats.items(), key=lambda kv: kv[1])
    months = sorted({(t.year, t.month) for t in ats.values()})
    warnings = []
    if len(months) > 1:
        warnings.append(f"8장의 촬영 월이 갈린다 {['%d-%02d' % m for m in months]} — 가장 최근 월 "
                        f"{latest.year}-{latest.month:02d}({latest_name}) 을 쓴다. 한 회차에 다시 찍는 것이 맞다")
    return f"{latest.year}년 {latest.month}월 기준", latest, warnings


# ──────────────────────────────────────────────────────────────────────────
# (a)(b) 촬영·대조 — 서브프로세스. 촬영 도구는 임포트만 해도 stdout 을 감싸고 playwright 를 끌어온다.
# ──────────────────────────────────────────────────────────────────────────
def _run_capture_tool(args: list[str]) -> int:
    cmd = [sys.executable, str(CAPTURE), *args]
    print(f"$ {' '.join(cmd[1:])}")
    sys.stdout.flush()      # 자식이 먼저 찍으면 로그 순서가 거짓말을 한다(대조 결과가 명령보다 위에 나온다)
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


def run_capture(hero_detail: str | None, hero_report: str | None) -> int:
    """(a) `--all`. 대상은 인자로 넘긴 것만 덧붙인다 — 없으면 촬영 도구의 `SUBMIT_TARGETS` 가 정한다.
    **외부 요청이 발생한다**(C.4 지연은 촬영 도구가 지킨다)."""
    args = ["--all"]
    if hero_detail:
        args += ["--hero-detail", hero_detail]
    if hero_report:
        args += ["--hero-report", hero_report]
    return _run_capture_tool(args)


def run_audit() -> int:
    """(b) `--audit` — 외부 요청 없음(디스크의 8장만 본다)."""
    return _run_capture_tool(["--audit"])


# ──────────────────────────────────────────────────────────────────────────
# (c) 오버레이 — store_overlay.main() 을 직접 부른다(같은 프로세스, 부작용 없음).
# ──────────────────────────────────────────────────────────────────────────
def run_overlay(src: pathlib.Path, out: pathlib.Path, basis: str, band_h: int = BAND_H) -> int:
    argv = ["--src", str(src), "--out", str(out), "--variants", VARIANT,
            "--band-h", str(band_h), "--basis", basis, "--no-thumbs"]
    print(f"$ store_overlay {' '.join(argv)}")
    return int(store_overlay.main(argv) or 0)


def final_name(stem: str) -> str:
    return f"{stem}__{VARIANT}.png"


# ──────────────────────────────────────────────────────────────────────────
# (d)(f) 장별 기준 커밋 + 규격·중복 검사
# ──────────────────────────────────────────────────────────────────────────
def validate_finals(out: pathlib.Path, src: pathlib.Path, rows, man: dict) -> tuple[list[str], dict]:
    """`final/` 8장을 검사하고 장별 기록을 만든다. 반환 `(위반 목록, 장별 기록)`.

    검사: 원본 있음 · 원본 md5 = HEAD.json 기록(기준 커밋을 믿을 수 있는가) · 최종 파일 있음 ·
    규격 1080×1920 · RGB(알파 없음, Play 24-bit) · 최종 8장 + 원본 8장 md5 전부 상이.
    """
    from PIL import Image
    bad: list[str] = []
    shots: dict[str, dict] = {}
    seen: dict[str, list[str]] = {}
    for slide, fname, cap in rows:
        stem = pathlib.Path(fname).stem
        sp = src / fname
        fp = out / final_name(stem)
        rec: dict = {"slide": slide, "source": fname, "alt_text": cap}
        if not sp.exists():
            bad.append(f"{fname}: 원본이 없다")
        else:
            s_md5 = md5(sp)
            m = man.get(fname) or {}
            rec.update(source_md5=s_md5, source_commit=m.get("commit"), source_at=m.get("at"))
            seen.setdefault(s_md5, []).append(fname)
            if not m:
                bad.append(f"{fname}: {MANIFEST_NAME} 에 기준 커밋 기록이 없다(PANEL-45)")
            elif m.get("md5") != s_md5:
                bad.append(f"{fname}: 원본 md5 {s_md5[:12]}… ≠ {MANIFEST_NAME} 기록 {str(m.get('md5'))[:12]}… "
                           f"— 도구 밖에서 바뀐 파일이라 기준 커밋을 믿을 수 없다")
        if not fp.exists():
            bad.append(f"{fp.name}: 최종 파일이 없다")
            shots[fp.name] = rec
            continue
        f_md5 = md5(fp)
        with Image.open(fp) as im:
            size, mode = im.size, im.mode
        rec.update(final_md5=f_md5, size=f"{size[0]}x{size[1]}", mode=mode)
        seen.setdefault(f_md5, []).append(fp.name)
        if size != CANVAS:
            bad.append(f"{fp.name}: 규격 {size[0]}x{size[1]} ≠ {CANVAS[0]}x{CANVAS[1]}")
        if mode != "RGB":
            bad.append(f"{fp.name}: 모드 {mode} — Play 는 24-bit PNG(알파 없음)")
        shots[fp.name] = rec
    for h, names in seen.items():
        if len(names) > 1:
            bad.append(f"md5 {h[:12]}… 가 같은 파일: {', '.join(names)} — 같은 그림이 두 번 올라간다")
    return bad, shots


def write_final_manifest(out: pathlib.Path, shots: dict, meta: dict) -> None:
    doc = {"_meta": meta, "shots": shots}
    (out / FINAL_MANIFEST_NAME).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")


def _clear_previous(out: pathlib.Path, rows) -> None:
    """지난 회차의 산출을 지운다 — 실패한 회차가 옛 장과 새 장을 섞어 두면 그게 제출된다."""
    for _, fname, _ in rows:
        (out / final_name(pathlib.Path(fname).stem)).unlink(missing_ok=True)
    for n in (FINAL_MANIFEST_NAME, ALT_TEXT_NAME, "metrics.json"):
        (out / n).unlink(missing_ok=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="스토어 최종 산출 파이프라인(촬영→대조→B-1 오버레이→final/ 검사)")
    ap.add_argument("--dry-run", action="store_true",
                    help="촬영(--all)을 건너뛰고 지금 screenshots/store/ 의 8장으로 나머지를 다 한다(외부 요청 없음)")
    ap.add_argument("--hero-detail", metavar="HREF", default=None, help="4·5번 대상 덮어쓰기(촬영 도구에 그대로 전달)")
    ap.add_argument("--hero-report", metavar="HREF", default=None, help="6·7번 대상 덮어쓰기(촬영 도구에 그대로 전달)")
    ap.add_argument("--src", type=pathlib.Path, default=SRC_DIR,
                    help="원본 8장 디렉터리(기본 screenshots/store). ⚠ (b) 대조는 촬영 도구가 자기 디렉터리"
                         "(screenshots/store)만 보므로 --src 를 다른 곳으로 돌려도 대조 대상은 바뀌지 않는다"
                         " — 테스트가 run_audit 를 막고 합성 원본을 쓰는 이유")
    ap.add_argument("--out", type=pathlib.Path, default=FINAL_DIR, help="최종 산출 디렉터리(기본 screenshots/store/final)")
    ap.add_argument("--band-h", type=int, default=BAND_H, help="띠 높이(px). 오너 확정 250")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    pipeline_commit = git_head()
    print(f"HEAD {pipeline_commit} · {'DRY-RUN(촬영 생략)' if a.dry_run else '촬영 포함'} · 원본 {a.src} → {a.out}")

    # 캡션 원천은 문서다. 표가 깨졌거나 그림 캡션과 갈리면 촬영조차 시작하지 않는다.
    rows = listing_captions()
    violations: list[str] = check_captions_against_overlay(rows)
    if violations:
        _report(violations)
        return 1

    # (a) 촬영 — dry-run 이면 건너뛴다(외부 요청 없음).
    if not a.dry_run:
        rc = run_capture(a.hero_detail, a.hero_report)
        if rc != 0:
            print(f"★ 촬영 실패(rc={rc}) — 중단. 해당 장은 이전 판 그대로다")
            return 1
    else:
        print("※ --dry-run: 촬영을 건너뛴다 — 지금 디스크의 8장을 쓴다")

    # (b) 대조 — 종료코드 1 이면 중단.
    rc = run_audit()
    if rc != 0:
        print(f"★ 대조 실패(rc={rc}) — 중단. 일부만 보는 대조는 대조가 아니다")
        return 1

    # 기준월 — HEAD.json 의 촬영 시각에서. 손으로 적지 않는다.
    man = read_manifest(a.src)
    names = [f for _, f, _ in rows]
    basis, latest_at, warnings = basis_from_manifest(man, names)
    for w in warnings:
        print(f"※ 경고: {w}")
    print(f"기준월 {basis!r} ← 가장 최근 촬영 {latest_at.isoformat(timespec='seconds')}")

    # (c) 오버레이 → final/
    a.out.mkdir(parents=True, exist_ok=True)
    _clear_previous(a.out, rows)
    rc = run_overlay(a.src, a.out, basis, a.band_h)
    if rc != 0:
        violations.append(f"store_overlay 가 rc={rc} 를 냈다(캡션이 카드보다 넓거나 md5 중복)")

    # (d)(f) 장별 기록 + 검사
    bad, shots = validate_finals(a.out, a.src, rows, man)
    violations += bad
    # (e) alt text
    violations += write_alt_text(a.out, rows)

    meta = {
        "pipeline_commit": pipeline_commit,
        "generated_at": _now_iso(),
        "dry_run": a.dry_run,
        "variant": VARIANT,
        "band_h": a.band_h,
        "basis": basis,
        "basis_from": latest_at.isoformat(timespec="seconds"),
        "basis_warnings": warnings,
        "alt_text_file": ALT_TEXT_NAME,
        "note": ("HEAD(한 줄)은 오버레이를 만든 커밋이다. 원본이 어느 커밋에서 찍혔는지는 장별 source_commit 을 보라 "
                 "— 여덟 장이 한 커밋에서 나오지 않을 수 있다(PANEL-45)"),
        "violations": violations,
    }
    write_final_manifest(a.out, shots, meta)

    print("\n=== final/ 8장 (제출 순서) ===")
    print("| # | 파일 | 규격 | md5 | 원본 md5 | 원본 커밋 | 촬영 시각 |")
    print("|---|---|---|---|---|---|---|")
    for name, r in shots.items():
        print(f"| {r['slide']} | `{name}` | {r.get('size', '-')} | `{r.get('final_md5', '-')}` "
              f"| `{str(r.get('source_md5', '-'))[:12]}…` | `{str(r.get('source_commit') or '-')[:7]}` | {r.get('source_at', '-')} |")
    print(f"\nALT_TEXT.txt {len(rows)}줄 · 최대 {max(len(c) for _, _, c in rows)}자(상한 {ALT_TEXT_MAX})"
          f" · 기준월 {basis!r} · 산출 {a.out}")
    _report(violations)
    return 1 if violations else 0


def _report(violations: list[str]) -> None:
    if violations:
        print(f"\n★ 위반 {len(violations)}건 — 제출하지 않는다:")
        for v in violations:
            print(f"  · {v}")
    else:
        print("\n합격  final/ 8장 규격·모드·md5 상이 · alt text 8줄 ≤ 140자 · 기준월 자동")


if __name__ == "__main__":
    raise SystemExit(main())
