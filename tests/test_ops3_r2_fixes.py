# -*- coding: utf-8 -*-
"""OPS-3 수정 회차(r2) — qa 결함 QA-OPS3-1·2·3 을 고친 규칙의 **가장자리**를 지킨다.

qa 의 적대적 테스트(`test_ops3_qa_adversarial.py`)가 결함 자체를 잡는다면, 여기는 고친 규칙이
새로 만든 경계를 잡는다. 보고서: `reports/2026-09-27-ops3-backend-r2.md`.

  ① 구간의 정체(시작일·지시서 id)는 상태 파일 `alert_runs` 에 고정된다 — ✅ 가 끊고, 3주 넘게 모르면 버린다
  ② 쓰는 쪽(daily_ops_report)의 세 가지 공급 절(판정·지난 기간·확인 불가)은 경고 없이 읽힌다 — 거짓 경고 0
  ③ 형식이 어긋난 곳마다 `issues` 가 생기고, 순환계·주간 보고가 **파일명과 함께** 드러낸다
  ④ 건너뛴 모름은 지시서·스탠드업에 적힌다(숨기지 않는다)
  ⑤ 문서가 코드와 같은 말을 한다(계약 §3 · daily-check · schedule_verdict 독스트링)
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import org_runtime as rt  # noqa: E402

_spec = importlib.util.spec_from_file_location("daily_ops_report_ops3_r2", ROOT / "tools" / "daily_ops_report.py")
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

NOW = datetime(2026, 9, 27, 13, 5, 0)
SUPPLY = ["물건 수집", "시세 분석", "엔카 시세", "케이카 교차검증", "낙찰결과", "시세 0표본", "실행 기록"]
MARK = {"ok": "✅ 정상", "warn": "⚠️ 이상", "down": "🛑 멈춤", "unknown": "❔ 확인 불가"}
JOBS = {"매일 시세·낙찰 갱신": "✅ 성공", "SSL 인증서 갱신 확인": "✅ 성공",
        "주간 전문가 패널": "— 없음", "사진 미분류 점검": "— 없음", "집 회선 터널": "✅ 성공"}
BACKLOG = """# 백로그

| ID | 제목 | 담당 | 상태 | 완료 기준(DoD) |
|---|---|---|---|---|
| AUD-06 | 공급 신호 오탐 | backend | todo · 확인(qa) | x |
"""


@pytest.fixture()
def org(tmp_path, monkeypatch):
    (tmp_path / "docs" / "daily-reports").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    shutil.copy(ROOT / "docs" / "org-contracts.md", tmp_path / "docs" / "org-contracts.md")
    (tmp_path / "docs" / "backlog.md").write_text(BACKLOG, encoding="utf-8")
    o = rt.Org(tmp_path)
    monkeypatch.setattr(o, "rhythm_states", lambda: [])
    monkeypatch.setattr(o, "schedule_states", lambda: ([], "테스트: 예약 작업을 읽지 않는다"))
    return o


def body(supply: dict | None = None, jobs: dict | None = None, *, late: bool = False) -> str:
    sup = {n: "ok" for n in SUPPLY}
    sup.update(supply or {})
    L = ["# 작업 결과 리포트", "", "- **요약** x", ""]
    if late:
        L += ["## 공급 상태", "", "> ❔ **지난 기간** — 공급 판정은 지금 값이라 지난 날짜 리포트에는 적지 않는다.", ""]
    else:
        L += ["## 공급 상태", "", "> x", "", "| 신호 | 상태 | 값 | 근거 | 티켓 |", "|---|---|---|---|---|"]
        L += [f"| {n} | {MARK[s]} | 값 | 근거 | — |" for n, s in sup.items()]
        L += [""]
    j = dict(JOBS)
    j.update(jobs or {})
    L += ["## 정기 작업", "", "| 작업 | 실행 위치 | 예정 | 실제 실행 | 건수 | 결과 |", "|---|---|---|---|---|---|"]
    L += [f"| {n} | 이 PC | x | x | — | {s} |" for n, s in j.items()]
    return "\n".join(L) + "\n"


def daily(org, day: str, supply: dict | None = None, jobs: dict | None = None, *, late: bool = False,
          text: str | None = None) -> Path:
    p = org.daily_dir / f"{day}.md"
    p.write_text(text if text is not None else body(supply, jobs, late=late), encoding="utf-8")
    return p


def alerts_of(org, reason="alert"):
    return [o for o in org.orders().values() if o["meta"]["reason"] == reason]


def at(d: date, hh: int = 13) -> datetime:
    return datetime.combine(d, datetime.min.time()) + timedelta(hours=hh, minutes=5)


# ════════════════════════════════════════════════════════════════════════
# ① 구간의 정체는 상태 파일에 고정된다
# ════════════════════════════════════════════════════════════════════════
def test_segment_start_and_order_id_are_written_to_state(org):
    daily(org, "2026-09-26", {"물건 수집": "down"})
    daily(org, "2026-09-27", {"물건 수집": "down"})
    org.scan(now=NOW)
    oid = alerts_of(org)[0]["meta"]["id"]
    seg = json.loads(org.state_file.read_text(encoding="utf-8"))["alert_runs"]["물건 수집"]
    assert (seg["kind"], seg["start"], seg["last"], seg["order"]) == ("supply", "2026-09-26", "2026-09-27", oid)
    assert seg["days"] == ["2026-09-26", "2026-09-27"]


def test_ok_report_ends_the_segment_and_clears_it_from_state(org):
    daily(org, "2026-09-25", {"물건 수집": "down"})
    daily(org, "2026-09-26", {"물건 수집": "down"})
    org.scan(now=at(date(2026, 9, 26)))
    daily(org, "2026-09-27")                                                      # ✅ 정상
    org.scan(now=NOW)
    assert "물건 수집" not in org._state().get("alert_runs", {})


def test_ok_report_before_the_stored_start_does_not_split_the_segment(org):
    """✅ 가 **구간 시작 전**이면 같은 구간이다 — 지난 리포트를 다시 만들어 시작일이 ❔ 가 돼도 키가 그대로다."""
    daily(org, "2026-09-24")                                                      # ✅
    daily(org, "2026-09-25", {"물건 수집": "down"})
    daily(org, "2026-09-26", {"물건 수집": "down"})
    org.scan(now=at(date(2026, 9, 26)))
    first = alerts_of(org)
    assert [o["meta"]["key"] for o in first] == ["alert:물건 수집:2026-09-25"]
    org.set_status(first[0], "done", note="의도된 상태")
    daily(org, "2026-09-25", late=True)                                           # 재생성 → ❔ 지난 기간
    daily(org, "2026-09-27", {"물건 수집": "down"})
    r = org.scan(now=NOW)
    ev = next(x for x in r["alerts"] if x["name"] == "물건 수집")
    assert (ev["start"], ev["action"], ev["n"]) == ("2026-09-25", "done-before", 3)
    assert len(alerts_of(org)) == 1


def test_regenerated_start_day_keeps_the_key_while_the_order_is_still_open(org):
    daily(org, "2026-09-25", {"물건 수집": "down"})
    daily(org, "2026-09-26", {"물건 수집": "down"})
    org.scan(now=at(date(2026, 9, 26)))
    daily(org, "2026-09-25", late=True)
    daily(org, "2026-09-27", {"물건 수집": "down"})
    r = org.scan(now=NOW)
    ev = next(x for x in r["alerts"] if x["name"] == "물건 수집")
    assert ev["key"] == "alert:물건 수집:2026-09-25" and ev["action"] == "done-before"
    assert len(alerts_of(org)) == 1


def test_thirty_day_segment_counts_every_day_not_only_the_window(org):
    d0 = date(2026, 9, 1)
    for i in range(30):
        d = d0 + timedelta(days=i)
        daily(org, d.isoformat(), {"물건 수집": "down"})
        r = org.scan(now=at(d))
    ev = next(x for x in r["alerts"] if x["name"] == "물건 수집")
    assert (ev["start"], ev["end"], ev["n"]) == ("2026-09-01", "2026-09-30", 30)
    assert len(alerts_of(org)) == 1


def test_three_weeks_of_nothing_then_an_alert_is_a_new_segment(org):
    """구간을 영원히 끌고 다니지 않는다 — 마지막 경보가 조회 창(21일)보다 오래됐고 그 사이 아무것도 몰랐으면 새 구간."""
    daily(org, "2026-09-01", {"물건 수집": "down"})
    daily(org, "2026-09-02", {"물건 수집": "down"})
    org.scan(now=at(date(2026, 9, 2)))
    org.set_status(alerts_of(org)[0], "done", note="의도된 상태")
    daily(org, "2026-09-26", {"물건 수집": "down"})
    daily(org, "2026-09-27", {"물건 수집": "down"})
    org.scan(now=NOW)
    assert sorted(o["meta"]["key"] for o in alerts_of(org)) == ["alert:물건 수집:2026-09-01",
                                                               "alert:물건 수집:2026-09-26"]


def test_stale_segment_is_dropped_from_state_when_nothing_is_known(org):
    """상태 파일이 끝난 구간을 끌고 다니지 않는다 — 창 안에 아무 리포트도 없고 마지막 경보가 창보다 오래됐으면 지운다."""
    daily(org, "2026-09-01", {"물건 수집": "down"})
    daily(org, "2026-09-02", {"물건 수집": "down"})
    org.scan(now=at(date(2026, 9, 2)))
    assert "물건 수집" in org._state()["alert_runs"]
    org.scan(now=NOW)                                                             # 09-06~09-27 에 리포트 없음
    assert "물건 수집" not in org._state()["alert_runs"]


def test_segment_is_kept_while_only_unknowns_are_visible(org):
    """경보가 보이던 리포트가 둘 다 다시 만들어져 ❔ 가 돼도, ✅ 를 보기 전까지는 같은 구간이다."""
    daily(org, "2026-09-25", {"물건 수집": "down"})
    daily(org, "2026-09-26", {"물건 수집": "down"})
    org.scan(now=at(date(2026, 9, 26)))
    org.set_status(alerts_of(org)[0], "done", note="의도된 상태")
    daily(org, "2026-09-25", late=True)
    daily(org, "2026-09-26", late=True)
    r = org.scan(now=at(date(2026, 9, 26), 18))
    assert not [x for x in r["alerts"] if x["name"] == "물건 수집"]                  # 지금 보이는 경보는 없다
    assert org._state()["alert_runs"]["물건 수집"]["start"] == "2026-09-25"         # 그래도 구간은 남는다
    daily(org, "2026-09-27", {"물건 수집": "down"})
    r = org.scan(now=NOW)
    ev = next(x for x in r["alerts"] if x["name"] == "물건 수집")
    assert (ev["start"], ev["action"]) == ("2026-09-25", "done-before")
    assert len(alerts_of(org)) == 1


def test_dry_run_does_not_persist_the_segment(org):
    daily(org, "2026-09-26", {"물건 수집": "down"})
    daily(org, "2026-09-27", {"물건 수집": "down"})
    org.scan(now=NOW)
    before = org.state_file.read_bytes()
    daily(org, "2026-09-28", {"시세 0표본": "warn"})
    daily(org, "2026-09-29", {"시세 0표본": "warn"})
    org.dry_run = True
    org.scan(now=at(date(2026, 9, 29)))
    assert org.state_file.read_bytes() == before


# ════════════════════════════════════════════════════════════════════════
# ② 쓰는 쪽의 실제 형식은 경고 없이 읽힌다 — 거짓 경고 0
# ════════════════════════════════════════════════════════════════════════
def _report_data(generated: datetime, **over):
    since, until = R.report_window(date(2026, 9, 26))
    sig = [{"key": "collect", "label": "물건 수집", "state": "down", "head": "0건", "detail": "d"},
           {"key": "analyze", "label": "시세 분석", "state": "ok", "head": "3건", "detail": "d"}]
    d = {"since": since, "until": until, "generated": generated,
         "server": {"runs": [], "settings": {"daily_time": "06:30", "daily_enabled": "1",
                                              "encar_health_state": "ok", "encar_health_ok_at": "2026-09-26 06:31:00"},
                    "certbot": {"started": 2, "finished": 2, "failed": 0}, "service": {"active": "active"}},
         "tasks": {R.PHOTO_TASK: {"state": "Ready", "last": "", "next": "", "result": 0},
                   R.TUNNEL_TASK: {"state": "Running", "last": "", "next": "", "result": 267009}},
         "panel": {"commits": []}, "photo_log": {}, "tunnel_log": {},
         "supply": {"state": "down", "headline": "h", "checked_at": "2026-09-26 12:00:00", "source": "운영 서버",
                    "signals": sig, "alerts": [sig[0]]},
         "routes": {"물건 수집": {"ticket": "", "state": ""}}}
    d.update(over)
    return d


@pytest.mark.parametrize("case", ["판정", "14:00 넘어 만든 당일(지난 기간)", "서버 못 읽음(확인 불가)"])
def test_writer_output_parses_without_issues(case):
    on_time = datetime(2026, 9, 26, 12, 0, 5)
    if case == "판정":
        md = R.build_markdown(_report_data(on_time))
    elif case.startswith("14:00"):
        md = R.build_markdown(_report_data(datetime(2026, 9, 26, 17, 8)))       # 09-22 실측 17:08
        assert "지난 기간" in md
    else:
        md = R.build_markdown(_report_data(on_time, supply=None))
        assert "확인 불가" in md
    p = rt.parse_daily_report(md, day="2026-09-26")
    assert p["issues"] == [], p["issues"]
    if case == "판정":
        assert p["supply"]["물건 수집"]["state"] == "alert"
    else:
        assert p["supply"] == {}                                                  # 모름 — 경고가 아니다


def test_real_daily_reports_raise_no_format_warnings():
    files = sorted((ROOT / "docs" / "daily-reports").glob("2026-*.md"))
    assert len(files) >= 7
    for f in files:
        p = rt.parse_daily_report(f.read_text(encoding="utf-8", errors="replace"), day=f.stem)
        assert p["issues"] == [], (f.name, p["issues"])


# ════════════════════════════════════════════════════════════════════════
# ③ 형식이 어긋난 곳마다 issues
# ════════════════════════════════════════════════════════════════════════
_OK_JOBS = ("## 정기 작업\n\n| 작업 | 실행 위치 | 예정 | 실제 실행 | 건수 | 결과 |\n|---|---|---|---|---|---|\n"
            "| SSL 인증서 갱신 확인 | 서버 | x | x | — | ✅ 성공 |\n")


@pytest.mark.parametrize("text,day,needle", [
    ("## 공급 상태\n\n| 신호 | 상태 | 값 | 근거 |\n|---|---|---|---|\n\n" + _OK_JOBS, "2026-09-27", "읽힌 행이 0"),
    ("## 공급 상태\n\n| 신호 | 상태 | 값 | 근거 |\n|---|---|---|---|\n| 물건 수집 | 🛑 멈춤 | 0 |\n\n" + _OK_JOBS,
     "2026-09-27", "읽힌 행이 0"),
    ("## 공급 상태\n\n| 신호 | 상태 | 값 | 근거 |\n|---|---|---|---|\n| 물건 수집 | 🛑 멈춤 | 0 | a |\n"
     "| 시세 분석 | ✅ 정상 | 0 |\n\n" + _OK_JOBS, "2026-09-27", "칸 수가 열과 다른 줄 1개"),
    ("## 공급 상태\n\n> 무엇인가 썼다\n\n" + _OK_JOBS, "2026-09-27", "표도 '지난 기간'·'확인 불가' 문장도 없다"),
    ("# 리포트\n\n" + _OK_JOBS, "2026-09-27", "`## 공급 상태` 절이 없다"),
    ("## 공급 상태\n\n> ❔ **지난 기간** — x\n\n## 정기 작업\n\n| 작업 | 결과 |\n|---|---|\n| SSL 인증서 갱신 확인 | 성공 |\n",
     "2026-09-27", "정기 작업 표 `결과` 칸의 표시를 모른다"),
    ("## 공급 상태\n\n> ❔ **지난 기간** — x\n\n", "2026-09-27", "`## 정기 작업` 절이 없다"),
])
def test_format_problems_become_issues(text, day, needle):
    issues = rt.parse_daily_report(text, day=day)["issues"]
    assert any(needle in i for i in issues), issues


def test_report_before_the_supply_section_existed_is_not_a_drift():
    assert rt.parse_daily_report("# 리포트\n\n" + _OK_JOBS, day="2026-09-23")["issues"] == []
    assert rt.parse_daily_report("# 리포트\n\n" + _OK_JOBS)["issues"] == []            # 날짜 모름 → 판단 안 함


def test_known_unknown_mark_is_not_an_issue():
    text = ("## 공급 상태\n\n| 신호 | 상태 | 값 | 근거 |\n|---|---|---|---|\n| 엔카 시세 | ❔ 확인 불가 | — | x |\n\n"
            "## 정기 작업\n\n| 작업 | 결과 |\n|---|---|\n| 집 회선 터널 | ⏳ 진행 중 |\n| 주간 전문가 패널 | — 없음 |\n")
    p = rt.parse_daily_report(text, day="2026-09-27")
    assert p["issues"] == [] and p["supply"]["엔카 시세"]["state"] == "unknown"


def test_scan_warning_names_the_drifted_file(org):
    daily(org, "2026-09-26", {"물건 수집": "down"})
    daily(org, "2026-09-27", text=body({"물건 수집": "down"}).replace("🛑 멈춤", "멈춤"))
    r = org.scan(now=NOW)
    w = [x for x in r["warnings"] if "docs/daily-reports/2026-09-27.md" in x]
    assert len(w) == 1 and "물건 수집 '멈춤'" in w[0]
    assert not [x for x in r["warnings"] if "2026-09-26.md" in x]                  # 멀쩡한 리포트는 조용하다


def test_standup_lists_the_drift_under_unread(org):
    daily(org, "2026-09-27", text=body().replace("| 신호 | 상태 |", "| 신호 | 판정 |"))
    text = org.standup(now=NOW).read_text(encoding="utf-8")
    unread = text.split("## 읽지 못한 것")[1]
    assert "2026-09-27.md" in unread and "`상태` 열이 없다" in unread


def test_weekly_ops_section_flags_drifted_reports():
    import weekly_report as W                                                   # noqa: PLC0415
    good = rt.parse_daily_report(body(), day="2026-09-26")
    bad = rt.parse_daily_report(body().replace("✅ 정상", "정상"), day="2026-09-27")
    assert bad["issues"]
    md = "\n".join(W.ops_section({"reports": [("2026-09-26", good), ("2026-09-27", bad)], "missing": [],
                                  "tickets": {}}))
    line = next(ln for ln in md.splitlines() if "형식이 달라 못 읽었을 수 있는 리포트" in ln)
    assert "09-27(" in line and "09-26(" not in line
    clean = "\n".join(W.ops_section({"reports": [("2026-09-26", good)], "missing": [], "tickets": {}}))
    assert "형식이 달라" not in clean


# ════════════════════════════════════════════════════════════════════════
# ④ 건너뛴 모름은 숨기지 않는다
# ════════════════════════════════════════════════════════════════════════
def test_standup_line_shows_skipped_unknowns_between_and_after(org):
    daily(org, "2026-09-24", {"물건 수집": "down"})
    daily(org, "2026-09-25", late=True)
    daily(org, "2026-09-26", {"물건 수집": "down", "시세 0표본": "warn"})
    daily(org, "2026-09-27", late=True)
    text = org.standup(now=NOW).read_text(encoding="utf-8")
    sec = text.split("## 경보 → 티켓")[1].split("\n## ")[0]
    line = next(ln for ln in sec.splitlines() if "`물건 수집`" in ln)
    assert "사이의 ❔ 모름 1편은 세지 않음" in line and "그 뒤 ❔ 모름 1편(2026-09-27까지" in line
    z = next(ln for ln in sec.splitlines() if "`시세 0표본`" in ln)
    assert "1개 리포트 연속" in z and "기준 2개 전" in z and "사이의" not in z


def test_done_before_line_names_the_order(org):
    daily(org, "2026-09-26", {"물건 수집": "down"})
    daily(org, "2026-09-27", {"물건 수집": "down"})
    org.scan(now=NOW)
    oid = alerts_of(org)[0]["meta"]["id"]
    text = org.standup(now=NOW + timedelta(hours=1)).read_text(encoding="utf-8")
    line = next(ln for ln in text.split("## 경보 → 티켓")[1].splitlines() if "`물건 수집`" in ln)
    assert "이미 만들었다" in line and f"`{oid}`" in line


# ════════════════════════════════════════════════════════════════════════
# ⑤ 문서 ↔ 코드
# ════════════════════════════════════════════════════════════════════════
def _sec(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i:text.index(end, i)]


def test_contract_section3_says_what_r2_does():
    s3 = _sec((ROOT / "docs" / "org-contracts.md").read_text(encoding="utf-8"), "## 3.", "### 3.1")
    assert "alert_runs" in s3 and "✅ 정상 리포트가 끼기 전까지" in s3
    assert "연속을 끊는 것은 `✅` 정상 리포트뿐이다" in s3 and "14:00 넘어 만든 당일 리포트" in s3
    assert "**연속을 끊는다**" not in s3                                            # 옛 규칙 문언
    assert "최대 하루" not in s3
    assert "규칙은 **둘**" in s3 and "꺼짐(Disabled)" in s3 and "규칙 하나" not in s3
    assert "형식이 어긋난 리포트는 경고로" in s3
    row = next(ln for ln in s3.splitlines() if ln.startswith("| **예약 작업**"))
    assert "꺼짐(Disabled)" in row and "실행된 적 없음 · 예정도 없음" in row


def test_schedule_verdict_docstring_matches_the_two_extra_rules():
    doc = rt.schedule_verdict.__doc__
    assert "규칙 하나" not in doc and "둘" in doc
    assert rt.schedule_verdict({"ok": True, "next_run": ""}) == (True, "다음 실행 없음")               # ⓐ
    assert rt.schedule_verdict({"ok": True, "next_run": "x", "enabled": False}) == (True, "꺼짐(Disabled)")  # ⓑ


def test_daily_check_sop_does_not_promise_an_order_for_every_two_day_alert():
    dc = (ROOT / ".claude" / "commands" / "daily-check.md").read_text(encoding="utf-8")
    first = _sec(dc, "## 1.", "## 2.")
    assert "만들었을 것이다" not in first
    assert "열린 티켓이 없고" in first and "지시서가 없다고 문제가 없는 것은 아니다" in first
    assert "형식이 달라" in first
