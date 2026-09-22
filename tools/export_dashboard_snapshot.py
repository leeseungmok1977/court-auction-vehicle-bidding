# -*- coding: utf-8 -*-
"""에이전트 현황판을 **자체 완결 HTML 한 장**으로 굽는다 — 집 PC 밖에서 보기 위한 것.

    python tools/export_dashboard_snapshot.py            # 굽기만 한다(기본)
    python tools/export_dashboard_snapshot.py --print-url # 공개 주소만 찍는다

왜 이 방식인가 (2026-09-23 오너 요청: 서버는 집 PC, 보는 곳은 회사 PC):

  집 PC 의 127.0.0.1 은 밖에서 닿지 않는다. 뚫는 길은 둘이었다 —
  ① 운영 서버가 역방향 터널로 집 PC 안을 실시간 중계 ② 산출물 한 장만 올려 두기.
  ②를 택했다. 회사에서 보려는 것은 '회사가 잘 돌아가나'이지 실시간 조작이 아니라
  5분 지연은 손해가 없는데, **열쇠가 새더라도 나가는 것이 "집 PC 로 가는 통로"가 아니라
  "5분 지난 현황판 한 장"** 이기 때문이다. 되돌리기도 파일 하나 지우면 끝이다.
  `docs/MONETIZATION_SPEC.md` §7.3 이 관리 화면을 공개 주소로 열지 않기로 이미 결정해
  뒀는데, ①은 그 결정과 정면으로 어긋난다.

안전장치:
  - 파일명이 곧 열쇠다(128비트 난수). `data/` 에 적어 두고 재사용하므로 주소가 안 바뀐다.
    켤 때마다 주소가 바뀌면 사람이 결국 안전장치를 빼게 된다.
  - `web/static/ops/` 는 `.gitignore` 대상이다 — 열쇠가 저장소에 들어가면 안 된다.
  - 파일 안에 `noindex,nofollow` 를 박는다. 서버 설정(robots)을 건드리지 않기 위해서다.
  - 대화 내용은 애초에 수집기가 읽지 않는다(시각·도구명·짧은 작업 라벨뿐).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent_dashboard as dash                              # noqa: E402

ROOT = dash.ROOT
OUT_DIR = ROOT / "web" / "static" / "ops"
NAME_FILE = ROOT / "data" / "ops_snapshot_name.txt"         # data/ 는 git 제외
PUBLIC_BASE = "https://naechaget.co.kr/static/ops"

_HEAD = ('<meta name="robots" content="noindex,nofollow">\n'
         '<meta name="referrer" content="no-referrer">\n')


def _wrap_console() -> None:
    for _s in ("stdout", "stderr"):
        try:
            setattr(sys, _s, io.TextIOWrapper(getattr(sys, _s).buffer,
                                              encoding="utf-8", errors="replace"))
        except Exception:                                    # noqa: BLE001
            pass


def snapshot_name() -> str:
    """주소를 고정한다 — 바뀌면 오너가 매번 새 주소를 받아야 하고, 그러면 안 쓰게 된다."""
    try:
        name = NAME_FILE.read_text(encoding="utf-8").strip()
        if name:
            return name
    except OSError:
        pass
    name = os.urandom(16).hex() + ".html"                    # 128비트 — 추측 불가
    NAME_FILE.parent.mkdir(parents=True, exist_ok=True)
    NAME_FILE.write_text(name, encoding="utf-8")
    return name


def build(state: dict, when: str) -> str:
    """대시보드 HTML 에 상태를 통째로 박아 넣는다 — 서버 없이 혼자 뜨게."""
    html = dash.HTML.read_text(encoding="utf-8")
    payload = json.dumps(state, ensure_ascii=False).replace("</", "<\\/")
    inject = (f"<script>window.__SNAPSHOT__={payload};"
              f"window.__SNAPSHOT_AT__={json.dumps(when)};</script>\n")
    # ★ 앱 스크립트보다 **앞에** 둬야 한다. 뒤에 두면 부트스트랩이 이미 돌아
    #   /api/state 를 부르고(없는 서버로) 빈 화면이 된다.
    marker = "<script>\nconst $ = s => document.querySelector(s);"
    if marker not in html:
        raise SystemExit("★ agent_dashboard.html 의 스크립트 시작점을 찾지 못했다 — "
                         "템플릿이 바뀌었는지 확인할 것(조용히 빈 화면을 굽지 않는다)")
    return html.replace("<meta charset=\"utf-8\">", "<meta charset=\"utf-8\">\n" + _HEAD, 1) \
               .replace(marker, inject + marker, 1)


def main(argv=None) -> int:
    _wrap_console()
    ap = argparse.ArgumentParser(description="현황판 스냅샷 굽기(로컬 산출물)")
    ap.add_argument("--print-url", action="store_true", help="공개 주소만 찍고 끝")
    a = ap.parse_args(argv)

    name = snapshot_name()
    if a.print_url:
        print(f"{PUBLIC_BASE}/{name}")
        return 0

    when = datetime.now().isoformat(timespec="seconds")
    state = dash.build_state()
    html = build(state, when)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    path.write_text(html, encoding="utf-8")

    kb = path.stat().st_size / 1024
    print(f"  구움: {path.relative_to(ROOT).as_posix()}  ({kb:.0f} KB · {when})")
    print(f"  주소: {PUBLIC_BASE}/{name}")
    # 읽지 못한 곳이 있으면 숨기지 않는다 — 0 으로 채운 화면을 올리지 않기 위해서다
    for p in state.get("problems", []) or []:
        print(f"  ⚠ {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
