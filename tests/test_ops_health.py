"""공급 감시 판정 회귀 — **정상과 이상 양쪽을 다 단언한다.**

한쪽만 있으면 공허하다(PANEL-39·46 에서 반복 확인된 교훈). 그래서 이 파일은 같은 규칙을
두 번씩 민다: ① 정상 데이터에서 '이상 없음'이 나오는가 ② 2026-09-19~21 실측을 그대로 넣으면
'이상'이 나오는가.

09-19~21 이 이 파일의 이유다 — 운영 `runs` 세 줄이 **전부 `status='done'`** 이었고
09-20 에는 `⚠엔카 error(HTTP None)` 까지 찍혔는데 아무도 몰랐다.
"""
from datetime import datetime

import pytest

from web import ops_health as oh

TH = oh.load_thresholds()

# 2026-09-19~21 운영 실측 원문(Steward 가 운영 서버에서 읽어 지시서에 옮긴 값 그대로).
RUNS_0919_21 = [
    {"started_at": "2026-09-19 06:30:00", "status": "done",
     "message": "입찰예정 410 · 분석 0 · 낙찰결과 167건"},
    {"started_at": "2026-09-20 06:30:00", "status": "done",
     "message": "입찰예정 410 · 분석 0 · 낙찰결과 158건 · ⚠엔카 error(HTTP None)"},
    {"started_at": "2026-09-21 06:30:00", "status": "done",
     "message": "입찰예정 410 · 분석 0 · 0표본 재조회 8 · 낙찰결과 158건"},
]
# 09-22~23 실측(정상으로 돌아온 이틀).
RUNS_OK = [
    {"started_at": "2026-09-22 06:30:00", "status": "done",
     "message": "입찰예정 390 · 분석 28 · 동급참조 5 · 0표본 재조회 15 · 사진정렬 28건 · 낙찰결과 197건"},
    {"started_at": "2026-09-23 06:30:00", "status": "done",
     "message": "입찰예정 396 · 분석 21 · 동급참조 2 · 0표본 재조회 15 · 사진정렬 17건 · 낙찰결과 190건"},
]

NOON = datetime(2026, 9, 23, 12, 0, 0)


def _snap(**over) -> dict:
    """오늘(09-23) 기준 **정상** 스냅샷. 각 테스트는 필요한 축만 망가뜨린다."""
    snap = {
        "collected_at": "2026-09-23 06:35:30",
        "analyzed_at": "2026-09-23 06:37:33",
        "result_checked_at": "2026-09-23 06:42:47",
        "kcar_checked_at": "2026-09-23 06:40:00",
        "encar_state": "ok", "encar_code": "200", "encar_ok_at": "2026-09-23 06:31:28",
        "daily_enabled": "1",
        "runs": list(RUNS_OK),
        "zero_sample": {"zero": 530, "total": 1472},
        "zero_history": [{"date": "2026-09-22", "zero": 540, "total": 1470}],
    }
    snap.update(over)
    return snap


def _sig(res: dict, key: str) -> dict:
    return next(s for s in res["signals"] if s["key"] == key)


# ── ① 정상 쪽: 이상이 없으면 조용해야 한다 ─────────────────────────────
def test_정상_데이터면_이상_없음():
    res = oh.evaluate(_snap(), TH, now=NOON)
    assert res["state"] == "ok", [a["label"] + a["head"] for a in res["alerts"]]
    assert res["alerts"] == []
    assert res["headline"] == "공급 이상 없음"
    assert {s["key"] for s in res["signals"]} == {
        "collect", "analyze", "encar", "kcar", "results", "zero_sample", "runs"}


def test_정상_쪽_경계값_바로_앞에서는_울지_않는다():
    """임계 '직전'까지는 정상이어야 한다 — 하루만 밀려도 우는 감시는 꺼지게 된다."""
    res = oh.evaluate(_snap(
        kcar_checked_at="2026-09-17 10:00:00",          # 6일 전 (임계 7일)
        result_checked_at="2026-09-22 06:42:47",        # 1일 전 (임계 2일)
        encar_ok_at="2026-09-22 06:31:28",              # 1일 전 (임계 2일)
        runs=[RUNS_0919_21[2], *RUNS_OK[:1],            # 분석 0 이 연속이 아니다
              {"started_at": "2026-09-23 06:30:00", "status": "done",
               "message": "입찰예정 396 · 분석 0 · 낙찰결과 190건"}],
    ), TH, now=NOON)
    assert res["state"] == "ok", [a["label"] + a["head"] for a in res["alerts"]]
    assert _sig(res, "analyze")["streak"] == 1          # 1일은 정상 — 조용히 넘어간다


# ── ② 이상 쪽: 09-19~21 을 실제로 잡는가 ───────────────────────────────
def test_0919_21_분석0건_3일연속을_멈춤으로_잡는다():
    """★ 지시서의 합격선. 세 줄 다 status='done' 인데도 '멈춤'이 나와야 한다."""
    res = oh.evaluate(_snap(runs=list(RUNS_0919_21), analyzed_at="2026-09-18 06:37:00"),
                      TH, now=datetime(2026, 9, 21, 12, 0, 0))
    a = _sig(res, "analyze")
    assert a["state"] == "down"
    assert a["streak"] == 3
    assert "2026-09-19~2026-09-21" in a["detail"]
    assert res["state"] == "down"
    assert all(r["status"] == "done" for r in RUNS_0919_21)   # 반증: done 만 보면 전부 성공이다


def test_분석0건_2일연속이면_이미_이상이다():
    """09-20 시점에 이미 울었어야 한다 — 3일째를 기다리지 않는다."""
    res = oh.evaluate(_snap(runs=RUNS_0919_21[:2], analyzed_at="2026-09-18 06:37:00"),
                      TH, now=datetime(2026, 9, 20, 12, 0, 0))
    assert _sig(res, "analyze")["state"] == "warn"
    assert _sig(res, "analyze")["streak"] == 2


def test_done_이어도_메시지의_경고를_잡는다():
    """09-20 의 '⚠엔카 error(HTTP None)' — status 는 done 이었다."""
    res = oh.evaluate(_snap(runs=[RUNS_0919_21[1]]), TH, now=datetime(2026, 9, 20, 12, 0, 0))
    r = _sig(res, "runs")
    assert r["state"] == "warn" and r["run_status"] == "done"
    assert "⚠엔카 error(HTTP None)" in r["detail"]


def test_케이카_18일_정지를_잡는다():
    """2026-09-23 실측: kcar_checked_at 이 09-05 에서 멈춘 채 18일. 신호가 0이었던 자리다."""
    res = oh.evaluate(_snap(kcar_checked_at="2026-09-05 23:10:39"), TH, now=NOON)
    k = _sig(res, "kcar")
    assert k["state"] == "warn" and k["stale_days"] == 18
    assert res["state"] == "warn"
    assert "케이카 교차검증" in res["headline"]


def test_수집이_멈추면_멈춤이고_새벽에는_판정을_미룬다():
    snap = _snap(collected_at="2026-09-21 06:35:30")
    assert _sig(oh.evaluate(snap, TH, now=NOON), "collect")["state"] == "down"
    # 같은 데이터라도 정기 갱신 전(03시)에는 '확인 불가' — 새벽 거짓 경보를 만들지 않는다
    early = oh.evaluate(_snap(collected_at="2026-09-22 06:35:30"), TH,
                        now=datetime(2026, 9, 23, 3, 0, 0))
    assert _sig(early, "collect")["state"] == "unknown"


def test_엔카_차단과_자동갱신_꺼짐은_멈춤이다():
    blocked = oh.evaluate(_snap(encar_state="blocked", encar_code="407"), TH, now=NOON)
    assert _sig(blocked, "encar")["state"] == "down" and blocked["state"] == "down"
    off = oh.evaluate(_snap(daily_enabled="0"), TH, now=NOON)
    assert _sig(off, "runs")["state"] == "down"


def test_오늘_실행_기록이_없으면_멈춤이다():
    res = oh.evaluate(_snap(runs=RUNS_OK[:1], collected_at="2026-09-22 06:35:30"), TH, now=NOON)
    assert _sig(res, "runs")["state"] == "down"
    assert "오늘 정기 갱신 기록이 없다" in _sig(res, "runs")["detail"]


# ── 0표본: 비율로 판정하고 절대 수는 반드시 함께 적는다 ────────────────
def test_0표본_비율이_내려도_절대수_증가를_감추지_않는다():
    """운영 실측: 어제 431/1,165(37%) → 오늘 530/1,472(36%). 비율은 내렸고 건수는 +99 다."""
    res = oh.evaluate(_snap(zero_sample={"zero": 530, "total": 1472},
                            zero_history=[{"date": "2026-09-22", "zero": 431, "total": 1165}]),
                      TH, now=NOON)
    z = _sig(res, "zero_sample")
    assert z["state"] == "ok"                 # 비율은 오르지 않았다 → 경보 아님
    assert "+99" in z["detail"] and "-1.0%p" in z["detail"]   # 37.0%→36.0%


def test_0표본_비율이_오르면_이상이다():
    res = oh.evaluate(_snap(zero_sample={"zero": 600, "total": 1472},
                            zero_history=[{"date": "2026-09-22", "zero": 500, "total": 1472}]),
                      TH, now=NOON)
    assert _sig(res, "zero_sample")["state"] == "warn"


def test_0표본_이력이_없으면_절대_상한으로만_판정한다():
    res = oh.evaluate(_snap(zero_sample={"zero": 700, "total": 1472}, zero_history=[]),
                      TH, now=NOON)
    z = _sig(res, "zero_sample")
    assert z["state"] == "warn" and "비교할 전일 기록이 없다" in z["detail"]


# ── 파서 반증: 모르는 것을 0으로 세지 않는다 ───────────────────────────
def test_진행_메시지는_분석0건이_아니라_모름이다():
    """끊긴 실행의 진행 메시지를 0건으로 세면 멀쩡한 날이 '멈춤'이 된다."""
    assert oh.parse_analyzed("시세 분석 27/80 · G80") is None
    assert oh.parse_analyzed("입찰예정 410 · 분석 0 · 낙찰결과 167건") == 0
    assert oh.parse_analyzed("입찰예정 396 · 분석 21 · 낙찰결과 190건") == 21
    # 모름을 만나면 연속 계산이 거기서 멈춘다
    runs = [RUNS_0919_21[0], RUNS_0919_21[1],
            {"started_at": "2026-09-21 06:30:00", "status": "error",
             "message": "시세 분석 27/80 · G80 (서버 재시작으로 중단됨)"}]
    assert oh.zero_streak(runs)[0] == 0


def test_같은_날_수동실행이_정기실행을_가리지_않는다():
    runs = [*RUNS_OK,
            {"started_at": "2026-09-23 09:10:00", "status": "done", "message": "시세 재교정 4건"}]
    picked = oh.daily_runs(runs)[-1]
    assert picked["message"].startswith("입찰예정 396")


def test_판정_보류는_정상으로_치지_않는다():
    """확인 불가가 ok 를 덮어써야 한다 — 모르는 것을 초록으로 칠하면 감시가 아니다."""
    assert oh.worst(["ok", "unknown"]) == "unknown"
    assert oh.worst(["unknown", "warn"]) == "warn"
    assert oh.worst(["warn", "down", "ok"]) == "down"
    res = oh.evaluate({"source": "빈 스냅샷"}, TH, now=NOON)
    assert res["state"] in ("warn", "down", "unknown") and res["state"] != "ok"


# ── 임계는 config.yaml 이 단일 진실원천 ────────────────────────────────
def test_임계는_config_yaml_이_모두_정의한다():
    """코드의 _FALLBACK 은 그물일 뿐 — config 가 모든 키를 덮고 있어야 한다."""
    cfg = oh._read_config_file()
    section = cfg.get("ops_alert") or {}
    missing = [k for k in oh._FALLBACK if k not in section]
    assert not missing, f"config.yaml ops_alert 에 빠진 임계: {missing}"
    assert oh.load_thresholds(cfg) == {**oh._FALLBACK, **section}


def test_config_임계를_바꾸면_판정이_따라온다():
    """외부화가 형식만이 아님을 민다 — 값을 바꾸면 결과가 바뀌어야 한다."""
    snap = _snap(kcar_checked_at="2026-09-05 23:10:39")
    loose = oh.load_thresholds({"ops_alert": {"kcar_stale_days": 30}})
    assert _sig(oh.evaluate(snap, loose, now=NOON), "kcar")["state"] == "ok"
    assert _sig(oh.evaluate(snap, TH, now=NOON), "kcar")["state"] == "warn"


# ── 서비스 계층: 스냅샷·추이 기록(임시 DB) ─────────────────────────────
@pytest.fixture
def svc(tmp_path, monkeypatch):
    from web import db, service
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "ops.db")
    db.init_db()
    return service


def test_supply_snapshot_은_외부요청_없이_필요한_값을_모은다(svc):
    from web import db
    db.upsert_vehicle({"id": "v1", "case_no": "2026타경1_1", "collected_at": "2026-09-23 06:35:30",
                       "analyzed_at": "2026-09-23 06:37:33", "sample_count": 7,
                       "median_price": 12_000_000})
    db.upsert_vehicle({"id": "v2", "case_no": "2026타경2_1", "collected_at": "2026-09-23 06:35:31"})
    db.set_setting("encar_health_state", "ok")
    db.set_setting("daily_enabled", "1")
    rid = db.create_run(target=0)
    db.update_run(rid, status="done", message="입찰예정 2 · 분석 1 · 낙찰결과 0건")
    snap = svc.supply_snapshot()
    assert snap["collected_at"] == "2026-09-23 06:35:31"
    assert snap["zero_sample"] == {"zero": 1, "total": 2}      # v2 만 0표본
    assert snap["encar_state"] == "ok" and snap["daily_enabled"] == "1"
    assert snap["runs"] and snap["runs"][-1]["status"] == "done"


def test_추이_기록은_하루_한_줄이고_어제와_비교된다(svc):
    from web import db
    db.upsert_vehicle({"id": "v1", "case_no": "2026타경1_1"})
    svc.record_supply_history(today="2026-09-22")
    db.upsert_vehicle({"id": "v2", "case_no": "2026타경2_1"})
    rows = svc.record_supply_history(today="2026-09-23")
    rows = svc.record_supply_history(today="2026-09-23")           # 같은 날 두 번 → 덮어쓴다
    assert [r["date"] for r in rows] == ["2026-09-22", "2026-09-23"]
    assert rows[-1] == {"date": "2026-09-23", "zero": 2, "total": 2}
    assert svc.supply_snapshot()["zero_history"][0]["date"] == "2026-09-22"


# ── 알림 경로 ①: 매일 12시 리포트 맨 위 ────────────────────────────────
# 기록이 아니라 **먼저 보이는 자리**인지 민다. 09-19~21 의 건수는 이 리포트 표 안에
# 이미 찍혀 있었는데도 사흘을 아무도 몰랐다.
import importlib.util  # noqa: E402
import json  # noqa: E402
from datetime import date as _date  # noqa: E402
from pathlib import Path  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = _load(_ROOT / "tools" / "daily_ops_report.py", "daily_ops_report_ops")
DASH = _load(_ROOT / "tools" / "agent_dashboard.py", "agent_dashboard_ops")


def _report_data(supply_runs, day=_date(2026, 9, 23), now=NOON, **over):
    since, until = R.report_window(day)
    d = {
        "since": since, "until": until, "generated": now,
        "server": {
            "runs": [], "certbot": {"started": 2, "finished": 2, "failed": 0},
            "service": {"active": "active", "since": ""},
            "settings": {"daily_time": "06:30", "daily_enabled": "1", "encar_health_state": "ok",
                         "encar_health_code": "200", "encar_health_ok_at": "2026-09-23 06:31:28",
                         "supply_zero_history": '[{"date": "2026-09-22", "zero": 540, "total": 1470}]'},
            "supply": {"collected_at": "2026-09-23 06:35:30", "analyzed_at": "2026-09-23 06:37:33",
                       "result_checked_at": "2026-09-23 06:42:47",
                       "kcar_checked_at": "2026-09-23 06:40:00",
                       "zero_sample": {"zero": 530, "total": 1472},
                       "runs": supply_runs},
        },
        "tasks": {R.PHOTO_TASK: {"state": "Ready", "last": "", "next": "", "result": 0},
                  R.TUNNEL_TASK: {"state": "Running", "last": "", "next": "", "result": 0}},
        "panel": {"commits": []}, "photo_log": {}, "tunnel_log": {},
    }
    d.update(over)
    d["supply"] = R.supply_verdict(d, now)
    return d


def test_리포트_정상이면_맨_위에_이상_없음이_적힌다():
    md = R.build_markdown(_report_data(list(RUNS_OK)))
    head = md.split("## 정기 작업")[0]
    assert "## 공급 상태" in head and "✅ 정상" in head
    assert "공급 이상 없음" in head and "먼저 볼 것" not in head


def test_리포트가_0919_21을_맨_위에_띄운다():
    at = datetime(2026, 9, 21, 12, 0, 0)
    d = _report_data(list(RUNS_0919_21), day=_date(2026, 9, 21), now=at)
    d["server"]["supply"]["collected_at"] = "2026-09-21 06:35:30"
    d["server"]["supply"]["analyzed_at"] = "2026-09-18 06:37:00"
    d["server"]["supply"]["result_checked_at"] = "2026-09-21 06:42:47"
    d["server"]["supply"]["kcar_checked_at"] = "2026-09-05 23:10:39"
    d["supply"] = R.supply_verdict(d, at)
    md = R.build_markdown(d)
    head = md.split("## 정기 작업")[0]
    assert "🛑 멈춤" in head and "먼저 볼 것" in head
    assert "시세 분석" in head and "케이카 교차검증" in head
    summary = next(ln for ln in head.splitlines() if ln.startswith("- **요약**"))
    assert "공급 🛑 멈춤(시세 분석 0건 3일 연속 외 " in summary   # 요약 줄은 1건 + 외 N건
    assert head.index("## 공급 상태") < md.index("## 정기 작업")


def test_서버를_못_읽으면_정상이_아니라_확인_불가다():
    since, until = R.report_window(_date(2026, 9, 23))
    md = R.build_markdown({"since": since, "until": until, "generated": NOON,
                           "server": {"error": "서버 조회 실패(코드 255): timeout"},
                           "tasks": {"error": "x"}, "panel": {"error": "x"},
                           "photo_log": {}, "tunnel_log": {}})
    assert "❔ **확인 불가**" in md and "정상이라는 뜻이 아니다" in md


def test_지난_날짜_리포트는_지금_판정을_적지_않는다():
    d = _report_data(list(RUNS_OK))
    d["since"], d["until"] = R.report_window(_date(2026, 9, 18))
    md = R.build_markdown(d)
    assert "지난 기간" in md.split("## 정기 작업")[0]


def test_원격_조회_스크립트는_0표본_문장을_베끼지_않고_실어_보낸다():
    s = R.remote_script(datetime(2026, 9, 22, 12, 0), datetime(2026, 9, 23, 12, 0))
    assert oh.ZERO_SAMPLE_SQL in s                    # 앱과 **같은 문장**으로 센다
    for mark in ("__SINCE__", "__UNTIL__", "__RUNS_SINCE__", "__ZERO_SQL__"):
        assert mark not in s
    assert '"2026-09-15 12:00:00"' in s               # runs 는 창보다 7일 더 읽는다
    assert "supply_zero_history" in s


# ── 알림 경로 ②: 사내 대시보드 상태 블록 ───────────────────────────────
def test_대시보드는_로컬DB가_아니라_서버_판정_파일을_읽는다(tmp_path, monkeypatch):
    """★ 로컬 auction.db 로 판정하면 개발 사본 때문에 매일 거짓 '수집 멈춤'이 뜬다."""
    f = tmp_path / "ops_supply.json"
    f.write_text(json.dumps({"state": "down", "headline": "시세 분석 0건 3일 연속",
                             "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                             "source": "운영 서버", "signals": [], "alerts": [{"label": "시세 분석"}]},
                            ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(DASH, "SUPPLY", f)
    v, err = DASH.read_supply()
    assert err is None and v["state"] == "down" and v["stale"] is False


def test_대시보드는_판정이_없거나_낡으면_초록으로_두지_않는다(tmp_path, monkeypatch):
    monkeypatch.setattr(DASH, "SUPPLY", tmp_path / "없음.json")
    v, err = DASH.read_supply()
    assert v == {} and "매일 12시 리포트" in err          # 없으면 '없다'고 쓴다
    old = tmp_path / "ops_supply.json"
    old.write_text(json.dumps({"state": "ok", "headline": "공급 이상 없음",
                               "checked_at": "2026-09-01 12:00:00", "signals": []}),
                   encoding="utf-8")
    monkeypatch.setattr(DASH, "SUPPLY", old)
    v, err = DASH.read_supply()
    assert err is None and v["state"] == "ok" and v["stale"] is True   # 값은 ok 지만 낡았다


def test_대시보드_타일과_띠는_같은_값을_쓴다():
    html = (_ROOT / "tools" / "agent_dashboard.html").read_text(encoding="utf-8")
    assert "const sst = k.supply_state;" in html
    body = html[html.index('<div id="problems">'):html.index('<div class="kpis"')]
    assert '<div id="supply"></div>' in body            # 공급 블록이 KPI 보다 위다
    js = html[html.index("$('#kpis').innerHTML"):]
    assert js.index("supTile,") < js.index("liveTile,")  # 타일도 맨 앞이다


# ── 케이카가 왜 멈췄는지 다음 사람이 볼 수 있게 ─────────────────────────
def test_케이카_세션_실패는_기록으로_남는다(svc, monkeypatch):
    """★ 2026-09-23 조사에서 **원인을 가릴 기록이 하나도 없었다.**

    재교정 경로는 세션 생성 실패를 `except: ks = None` 로 삼키고, run_id=None 이라
    실행 메시지도 남기지 않는다. 동작(엔카 단독 진행)은 그대로 두고 사유만 남긴다.
    """
    from web import db
    from src.collect import kcar

    def _boom():
        raise RuntimeError("Chromium distribution 'chrome' is not found")

    monkeypatch.setattr(kcar, "new_session", _boom)
    monkeypatch.setattr(svc, "load_config", lambda: {"kcar_cross_enabled": True,
                                                     "min_sample_count": 5, "year_tol": 1,
                                                     "mileage_tol": 0.30})
    db.upsert_vehicle({"id": "v1", "case_no": "2026타경1_1", "maker": "현대",
                       "model": "그랜저", "year": 2020, "mileage_km": 50000})
    monkeypatch.setattr(svc.encar, "new_session", lambda: object())
    monkeypatch.setattr(svc.encar, "search", lambda *a, **k: {"count": 0, "results": []})
    svc.recompute_all_market(finalize=False)
    s = db.get_all_settings()
    assert s["kcar_health_state"] == "error"
    assert "chrome" in s["kcar_health_msg"]
    # 판정에도 사유가 실린다 — '왜 멈췄나'를 화면에서 바로 읽을 수 있어야 한다
    res = oh.evaluate({"kcar_checked_at": "2026-09-05 23:10:39",
                       "kcar_state": "error", "kcar_msg": s["kcar_health_msg"],
                       "kcar_state_at": s["kcar_health_at"]}, TH, now=NOON)
    k = _sig(res, "kcar")
    assert k["state"] == "warn" and "마지막 시도 error" in k["detail"] and "chrome" in k["detail"]


def test_케이카_기록이_최근이어도_마지막_시도가_실패면_이상이다():
    res = oh.evaluate(_snap(kcar_state="blocked", kcar_msg="차단 감지(C.4-5)",
                            kcar_state_at="2026-09-23 06:40:00"), TH, now=NOON)
    k = _sig(res, "kcar")
    assert k["state"] == "warn" and "마지막 수집 시도가 실패했다" in k["detail"]
    # 반증: 같은 데이터에서 상태만 ok 면 조용하다
    assert _sig(oh.evaluate(_snap(kcar_state="ok"), TH, now=NOON), "kcar")["state"] == "ok"
