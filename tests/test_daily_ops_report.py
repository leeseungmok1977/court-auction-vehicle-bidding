"""매일 12시 작업 결과 리포트(tools/daily_ops_report.py) — 네트워크 없이 해석·작성 규칙만 검증.

리포트가 틀리면 안 되는 지점:
  - 서버 기록은 0건인 단계를 문장에서 뺀다 → 빠진 단계를 '성공'으로 부풀리면 안 된다.
  - 중간에 끊긴 실행은 마지막 진행 메시지만 남는다 → 멈춘 단계를 짚고 뒤 단계는 '미실행'이어야 한다.
  - 읽지 못한 곳은 '확인 불가'로 — 모르는 것을 성공으로 적지 않는다.
  - 리포트는 저장소에 남는 문서라 서버 주소·키 경로가 새면 안 된다.
실제 서버 기록 문장(2026-09-13·14·15)을 그대로 픽스처로 쓴다.
"""
import importlib.util
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("daily_ops_report", ROOT / "tools" / "daily_ops_report.py")
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

MSG_0915 = ("입찰예정 441 · 분석 32 · 동급참조 22 · 출시가 3건(대기 282) · 사진정렬 49건 · "
            "낙찰결과 256건 · ⚠엔카 error(HTTP None)")
MSG_0913 = "입찰예정 436 · 분석 1 · 출시가 19건(대기 213) · 낙찰결과 218건"
MSG_0914_INTERRUPTED = "당시 출시가 범위 수집(보배드림) (서버 재시작으로 중단됨)"


def _run(started, status, msg, finished=None):
    return {"id": 1, "started_at": started, "finished_at": finished, "status": status,
            "scanned": 0, "processed": 0, "target": 0, "message": msg}


def _status(rows, step):
    return next(r for r in rows if r["step"] == step)


# ── 기간 ──
def test_window_is_previous_noon_to_noon():
    since, until = R.report_window(date(2026, 9, 16))
    assert since == datetime(2026, 9, 15, 12, 0) and until == datetime(2026, 9, 16, 12, 0)


def test_weekly_due_only_when_the_slot_falls_inside_the_window():
    fri_sat = R.report_window(date(2026, 9, 19))          # 금 12:00 ~ 토 12:00
    assert R.weekly_due(*fri_sat, R.PANEL_WEEKDAY, *R.PANEL_AT) == datetime(2026, 9, 19, 9, 20)
    sat_sun = R.report_window(date(2026, 9, 20))          # 토 12:00 ~ 일 12:00 — 토 09:20 은 이미 지남
    assert R.weekly_due(*sat_sun, R.PANEL_WEEKDAY, *R.PANEL_AT) is None
    assert R.weekly_due(*sat_sun, R.PHOTO_WEEKDAY, *R.PHOTO_AT) == datetime(2026, 9, 20, 8, 17)


# ── 서버 기록 해석 ──
def test_parse_real_daily_summary():
    p = R.parse_daily_message(MSG_0915)
    assert p["stored"] == 441 and p["analyzed"] == 32 and p["reuse"] == 22
    assert p["newcar"] == (3, 282) and p["photos"] == 49 and p["results"] == 256
    assert p["encar"] == ("error", "None") and p["unknown"] == []


def test_parse_review_requery_and_photo_skip():
    p = R.parse_daily_message("입찰예정 400 · 분석 5 · 0표본 재조회 7 · ⚠사진정렬 건너뜀 · "
                              "낙찰결과 10건 · 검토 재확인 3(복원 2·보류 1)")
    assert p["requery"] == 7 and p["photos_skipped"] is True and p["review"] == (3, 2, 1)


def test_unknown_fragments_are_kept_not_dropped():
    p = R.parse_daily_message("입찰예정 1 · 분석 0 · 새 단계 5건 · 낙찰결과 0건")
    assert p["unknown"] == ["새 단계 5건"]


def test_encar_failure_is_a_failed_step_and_the_run_a_warning():
    rows = R.daily_steps(_run("2026-09-15 06:30:50", "done", MSG_0915, "2026-09-15 07:10:03"))
    assert _status(rows, "엔카 시세 조회 연결")["status"] == R.FAIL
    assert _status(rows, "시세 분석")["status"] == R.WARN
    assert _status(rows, "낙찰결과 반영") == {"step": "낙찰결과 반영", "count": "256건", "status": R.OK}
    assert _status(rows, "사진 자동 정렬")["count"] == "49건"


def test_absent_steps_are_zero_not_success():
    """서버는 0건 단계를 문장에서 뺀다 — 빠진 단계를 ✅로 적으면 일을 한 것처럼 부풀린다."""
    rows = R.daily_steps(_run("2026-09-13 06:30:31", "done", MSG_0913, "2026-09-13 07:02:05"))
    for step in ("동급 시세 참조 보완", "사진 자동 정렬", "0표본 차종 재조회"):
        assert _status(rows, step) == {"step": step, "count": "0건", "status": R.NA}, step
    assert _status(rows, "엔카 시세 조회 연결")["status"] == R.OK


def test_interrupted_run_points_at_the_step_where_it_stopped():
    rows = R.daily_steps(_run("2026-09-14 06:30:22", "error", MSG_0914_INTERRUPTED, "2026-09-14 07:02:37"))
    assert _status(rows, "시세 분석")["status"] == R.OK            # 앞 단계는 지나갔다
    assert _status(rows, "당시 출시가 수집")["status"] == R.FAIL   # 여기서 멈췄다
    assert _status(rows, "사진 자동 정렬")["status"] == R.SKIP     # 뒤는 돌지 않았다
    assert _status(rows, "낙찰결과 반영")["status"] == R.SKIP
    assert R.daily_counts(_run("x", "error", MSG_0914_INTERRUPTED)) == "당시 출시가 수집 단계에서 멈춤"


def test_scheduled_run_is_the_first_one_within_15_minutes_of_the_slot():
    until = datetime(2026, 9, 23, 12, 0)
    runs = [_run("2026-09-22 23:10:00", "done", "재분석 완료 0건 / 대상 7건"),
            _run("2026-09-23 06:30:10", "done", MSG_0913),
            _run("2026-09-23 07:46:26", "done", "입찰예정 480 · 분석 0 · 낙찰결과 136건")]
    due, sched, manual = R.split_runs(runs, until, "06:30")
    assert due == datetime(2026, 9, 23, 6, 30) and sched["started_at"].startswith("2026-09-23 06:30")
    assert [R.run_kind(m["message"]) for m in manual] == ["시세 재분석", "매일 갱신(수동)"]


# ── PC 로그 해석 ──
def test_photo_log_with_mixed_utf8_and_utf16_reads_the_latest_count():
    """실제 로그가 UTF-8 뒤에 UTF-16이 덧붙어 있다(PowerShell 5.1 Tee-Object -Append) — 9/13 기록을 놓칠 뻔했다."""
    raw = ("2026-09-06 08:29:04    UNCLASSIFIED=0\n".encode("utf-8")
           + "2026-09-13 08:17:02    UNCLASSIFIED=5\r\n".encode("utf-16-le"))
    assert R.last_unclassified(raw) == ("2026-09-13 08:17:02", 5)
    odd = b"x" + raw                                               # UTF-16 부분이 홀수 바이트에서 시작해도
    assert R.last_unclassified(odd) == ("2026-09-13 08:17:02", 5)


def test_tunnel_log_counts_only_inside_the_window():
    text = "\n".join([
        "[2026-09-15 11:00:00] tunnel closed (exit 255) - retry in 15s",     # 기간 밖
        "[2026-09-16 05:24:43] service start (user=14ZB95N, key exists=True)",
        "[2026-09-16 05:24:47] tunnel connecting",
        "[2026-09-16 09:00:00] tunnel closed (exit 255) - retry in 15s",
        "[2026-09-16 09:00:15] tunnel connecting",
    ])
    ev = R.tunnel_events(text, *R.report_window(date(2026, 9, 16)))
    assert ev["closed"] == 1 and ev["connecting"] == 2 and ev["service_start"] == 1


def test_remote_script_injects_dates_only_as_string_literals():
    s = R.remote_script(datetime(2026, 9, 15, 12, 0), datetime(2026, 9, 16, 12, 0))
    assert 'SINCE = "2026-09-15 12:00:00"' in s and 'UNTIL = "2026-09-16 12:00:00"' in s
    assert "__SINCE__" not in s and "__UNTIL__" not in s


# ── 리포트 작성 ──
def _data(**over):
    since, until = R.report_window(date(2026, 9, 16))
    d = {
        "since": since, "until": until, "generated": datetime(2026, 9, 16, 12, 0, 5),
        "server": {"runs": [_run("2026-09-16 06:30:10", "done", MSG_0913, "2026-09-16 07:01:00")],
                   "settings": {"daily_time": "06:30", "daily_enabled": "1", "encar_health_state": "ok",
                                "encar_health_ok_at": "2026-09-16 06:31:00"},
                   "certbot": {"started": 2, "finished": 2, "failed": 0},
                   "service": {"active": "active", "since": ""}},
        "tasks": {R.PHOTO_TASK: {"state": "Ready", "last": "2026-09-13 08:17:00", "next": "", "result": 0},
                  R.TUNNEL_TASK: {"state": "Running", "last": "2026-09-16 05:24:43", "next": "", "result": 267009}},
        "panel": {"commits": []},
        "photo_log": {"at": "2026-09-13 08:17:02", "count": 0},
        "tunnel_log": {"connecting": 1, "closed": 0, "service_start": 1, "last": None},
    }
    d.update(over)
    return d


def test_ordinary_day_has_every_job_and_no_failure():
    md = R.build_markdown(_data())
    for job in ("매일 시세·낙찰 갱신", "SSL 인증서 갱신 확인", "주간 전문가 패널", "사진 미분류 점검", "집 회선 터널"):
        assert f"| {job} |" in md, job
    assert "기간** 2026-09-15 12:00 ~ 2026-09-16 12:00" in md
    assert "성공 3 · 경고 0 · 실패 0 · 진행 중 0 · 확인 불가 0" in md     # 주간 작업 둘은 이번 기간 예정 없음
    assert "입찰예정 436 · 분석 1 · 낙찰결과 218" in md
    assert "| 이번 기간 예정 없음 |" in md


def test_unreadable_server_is_reported_as_unknown_not_success():
    md = R.build_markdown(_data(server={"error": "서버 조회 실패(코드 255): timeout"}))
    assert "## 확인 불가" in md and "운영 서버: 서버 조회 실패" in md
    assert "| 매일 시세·낙찰 갱신 | 운영 서버 | 매일 06:30 | — | — | ❔ 확인 불가 |" in md
    assert "확인 불가 2" in md                                        # 매일 갱신·SSL


def test_missing_daily_run_after_the_slot_is_a_failure():
    d = _data()
    d["server"]["runs"] = []
    md = R.build_markdown(d)
    assert "| 매일 시세·낙찰 갱신 | 운영 서버 | 매일 06:30 | 실행 기록 없음 | — | ❌ 실패 |" in md


def test_weekly_panel_without_commit_is_a_failure_on_its_day():
    since, until = R.report_window(date(2026, 9, 19))
    d = _data(since=since, until=until, generated=datetime(2026, 9, 19, 12, 0))
    d["server"]["runs"] = []
    assert "| 주간 전문가 패널 | 클라우드 루틴 | 매주 토 09:20 | 리포트 커밋 없음 | — | ❌ 실패 |" in R.build_markdown(d)
    d["panel"] = {"commits": [{"hash": "abc", "at": "2026-09-19 10:05",
                               "subject": "docs(주간평가): 6회차 — 중고차 83 / 디자인 81"}]}
    assert "리포트 커밋 10:05" in R.build_markdown(d)


def test_tunnel_down_or_encar_error_is_a_failure():
    d = _data()
    d["server"]["settings"]["encar_health_state"] = "error"
    assert "| 집 회선 터널 |" in (md := R.build_markdown(d)) and "엔카 error" in md
    row = next(line for line in md.splitlines() if line.startswith("| 집 회선 터널 |"))
    assert row.endswith("❌ 실패 |")


def test_report_never_contains_the_server_address_or_key_path():
    d = _data(server={"error": R._scrub(f"ssh {R.SERVER} -i {R.KEY} failed")})
    md = R.build_markdown(d)
    assert R.SERVER.split("@")[-1] not in md and R.KEY.name not in md and str(R.KEY) not in md


def test_manual_runs_are_listed_separately():
    d = _data()
    d["server"]["runs"].append(_run("2026-09-16 10:58:48", "done", "시세 재교정 482건 · 케이카 0회 조회"))
    md = R.build_markdown(d)
    assert "## 수동 실행" in md and "| 09-16 10:58 | 시세 재교정 |" in md


def test_past_date_report_judges_the_tunnel_from_that_days_run_not_from_now():
    """지난 날짜 리포트에 '지금'의 터널·엔카 상태를 쓰면, 터널이 꺼져 있던 9/15를 정상으로 적는다(드라이런에서 실제 발생)."""
    since, until = R.report_window(date(2026, 9, 15))
    d = _data(since=since, until=until, generated=datetime(2026, 9, 16, 5, 48))   # 지금 값은 작업 Running · 엔카 ok
    d["server"]["runs"] = [_run("2026-09-15 06:30:50", "done", MSG_0915, "2026-09-15 07:10:03")]
    row = next(line for line in R.build_markdown(d).splitlines() if line.startswith("| 집 회선 터널 |"))
    assert "그날 06:30 엔카 error" in row and "지난 기간" in row and row.endswith("❌ 실패 |"), row
    d["server"]["runs"] = [_run("2026-09-15 06:30:50", "done", MSG_0913, "2026-09-15 07:02:00")]
    row = next(line for line in R.build_markdown(d).splitlines() if line.startswith("| 집 회선 터널 |"))
    assert "그날 06:30 엔카 정상" in row and row.endswith("✅ 성공 |"), row


# ── 2026-09-16 변경: 출시가 수집을 맨 뒤로 + 멈춘 사유 기록 ──
MSG_NEW_BUDGET = ("입찰예정 450 · 분석 20 · 동급참조 5 · 사진정렬 12건 · 낙찰결과 240건 · "
                  "출시가 61건(대기 207·예산 2400 소진)")
MSG_NEW_BLOCKED = "입찰예정 450 · 분석 20 · 낙찰결과 240건 · 출시가 2건(대기 266·⚠차단 HTTP 403)"
MSG_NEW_COLLECTING = "입찰예정 450 · 분석 20 · 낙찰결과 240건 · 출시가 수집 중"


def test_release_price_token_carries_the_stop_reason():
    p = R.parse_daily_message(MSG_NEW_BUDGET)
    assert p["newcar"] == (61, 207) and p["newcar_why"] == "예산 2400 소진" and p["unknown"] == []
    assert R.parse_daily_message(MSG_0913)["newcar"] == (19, 213)          # 옛 형식도 그대로 읽는다


def test_budget_exhaustion_is_normal_but_a_block_is_a_failure():
    """예산 소진은 백필을 여러 날에 나눠 도는 정상 동작 — 차단·오류만 실패."""
    rows = R.daily_steps(_run("2026-09-17 06:30:10", "done", MSG_NEW_BUDGET, "2026-09-17 09:40:00"))
    assert rows[-1]["step"] == "당시 출시가 수집", "출시가 수집은 맨 뒤 단계다"
    assert rows[-1]["status"] == R.OK and "예산 2400 소진" in rows[-1]["count"]
    blocked = R.daily_steps(_run("2026-09-17 06:30:10", "done", MSG_NEW_BLOCKED, "2026-09-17 07:20:00"))
    assert blocked[-1]["status"] == R.FAIL and "차단 HTTP 403" in blocked[-1]["count"]


def test_run_cut_during_release_price_collection_keeps_earlier_counts():
    """긴 수집 전에 요약을 먼저 남기므로, 재시작으로 끊겨도 앞 단계 건수는 남는다 — 갱신 전체를 실패로 적지 않는다."""
    cut = _run("2026-09-16 06:30:10", "error", MSG_NEW_COLLECTING + " (서버 재시작으로 중단됨)", "2026-09-16 08:00:00")
    rows = R.daily_steps(cut)
    assert _status(rows, "낙찰결과 반영") == {"step": "낙찰결과 반영", "count": "240건", "status": R.OK}
    assert _status(rows, "당시 출시가 수집")["status"] == R.FAIL
    assert R.daily_counts(cut) == "입찰예정 450 · 분석 20 · 낙찰결과 240 · 출시가 수집 중 끊김"
    d = _data()
    d["server"]["runs"] = [cut]
    row = next(line for line in R.build_markdown(d).splitlines() if line.startswith("| 매일 시세·낙찰 갱신 |"))
    assert row.endswith("⚠️ 경고 |"), row


def test_run_still_collecting_at_report_time_is_in_progress():
    live = _run("2026-09-16 06:30:10", "running", MSG_NEW_COLLECTING)
    assert _status(R.daily_steps(live), "당시 출시가 수집")["status"] == R.RUNNING
    d = _data()
    d["server"]["runs"] = [live]
    row = next(line for line in R.build_markdown(d).splitlines() if line.startswith("| 매일 시세·낙찰 갱신 |"))
    assert row.endswith("⏳ 진행 중 |") and "출시가 수집 중" in row, row
