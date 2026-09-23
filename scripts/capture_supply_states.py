# -*- coding: utf-8 -*-
"""사내 대시보드 **공급 블록** 3종 상태 캡처 + 계산된 색 측정.

    python scripts/capture_supply_states.py --tag before
    python scripts/capture_supply_states.py --tag after

## 왜 이 스크립트가 저장소에 남는가

2026-09-24 검수 ③: 앞선 회차의 `ok-1440-v3.png` 는 칩 7개가 전부 초록 `정상` 인데 같은 행
본문은 `0건 3일 연속` · `16일째 없음` 을 말하고 있었다. **`state` 만 뒤집고 `head`·`detail`
은 down 픽스처 그대로** 쓴 화면이었다 — 전날 `PANEL-46` 에서 닫은 **공허 픽스처**와 정확히
같은 형태다. 손으로 JSON 을 만들면 또 그렇게 된다.

그래서 여기서는 **`web/ops_health.evaluate()` 를 실제로 돌려** 판정을 만든다. 판정 함수가
`state` 와 `head`·`detail` 을 **한 자리에서 같이** 만들기 때문에 셋이 어긋날 수가 없다.
스냅샷(입력)만 건강하게 주면 화면의 모든 칸이 저절로 정상을 말한다.

## 5종

| 이름 | 무엇 | 만드는 법 |
|---|---|---|
| `ok` | 정상 — 초록이어도 되는 유일한 화면 | 건강한 스냅샷을 **1시간 전** 시각으로 판정 |
| `stale` | 낡음 — 저장된 값은 `ok` 인데 30시간 전 것 | 같은 건강한 스냅샷을 **30시간 전** 시각으로 판정 |
| `missing` | 판정 파일 자체가 없음 (지금 실물이 이 상태다) | `SUPPLY` 를 없는 경로로 가리킨다 |
| `warn` | 이상 — 케이카 8일 정지 + 0표본 비율 상승 | 건강한 스냅샷에서 그 두 축만 망가뜨린다 |
| `down` | 멈춤 — 09-19~21 분석 0건 3일 + 엔카 차단 | 같은 방식으로 세 축을 망가뜨린다 |

`stale` 이 핵심이다. 파일에는 `정상` 7개가 들어 있고, 화면은 그걸 **초록으로 그리면 안 된다.**
`warn`·`down` 은 **심각도 순서**(정상 < 확인 불가 < 이상 < 멈춤)가 실제로 한 방향인지
네 상태를 나란히 재려고 둔다 — 주장하지 말고 색값으로 보이라는 것이 검수 ②의 요구다.

## 하지 않는 것
- 외부 요청 0건. 전부 로컬 파일과 순수 함수다.
- 포트 8765 는 건드리지 않는다(오너가 보고 있는 대시보드). 여기서는 `--port` 기본 8791 을
  쓰고 캡처가 끝나면 즉시 내린다.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from web import ops_health as oh  # noqa: E402

WIDTHS_SHOT = (1440, 768)
# CLAUDE.md 검수 SOP 1번 — 측정은 6개 폭 전부에서 한다(360 은 갤럭시 A 폭이다).
WIDTHS_MEASURE = (320, 360, 390, 430, 768, 1440)


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)                                  # type: ignore[union-attr]
    return mod


DASH = _load(ROOT / "tools" / "agent_dashboard.py", "agent_dashboard_capture")
HTML = (ROOT / "tools" / "agent_dashboard.html").read_bytes()


def healthy_snapshot(anchor: datetime) -> dict:
    """**전 신호가 정상**인 스냅샷. 날짜는 판정 시각(anchor)에 맞춰 움직인다.

    ★ `state` 를 손으로 적지 않는다 — 여기서 주는 것은 원자료뿐이고 판정은 evaluate() 가 한다.
      그래야 `정상` 칩 옆의 `head`·`detail` 이 같이 정상을 말한다.
    """
    d = anchor.date()
    y = d - timedelta(days=1)
    return {
        "collected_at": f"{d} 06:35:30",
        "analyzed_at": f"{d} 06:37:33",
        "result_checked_at": f"{d} 06:42:47",
        "kcar_checked_at": f"{d} 06:40:00",
        "encar_state": "ok", "encar_code": "200", "encar_ok_at": f"{d} 06:31:28",
        "kcar_state": "ok",
        "daily_enabled": "1",
        "runs": [
            {"started_at": f"{y} 06:30:00", "status": "done",
             "message": "입찰예정 402 · 분석 31 · 동급참조 4 · 0표본 재조회 15 · "
                        "사진정렬 22건 · 낙찰결과 188건"},
            {"started_at": f"{d} 06:30:00", "status": "done",
             "message": "입찰예정 396 · 분석 37 · 동급참조 6 · 0표본 재조회 12 · "
                        "사진정렬 19건 · 낙찰결과 194건"},
        ],
        # 0표본은 **내려가는 중**이어야 정상이다 — 비율도 절대수도 전일보다 낮게 둔다.
        "zero_sample": {"zero": 512, "total": 1481},
        "zero_history": [{"date": y.isoformat(), "zero": 528, "total": 1476}],
        "source": "운영 서버",
    }


def fixtures(tmp: pathlib.Path) -> list[tuple[str, pathlib.Path | None]]:
    now = datetime.now()
    out: list[tuple[str, pathlib.Path | None]] = []

    fresh = now - timedelta(hours=1)                  # 1시간 전 판정 → stale 아님
    v = oh.evaluate(healthy_snapshot(fresh), now=fresh)
    assert v["state"] == "ok" and all(s["state"] == "ok" for s in v["signals"]), \
        f"정상 픽스처가 정상이 아니다: {[(s['key'], s['state']) for s in v['signals']]}"
    p = tmp / "ok.json"
    p.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
    out.append(("ok", p))

    old = now - timedelta(hours=30)                   # 30시간 전 판정 → SUPPLY_MAX_AGE_H(26) 초과
    v2 = oh.evaluate(healthy_snapshot(old), now=old)
    assert v2["state"] == "ok" and all(s["state"] == "ok" for s in v2["signals"]), \
        "낡음 픽스처의 원본은 '전부 정상'이어야 한다 — 그래야 화면이 초록을 참는지 본다"
    p2 = tmp / "stale.json"
    p2.write_text(json.dumps(v2, ensure_ascii=False, indent=1), encoding="utf-8")
    out.append(("stale", p2))

    out.append(("missing", None))                     # 파일 자체가 없다(지금 실물이 이 상태)

    # ── 이상·멈춤 — 심각도 순서를 **재기 위한** 두 장. 여기도 state 를 손으로 적지 않는다.
    s_warn = healthy_snapshot(fresh)
    s_warn["kcar_checked_at"] = f"{(fresh - timedelta(days=8)).date()} 06:40:00"
    s_warn["zero_sample"] = {"zero": 620, "total": 1481}      # 비율 +6.1%p → 이상
    v3 = oh.evaluate(s_warn, now=fresh)
    assert v3["state"] == "warn", v3["state"]
    p3 = tmp / "warn.json"
    p3.write_text(json.dumps(v3, ensure_ascii=False, indent=1), encoding="utf-8")
    out.append(("warn", p3))

    # 09-19~21 실측의 형태 — 분석 0건 3일 연속(전부 status=done) + 엔카 차단 + 케이카 18일.
    s_down = healthy_snapshot(fresh)
    d0 = fresh.date()
    s_down["runs"] = [
        {"started_at": f"{d0 - timedelta(days=n)} 06:30:00", "status": "done",
         "message": f"입찰예정 410 · 분석 0 · 낙찰결과 {158 + n}건"} for n in (2, 1, 0)]
    s_down["encar_state"], s_down["encar_code"] = "error", "None"
    s_down["kcar_checked_at"] = f"{(fresh - timedelta(days=18)).date()} 23:10:39"
    v4 = oh.evaluate(s_down, now=fresh)
    assert v4["state"] == "down", v4["state"]
    p4 = tmp / "down.json"
    p4.write_text(json.dumps(v4, ensure_ascii=False, indent=1), encoding="utf-8")
    out.append(("down", p4))
    return out


def build(supply_path: pathlib.Path | None) -> dict:
    DASH.SUPPLY = supply_path or (ROOT / "data" / "__없는_판정파일__.json")
    return DASH.build_state()


class _H(BaseHTTPRequestHandler):
    state: dict = {}

    def _send(self, body: bytes, ctype: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):                                             # noqa: N802
        if self.path.startswith("/api/state"):
            self._send(json.dumps(_H.state, ensure_ascii=False).encode(),
                       "application/json; charset=utf-8")
        else:
            self._send(HTML, "text/html; charset=utf-8")

    def log_message(self, *a):
        pass


PROBE = """() => {
  const band = document.querySelector('#supply .band');
  const cs = e => e ? getComputedStyle(e) : null;
  const b = cs(band);
  const chips = [...document.querySelectorAll('#supply .pill')].map(p => ({
    text: p.textContent.trim(), color: cs(p).color,
    bg: cs(p).backgroundColor, shadow: cs(p).boxShadow}));
  const tiles = [...document.querySelectorAll('.kpi')].map(t => ({
    k: t.querySelector('.k')?.textContent.trim(),
    v: t.querySelector('.v')?.textContent.trim(),
    s: t.querySelector('.s')?.textContent.trim(),
    cls: t.className,
    vColor: cs(t.querySelector('.v')).color,
    bg: cs(t).backgroundColor, border: cs(t).borderTopColor}));
  const rows = [...document.querySelectorAll('#supply table tr')].map(
    r => [...r.children].map(c => c.textContent.trim()));
  const probBand = document.querySelector('#problems .band');
  const de = document.documentElement;
  const over = [...document.querySelectorAll('body *')].filter(e => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && (r.right > de.clientWidth + 1 || r.left < -1);
  }).map(e => e.tagName + '.' + (e.className || '') + '|' + Math.round(e.getBoundingClientRect().right));
  return {
    bandClass: band ? band.className : null,
    bandBg: b ? b.backgroundColor : null, bandBorder: b ? b.borderTopColor : null,
    bandColor: b ? b.color : null,
    bandText: band ? band.textContent.replace(/\\s+/g, ' ').trim().slice(0, 260) : null,
    chips, tiles, rows,
    problemsBg: probBand ? getComputedStyle(probBand).backgroundColor : null,
    problemsBorder: probBand ? getComputedStyle(probBand).borderTopColor : null,
    problemsText: probBand ? probBand.textContent.replace(/\\s+/g, ' ').trim().slice(0, 200) : null,
    scrollW: de.scrollWidth, clientW: de.clientWidth, overflow: over.slice(0, 12),
  };
}"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="공급 블록 3종 캡처(외부 요청 0건)")
    ap.add_argument("--tag", required=True, choices=("before", "after"))
    ap.add_argument("--port", type=int, default=8791,
                    help="★ 8765 는 오너가 보는 대시보드다. 절대 쓰지 않는다")
    a = ap.parse_args(argv)
    assert a.port != 8765, "8765 는 오너가 보고 있는 대시보드다"

    from playwright.sync_api import sync_playwright        # noqa: PLC0415

    out = ROOT / "screenshots" / "supply" / a.tag
    out.mkdir(parents=True, exist_ok=True)
    tmp = ROOT / "data" / "_supply_fixtures"               # data/ 는 git 제외
    tmp.mkdir(parents=True, exist_ok=True)

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                          text=True).stdout.strip()
    diff = subprocess.run(["git", "diff", "HEAD", "--", "tools/agent_dashboard.html",
                           "tools/agent_dashboard.py"], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace").stdout
    dirty = hashlib.md5(diff.encode("utf-8", "replace")).hexdigest() if diff.strip() else "clean"
    (out / "HEAD").write_text(
        f"{head}\n"
        f"tag={a.tag}\n"
        f"worktree_diff_md5={dirty}  # 'clean' 이면 커밋 그대로다\n"
        f"captured_at={datetime.now().isoformat(timespec='seconds')}\n", encoding="utf-8")

    srv = HTTPServer(("127.0.0.1", a.port), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    report: dict = {}
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            for name, path in fixtures(tmp):
                _H.state = build(path)
                for w in WIDTHS_MEASURE:
                    pg = br.new_page(viewport={"width": w, "height": 1000},
                                     device_scale_factor=2 if w in WIDTHS_SHOT else 1)
                    pg.goto(f"http://127.0.0.1:{a.port}/", wait_until="networkidle")
                    pg.wait_for_selector("#kpis .kpi", timeout=15000)
                    pg.wait_for_timeout(250)
                    report[f"{name}-{w}"] = pg.evaluate(PROBE)
                    if w in WIDTHS_SHOT:
                        f = out / f"{name}-{w}.png"
                        pg.screenshot(path=str(f), clip={"x": 0, "y": 0,
                                                         "width": w, "height": 900})
                        report[f"{name}-{w}"]["png"] = f.name
                        report[f"{name}-{w}"]["md5"] = hashlib.md5(f.read_bytes()).hexdigest()
                    pg.close()
            br.close()
    finally:
        srv.shutdown()
        srv.server_close()

    (out / "measure.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    for k in sorted(report):
        r = report[k]
        green = [c for c in r["chips"] if c["text"] == "정상"]
        print(f"\n== {k}  band={r['bandClass']} bg={r['bandBg']} border={r['bandBorder']}")
        print(f"   칩 {len(r['chips'])}개 · '정상' 칩 {len(green)}개"
              + (f" · {r['chips'][0]['text']} color={r['chips'][0]['color']}"
                 f" bg={r['chips'][0]['bg']}" if r["chips"] else ""))
        sup = next((t for t in r["tiles"] if t["k"] == "공급 상태"), None)
        if sup:
            print(f"   타일 v='{sup['v']}' color={sup['vColor']} bg={sup['bg']}"
                  f" border={sup['border']} cls='{sup['cls']}'")
            print(f"   타일 부제='{sup['s']}'")
        print(f"   띠: {r['bandText'][:160] if r['bandText'] else None}")
        if r["problemsText"]:
            print(f"   ⚠ #problems {r['problemsBorder']}: {r['problemsText'][:110]}")
        if r["scrollW"] > r["clientW"] + 1 or r["overflow"]:
            print(f"   ✗ 가로 {r['scrollW']}>{r['clientW']} · 밖으로 나간 것 {r['overflow'][:4]}")
        if "md5" in r:
            print(f"   png={r['png']} md5={r['md5']}")
    print(f"\n{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
