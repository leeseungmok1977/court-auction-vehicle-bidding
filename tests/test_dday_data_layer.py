# -*- coding: utf-8 -*-
"""D-day 를 **날짜만으로** 계산하던 나머지 자리 — 데이터 층 (PANEL-16, 2026-09-23).

목록·상세는 이미 막았다(tests/test_dday_after_bid_time.py). 그런데 D-day 를 만드는 자리는
그 둘만이 아니었다. 교차검수 지적:

  · **즐겨찾기**(`/watchlist`)는 날짜만 빼 `dday` 를 만들고 `_display_judgment` 도 거치지
    않는다 → watchlist.html 의 `dd<=1 → bg-rose-100` 빨강과 DB 원본 '유찰 대기'가 그대로
    나온다. 즐겨찾기는 사용자가 **직접 담아 둔** 물건이라 그 화면을 더 오래·더 믿고 본다.
  · **대시보드**는 `service.alert_items()`·`_pick_dict()` 가 날짜만 본다 → 오늘 10시에 끝난
    차가 '임박 매각기일'(빨강 D-DAY + 헤더 벨 배지)과 '오늘의 추천' 캐러셀에 그대로 남는다.

판정 엔진(`service.bid_state` → `sale_time_passed`)은 처음부터 옳았다. 틀린 것은 그 값을
안 보는 **데이터 층**이다.

⚠ 시각을 **모르는** 물건은 '지나지 않음'으로 남긴다(보수적). 아직 입찰할 수 있는 차를
  끝났다고 말해 기회를 뺏는 쪽이 이 화면들에서는 더 비싼 실수다.

⚠ 정렬 규칙도 여기서 고정한다. 즐겨찾기의 `dday` 는 **정렬 키를 겸하므로**, 표시용으로
  None 을 넣으면 순서가 조용히 바뀐다. 규칙은 `web.app._dday_sort_key` 의 독스트링에 있다.
"""
import json
import re
from datetime import date, timedelta

import pytest
from starlette.testclient import TestClient

from web import db, service
from tests.test_dashboard_link_parity import BT

# 공개 사용자로 본다 — XFF 가 없으면 이 앱은 요청을 관리자(SSH 터널)로 판정한다.
_PUBLIC = {"x-forwarded-for": "203.0.113.7"}

TODAY = date.today()
_T = TODAY.isoformat()

_BASE = {
    "item_no": "1", "court": "수원지방법원", "maker": "현대", "model": "쏘나타", "year": 2020,
    "min_sale_price": 28_000_000, "appraisal_value": 32_000_000, "fail_count": 1,
    "status": "완료", "median_price": 40_000_000, "market_confidence": 78,
    "market_confidence_label": "높음", "sample_count": 12, "photo_count": 3,
    "mileage_km": 50_000,
}

# 같은 사실을 말하는 물건 한 쌍 + 보수적 대조군.
#   *_ENDED : 오늘 기일인데 입찰 시각이 지났다('00:00'은 하루 중 언제 돌려도 지난 시각)
#   *_LIVE  : 오늘 기일이고 아직 시각 전
#   *_UNK   : 오늘 기일인데 시각을 모른다 → 지나지 않은 것으로 본다
_CARS = [
    dict(_BASE, id="WL_LIVE0", case_no="2026타경8001", sale_date=_T, sale_time="23:59",
         judgment="유찰 대기"),
    dict(_BASE, id="WL_ENDED0", case_no="2026타경8002", sale_date=_T, sale_time="00:00",
         judgment="유찰 대기"),
    dict(_BASE, id="WL_UNK0", case_no="2026타경8003", sale_date=_T, judgment="유찰 대기"),
    dict(_BASE, id="WL_D3", case_no="2026타경8004", sale_time="10:00",
         sale_date=(TODAY + timedelta(days=3)).isoformat(), judgment="유찰 대기"),
    dict(_BASE, id="WL_PAST1", case_no="2026타경8005", sale_time="10:00",
         sale_date=(TODAY - timedelta(days=1)).isoformat(), judgment="유찰 대기"),
    dict(_BASE, id="WL_PAST7", case_no="2026타경8006", sale_time="10:00",
         sale_date=(TODAY - timedelta(days=7)).isoformat(), judgment="유찰 대기"),
    dict(_BASE, id="WL_NODATE", case_no="2026타경8007", judgment="유찰 대기"),
    # 대시보드 알림·캐러셀용 — 알림은 judgment='입찰 검토 가능'만 본다.
    dict(_BASE, id="AL_ENDED", case_no="2026타경8011", sale_date=_T, sale_time="00:00",
         judgment="입찰 검토 가능"),
    dict(_BASE, id="AL_LIVE", case_no="2026타경8012", sale_date=_T, sale_time="23:59",
         judgment="입찰 검토 가능"),
    dict(_BASE, id="AL_UNK", case_no="2026타경8013", sale_date=_T, judgment="입찰 검토 가능"),
    dict(_BASE, id="AL_D2", case_no="2026타경8014", sale_time="10:00",
         sale_date=(TODAY + timedelta(days=2)).isoformat(), judgment="입찰 검토 가능"),
]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "dday.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    for c in _CARS:
        db.upsert_vehicle(dict(c, folder_key=c["id"]))
    import web.app as A
    return TestClient(A.app)


def _wl(client, ids: str, sort: str = "dday") -> str:
    r = client.get(f"/watchlist?ids={ids}&sort={sort}", headers=_PUBLIC)
    assert r.status_code == 200, f"/watchlist 가 {r.status_code}"
    return r.text


def _near(html: str, *needles: str) -> str:
    """판정 옆에 **원문**을 함께 싣는다 — 이 저장소에서 측정 스크립트가 거짓 판정을 낸 적이 있다."""
    for n in needles:
        i = html.find(n)
        if i >= 0:
            return f"...{html[max(0, i - 260):i + 260]}..."
    return "(D-DAY·기일 경과 둘 다 없음)"


def _order(html: str) -> list:
    """렌더된 순서(맨 위부터). 표가 먼저 그려지므로 첫 등장 순서 = 정렬 결과.

    ⚠ 물건 id 는 운영에서 '2026타경30666_1' 처럼 **한글**이다. `[A-Za-z0-9_]+` 로 뽑으면
      한글 앞에서 끊겨 전부 '2026' 이 되고, 정렬이 뒤죽박죽이어도 테스트가 통과한다
      (2026-09-23 실측 스크립트가 실제로 이 거짓 판정을 냈다). 따옴표까지 통째로 받는다.
    """
    out, seen = [], set()
    for m in re.finditer(r'/vehicle/([^"?]+)"', html):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(m.group(1))
    return out


# ── 1. 즐겨찾기 — 끝난 경매에 빨강 D-DAY 를 붙이지 않는다 ─────────────────
def test_즐겨찾기_시각이_지나면_빨강_DDAY_배지를_끈다(env):
    html = _wl(env, "WL_ENDED0")
    assert "D-DAY" not in html, (
        "입찰 시각이 지났는데 즐겨찾기에 'D-DAY' 배지가 남았다 — 끝난 경매를 오늘 입찰이라 말한다:\n"
        + _near(html, "D-DAY"))


def test_즐겨찾기_판정_칩이_기일_경과를_말한다(env):
    """DB 원본('유찰 대기', 앰버)이 그대로 나오면 '기다리면 된다'로 읽힌다."""
    from web.app import ELAPSED_LABEL

    html = _wl(env, "WL_ENDED0")
    assert ELAPSED_LABEL + "</span>" in html, (
        "즐겨찾기 판정 칩이 목록·상세와 다른 말을 한다:\n" + _near(html, "유찰 대기", "기일 경과"))
    assert "유찰 대기</span>" not in html, (
        "끝난 경매에 앰버 '유찰 대기'가 그대로 붙어 있다:\n" + _near(html, "유찰 대기"))


def test_즐겨찾기_시각_전에는_DDAY_배지가_그대로_있다(env):
    """대조군이 없으면 위 테스트들은 '배지가 원래 안 나온다'로도 통과한다."""
    html = _wl(env, "WL_LIVE0")
    assert "D-DAY" in html, (
        "아직 입찰 전인 오늘 기일 물건인데 카운트다운 배지가 사라졌다:\n" + _near(html, "D-DAY"))


def test_즐겨찾기_시각을_모르면_보수적으로_남긴다(env):
    html = _wl(env, "WL_UNK0")
    assert "D-DAY" in html, (
        "시각을 모르는 물건을 '지난 것'으로 단정했다 — 입찰 기회를 뺏는다:\n" + _near(html, "D-DAY"))


# ── 2. 정렬 규칙(회귀 고정) ─────────────────────────────────────────────
def test_정렬규칙_아직_입찰가능_먼저_끝난것은_뒤로(env):
    """★ 이 순서를 모르고 되돌리지 못하게 **렌더된 결과로** 고정한다.

    끝난 물건을 목록에서 지우지는 않는다(결과를 기다리는 물건이다). 다만 지금 입찰할 수
    있는 물건보다 앞에 둘 이유가 없다. 기일 미상은 판단 근거가 없으므로 맨 끝.
    """
    scrambled = "WL_PAST7,WL_ENDED0,WL_NODATE,WL_D3,WL_PAST1,WL_LIVE0"
    got = _order(_wl(env, scrambled, sort="dday"))
    assert got == ["WL_LIVE0", "WL_D3", "WL_ENDED0", "WL_PAST1", "WL_PAST7", "WL_NODATE"], (
        f"즐겨찾기 '매각기일 가까운 순'이 규칙과 다르다.\n"
        f"  요청 순서: {scrambled}\n  렌더 순서: {got}")


def test_정렬키_규칙_자체를_고정한다():
    """표시용 dday(None)와 정렬용 값을 **분리**했다는 사실을 키 함수 수준에서 못 박는다."""
    from web.app import _dday_sort_key

    live0 = {"dday_raw": 0, "bidding_over": False}     # 오늘, 아직 입찰 전
    live3 = {"dday_raw": 3, "bidding_over": False}
    ended = {"dday_raw": 0, "bidding_over": True, "dday": None}   # 오늘, 시각 경과
    past1 = {"dday_raw": -1, "bidding_over": False}
    past7 = {"dday_raw": -7, "bidding_over": False}
    none_ = {"dday_raw": None, "bidding_over": False}
    got = sorted([past7, ended, none_, live3, past1, live0], key=_dday_sort_key)
    assert got == [live0, live3, ended, past1, past7, none_], got
    assert _dday_sort_key(ended) > _dday_sort_key(live3), (
        "끝난 오늘 기일이 아직 입찰 가능한 D-3 보다 앞에 온다")
    assert _dday_sort_key(none_) > _dday_sort_key(past7), "기일 미상이 맨 끝이 아니다"


# ── 3. 대시보드 임박 알림 ───────────────────────────────────────────────
def test_알림에서_시각이_지난_오늘_기일은_빠진다(env):
    ids = {r["id"] for r in service.alert_items(3)}
    assert "AL_ENDED" not in ids, f"오늘 10시에 끝난 물건이 '임박 매각기일' 알림에 남았다: {sorted(ids)}"
    assert {"AL_LIVE", "AL_UNK", "AL_D2"} <= ids, (
        f"아직 입찰 가능한 물건·시각 미상 물건까지 같이 사라졌다: {sorted(ids)}")


def test_알림_dday_는_항상_0이상_정수다(env):
    """알림 카드는 dday 를 그대로 비교·출력한다 — None 을 실어 보내면 화면이 깨진다.
    그래서 알림에서는 '배지를 끄는' 대신 **대상에서 뺀다**."""
    for r in service.alert_items(3):
        assert isinstance(r.get("dday"), int) and r["dday"] >= 0, (
            f"알림에 쓸 수 없는 dday 가 실렸다: {r['id']} → {r.get('dday')!r}")


def test_벨_배지와_알림_카드_수가_같다(env):
    """헤더 벨은 다른 화면에서 alert_count() 를 따로 돈다 — 한쪽만 고치면
    홈은 3건인데 벨은 4로 뜨고, 눌러도 없는 물건이 된다."""
    items, cnt = service.alert_items(3), service.alert_count(3)
    assert cnt == len(items), (
        f"벨 배지 {cnt} ≠ 홈 알림 {len(items)} ({sorted(r['id'] for r in items)})")


# ── 4. 홈 '오늘의 추천' 캐러셀 ──────────────────────────────────────────
def _cache_picks(*ids):
    db.set_setting("daily_picks_ids", json.dumps([{"id": i, "kind": "resale"} for i in ids]))
    db.set_setting("daily_picks_date", date.today().isoformat())


def test_오늘_끝난_경매는_추천_캐러셀에서_빠진다(env):
    """'여전히 유효(검토가능·미래기일)한 것만'이라는 기존 게이트가 날짜 단위라 못 걸렀다."""
    live = db.get_vehicle("AL_LIVE")
    tone = (service.bid_state(live, BT) or {}).get("tone")
    assert tone != "stop", f"픽스처 전제가 깨졌다 — 대조군이 stop 이라 어차피 빠진다(tone={tone})"

    _cache_picks("AL_ENDED", "AL_LIVE")
    got = [p["id"] for p in service.get_daily_picks(5)]
    assert "AL_ENDED" not in got, f"오늘 10시에 끝난 차가 '오늘의 추천'에 남았다: {got}"
    assert "AL_LIVE" in got, f"아직 입찰 가능한 차까지 같이 사라졌다: {got}"


def test_시각_미상은_추천에_남는다(env):
    _cache_picks("AL_UNK")
    assert [p["id"] for p in service.get_daily_picks(5)] == ["AL_UNK"], (
        "시각을 모르는 물건을 '끝났다'고 단정해 추천에서 뺐다")


def test_캐러셀_배지도_시각을_본다(env):
    """게이트가 하나뿐이면 다음 사람이 모르고 푼다 — 배지를 만드는 자리에서도 끈다."""
    ended = db.get_vehicle("AL_ENDED")
    assert service._pick_dict(ended, BT)["dday"] is None, (
        "캐러셀 카드가 끝난 경매에 빨강 'D-DAY'(bg-rose-600)를 붙인다")
    assert service._pick_dict(db.get_vehicle("AL_LIVE"), BT)["dday"] == 0, (
        "아직 입찰 전인 오늘 기일 물건의 카운트다운까지 꺼졌다")


# ── 5. 드리프트 가드 ────────────────────────────────────────────────────
def test_표시계층과_판정엔진이_같은_사실을_본다():
    """app 쪽(_bidding_over)과 service 쪽(sale_time_passed)이 갈리면 화면마다 말이 달라진다.
    즐겨찾기는 배지를 끄는데 홈 알림은 그대로 뜨는 식이다."""
    from web.app import _bidding_over

    car = dict(_BASE, id="X", case_no="2026타경9999", sale_date=_T, sale_time="00:00")
    assert _bidding_over(car, _T) is True and service.sale_time_passed(car) is True
    for t in (None, "", "오전 10시", "99:99"):
        c = dict(car, sale_time=t)
        assert _bidding_over(c, _T) is False, f"시각 '{t}' 를 지난 것으로 단정했다"
        assert service.sale_time_passed(c) is False, f"시각 '{t}' 를 지난 것으로 단정했다"
