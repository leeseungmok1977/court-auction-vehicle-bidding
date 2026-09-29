# -*- coding: utf-8 -*-
"""OPS-7 — 주간·월간 보고 파일의 날짜를 '구간 첫날'이 아니라 '만들어질 예정일'로 읽는다.

2026-09-29: 09-26(토) 13:00 에 정상 생성된 2026-W39.md 를 리듬이 09-21(월)로 읽어 '8일 전 · 늦음'
지시서를 세웠다. 닫자마자 스캔이 다시 세웠다. 월간(2026-09.md, 10-01 생성)은 9월 1일로 읽혀 10-02 부터
한 달 내내 늦음이 될 참이었다.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import agent_dashboard as ad  # noqa: E402


def _touch(p: Path, when: datetime) -> Path:
    p.write_text("x", encoding="utf-8")
    ts = when.timestamp()
    os.utime(p, (ts, ts))
    return p


def test_week_file_is_dated_on_its_saturday(tmp_path):
    f = _touch(tmp_path / "2026-W39.md", datetime(2026, 9, 26, 13, 0))
    d, how = ad._file_date(f)
    assert d == date(2026, 9, 26) and "주차" in how


def test_week_file_edited_later_still_counts_from_saturday(tmp_path):
    f = _touch(tmp_path / "2026-W39.md", datetime(2026, 9, 29, 10, 0))       # 뒤에 오타를 고쳤다
    assert ad._file_date(f)[0] == date(2026, 9, 26)                            # 젊어지지 않는다


def test_week_file_made_early_uses_its_real_time(tmp_path):
    f = _touch(tmp_path / "2026-W39.md", datetime(2026, 9, 23, 9, 0))        # 수요일에 수동 생성
    assert ad._file_date(f)[0] == date(2026, 9, 23)


def test_month_file_is_dated_on_the_first_of_next_month(tmp_path):
    f = _touch(tmp_path / "2026-09.md", datetime(2026, 10, 1, 13, 30))
    assert ad._file_date(f)[0] == date(2026, 10, 1)
    g = _touch(tmp_path / "2026-12.md", datetime(2027, 1, 1, 13, 30))         # 해 넘김
    assert ad._file_date(g)[0] == date(2027, 1, 1)


def test_day_files_are_unchanged(tmp_path):
    f = _touch(tmp_path / "2026-09-28.md", datetime(2026, 9, 29, 12, 0))
    assert ad._file_date(f) == (date(2026, 9, 28), "파일명(일)")


def _rhythm(tmp_path, monkeypatch, sub, name, made, period, today):
    d = tmp_path / sub
    d.mkdir(parents=True)
    _touch(d / name, made)
    monkeypatch.setattr(ad, "ROOT", tmp_path)

    class _DT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(today.year, today.month, today.day, 12, 0)
    monkeypatch.setattr(ad, "datetime", _DT)
    return ad.check_rhythms([{"glob": f"{sub}/*.md", "period": period, "since": "2026-09-01"}])[0]


def test_weekly_monday_after_a_normal_saturday_is_normal(tmp_path, monkeypatch):
    r = _rhythm(tmp_path, monkeypatch, "w", "2026-W39.md", datetime(2026, 9, 26, 13), 7, date(2026, 9, 29))
    assert r["state"] == "정상" and r["age"] == 3


def test_weekly_missing_next_report_is_late_the_day_after_it_was_due(tmp_path, monkeypatch):
    # W40 은 10-03(토)에 나와야 한다. 10-04 에도 W39 뿐이면 늦음이다(8일 > 7일).
    r = _rhythm(tmp_path, monkeypatch, "w", "2026-W39.md", datetime(2026, 9, 26, 13), 7, date(2026, 10, 4))
    assert r["state"] == "늦음"


def test_monthly_is_normal_through_the_month_after_its_first_of_month_report(tmp_path, monkeypatch):
    r = _rhythm(tmp_path, monkeypatch, "m", "2026-09.md", datetime(2026, 10, 1, 13, 30), 31, date(2026, 10, 31))
    assert r["state"] == "정상"


def test_monthly_after_a_31_day_month_is_not_late_on_the_morning_of_the_1st(tmp_path, monkeypatch):
    # 10월은 31일이다. 2026-09.md(10-01 생성) 뒤 11-01 13:30 전 아침 스캔에서 늦음이면 거짓 경보다.
    r = _rhythm(tmp_path, monkeypatch, "m", "2026-09.md", datetime(2026, 10, 1, 13, 30), 31, date(2026, 11, 1))
    assert r["state"] == "정상"


def test_utilization_table_gives_monthly_a_31_day_period():
    _, rh, err = ad.read_utilization()
    assert err is None
    row = next(r for r in rh if r["glob"] == "docs/monthly-reports/*.md")
    assert row["period"] == 31
