# -*- coding: utf-8 -*-
"""마크다운 표가 깨졌는지 센다. 문서를 커밋하기 전 게이트로 쓴다.

왜 도구로 굳히나 — 2026-09-23 에 이 검사를 **세 번 고쳐서야** 맞았다.

  1차: `①②③` 로 시작하는 **모든** 행에 5파이프를 요구했다.
       → 같은 문서의 **2열 표**(`| 문 | 결과 |`)를 깨진 것으로 잡았다.
  2차: 파이프를 그냥 셌다.
       → `scripts/photo_classify.py prep\\|apply` 의 **이스케이프된 파이프**를
         셀 구분자로 셌다. 마크다운에서 `\\|` 는 셀을 나누지 않는다.
  3차: 표마다 **머리글 행에서 기대 열수를 읽고**, `\\|` 를 빼고 센다. ← 이 파일

두 번의 거짓양성이 모두 **표가 아니라 검사기**의 잘못이었다. 매번 다시 유도하면
매번 같은 함정을 다시 밟는다.

★ 이 스크립트를 게이트로 쓸 때는 반드시 `&&` 로 건다:

    python tools/check_md_tables.py docs/backlog.md && git commit ...

  `set -e` 로 걸면 **막히지 않는다.** 실측(2026-09-23): 이 실행 환경에서 `set -e` 는
  실패한 명령 뒤의 줄을 그대로 실행한다. 그때 게이트가 붉은데 커밋·푸시가 나갔다.
  문은 '울리는지'가 아니라 '막는지'로 확인한다.

사용:
    python tools/check_md_tables.py [파일...]      # 기본: docs/*.md
종료코드 0 = 정합, 1 = 어긋난 행 있음(자리와 기대값을 찍는다).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _cells(line: str) -> int:
    """셀 구분자 개수. `\\|` 는 리터럴 파이프라 세지 않는다."""
    return line.replace(r"\|", "").count("|")


def _is_divider(line: str) -> bool:
    """`|---|:--:|` 같은 구분선인가."""
    body = line.replace("|", "").replace(" ", "")
    return bool(body) and set(body) <= set("-:")


def check_file(path: Path) -> list[str]:
    """어긋난 행의 설명을 돌려준다. 빈 리스트면 정합."""
    problems: list[str] = []
    header: int | None = None
    header_line = 0
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.startswith("|"):
            header = None          # 표가 끝났다 — 다음 표는 제 머리글을 기준으로 삼는다
            continue
        if _is_divider(line):
            continue
        n = _cells(line)
        if header is None:
            header, header_line = n, i
        elif n != header:
            problems.append(
                f"{path.as_posix()}:{i} 셀 구분자 {n}개 — "
                f"{header_line}행 머리글은 {header}개다"
                + ("  (리터럴 파이프라면 `\\|` 로 이스케이프할 것)" if n > header else "")
            )
    return problems


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv[1:]] or sorted((ROOT / "docs").glob("*.md"))
    targets = [t if t.is_absolute() else ROOT / t for t in targets]
    problems: list[str] = []
    for t in targets:
        if t.is_file():
            problems.extend(check_file(t))
    if problems:
        print(f"★ 표가 깨졌다 ({len(problems)}곳):")
        for p in problems:
            print("   " + p)
        return 1
    print(f"표 정합 — {len(targets)}개 파일 이상 없음")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main(sys.argv))
