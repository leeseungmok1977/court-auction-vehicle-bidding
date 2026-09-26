# -*- coding: utf-8 -*-
"""조직 순환계 — 지시서 대기열·인계·리듬을 사람 없이 돌린다.

    python tools/org_runtime.py scan                  # 보고서·리듬·백로그를 읽어 지시서를 만든다(LLM 호출 없음)
    python tools/org_runtime.py standup               # scan + 오늘의 브리핑 docs/standups/YYYY-MM-DD.md
    python tools/org_runtime.py standup --dispatch 3  # + 자동 실행 가능한 지시서를 당직 Steward 가 처리
    python tools/org_runtime.py order --to insight --purpose "…" [--ticket FEAT-1] [--input reports/x.md]
    python tools/org_runtime.py close 2026-09-26-04 --status cancelled --note "중복"
    python tools/org_runtime.py dispatch 2026-09-26-04 [--dry-run]
    python tools/org_runtime.py board                 # 대기열 요약 JSON (대시보드가 같은 함수를 쓴다)

## 왜 만들었나 (2026-09-26 오너 지시)

*"회사라면 각각의 조직원들이 유기적으로 움직여야 하는데, 그렇지 않다."*

실측해 보니 조직도는 멀쩡했고 **순환계가 없었다.** 서브에이전트는 서로 부르지 못하므로
(ORG §1) 모든 인계가 Steward 를 거치는데, Steward 는 **오너가 세션을 열 때만 존재한다.**
그래서 `리듬중단` 3자리는 13일째 화면에 떠 있기만 했고, PM 은 3일째 안 불렸고,
인계는 Steward 의 기억 속에만 있었다. 이 도구는 세 가지만 한다.

1. 보고서 머리말(`.claude/agents/_handoff-protocol.md`)을 읽어 **다음 지시서를 파일로** 만든다.
2. 리듬 중단·미배분 티켓·정체·왕복 상한 초과를 감지해 **맡을 자리에 지시서를** 만든다.
3. 정해진 시각에 **당직 Steward**(헤드리스 `claude -p`)를 깨워 자동 실행 가능한 지시서를 처리한다.

규칙은 전부 `docs/org-contracts.md` 표에서 읽는다 — 코드에 박지 않는다(대시보드와 같은 원칙).

## 이 도구가 하지 않는 것

- **지어내지 않는다.** 보고서가 안 나오면 지시서를 `done` 으로 바꾸지 않고 `blocked` 로 적는다.
- **오너 승인 항목을 실행하지 않는다.** 당직은 허용 목록(`DISPATCH_ALLOWED`) 밖 도구를 못 쓴다 —
  헤드리스 실행에서 허용 목록 밖 도구는 묻지 않고 거부된다. 커밋·푸시·ssh·코드 편집은 목록에 없다.
- **LLM 을 부르는 것은 `dispatch` 뿐이다.** `scan` 은 파일만 읽고 쓰므로 매시간 돌려도 비용이 없다.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml                                            # requirements.txt 에 있다(PyYAML)
except Exception:                                          # noqa: BLE001
    yaml = None

REPO = Path(__file__).resolve().parents[1]

# 당직 Steward 가 쓸 수 있는 도구. **여기 없는 것은 헤드리스에서 전부 거부된다.**
# 오너 승인 항목(ORG §3)을 페르소나가 아니라 권한으로 막는다 — ORG §1 "가드레일은 도구 권한으로 건다".
DISPATCH_ALLOWED = [
    "Read", "Grep", "Glob", "Agent", "Task",
    "Write(reports/**)", "Edit(reports/**)",          # 보고서만 쓴다
    "Write(orders/**)", "Edit(orders/**)",            # 지시서 상태만 고친다
    "Bash(python -m pytest:*)",                        # 테스트 게이트(qa)
    "Bash(python tools/org_runtime.py:*)",
    "Bash(git log:*)", "Bash(git diff:*)", "Bash(git status:*)", "Bash(git show:*)",
    "Bash(sqlite3:*)",
    "WebFetch(domain:naechaget.co.kr)",                # 라이브 확인(C.4 는 우리 서버에 해당하지 않는다)
]
# 허용 목록이 1차 문이고, 이것은 **두 번째 문**이다. 한 줄 실수로 허용 목록이 넓어져도
# 되돌릴 수 없는 것만은 막는다(agent-utilization §6-15: 문은 울리는지가 아니라 막는지로 확인한다).
DISPATCH_DENIED = [
    "Bash(git commit:*)", "Bash(git push:*)", "Bash(ssh:*)", "Bash(scp:*)",
    "Bash(rm:*)", "Bash(schtasks:*)", "Bash(pip install:*)",
    "Edit(src/**)", "Edit(web/**)", "Edit(config.yaml)", "Edit(.claude/**)",
    "Write(src/**)", "Write(web/**)", "Write(config.yaml)", "Write(.claude/**)",
]
DISPATCH_TIMEOUT_SEC = 25 * 60        # 서브에이전트 최장 실측 6분대(2026-09-22). 넉넉히 4배

STEWARD = "steward"                   # 오너·Steward 결재함 — 에이전트가 아니다
OPEN_STATES = ("open", "doing", "blocked")
RESULTS = ("done", "fail", "blocked", "needs-owner")
_ID = re.compile(r"^(\d{4}-\d{2}-\d{2})-(\d{2,3})$")
ORDER_REF = re.compile(r"\b\d{4}-\d{2}-\d{2}-\d{2,3}\b")   # 호출 라벨에 지시서 번호가 있는가
_TICK = re.compile(r"`([^`]+)`")


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


# ── 마크다운·머리말 ─────────────────────────────────────────────────────────
def md_rows(text: str, section: str, ncells: int) -> list[list[str]]:
    """`## <section>` 구간 안 표에서 셀 수가 맞고 첫 칸이 백틱인 행만.

    agent_dashboard._md_rows 와 같은 규칙이다 — 구간을 안 자르면 다른 절의 표까지 먹는다
    (2026-09-23 부서표 파서가 §4 보고 리듬 표를 부서로 읽은 전례).
    """
    out, inside = [], False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            inside = s.startswith(section)
            continue
        if not inside or not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) != ncells or not cells[0].startswith("`"):
            continue
        out.append(cells)
    return out


def split_front(text: str) -> tuple[dict | None, str]:
    """맨 첫 줄이 `---` 인 YAML 머리말만 읽는다. 없거나 깨졌으면 (None, 원문).

    ★ 깨진 머리말을 빈 dict 로 바꾸지 않는다 — '머리말 없음' 과 '머리말이 틀림' 은 다르다.
      틀린 것은 호출자가 경고로 드러낸다.
    """
    if not text.startswith("---"):
        return None, text
    lines = text.splitlines()
    for i in range(1, min(len(lines), 80)):
        if lines[i].strip() == "---":
            head = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1:])
            if yaml is None:
                raise RuntimeError("PyYAML 이 없다 — pip install -r requirements.txt")
            try:
                meta = yaml.safe_load(head) or {}
            except Exception:                              # noqa: BLE001
                return {"__broken__": True}, body
            return (meta if isinstance(meta, dict) else {"__broken__": True}), body
    return None, text


def dump_front(meta: dict, body: str) -> str:
    head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, default_flow_style=False).strip()
    return f"---\n{head}\n---\n{body.rstrip()}\n"


# ── 조직 ────────────────────────────────────────────────────────────────────
class Org:
    """한 저장소의 순환계. 테스트에서는 임시 폴더를 root 로 준다."""

    def __init__(self, root: Path | str = REPO):
        self.root = Path(root)
        self.contracts_md = self.root / "docs" / "org-contracts.md"
        self.orders_dir = self.root / "orders"
        self.reports_dir = self.root / "reports"
        self.backlog_md = self.root / "docs" / "backlog.md"
        self.standups = self.root / "docs" / "standups"
        self.bus = self.root / "data" / "org-bus.jsonl"
        self.state_file = self.root / "data" / "org-state.json"
        self.dispatch_logs = self.root / "data" / "org-dispatch"
        self.warnings: list[str] = []
        self.claude_exe = ""

    # ── 계약 ──
    def contracts(self) -> tuple[dict, dict]:
        """(설정, 자리별 계약). 문서가 없으면 빈 값 + 경고 — 0 으로 채운 척하지 않는다."""
        settings = {"자동 디스패치": "꺼짐", "하루 디스패치 상한": 0,
                    "정체 기준(일)": 3, "기본 왕복 상한": 3}
        seats: dict[str, dict] = {}
        if not self.contracts_md.exists():
            self.warnings.append("docs/org-contracts.md 가 없다 — 인계 계약을 읽지 못했다")
            return settings, seats
        text = self.contracts_md.read_text(encoding="utf-8")
        for c in md_rows(text, "## 1.", 3):
            k = c[0].strip("`")
            v = c[1].strip("`")
            settings[k] = int(v) if v.isdigit() else v
        for c in md_rows(text, "## 2.", 6):
            name = c[0].strip("`")
            rh = c[4].strip("`").strip()
            cap = c[5].strip("`").strip()
            seats[name] = {
                "name": name,
                "wakes_on": c[1],
                "routes": _TICK.findall(c[2]),
                "auto": c[3].strip("`").strip() == "예",
                "rhythm": int(rh) if rh.isdigit() else None,
                "cap": int(cap) if cap.isdigit() else None,
            }
        if not seats:
            self.warnings.append("org-contracts.md §2 에서 계약 표를 찾지 못했다 — 형식이 바뀌었는지 볼 것")
        return settings, seats

    # ── 지시서 ──
    def orders(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        if not self.orders_dir.exists():
            return out
        for f in sorted(self.orders_dir.glob("*.md")):
            if f.name == "README.md":
                continue
            meta, body = split_front(f.read_text(encoding="utf-8"))
            if not meta or meta.get("__broken__") or not meta.get("id"):
                self.warnings.append(f"지시서 머리말을 읽지 못했다: {f.name}")
                continue
            meta["id"] = str(meta["id"])
            out[meta["id"]] = {"meta": meta, "body": body, "path": f}
        return out

    def _next_id(self, orders: dict, day: str) -> str:
        n = 0
        for oid in orders:
            m = _ID.match(oid)
            if m and m.group(1) == day:
                n = max(n, int(m.group(2)))
        return f"{day}-{n + 1:02d}"

    def save_order(self, o: dict) -> None:
        self.orders_dir.mkdir(parents=True, exist_ok=True)
        o["path"].write_text(dump_front(o["meta"], o["body"]), encoding="utf-8", newline="\n")

    def create_order(self, orders: dict, *, to: str, frm: str, purpose: str, reason: str,
                     key: str = "", ticket: str = "", inputs: list[str] | None = None,
                     scope: str = "", done_when: str = "", due_days: int = 2,
                     rnd: int | None = None, now: datetime | None = None) -> dict:
        now = now or _now()
        oid = self._next_id(orders, now.date().isoformat())
        ticket = ticket or oid
        if rnd is None:
            rnd = 1 + sum(1 for x in orders.values()
                          if str(x["meta"].get("ticket")) == ticket and x["meta"].get("to") == to
                          and x["meta"].get("status") != "cancelled")
        # 티켓이 없으면 지시서 번호가 티켓이 된다 — 그때 파일명에 날짜가 두 번 찍히지 않게 사유를 쓴다
        slug = re.sub(r"[^\w가-힣-]+", "-", ticket if ticket != oid else reason)[:40].strip("-")
        meta = {
            "id": oid, "to": to, "from": frm, "ticket": ticket, "status": "open",
            "round": rnd, "reason": reason, "key": key or f"{reason}:{oid}",
            "due": (now + timedelta(days=due_days)).date().isoformat(),
            "created": now.isoformat(),
            "inputs": list(inputs or []),
            "output": (f"reports/{now.date().isoformat()}-{to}-{slug}"
                       f"{'-r' + str(rnd) if rnd > 1 else ''}.md") if to != STEWARD else "",
        }
        body = (f"## 목적\n{purpose.strip()}\n\n"
                f"## 범위\n{scope.strip() or '포함: 목적에 적힌 것 · 제외: 오너 승인 항목(ORG §3) 전부'}\n\n"
                f"## 완료 기준\n{done_when.strip() or '보고서 머리말(`_handoff-protocol.md`)에 이 지시서 번호를 달아 `output` 경로에 남긴다.'}\n")
        o = {"meta": meta, "body": body, "path": self.orders_dir / f"{oid}.md"}
        orders[oid] = o
        self.save_order(o)
        self.emit("order.created", order=oid, to=to, frm=frm, ticket=ticket,
                  note=purpose.strip().splitlines()[0][:80], reason=reason)
        return o

    def set_status(self, o: dict, status: str, note: str = "", **extra) -> None:
        o["meta"]["status"] = status
        o["meta"]["updated"] = _now().isoformat()
        if note:
            o["meta"]["note"] = note
        o["meta"].update({k: v for k, v in extra.items() if v not in (None, "")})
        self.save_order(o)
        self.emit("order." + status, order=o["meta"]["id"], to=o["meta"].get("to"),
                  ticket=o["meta"].get("ticket"), note=note)

    # ── 이벤트 버스(data/ — git 제외) ──
    def emit(self, kind: str, **kw) -> None:
        rec = {"ts": _now().isoformat(), "kind": kind}
        rec.update({k: v for k, v in kw.items() if v not in (None, "")})
        try:
            self.bus.parent.mkdir(parents=True, exist_ok=True)
            with open(self.bus, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass                                           # 기록 한 줄 때문에 순환을 세우지 않는다

    def events(self, since: datetime | None = None) -> list[dict]:
        if not self.bus.exists():
            return []
        out = []
        with open(self.bus, "r", encoding="utf-8", errors="replace") as f:
            for ln in f:
                try:
                    e = json.loads(ln)
                except Exception:                          # noqa: BLE001
                    continue
                if since and str(e.get("ts", "")) < since.isoformat():
                    continue
                out.append(e)
        return out

    def _state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:                                  # noqa: BLE001
            return {"reports": {}}

    def _save_state(self, st: dict) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── 백로그 ──
    def backlog_todo(self) -> list[dict]:
        """`담당` 열이 있는 표에서 상태가 todo 로 시작하는 티켓. 분류 표(유료 훅 등)는 배분 대상이 아니다."""
        if not self.backlog_md.exists():
            return []
        out, cols = [], None
        for line in self.backlog_md.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s.startswith("|"):
                cols = None
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if cells and cells[0] == "ID":
                cols = cells
                continue
            if not cols or len(cells) != len(cols) or "담당" not in cols or set(cells[0]) <= set("-: "):
                continue
            st = cells[cols.index("상태")] if "상태" in cols else ""
            if not re.match(r"^\**todo", st):
                continue
            out.append({"id": cells[0].strip("`* "), "title": cells[1][:60],
                        "owner": cells[cols.index("담당")], "status": st})
        return out

    # ── 리듬 — 대시보드와 **같은 함수**로 잰다(정의가 두 벌이면 둘이 다른 말을 한다) ──
    def rhythm_states(self) -> list[dict]:
        tools_dir = str(Path(__file__).resolve().parent)
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        try:
            import agent_dashboard as ad                   # noqa: WPS433
        except Exception as e:                             # noqa: BLE001
            self.warnings.append(f"리듬을 재지 못했다(agent_dashboard import 실패: {type(e).__name__})")
            return []
        saved = (ad.ROOT, ad.UTIL_MD)
        ad.ROOT, ad.UTIL_MD = self.root, self.root / "docs" / "agent-utilization.md"
        try:
            _, rhythms, err = ad.read_utilization()
            if err:
                self.warnings.append(err)
            return ad.check_rhythms(rhythms)
        finally:
            ad.ROOT, ad.UTIL_MD = saved

    # ── 스캔 ────────────────────────────────────────────────────────────────
    def scan(self, now: datetime | None = None) -> dict:
        now = now or _now()
        settings, seats = self.contracts()
        orders = self.orders()
        st = self._state()
        made: list[str] = []
        closed: list[str] = []
        legacy = 0

        def has_key(key: str, open_only: bool = False) -> bool:
            return any(x["meta"].get("key") == key
                       and (not open_only or x["meta"].get("status") in OPEN_STATES)
                       for x in orders.values())

        def make(**kw) -> None:
            o = self.create_order(orders, now=now, **kw)
            made.append(o["meta"]["id"])

        # ① 보고서 머리말 → 지시서 닫기·인계
        for f in sorted(self.reports_dir.glob("*.md")) if self.reports_dir.exists() else []:
            if f.name == "README.md":
                continue
            rel = f.relative_to(self.root).as_posix()
            mt = f.stat().st_mtime
            if st["reports"].get(rel) == mt:
                continue
            meta, _ = split_front(f.read_text(encoding="utf-8", errors="replace"))
            if meta is None:
                legacy += 1
                st["reports"][rel] = mt
                continue
            if meta.get("__broken__") or not meta.get("from"):
                self.warnings.append(f"보고서 머리말이 규약과 다르다: {rel} (from 없음 또는 YAML 오류)")
                st["reports"][rel] = mt
                continue
            frm = str(meta["from"])
            result = str(meta.get("result") or "done")
            if result not in RESULTS:
                self.warnings.append(f"{rel}: result '{result}' 는 규약에 없다 — done 으로 읽지 않고 blocked 로 본다")
                result = "blocked"
            parent = orders.get(str(meta.get("order") or ""))
            ticket = str(meta.get("ticket") or (parent["meta"].get("ticket") if parent else "") or "")
            if parent and parent["meta"].get("status") in OPEN_STATES:
                self.set_status(parent, "blocked" if result == "blocked" else "done",
                                note=f"보고서 {rel} · result {result}", report=rel, result=result)
                closed.append(parent["meta"]["id"])
            elif meta.get("order") and not parent:
                self.warnings.append(f"{rel}: 지시서 {meta.get('order')} 가 orders/ 에 없다")
            ticket = ticket or (parent["meta"]["id"] if parent else "")

            hand = meta.get("handoff") or []
            if isinstance(hand, dict):
                hand = [hand]
            routes = set(seats.get(frm, {}).get("routes", []))
            for h in hand:
                to = str((h or {}).get("to") or "").strip()
                why = str((h or {}).get("why") or "").strip() or "(사유 없음 — 보고서를 읽을 것)"
                if not to:
                    continue
                key = f"handoff:{rel}>{to}"
                if has_key(key):
                    continue
                if to != STEWARD and (to not in seats or to not in routes):
                    make(to=STEWARD, frm="org-runtime", reason="route", key=key, ticket=ticket,
                         inputs=[rel], purpose=f"계약에 없는 인계: `{frm}` → `{to}` — {why}",
                         scope="포함: 이 경로를 허용할지(org-contracts §2 개정 = 오너 승인) 또는 다른 담당으로 돌릴지 결정")
                    self.emit("handoff.rejected", frm=frm, to=to, ticket=ticket, note=why[:80])
                    continue
                rnd = 1 + sum(1 for x in orders.values()
                              if str(x["meta"].get("ticket")) == ticket and x["meta"].get("to") == to
                              and x["meta"].get("status") != "cancelled") if ticket else 1
                cap = (seats.get(to, {}).get("cap") or int(settings.get("기본 왕복 상한") or 3))
                if to != STEWARD and ticket and rnd > cap:
                    ck = f"cap:{ticket}>{to}"
                    if not has_key(ck, open_only=True):
                        make(to=STEWARD, frm="org-runtime", reason="cap", key=ck, ticket=ticket,
                             inputs=[rel], purpose=(f"왕복 상한 초과 — `{ticket}` 에서 `{to}` 가 {rnd}번째 "
                                                    f"지시서를 받을 차례다(상한 {cap}). 더 돌리지 말고 결정한다: {why}"),
                             scope="포함: 지금 안으로 닫을지 · 범위를 줄여 분리할지(CLAUDE.md 운영 규칙 7) · 오너 판단")
                    self.emit("handoff.capped", frm=frm, to=to, ticket=ticket, note=f"{rnd}>{cap}")
                    st.setdefault("capped", []).append(key)
                    continue
                make(to=to, frm=frm, reason="handoff", key=key, ticket=ticket, inputs=[rel],
                     purpose=why, rnd=rnd)
                self.emit("handoff", frm=frm, to=to, ticket=ticket, note=why[:80])

            if result in ("fail", "blocked") and not hand and not has_key(f"result:{rel}"):
                make(to="pm-orchestrator", frm=frm, reason="result", key=f"result:{rel}", ticket=ticket,
                     inputs=[rel], purpose=f"`{frm}` 가 `{result}` 로 끝냈는데 다음 담당을 적지 않았다. 반려·재배분을 판정한다.")
            if result == "needs-owner" and not has_key(f"owner:{rel}"):
                make(to=STEWARD, frm=frm, reason="owner", key=f"owner:{rel}", ticket=ticket, inputs=[rel],
                     purpose=f"`{frm}` 가 오너 결정을 요청했다 — 보고서를 재현한 뒤(CLAUDE.md 규칙 5) 오너에게 올린다.")
            st["reports"][rel] = mt

        # ② 리듬 중단 → 담당 또는 결재함
        for r in self.rhythm_states():
            if r.get("state") not in ("늦음", "끊김", "없음"):
                continue
            key = f"rhythm:{r['glob']}"
            if has_key(key, open_only=True):
                continue
            owners = [n for n in _TICK.findall(r.get("owner", "")) if seats.get(n, {}).get("auto")]
            to = owners[0] if owners else STEWARD
            make(to=to, frm="org-runtime", reason="rhythm", key=key,
                 purpose=(f"리듬 `{r['state']}` — `{r['glob']}` 마지막 {r.get('last') or '없음'}"
                          f"({r.get('age') if r.get('age') is not None else '—'}일 전, 주기 {r['period']}일). "
                          f"끊기면: {r.get('impact', '')}"),
                 scope=("포함: 왜 멈췄는지 산출물·로그로 확인하고, 사람이 할 조치가 있으면 그것만 적는다. "
                        "제외: 리듬을 맞추려고 파일을 대신 쓰는 것(agent-utilization §3)"))

        # ③ 미배분 티켓 → PM (하루 한 건)
        referenced = {str(x["meta"].get("ticket")) for x in orders.values()
                      if x["meta"].get("status") != "cancelled"}
        todo = [t for t in self.backlog_todo() if t["id"] not in referenced]
        ukey = f"unassigned:{now.date().isoformat()}"
        if todo and "pm-orchestrator" in seats and not has_key(ukey) \
                and not any(x["meta"].get("reason") == "unassigned" and x["meta"].get("status") in OPEN_STATES
                            for x in orders.values()):
            lines = "\n".join(f"- `{t['id']}` {t['title']} — 담당 칸: {t['owner']}" for t in todo[:60])
            make(to="pm-orchestrator", frm="org-runtime", reason="unassigned", key=ukey,
                 inputs=["docs/backlog.md", "docs/org-contracts.md"],
                 purpose=(f"백로그 `todo` 중 지시서가 없는 티켓 {len(todo)}건. 이번 주에 착수할 것 최대 3건을 고르고 "
                          f"각각 담당·완료 기준을 정해 보고서 `handoff:` 로 넘긴다. 나머지는 왜 기다리는지 한 줄씩."),
                 scope=f"대상 티켓:\n{lines}" + ("\n- …(60건까지만 적었다)" if len(todo) > 60 else ""))

        # ④ 정체 → PM (하루 한 건)
        lim = int(settings.get("정체 기준(일)") or 3)
        stale = []
        for x in orders.values():
            m = x["meta"]
            if m.get("status") not in ("open", "doing") or m.get("to") == STEWARD:
                continue
            try:
                age = (now - datetime.fromisoformat(str(m.get("created")))).days
            except ValueError:
                continue
            if age > lim:
                stale.append((m["id"], m.get("to"), age))
        skey = f"stale:{now.date().isoformat()}"
        if stale and "pm-orchestrator" in seats and not has_key(skey):
            make(to="pm-orchestrator", frm="org-runtime", reason="stale", key=skey,
                 inputs=[f"orders/{i}.md" for i, _, _ in stale],
                 purpose=f"{lim}일 넘게 열린 지시서 {len(stale)}건 — 막힌 이유를 찾아 재배분·취소·분리를 판정한다.",
                 scope="\n".join(f"- `{i}` → `{t}` · {a}일째" for i, t, a in stale))

        # ⑤ 계약상 리듬(일) — 그 기간 지시서가 한 건도 없던 자리
        for name, s in seats.items():
            if not s.get("rhythm"):
                continue
            since = now - timedelta(days=s["rhythm"])
            recent = any(x["meta"].get("to") == name
                         and str(x["meta"].get("created", "")) >= since.isoformat() for x in orders.values())
            rkey = f"routine:{name}:{now.date().isoformat()}"
            if recent or has_key(rkey):
                continue
            make(to=name, frm="org-runtime", reason="routine", key=rkey,
                 purpose=f"정기 점검({s['rhythm']}일 주기) — {s['wakes_on']}",
                 scope="볼 것이 없으면 `result: done` 한 줄로 닫는다. 분량을 채우지 않는다(_handoff-protocol §3).")

        st["last_scan"] = now.isoformat()
        self._save_state(st)
        self.emit("scan", note=f"new {len(made)} · closed {len(closed)} · legacy {legacy}")
        return {"created": made, "closed": closed, "legacy_reports": legacy, "warnings": list(self.warnings)}

    # ── 대기열 요약(대시보드·브리핑 공용) ──────────────────────────────────
    def board(self, now: datetime | None = None) -> dict:
        now = now or _now()
        settings, seats = self.contracts()
        orders = self.orders()
        per: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        oldest: dict[str, int] = {}
        open_list = []
        for x in orders.values():
            m = x["meta"]
            to, stt = str(m.get("to")), str(m.get("status"))
            per[to][stt] += 1
            if stt in OPEN_STATES:
                try:
                    age = (now - datetime.fromisoformat(str(m.get("created")))).days
                except ValueError:
                    age = None
                if age is not None:
                    oldest[to] = max(oldest.get(to, 0), age)
                purpose = x["body"].split("## 목적", 1)[-1].strip().splitlines()
                open_list.append({"id": m["id"], "to": to, "from": m.get("from"), "status": stt,
                                  "ticket": m.get("ticket"), "reason": m.get("reason"), "round": m.get("round"),
                                  "age": age, "purpose": (purpose[0] if purpose else "")[:140],
                                  "auto": bool(seats.get(to, {}).get("auto"))})
        open_list.sort(key=lambda o: (o["to"] != STEWARD, -(o["age"] or 0)))
        week = now - timedelta(days=7)
        ev = self.events(since=week)
        routes = collections.Counter((e.get("frm"), e.get("to")) for e in ev if e.get("kind") == "handoff")
        today = now.date().isoformat()
        dispatched_today = sum(1 for e in ev if e.get("kind") == "dispatch.start"
                               and str(e.get("ts", "")).startswith(today))
        st = self._state()
        return {
            "enabled": self.contracts_md.exists(),
            "settings": settings,
            "seats": {n: {"auto": s["auto"], "rhythm": s["rhythm"], "routes": s["routes"]}
                      for n, s in seats.items()},
            "queue": {to: {"open": c["open"], "doing": c["doing"], "blocked": c["blocked"],
                           "done": c["done"], "oldest": oldest.get(to)} for to, c in per.items()},
            "open": open_list,
            "inbox": [o for o in open_list if o["to"] == STEWARD],
            "totals": {"open": sum(c["open"] for c in per.values()),
                       "doing": sum(c["doing"] for c in per.values()),
                       "blocked": sum(c["blocked"] for c in per.values()),
                       "inbox": sum(1 for o in open_list if o["to"] == STEWARD)},
            "routes_7d": [{"from": a, "to": b, "n": n} for (a, b), n in routes.most_common(20)],
            # 인계는 `handoff` 한 줄로 충분하다 — 같은 순간의 `order.created`(인계로 생긴 지시서)까지 두면
            # 피드가 두 줄씩 겹쳐 움직임이 두 배로 보인다(2026-09-26 첫 캡처에서 실측).
            "feed": [e for e in ev if e.get("kind") != "scan"
                     and not (e.get("kind") == "order.created" and e.get("reason") == "handoff")][-30:][::-1],
            "handoffs_7d": sum(routes.values()),
            "dispatched_today": dispatched_today,
            "last_scan": st.get("last_scan"),
            "warnings": list(self.warnings),
        }

    # ── 스탠드업 ────────────────────────────────────────────────────────────
    def standup(self, dispatch: int = 0, dry_run: bool = False, now: datetime | None = None) -> Path:
        now = now or _now()
        res = self.scan(now=now)
        b = self.board(now=now)
        settings = b["settings"]
        on = str(settings.get("자동 디스패치")) == "켜짐"
        cap = int(settings.get("하루 디스패치 상한") or 0)
        plan = self.dispatch_plan(b, limit=min(dispatch, max(0, cap - b["dispatched_today"])) if on else 0)
        t = b["totals"]
        since = now - timedelta(days=1)
        ev = [e for e in self.events(since=since) if e.get("kind") in
              ("handoff", "handoff.capped", "handoff.rejected", "order.done", "order.blocked", "order.created")]

        L = [f"# 스탠드업 {now.date().isoformat()}",
             "",
             f"> `tools/org_runtime.py standup` 이 {now.strftime('%H:%M')} 에 썼다. 숫자는 `orders/` 와 "
             "`data/org-bus.jsonl` 에서 센 것이다 — 사람이 옮겨 적지 않았다.",
             "",
             "## [요약]",
             f"열린 지시서 **{t['open']}** · 진행 {t['doing']} · 막힘 **{t['blocked']}** · "
             f"결재함 **{t['inbox']}** · 지난 7일 인계 {b['handoffs_7d']}건",
             f"이번 스캔: 새 지시서 {len(res['created'])}건 · 닫힘 {len(res['closed'])}건"
             + (f" · 머리말 없는 옛 보고서 {res['legacy_reports']}건은 건너뜀" if res["legacy_reports"] else ""),
             ""]
        if b["inbox"]:
            L += ["## 결재함 — 오너·Steward 가 봐야 하는 것", ""]
            L += [f"- `{o['id']}` ({o['reason']}) {o['purpose']}" for o in b["inbox"]]
            L.append("")
        L += ["## 자리별 대기열", "", "| 담당 | 자동 | 열림 | 진행 | 막힘 | 가장 오래된 |", "|---|---|---|---|---|---|"]
        for to in sorted(b["queue"], key=lambda k: (k == STEWARD, k)):
            q = b["queue"][to]
            if not (q["open"] or q["doing"] or q["blocked"]):
                continue
            auto = "결재함" if to == STEWARD else ("예" if b["seats"].get(to, {}).get("auto") else "아니오")
            L.append(f"| `{to}` | {auto} | {q['open']} | {q['doing']} | {q['blocked']} | "
                     f"{'—' if q['oldest'] is None else str(q['oldest']) + '일'} |")
        L.append("")
        L += ["## 지난 24시간 흐름", ""]
        L += ([f"- {str(e.get('ts', ''))[11:16]} `{e['kind']}` "
               f"{e.get('frm', '') + ' → ' if e.get('frm') else ''}{e.get('to', '')} "
               f"{e.get('order', '')} {e.get('note', '')}".rstrip() for e in ev] or ["- 움직임 없음"])
        L.append("")
        L += ["## 오늘 당직이 부르는 것", ""]
        if not on:
            L.append("- `자동 디스패치`가 `꺼짐`이다(org-contracts §1) — 부르지 않는다.")
        elif not plan:
            L.append("- 없음 — 자동 실행 가능한 열린 지시서가 없거나 하루 상한을 다 썼다"
                     f"(오늘 {b['dispatched_today']}/{cap}).")
        else:
            L += [f"- `{o['id']}` → `{o['to']}` · {o['purpose'][:90]}" for o in plan]
        if res["warnings"]:
            L += ["", "## 읽지 못한 것", ""] + [f"- {w}" for w in res["warnings"]]

        self.standups.mkdir(parents=True, exist_ok=True)
        out = self.standups / f"{now.date().isoformat()}.md"
        out.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")

        for o in plan:
            self.dispatch(o["id"], dry_run=dry_run)
        return out

    # ── 디스패치 ────────────────────────────────────────────────────────────
    def dispatch_plan(self, b: dict, limit: int) -> list[dict]:
        """자동 실행할 지시서 고르기. PM 먼저(배분이 막히면 나머지가 다 막힌다), 그다음 오래된 순.

        한 자리에 `doing` 이 있으면 그 자리는 건너뛴다 — 한 번에 하나(pm-orchestrator 원칙).
        """
        if limit <= 0:
            return []
        busy = {o["to"] for o in b["open"] if o["status"] == "doing"}
        cand = [o for o in b["open"] if o["status"] == "open" and o["auto"] and o["to"] not in busy]
        cand.sort(key=lambda o: (o["to"] != "pm-orchestrator", -(o["age"] or 0), o["id"]))
        out, seen = [], set()
        for o in cand:
            if o["to"] in seen:
                continue
            seen.add(o["to"])
            out.append(o)
            if len(out) >= limit:
                break
        return out

    def dispatch_prompt(self, o: dict) -> str:
        m = o["meta"]
        return f"""너는 Steward 당직이다 — 오너는 지금 없다(헤드리스 실행). CLAUDE.md 와 docs/ORG.md 를 따른다.
오늘은 지시서 **한 건만** 처리한다: orders/{m['id']}.md

1. orders/{m['id']}.md 와 거기 적힌 inputs 를 읽는다. .claude/agents/_handoff-protocol.md 도 읽는다.
2. `{m['to']}` 서브에이전트에게 Agent 도구로 위임한다. description 은 반드시 `{m['id']} ` 로 시작한다
   (대시보드가 이 번호로 '지시서를 거친 호출'을 센다). 프롬프트는 CLAUDE.md 의 [작업 지시서] 형식으로 쓴다.
3. 결과를 {m.get('output') or 'reports/ 아래 새 파일'} 에 쓴다. 파일 맨 첫 줄부터 머리말을 단다:
   order: {m['id']} / from: {m['to']} / ticket: {m.get('ticket', '')} / result / verified / handoff.
   handoff 의 to 는 docs/org-contracts.md §2 '넘길 수 있는 곳'에서만 고른다. 서브에이전트가 말한 다음 담당만 옮기고 지어내지 않는다.
4. 서브에이전트의 주장 중 코드·DB·라이브로 재현하지 못한 것은 verified: 미검증 으로 적는다(CLAUDE.md 운영 규칙 5).
5. 오너 승인 항목(ORG §3)에 닿으면 실행하지 말고 result: needs-owner 로 닫는다.
   커밋·푸시·배포·ssh·설정 변경·코드 편집은 하지 않는다 — 이 실행에는 그 권한이 없다.
6. 마지막으로 `python tools/org_runtime.py scan` 을 실행한다.
"""

    def dispatch(self, oid: str, dry_run: bool = False) -> dict:
        orders = self.orders()
        o = orders.get(oid)
        if not o:
            return {"ok": False, "why": f"지시서 {oid} 가 없다"}
        m = o["meta"]
        _, seats = self.contracts()
        if m.get("to") == STEWARD or not seats.get(str(m.get("to")), {}).get("auto"):
            return {"ok": False, "why": f"`{m.get('to')}` 는 자동 실행 자리가 아니다(org-contracts §2)"}
        if m.get("status") != "open":
            return {"ok": False, "why": f"상태가 {m.get('status')} 다 — open 만 부른다"}
        prompt = self.dispatch_prompt(o)
        cmd = self._claude_cmd()
        if dry_run:
            return {"ok": True, "dry_run": True, "cmd": cmd, "prompt": prompt}
        if not cmd:
            self.set_status(o, "blocked", note="당직 실패 — claude 실행 파일을 찾지 못했다")
            return {"ok": False, "why": "claude 를 찾지 못했다"}
        self.set_status(o, "doing", note="당직 Steward 가 불렀다")
        self.emit("dispatch.start", order=oid, to=m.get("to"))
        self.dispatch_logs.mkdir(parents=True, exist_ok=True)
        log = self.dispatch_logs / f"{oid}.log"
        code: int | str
        try:
            p = subprocess.run(cmd, input=prompt.encode("utf-8"), cwd=str(self.root),
                               capture_output=True, timeout=DISPATCH_TIMEOUT_SEC)
            code = p.returncode
            log.write_bytes(p.stdout[-200_000:] + b"\n--- stderr ---\n" + p.stderr[-50_000:])
        except subprocess.TimeoutExpired:
            code = "timeout"
            log.write_text(f"{DISPATCH_TIMEOUT_SEC}초 제한 초과", encoding="utf-8")
        except Exception as e:                             # noqa: BLE001
            code = type(e).__name__
            log.write_text(f"실행 실패: {e!r}", encoding="utf-8")
        self.scan()                                        # 보고서가 나왔으면 여기서 닫힌다
        again = self.orders().get(oid)
        if again and again["meta"].get("status") == "doing":
            # ★ 보고서가 없는데 끝났다고 치지 않는다. 종료코드 0 은 '일을 했다'가 아니다
            #   (agent-utilization §4: pip 은 실패해도 0 을 돌려줬다 — 상태값이 아니라 산출물로 판정한다).
            self.set_status(again, "blocked",
                            note=f"당직 실행 후 보고서 없음(종료 {code}) — data/org-dispatch/{oid}.log")
        self.emit("dispatch.end", order=oid, to=m.get("to"), note=f"exit {code}")
        return {"ok": code == 0, "exit": code, "log": log.relative_to(self.root).as_posix()}

    def _claude_cmd(self) -> list[str]:
        # ★ 예약 작업(S4U)에는 대화형 PATH 가 보장되지 않는다 — npm 전역 폴더가 빠지면 which 가 못 찾는다.
        #   그래서 등록 스크립트가 전체 경로를 --claude 로 넘긴다(register_daily_report_task.ps1 의 python 과 같은 이유).
        exe = self.claude_exe or shutil.which("claude") or shutil.which("claude.cmd")
        if not exe:
            return []
        return [exe, "-p", "--output-format", "json",
                "--allowedTools", ",".join(DISPATCH_ALLOWED),
                "--disallowedTools", ",".join(DISPATCH_DENIED)]


# ── CLI ─────────────────────────────────────────────────────────────────────
def _wrap_console() -> None:
    """Windows 콘솔(cp949)에서 '—'·'★' 로 죽지 않게 — main 에서만 부른다(agent_dashboard 와 같은 이유)."""
    for s in ("stdout", "stderr"):
        with contextlib.suppress(Exception):
            setattr(sys, s, io.TextIOWrapper(getattr(sys, s).buffer, encoding="utf-8", errors="replace"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="조직 순환계")
    ap.add_argument("--root", default=str(REPO), help=argparse.SUPPRESS)
    ap.add_argument("--claude", default="", help="claude 실행 파일 전체 경로(예약 작업용)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan")
    sp = sub.add_parser("standup")
    sp.add_argument("--dispatch", type=int, default=0, help="부를 최대 건수(하루 상한 안에서)")
    sp.add_argument("--dry-run", action="store_true")
    sub.add_parser("board")
    op = sub.add_parser("order")
    op.add_argument("--to", required=True)
    op.add_argument("--purpose", required=True)
    op.add_argument("--ticket", default="")
    op.add_argument("--input", action="append", default=[])
    op.add_argument("--scope", default="")
    op.add_argument("--from", dest="frm", default=STEWARD)
    cp = sub.add_parser("close")
    cp.add_argument("id")
    cp.add_argument("--status", required=True, choices=["done", "blocked", "cancelled"])
    cp.add_argument("--note", required=True, help="왜 닫는가 — 비우지 않는다")
    dp = sub.add_parser("dispatch")
    dp.add_argument("id")
    dp.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    org = Org(a.root)
    org.claude_exe = a.claude

    if a.cmd == "scan":
        r = org.scan()
        print(json.dumps(r, ensure_ascii=False, indent=1))
    elif a.cmd == "standup":
        p = org.standup(dispatch=a.dispatch, dry_run=a.dry_run)
        print(p.relative_to(org.root).as_posix())
    elif a.cmd == "board":
        print(json.dumps(org.board(), ensure_ascii=False, indent=1))
    elif a.cmd == "order":
        _, seats = org.contracts()
        if a.to != STEWARD and a.to not in seats:
            print(f"`{a.to}` 는 org-contracts §2 에 없는 자리다", file=sys.stderr)
            return 2
        orders = org.orders()
        o = org.create_order(orders, to=a.to, frm=a.frm, purpose=a.purpose, reason="manual",
                             ticket=a.ticket, inputs=a.input, scope=a.scope)
        print(o["path"].relative_to(org.root).as_posix())
    elif a.cmd == "close":
        o = org.orders().get(a.id)
        if not o:
            print(f"지시서 {a.id} 가 없다", file=sys.stderr)
            return 2
        if a.status == "done" and not o["meta"].get("report"):
            # CLAUDE.md 운영 규칙 7 — 보고서(=DoD 대조 근거) 없이 완료로 바꾸지 않는다
            print("보고서 없이 done 으로 닫지 않는다 — 머리말 단 보고서를 먼저 남기거나 cancelled 로 닫는다",
                  file=sys.stderr)
            return 2
        org.set_status(o, a.status, note=a.note)
        print(f"{a.id} → {a.status}")
    elif a.cmd == "dispatch":
        r = org.dispatch(a.id, dry_run=a.dry_run)
        print(json.dumps(r, ensure_ascii=False, indent=1) if not a.dry_run else
              " ".join(r.get("cmd") or ["(claude 없음)"]) + "\n\n" + r.get("prompt", r.get("why", "")))
        return 0 if r.get("ok") else 1
    for w in org.warnings:
        print(f"  ⚠ {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    # ★ 콘솔 감싸기는 **진입점에서만** 한다. main() 안에서 하면 테스트가 main() 을 부를 때
    #   pytest 의 출력 포획을 갈아치워 'I/O operation on closed file' 로 죽는다 — 2026-09-26 실측.
    #   agent_dashboard._wrap_console 주석이 경고한 함정의 다섯 번째 변형이다.
    _wrap_console()
    raise SystemExit(main())
