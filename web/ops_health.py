"""공급 감시 판정 — "기록은 다 남는데 아무도 안 본다"를 판정으로 바꾼다.

2026-09-23 실측이 이 파일의 이유다.
  · 09-19~21 **사흘 연속 분석 0건**이었고 09-20 엔카 에러까지 찍혔는데 아무도 몰랐다.
    `runs.status` 가 전부 `done` 이라 **성공처럼 보였다.**
  · `kcar_checked_at` 이 09-05 에서 멈춘 채 18일이 지났는데 신호가 0이었다
    (홈 배너는 엔카만 본다).
→ 그래서 이 모듈의 첫 번째 규칙은 **`status='done'` 을 성공으로 읽지 않는다** 이다.

## 순수 함수다 — DB도 네트워크도 만지지 않는다
판정을 쓰는 자리가 셋이고 **보는 데이터가 서로 다르기** 때문이다.
  ① 매일 12시 리포트(`tools/daily_ops_report.py`) — ssh 로 **운영 서버**를 읽어 스냅샷을 만든다
  ② 사내 대시보드(`tools/agent_dashboard.py`) — ①이 남긴 스냅샷 파일을 읽는다
  ③ 웹 서비스(`web/service.py::supply_health`) — 자기 DB 를 읽는다
셋이 같은 결론을 내려면 판정이 한 곳에 있어야 한다. 그리고 **표준 라이브러리만** 쓴다 —
사내 도구가 `requests`·`yaml` 을 못 찾아 죽으면 감시가 먼저 멈춘다.

⚠ **로컬 `data/auction.db` 로 공급을 판정하지 마라.** 그 파일은 수집이 꺼진 개발 사본이라
  `max(collected_at)` 이 며칠씩 낡아 있다(2026-09-23 실측: 로컬 09-17 vs 운영 09-23).
  그 값으로 빨간불을 켜면 **매일 거짓 경보**가 뜨고, 그러면 사람은 경보를 안 보게 된다.
  대시보드가 스냅샷 파일을 읽는 이유가 이것이다.

## 임계의 단일 진실원천은 `config.yaml` 의 `ops_alert:` 다
아래 `_FALLBACK` 은 config 를 못 읽은 도구가 **조용히 통과하지 않도록** 두는 그물이고,
`tests/test_ops_health.py` 가 두 값이 갈라지지 않게 고정한다.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from typing import Optional

# 상태 4종. '판정 보류(unknown)'를 따로 두는 이유: 모르는 것을 초록으로 칠하지 않기 위해서다.
STATE_ORDER = {"ok": 0, "unknown": 1, "warn": 2, "down": 3}
STATE_LABEL = {"ok": "정상", "unknown": "확인 불가", "warn": "이상", "down": "멈춤"}

# config.yaml `ops_alert:` 가 단일 진실원천. 여기 값은 그 사본이 아니라 **비상용 그물**이다.
_FALLBACK = {
    "day_start_hour": 9,          # 이 시각 전에는 '오늘 갱신 전'이라 수집·실행을 판정하지 않는다
    "collect_stale_days": 1,      # 새 물건이 들어온 마지막 날이 오늘이 아니면 멈춤
    "analyze_zero_days": 2,       # 분석 0건이 이 일수만큼 연속 → 이상
    "analyze_down_days": 3,       # 이 일수만큼 연속 → 멈춤 (09-19~21 이 정확히 여기다)
    "analyze_stale_days": 3,      # 실행 기록을 못 읽을 때 쓰는 대체 신호(analyzed_at 신선도)
    "encar_stale_days": 2,        # 엔카 마지막 정상 확인이 이 일수 이상 전
    "kcar_stale_days": 7,         # 케이카 교차검증 기록이 이 일수 이상 없음
    "results_stale_days": 2,      # 낙찰결과 확인 기록이 이 일수 이상 없음
    "zero_sample_rise_pp": 2.0,   # 0표본 **비율**이 전일 대비 이만큼(%p) 오르면 이상
    "zero_sample_max_ratio": 0.40,  # 비율이 이 이상이면(=지금보다 나빠지면) 이상
    "history_days": 14,           # 0표본 추이를 몇 일치 보관하나
}

# 0표본의 정의는 **requery_missing_market 의 대상 조건과 같다** — 시세가 아예 없는 물건.
# 여기(표준 라이브러리 모듈)에 두는 이유: 운영 서버에서 ssh 로 돌리는 조회 스크립트
# (`tools/daily_ops_report.py`)와 앱(`web/service.py`)이 **같은 문장**을 써야 하기 때문이다.
# 두 곳이 갈라지면 '재조회 대상'과 '0표본 경보'가 서로 다른 수를 말한다.
ZERO_SAMPLE_SQL = ("select count(*) n from vehicles "
                   "where coalesce(sample_count, 0) = 0 and median_price is null")

_DAILY_SUMMARY = re.compile(r"^입찰예정 \d+ · 분석 \d+")
_ANALYZED_PART = re.compile(r"^분석 (\d+)$")
_CONFIG_NAME = "config.yaml"


def _read_config_file(path: Optional[str] = None) -> dict:
    """config.yaml 을 읽는다. 읽기 실패는 예외로 만들지 않는다(감시가 먼저 죽으면 안 된다)."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            _CONFIG_NAME)
    try:
        import yaml  # noqa: PLC0415 — 표준 라이브러리만으로도 돌아야 하므로 지연 임포트
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:  # noqa: BLE001
        return {}


def load_thresholds(config: Optional[dict] = None) -> dict:
    """임계 묶음. `config.yaml: ops_alert` 가 단일 진실원천이고 여기서 덮어쓴다."""
    if config is None:
        config = _read_config_file()
    th = dict(_FALLBACK)
    for k, v in ((config or {}).get("ops_alert") or {}).items():
        if k in _FALLBACK and v is not None:
            th[k] = v
    return th


# ── 작은 도구들 ────────────────────────────────────────────────────
def _as_date(value) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value or "")[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def stale_days(value, today: date) -> Optional[int]:
    """기록 시각이 오늘보다 며칠 낡았나. 0=오늘. 읽을 수 없으면 None."""
    d = _as_date(value)
    return None if d is None else (today - d).days


def parse_analyzed(message: Optional[str]) -> Optional[int]:
    """매일 갱신 요약에서 분석 건수만 꺼낸다. 요약이 아니면 None(=0건이 아니라 **모름**).

    ⚠ 0 과 None 을 섞으면 끊긴 실행이 '분석 0건 연속'으로 둔갑한다.
    """
    for part in str(message or "").split(" · "):
        m = _ANALYZED_PART.match(part.strip())
        if m:
            return int(m.group(1))
    return None


def warn_parts(message: Optional[str]) -> list:
    """요약 안의 ⚠ 조각들. `status='done'` 이어도 여기에 사고가 적혀 있다(09-20 엔카 error)."""
    return [p.strip() for p in str(message or "").split(" · ") if "⚠" in p]


def daily_runs(runs) -> list:
    """날짜별 '그날의 정기 갱신 1건'(오래된 → 최신).

    같은 날 수동 실행이 섞이면 **매일 갱신 요약이 있는 기록**을 그날의 대표로 본다
    (`tools/daily_ops_report.py::is_daily_summary` 와 같은 기준). 둘 다 요약이면 늦은 쪽.
    """
    by_day: dict = {}
    for r in runs or []:
        day = str(r.get("started_at") or "")[:10]
        if not day:
            continue
        cur = by_day.get(day)
        if cur is None:
            by_day[day] = r
            continue
        cur_sum = bool(_DAILY_SUMMARY.match(str(cur.get("message") or "")))
        new_sum = bool(_DAILY_SUMMARY.match(str(r.get("message") or "")))
        if new_sum and not cur_sum:
            by_day[day] = r
        elif new_sum == cur_sum and str(r.get("started_at") or "") > str(cur.get("started_at") or ""):
            by_day[day] = r
    return [by_day[d] for d in sorted(by_day)]


def zero_streak(runs) -> tuple:
    """최신 날짜부터 세어 **분석 0건이 며칠 연속**인가. (연속일수, 마지막으로 본 날짜들).

    기록을 못 읽는 날(요약 없음)을 만나면 **거기서 멈춘다** — 모르는 날을 0건으로 세지 않는다.
    """
    days_hit = []
    for r in reversed(daily_runs(runs)):
        n = parse_analyzed(r.get("message"))
        if n is None or n > 0:
            break
        days_hit.append(str(r.get("started_at") or "")[:10])
    return len(days_hit), list(reversed(days_hit))


def worst(states) -> str:
    out = "ok"
    for s in states:
        if STATE_ORDER.get(s, 1) > STATE_ORDER.get(out, 0):
            out = s
    return out


def _sig(key: str, label: str, state: str, head: str, detail: str = "", **extra) -> dict:
    row = {"key": key, "label": label, "state": state, "head": head, "detail": detail}
    row.update(extra)
    return row


# ── 판정 ──────────────────────────────────────────────────────────
def evaluate(snapshot: dict, thresholds: Optional[dict] = None,
             now: Optional[datetime] = None) -> dict:
    """공급 스냅샷 → 신호별 판정.

    snapshot 키(전부 선택 — 없으면 '확인 불가'로 떨어진다):
      collected_at / analyzed_at / result_checked_at / kcar_checked_at : 'YYYY-MM-DD HH:MM:SS'
      encar_state / encar_code / encar_ok_at : settings 값
      daily_enabled : '1' | '0'
      runs : [{started_at, status, message}] — 최근 며칠치(순서 무관)
      zero_sample : {"zero": int, "total": int}
      zero_history : [{"date","zero","total"}] — 전일 비교용(오늘 것은 무시한다)
      source : 화면에 적을 출처 문구(예: '운영 서버')
    """
    th = thresholds if thresholds is not None else load_thresholds()
    now = now or datetime.now()
    today = now.date()
    signals = []

    # ① 수집 — 새 물건이 오늘 들어왔나
    st = snapshot.get("collected_at")
    d = stale_days(st, today)
    if d is None:
        signals.append(_sig("collect", "물건 수집", "unknown", "기록 없음",
                            "collected_at 을 읽지 못했다", stale_days=None))
    elif d < int(th["collect_stale_days"]):
        signals.append(_sig("collect", "물건 수집", "ok", f"{str(st)[:16]}",
                            "오늘 새 물건이 들어왔다", stale_days=d))
    elif now.hour < int(th["day_start_hour"]):
        signals.append(_sig("collect", "물건 수집", "unknown", f"{d}일 전",
                            f"오늘 정기 갱신({th['day_start_hour']}시) 전이라 판정을 미룬다", stale_days=d))
    else:
        signals.append(_sig("collect", "물건 수집", "down", f"{d}일째 없음",
                            f"마지막 수집 {str(st)[:16]} — 새 물건이 {d}일째 들어오지 않는다",
                            stale_days=d))

    # ② 분석 — status 가 아니라 **건수**를 본다(09-19~21 은 전부 done 이었다)
    streak, streak_days = zero_streak(snapshot.get("runs"))
    a_stale = stale_days(snapshot.get("analyzed_at"), today)
    span = f"{streak_days[0]}~{streak_days[-1]}" if len(streak_days) > 1 else (streak_days[0] if streak_days else "")
    if streak >= int(th["analyze_down_days"]):
        signals.append(_sig("analyze", "시세 분석", "down", f"0건 {streak}일 연속",
                            f"{span} 실행이 모두 done 인데 분석은 0건이다", streak=streak))
    elif streak >= int(th["analyze_zero_days"]):
        signals.append(_sig("analyze", "시세 분석", "warn", f"0건 {streak}일 연속",
                            f"{span} 분석 0건 — 새 물건이 산정까지 가지 못하고 있다", streak=streak))
    elif not daily_runs(snapshot.get("runs")):
        if a_stale is None:
            signals.append(_sig("analyze", "시세 분석", "unknown", "기록 없음",
                                "실행 기록도 analyzed_at 도 읽지 못했다", streak=streak))
        elif a_stale >= int(th["analyze_stale_days"]):
            signals.append(_sig("analyze", "시세 분석", "warn", f"{a_stale}일 전",
                                "실행 기록이 없어 analyzed_at 으로 대신 판정했다", streak=streak))
        else:
            signals.append(_sig("analyze", "시세 분석", "ok", f"{a_stale}일 전",
                                "실행 기록은 없지만 분석 시각은 최근이다", streak=streak))
    else:
        last_n = parse_analyzed(daily_runs(snapshot.get("runs"))[-1].get("message"))
        signals.append(_sig("analyze", "시세 분석", "ok",
                            "모름" if last_n is None else f"{last_n}건",
                            f"직전 갱신 분석 {last_n}건" if last_n is not None
                            else "직전 갱신의 분석 건수를 읽지 못했다(요약 없음)", streak=streak))

    # ③ 엔카 — 이미 있던 신호를 같은 판정 안으로 들여온다
    e_state = str(snapshot.get("encar_state") or "")
    e_code = snapshot.get("encar_code") or ""
    e_stale = stale_days(snapshot.get("encar_ok_at"), today)
    if not e_state or e_state == "unknown":
        signals.append(_sig("encar", "엔카 시세", "unknown", "기록 없음",
                            "encar_health_state 를 읽지 못했다", stale_days=e_stale))
    elif e_state != "ok":
        signals.append(_sig("encar", "엔카 시세", "down", f"{e_state}(HTTP {e_code})",
                            "엔카 조회가 막혔다 — 시세 분석 단계가 통째로 건너뛰어진다",
                            stale_days=e_stale))
    elif e_stale is not None and e_stale >= int(th["encar_stale_days"]):
        signals.append(_sig("encar", "엔카 시세", "warn", f"정상 확인 {e_stale}일 전",
                            "상태는 ok 인데 마지막 정상 확인이 오래됐다", stale_days=e_stale))
    else:
        signals.append(_sig("encar", "엔카 시세", "ok", f"ok(HTTP {e_code})",
                            f"마지막 정상 확인 {str(snapshot.get('encar_ok_at') or '')[:16]}",
                            stale_days=e_stale))

    # ④ 케이카 — 18일 멈추고도 신호가 0이었던 자리
    #    수집 시도 결과(kcar_state)가 있으면 **사유까지** 붙인다. 없으면 신선도만 본다.
    k_stale = stale_days(snapshot.get("kcar_checked_at"), today)
    k_state = str(snapshot.get("kcar_state") or "")
    # '수집이 되는가'만 본다 — error/blocked 만 실패다. skipped(표본 부족·대상 아님)는 정상 결과다.
    k_bad = k_state in ("error", "blocked")
    k_why = ""
    if k_bad:
        k_why = (f" · 마지막 시도 {k_state}"
                 f"({str(snapshot.get('kcar_msg') or '')[:80]}, {str(snapshot.get('kcar_state_at') or '')[:16]})")
    if k_stale is None:
        signals.append(_sig("kcar", "케이카 교차검증", "warn", "기록 없음",
                            "kcar_checked_at 이 한 건도 없다 — 2소스 표기의 근거가 없다" + k_why,
                            stale_days=None, kcar_state=k_state or None))
    elif k_stale >= int(th["kcar_stale_days"]):
        signals.append(_sig("kcar", "케이카 교차검증", "warn", f"{k_stale}일째 없음",
                            f"마지막 교차검증 {str(snapshot.get('kcar_checked_at') or '')[:16]} — "
                            "자동 경로가 없어 사람이 돌릴 때만 갱신된다" + k_why,
                            stale_days=k_stale, kcar_state=k_state or None))
    elif k_bad:
        signals.append(_sig("kcar", "케이카 교차검증", "warn", f"{k_stale}일 전",
                            f"기록은 최근인데 마지막 수집 시도가 실패했다{k_why}",
                            stale_days=k_stale, kcar_state=k_state))
    else:
        signals.append(_sig("kcar", "케이카 교차검증", "ok", f"{k_stale}일 전",
                            str(snapshot.get("kcar_checked_at") or "")[:16],
                            stale_days=k_stale, kcar_state=k_state or None))

    # ⑤ 낙찰결과 — 백테스트·적중률의 원천이라 멈추면 정확도 근거가 늙는다
    r_stale = stale_days(snapshot.get("result_checked_at"), today)
    if r_stale is None:
        signals.append(_sig("results", "낙찰결과", "unknown", "기록 없음",
                            "result_checked_at 을 읽지 못했다", stale_days=None))
    elif r_stale >= int(th["results_stale_days"]):
        signals.append(_sig("results", "낙찰결과", "warn", f"{r_stale}일째 없음",
                            "낙찰결과 반영이 멈추면 적중률 근거가 갱신되지 않는다", stale_days=r_stale))
    else:
        signals.append(_sig("results", "낙찰결과", "ok", f"{r_stale}일 전",
                            str(snapshot.get("result_checked_at") or "")[:16], stale_days=r_stale))

    # ⑥ 0표본 — **비율**로 판정하고 절대 수 증감은 함께 적는다(둘이 반대로 움직인다)
    signals.append(_zero_sample_signal(snapshot, th, today))

    # ⑦ 실행 기록 — done 을 성공으로 읽지 않는다
    signals.append(_runs_signal(snapshot, th, now))

    state = worst(s["state"] for s in signals)
    alerts = [s for s in signals if s["state"] in ("down", "warn")]
    alerts.sort(key=lambda s: -STATE_ORDER[s["state"]])
    return {
        "state": state,
        "label": STATE_LABEL[state],
        "checked_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "source": snapshot.get("source") or "",
        "signals": signals,
        "alerts": alerts,
        "headline": headline(state, alerts),
    }


def _zero_sample_signal(snapshot: dict, th: dict, today: date) -> dict:
    z = snapshot.get("zero_sample") or {}
    zero, total = z.get("zero"), z.get("total")
    if not total:
        return _sig("zero_sample", "시세 0표본", "unknown", "기록 없음",
                    "0표본 집계를 읽지 못했다")
    ratio = zero / total
    head = f"{zero:,}/{total:,} ({ratio * 100:.0f}%)"
    prev = None
    for row in sorted(snapshot.get("zero_history") or [], key=lambda r: str(r.get("date") or "")):
        if str(row.get("date") or "")[:10] < today.isoformat() and row.get("total"):
            prev = row
    if prev is None:
        state = "warn" if ratio >= float(th["zero_sample_max_ratio"]) else "ok"
        return _sig("zero_sample", "시세 0표본", state, head,
                    "비교할 전일 기록이 없다 — 절대 비율로만 판정했다", ratio=ratio, delta_pp=None)
    p_ratio = prev["zero"] / prev["total"]
    d_pp = (ratio - p_ratio) * 100
    d_abs = zero - prev["zero"]
    tail = (f"전일 {prev['zero']:,}/{prev['total']:,}({p_ratio * 100:.0f}%) 대비 "
            f"비율 {d_pp:+.1f}%p · 건수 {d_abs:+,}")
    if d_pp >= float(th["zero_sample_rise_pp"]):
        return _sig("zero_sample", "시세 0표본", "warn", head,
                    f"0표본 비율이 올랐다 — {tail}", ratio=ratio, delta_pp=d_pp, delta_abs=d_abs)
    if ratio >= float(th["zero_sample_max_ratio"]):
        return _sig("zero_sample", "시세 0표본", "warn", head,
                    f"비율이 상한 {float(th['zero_sample_max_ratio']) * 100:.0f}% 를 넘었다 — {tail}",
                    ratio=ratio, delta_pp=d_pp, delta_abs=d_abs)
    return _sig("zero_sample", "시세 0표본", "ok", head, tail,
                ratio=ratio, delta_pp=d_pp, delta_abs=d_abs)


def _runs_signal(snapshot: dict, th: dict, now: datetime) -> dict:
    enabled = str(snapshot.get("daily_enabled") if snapshot.get("daily_enabled") is not None else "")
    if enabled in ("0", "False", "false"):
        return _sig("runs", "실행 기록", "down", "자동 갱신 꺼짐",
                    "daily_enabled=0 — 매일 갱신 스케줄러가 돌지 않는다")
    runs = daily_runs(snapshot.get("runs"))
    if not runs:
        if now.hour < int(th["day_start_hour"]):
            return _sig("runs", "실행 기록", "unknown", "기록 없음", "오늘 정기 갱신 전이다")
        return _sig("runs", "실행 기록", "unknown", "기록 없음",
                    "최근 실행 기록을 읽지 못했다")
    last = runs[-1]
    day = str(last.get("started_at") or "")[:10]
    status = str(last.get("status") or "")
    msg = str(last.get("message") or "")
    if day != now.date().isoformat() and now.hour >= int(th["day_start_hour"]):
        return _sig("runs", "실행 기록", "down", f"마지막 {day}",
                    "오늘 정기 갱신 기록이 없다", run_status=status)
    if status == "error":
        return _sig("runs", "실행 기록", "down", "error",
                    f"{day} 실행이 오류로 끝났다 — {msg[:80]}", run_status=status)
    if status == "running":
        return _sig("runs", "실행 기록", "unknown", "진행 중",
                    f"{day} 실행이 아직 돌고 있다 — {msg[:80]}", run_status=status)
    w = warn_parts(msg)
    if w:
        return _sig("runs", "실행 기록", "warn", "done(경고 포함)",
                    f"{day} 기록에 경고가 있다 — {' · '.join(w)[:120]}", run_status=status)
    return _sig("runs", "실행 기록", "ok", f"{day} done", msg[:90], run_status=status)


def headline(state: str, alerts: list, limit: int = 3) -> str:
    """한 줄 요약. limit 으로 몇 건까지 이름을 부를지 정한다(요약 줄은 1건 + '외 N건')."""
    if state == "ok":
        return "공급 이상 없음"
    if not alerts:
        return f"공급 상태 {STATE_LABEL.get(state, state)}"
    names = " · ".join(f"{a['label']} {a['head']}" for a in alerts[:limit])
    more = f" 외 {len(alerts) - limit}건" if len(alerts) > limit else ""
    return f"{names}{more}"
