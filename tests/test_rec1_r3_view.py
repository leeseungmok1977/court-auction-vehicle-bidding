# -*- coding: utf-8 -*-
"""REC-1 3회차(지시서 2026-09-30-02) — 2회차 교차검수·qa 가 남긴 **화면** 결함과 테스트 공백.

  1  홈 캐러셀 방어선 — 예상낙찰가가 없는 카드에 판정 배지('✓ 되팔아도 남음')를 그리지 않고 '미산출'(qa N1).
  2  리포트 가드 문장 — ⓐ 저감률 출처(이 법원 / 전국 기준) ⓑ 01 마지막 요점 ⓒ 03 최저매각가 말풍선
     ⓓ 04 보험 이력 '?' · 상한선 문단의 사고 감가(use=None 이면 쉼표만 매달렸다).
  3  관심 화면 — 가드 물건은 목록과 같은 칩, 낡은 최저가 로즈 끔, '미산출' 아래 이유(qa N4).
  4  기일내역 어휘 — '수집된 기일내역', 표 제목 아래 '수집 시점 기록'. 미래 행 '예정/미확정'은 그대로(REC-6 아님).
  5  설명 행 ④ 사유별(REC-7 ⑹) — 최저가 말고도 막는 사유가 있으면 '확인 전까지 내지 않습니다'라고 약속하지 않는다.
  6  가드 상세 상한선 행 '(직접 탈 목적)' + 근거 줄.
  7  qa N6 생존 변이 8종 — 입찰 시각·오늘 경계, 종결 제외, 입찰 전이 아닌 가드의 추정값·조건문, 비가드 '위 추천 입찰 전략',
     가드 재판매 상자 문장, 홈 'N대 제외' 값. qa N5 — 07 표 '현 최저가' 꼬리표.

가리킬 때는 줄 번호가 아니라 **앵커 문자열**로 가리킨다(CLAUDE.md 규칙 8).
외부 요청 0 — 루프백 밖 소켓 연결을 막는다(TEST-1).
"""
import hashlib
import re
import socket
from datetime import date

import pytest
from starlette.testclient import TestClient

from web import db, service
from tests.test_render_smoke import BT

_PUB = {"x-forwarded-for": "203.0.113.7"}
FAR = "2999-01-01"
PAST = "2020-01-01"
TODAY = date.today().isoformat()

_BASE = {"court": "수원지방법원", "maker": "현대", "model": "쏘나타", "year": 2020, "item_no": "1",
         "sale_date": FAR, "sale_time": "10:00", "status": "완료", "market_confidence": 78,
         "market_confidence_label": "높음", "sample_count": 12, "photo_count": 3, "judgment": "유찰 대기"}

_HIST = [  # 53697_4 꼴 — 우리가 수집한 기일내역이 유찰 2회에서 멈췄다(지난 날짜 결과 없음 1행 + 미래 날짜 1행)
    {"ymd": "2026-01-10", "lws_price": 10_000_000, "result": "유찰"},
    {"ymd": "2026-02-20", "lws_price": 7_000_000, "result": "유찰"},
    {"ymd": "2026-04-01", "lws_price": 4_900_000},
    {"ymd": "2998-01-01", "lws_price": 3_430_000},
]

VEH = {
    # 520d 꼴: 감정 2,000만 · 최저 980만(0.7²) · 유찰 3 → 한 단계 지연. 내차 8회 → 사고 감가 30%. 이 법원(수원) 저감률 표본 있음.
    "lag_1": dict(case_no="2026타경91101", appraisal_value=20_000_000, min_sale_price=9_800_000, fail_count=3,
                  median_price=20_795_000, upper_bid=7_525_950, accident_grade="accident",
                  insurance_history={"own_damage": 8, "opp_damage": 2}),
    # 카니발 35384 꼴: 표본이 없는 법원 → 전국 기준 저감률.
    "lag_g": dict(case_no="2026타경91102", court="대전지방법원", model="카니발", appraisal_value=16_000_000,
                  min_sale_price=11_200_000, fail_count=2, median_price=12_200_000, upper_bid=5_832_000),
    # E300 꼴: 저장 판정이 '입찰 검토 가능'인 가드 물건(관심 화면이 초록 칩을 냈다).
    "e300_1": dict(case_no="2026타경91103", maker="벤츠", model="E300", appraisal_value=19_000_000,
                   min_sale_price=9_310_000, fail_count=3, median_price=18_595_000, upper_bid=9_413_200,
                   judgment="입찰 검토 가능"),
    # 최저가 말고도 예상가·판정을 막는 사유가 있는 가드 물건들
    "stop_1": dict(case_no="2026타경91104", appraisal_value=5_000_000, min_sale_price=5_000_000, fail_count=1,
                   median_price=4_300_000, upper_bid=1_000_000, runnable="no"),
    "lowc_1": dict(case_no="2026타경91105", appraisal_value=20_000_000, min_sale_price=14_000_000, fail_count=2,
                   median_price=18_000_000, upper_bid=9_000_000, market_confidence=30, market_confidence_label="낮음"),
    "nomed_1": dict(case_no="2026타경91106", appraisal_value=5_000_000, min_sale_price=3_500_000, fail_count=2,
                    median_price=None, upper_bid=None, market_confidence=None, market_confidence_label=None),
    "nomkt_1": dict(case_no="2026타경91107", model="굴착기", appraisal_value=30_000_000, min_sale_price=21_000_000,
                    fail_count=2, median_price=None, upper_bid=None, market_confidence=None, market_confidence_label=None),
    "flood_1": dict(case_no="2026타경91108", appraisal_value=10_000_000, min_sale_price=7_000_000, fail_count=2,
                    median_price=9_000_000, upper_bid=3_000_000, accident_grade="flood"),
    # 수집된 기일내역이 유찰을 다 못 담은 가드(최저가÷감정가 0.7³ 는 유찰 3회와 맞는데 기일내역의 유찰은 2회)
    "hist_1": dict(case_no="2026타경91109", appraisal_value=10_000_000, min_sale_price=3_430_000, fail_count=3,
                   median_price=6_000_000, upper_bid=1_500_000, dxdy_history=_HIST),
    # 가드가 아닌 물건 — 렌더가 예전과 같아야 한다
    "g90_1": dict(case_no="2026타경91110", model="G90", appraisal_value=29_000_000, min_sale_price=16_240_000,
                  fail_count=2, median_price=34_050_000, upper_bid=17_818_000, judgment="입찰 검토 가능",
                  dxdy_history=[{"ymd": FAR, "lws_price": 16_240_000}]),
    "block_1": dict(case_no="2026타경91111", model="스토닉", appraisal_value=13_000_000, min_sale_price=13_000_000,
                    fail_count=0, median_price=11_600_000, upper_bid=5_496_000),
    # 매각 종료 — service.floor_unconfirmed 는 참이지만(최저가=감정가·유찰 1) 화면 가드는 꺼져야 한다
    "closed_s": dict(case_no="2026타경91112", appraisal_value=20_000_000, min_sale_price=20_000_000, fail_count=1,
                     median_price=18_000_000, upper_bid=9_000_000, auction_result="낙찰", winning_price=19_000_000,
                     judgment="종결"),
    # 매각 종료 · 비가드 · 재판매 상자가 그려지는데 추천 입찰 전략 섹션은 없다(_strategy 거짓)
    "closed_r": dict(case_no="2026타경91113", appraisal_value=20_000_000, min_sale_price=14_000_000, fail_count=1,
                     median_price=25_000_000, upper_bid=15_000_000, auction_result="낙찰", winning_price=16_000_000,
                     judgment="종결"),
    # 오늘 기일 — 입찰 시각 전 / 후(시각 판단은 아래 픽스처가 고정한다)
    "today_open": dict(case_no="2026타경91114", sale_date=TODAY, sale_time="23:59", appraisal_value=20_000_000,
                       min_sale_price=9_800_000, fail_count=3, median_price=20_795_000, upper_bid=7_525_950),
    "today_over": dict(case_no="2026타경91115", sale_date=TODAY, sale_time="00:00", appraisal_value=20_000_000,
                       min_sale_price=9_800_000, fail_count=3, median_price=20_795_000, upper_bid=7_525_950),
    # 기일이 지난 1회 지연(stale_floor)
    "past_1": dict(case_no="2026타경91116", appraisal_value=20_000_000, min_sale_price=20_000_000, fail_count=1,
                   median_price=18_000_000, upper_bid=9_000_000, sale_date=PAST),
}
HOLD = {"stop_1": "stop", "lowc_1": "lowconf", "nomed_1": "nomed", "nomkt_1": "nomarket", "flood_1": "flood"}
RATES = {"by_court": {"수원지방법원": {"ratio": 0.7, "n": 18, "share": 1.0}}, "global": 0.7, "n": 100,
         "observed": {0.7: 100}}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    real, real_ex = socket.socket.connect, socket.socket.connect_ex

    def _lo(addr):
        h = addr[0] if isinstance(addr, tuple) and addr else addr
        return str(h) in ("127.0.0.1", "::1", "localhost")

    def deny(self, addr, *a, **k):
        if _lo(addr):
            return real(self, addr, *a, **k)
        raise AssertionError(f"외부 연결 시도 {addr!r} — 화면 테스트는 외부 요청 0 이어야 한다(C.4)")

    def deny_ex(self, addr, *a, **k):
        if _lo(addr):
            return real_ex(self, addr, *a, **k)
        raise AssertionError(f"외부 연결 시도 {addr!r} — 화면 테스트는 외부 요청 0 이어야 한다(C.4)")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_ex)


def seed(tmp_path, monkeypatch, picks=()):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "r3_view.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    monkeypatch.setattr(service, "court_reduction_rates", lambda: RATES)
    # 입찰 시각은 벽시계가 아니라 픽스처로 정한다 — 오늘 기일 두 대의 '전/후'가 실행 시각에 따라 뒤집히지 않게.
    monkeypatch.setattr(service, "sale_time_passed", lambda v, now=None: v.get("id") == "today_over")
    db.init_db()
    for vid, kw in VEH.items():
        db.upsert_vehicle({**_BASE, "id": vid, "folder_key": vid, **kw})
    built = []
    for vid, kind in picks:
        d = service._pick_dict(db.get_vehicle(vid), BT)
        d["pick_kind"] = kind
        built.append(d)
    monkeypatch.setattr(service, "get_daily_picks", lambda n=5: list(built))
    import web.app as A
    return TestClient(A.app), built


@pytest.fixture
def client(tmp_path, monkeypatch):
    return seed(tmp_path, monkeypatch)[0]


def _text(html: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))


def _get(client, vid, kind="detail"):
    path = f"/vehicle/{vid}" + ("/report" if kind == "report" else "")
    r = client.get(path, headers=_PUB)
    assert r.status_code == 200, (path, r.status_code)
    return r.text


def _amber(html):
    """상세 '가격 확인 필요' 행(dd)의 텍스트."""
    i = html.index(">가격 확인 필요</dt>")
    return _text(html[i:html.index("</dd>", i)])


def _sec01(html):
    return html[html.index('id="sec01"'):html.index('id="sec02"')]


# ── 픽스처가 그 분기를 **실제로** 만드는지(공허 통과 방지) ─────────────────────────────
def test_fixtures_really_hit_their_branches(client):
    import web.app as A
    guard = ("lag_1", "lag_g", "e300_1", "stop_1", "lowc_1", "nomed_1", "nomkt_1", "flood_1", "hist_1",
             "today_open", "today_over", "past_1")
    for vid in guard:
        assert A._floor_unconf(db.get_vehicle(vid)), f"{vid}: 가드 픽스처인데 가드가 아니다"
    for vid in ("g90_1", "block_1", "closed_r"):
        assert not service.floor_unconfirmed(db.get_vehicle(vid)), vid
    # 관심 화면 전제(app-design 확인 방법): 가드이고 **재판매 상한가 < 표시 최저가** — 예전엔 이 조건으로 로즈였다
    for vid in ("lag_1", "lag_g"):
        v = db.get_vehicle(vid)
        assert service.floor_unconfirmed(v) and v["upper_bid"] < v["min_sale_price"], vid
    b = db.get_vehicle("block_1")
    assert b["upper_bid"] < b["min_sale_price"], "비가드 대조군: 확인된 최저가 > 상한가(로즈가 남아야 한다)"
    # 저감률 출처 분기
    assert service.next_min_sale(db.get_vehicle("lag_1"))["basis"] == "court"
    assert service.next_min_sale(db.get_vehicle("lag_g"))["basis"] == "global"
    # 기일내역 분기(최저가÷감정가는 유찰 수와 맞고, 기일내역의 유찰이 모자란다)
    h = db.get_vehicle("hist_1")
    assert service.implied_reductions(h["appraisal_value"], h["min_sale_price"]) == h["fail_count"] == 3
    assert "dxdy_fails_behind" in service.floor_lag(h)
    # 매각 종료: service 신호는 참인데 화면 가드는 꺼져야 한다(F_unconf_keep_closed 의 전제)
    assert service.floor_unconfirmed(db.get_vehicle("closed_s"))
    # 오늘 기일 전/후
    assert A._bidding_over(db.get_vehicle("today_over"), TODAY)
    assert not A._bidding_over(db.get_vehicle("today_open"), TODAY)
    # 과거 1회 지연은 한 단계 지연이라 next_min 이 있다 — 게이트가 없으면 '추정'이 새어 나온다
    p = db.get_vehicle("past_1")
    assert service.next_min_sale(p) and service.bid_state(p, BT)["max_bid"]


# ── 1. 홈 캐러셀 방어선 ─────────────────────────────────────────────────────────────
def _cards(html):
    i = html.index('id="pickTrack"')
    j = html.index('id="pickDots"', i) if 'id="pickDots"' in html[i:] else html.index("</section>", i)
    track = html[i:j]
    out = {}
    for m in re.finditer(r'<a href="/vehicle/([^"]+)" class="snap-start', track):
        out[m.group(1)] = track[m.start():track.index("</a>", m.start())]
    return out


def test_carousel_card_without_expected_price_has_no_verdict_badge(tmp_path, monkeypatch):
    c, picks = seed(tmp_path, monkeypatch, picks=[("e300_1", "resale"), ("g90_1", "resale")])
    by = {p["id"]: p for p in picks}
    # 전제: 캐시 경로가 다시 쓴 저장 추천 = 예상가 없는 재판매 카드(배포 당일 E300) + 예상가 있는 대조군
    assert by["e300_1"]["expected_win"] is None
    assert by["g90_1"]["expected_win"], "대조군이 공허하면 '배지를 지웠다'가 '배지가 원래 없다'와 구별되지 않는다"
    html = c.get("/", headers=_PUB).text
    cards = _cards(html)
    assert set(cards) == {"e300_1", "g90_1"}
    guard = _text(cards["e300_1"])
    assert "되팔아도 남음" not in guard, "판정을 만든 예상낙찰가 없이 '되팔아도 남음'을 말한다"
    assert "미산출" in guard and "—" not in guard
    assert 'text-mut' in cards["e300_1"].split("AI 예상낙찰가", 1)[1][:400], "미산출은 한 단계 낮춘 회색"
    ok = _text(cards["g90_1"])
    assert "되팔아도 남음" in ok and f"{by['g90_1']['expected_win']:,}" in ok


def test_home_excluded_count_is_the_real_carousel_length(tmp_path, monkeypatch):
    """'오늘의 추천 N대 제외'의 N 은 캐러셀 장수다(H_count_fixed5 — 소스 문자열 검사는 점 조건의 같은 문자열에 속았다)."""
    c, picks = seed(tmp_path, monkeypatch, picks=[("g90_1", "resale"), ("block_1", "resale")])
    html = c.get("/", headers=_PUB).text
    assert len(_cards(html)) == len(picks) == 2
    assert '오늘의 추천 <span class="tnum">2</span>대 제외' in html


# ── 2. 리포트 가드 문장 ─────────────────────────────────────────────────────────────
def test_reduction_rate_source_is_not_asserted_as_this_court(client):
    """ⓐ 이 법원 표본이 없으면 '전국 기준 저감률'. 상세 말풍선과 리포트 요점이 같은 분기."""
    d, r = _get(client, "lag_1"), _text(_get(client, "lag_1", "report"))
    assert "이 법원 저감률을 한 번 적용해" in d and "이 법원 저감률로 약" in r
    dg, rg = _get(client, "lag_g"), _text(_get(client, "lag_g", "report"))
    assert "이 법원 저감률" not in dg and "이 법원 저감률" not in rg
    assert "전국 기준 저감률(이 법원 표본 부족)을 한 번 적용해" in dg
    assert "전국 기준 저감률(이 법원 표본 부족)로 약" in rg


@pytest.mark.parametrize("vid", ("lag_1", "lag_g", "e300_1"))
def test_guard_report_last_point_and_floor_gloss(client, vid):
    """ⓑ '현장확인뿐'·'밴드'는 가드에서 거짓 ⓒ 03 말풍선도 상세와 같은 분기."""
    html = _get(client, vid, "report")
    t = _text(html)
    for ph in ("현장확인(상태·정비비)뿐", "밴드가 조정될 수 있음", "이번 기일에 이 금액 이상 써내야"):
        assert ph not in t, f"{vid}: 가드 리포트에 '{ph}'"
    assert "미확정 요소는 이번 회차 최저가 와 현장확인(상태·정비비)입니다" in t
    assert 'aria-label="표시된 최저매각가 — 법원 목록에 표시된 금액이에요.' in html


def test_non_guard_report_keeps_the_old_sentences(client):
    t = _text(_get(client, "g90_1", "report"))
    assert "미확정 요소는 현장확인(상태·정비비)뿐이며 결과에 따라 밴드가 조정될 수 있음(09)" in t
    assert "이번 기일에 이 금액 이상 써내야 입찰돼요" in t


def test_report_insurance_history_matches_detail(client):
    """ⓓ '?' 대신 '기재 없음', 횟수엔 '회' — '검증' 태그가 '?' 옆에 붙지 않는다."""
    html = _get(client, "lag_1", "report")
    i = html.index(">보험 이력</div>")
    p = _text(html[i:html.index("</p>", i)]).replace(" ", "")
    assert "전손기재없음·침수기재없음·내차피해8회·소유자변경기재없음" in p
    assert "?" not in p


def test_guard_report_ceiling_paragraph_names_the_accident_rate(client):
    """use(절감액 내역)가 None 인 가드 물건에서 '사고 감가 N%'가 빠지고 '포함,' 쉼표만 매달렸다 — 520d 는 30%."""
    v = db.get_vehicle("lag_1")
    assert service.personal_use_detail(v, BT) is None, "전제: 가드 물건은 use 가 None"
    t = _text(_sec01(_get(client, "lag_1", "report")))
    i = t.index("정비 충당 포함,")
    tail = t[i:t.index("단, 유치권", i)]
    assert "사고 감가 30%" in tail and "정비 충당 620,000원" in tail, tail


def test_report_07_row_tag_does_not_call_the_unconfirmed_floor_current(client):
    """qa N5 — 07 수익 시뮬레이션의 낡은 최저가 행 꼬리표."""
    html = _get(client, "lag_1", "report")
    assert '<span class="tag basis">표시된 최저가</span>' in html
    assert ">현 최저가<" not in html
    assert '<span class="tag basis">현 최저가</span>' in _get(client, "g90_1", "report"), "비가드는 그대로"


# ── 3. 관심 화면 ───────────────────────────────────────────────────────────────────
def _watch(client, ids):
    r = client.get("/watchlist?ids=" + ",".join(ids), headers=_PUB)
    assert r.status_code == 200
    return r.text


def _watch_rows(html, vid):
    """표 한 줄(<tr>)과 모바일 카드(<a>) — D-day 숫자는 날마다 바뀌므로 지운다."""
    a = html.index(f'<a href="/vehicle/{vid}" class="text-primary font-medium')
    tr = html[html.rindex("<tr", 0, a):html.index("</tr>", a)]
    b = html.index(f'<a href="/vehicle/{vid}" class="block px-4 py-3')
    card = html[b:html.index("</a>", b)]
    return [re.sub(r"D-\d+", "D-N", s) for s in (tr, card)]


@pytest.mark.parametrize("vid", ("lag_1", "lag_g", "e300_1"))
def test_watchlist_guard_row_uses_list_chip_no_stale_rose_and_says_why(client, vid):
    html = _watch(client, ["lag_1", "lag_g", "e300_1", "g90_1", "block_1"])
    for seg in _watch_rows(html, vid):
        t = _text(seg)
        assert "이번 회차 최저가 확인 필요" in t, f"{vid}: 목록과 같은 칩이 아니다"
        assert "유찰 대기" not in t and "입찰 검토 가능" not in t, f"{vid}: 레거시 판정 칩"
        assert "text-rose-600" not in seg, f"{vid}: 확인되지 않은 최저가 > 상한가 로즈"
        assert "미산출 최저가 확인 필요" in t, f"{vid}: '미산출' 아래 이유 한 줄"


def test_watchlist_non_guard_rows_keep_legacy_chip_and_rose(client):
    html = _watch(client, ["lag_1", "g90_1", "block_1"])
    tr, card = _watch_rows(html, "block_1")
    assert "text-rose-600" in tr and "text-rose-600" in card, "확인된 최저가 > 상한가 로즈는 그대로"
    assert "최저가 확인 필요" not in _text(tr + card)
    assert "입찰 검토 가능" in _text(_watch_rows(html, "g90_1")[0])


# 변경 **전** 렌더에서 잰 md5 — 기준: REC-1 2회차 작업 트리 판 app.py·watchlist.html(= 이 회차 시작 시점),
# 이 파일의 seed()·_watch_rows() 를 그대로 돌린 값(보고서 §테스트). ⚠ 의도적으로 바꾸면 다시 잰다.
_WATCH_PLAIN_MD5 = {   # (표 <tr>, 모바일 카드 <a>) — scratch 변경 전 트리(app.py 19d9a8e8 · watchlist.html b0631836)에서 측정
    "g90_1": ("35aa784031e6d2c445ed1cd66cb379ee", "b2b1a8bcc30be89ba6882d2a0d4a207a"),
    "block_1": ("678940a1183a9baf27105c1ca1efda80", "74603d2b4f81ce107a29f747aa33e5f4"),
}


@pytest.mark.parametrize("vid", ("g90_1", "block_1"))
def test_watchlist_non_guard_rows_are_byte_identical_to_before(client, vid):
    html = _watch(client, ["lag_1", "lag_g", "e300_1", "g90_1", "block_1"])
    got = tuple(hashlib.md5(s.encode("utf-8")).hexdigest() for s in _watch_rows(html, vid))
    assert got == _WATCH_PLAIN_MD5[vid], f"{vid}: 가드가 아닌 관심 화면 줄이 바뀌었다 {got}"


# ── 4. 기일내역 어휘 ───────────────────────────────────────────────────────────────
def test_collected_history_wording_and_table_note(client):
    html = _get(client, "hist_1")
    a = _amber(html)
    assert "수집된 기일내역에는 유찰이 2 회까지만" in a
    assert "법원 기일내역" not in _text(html), "'법원'은 법원 사이트에만"
    i = html.index(">기일내역</h3>")
    box = html[i:html.index("</table>", i)]
    assert "수집 시점 기록입니다 — 이번 기일( 2999-01-01 ) 최저가는 이 표에 없습니다." in _text(box)
    # REC-6(모든 물건 '결과 미수집')은 이번에 하지 않는다 — 미래 날짜 행의 '예정/미확정'은 그대로여야 한다(공허 통과 방지)
    future = box[box.rindex("<tr", 0, box.index("2998-01-01")):]
    assert "예정/미확정" in future[:future.index("</tr>")]


def test_non_guard_history_table_has_no_note(client):
    html = _get(client, "g90_1")
    i = html.index(">기일내역</h3>")
    box = html[i:html.index("</table>", i)]
    assert "수집 시점 기록" not in box and "예정/미확정" in box


# ── 5. 설명 행 ④ 사유별 ───────────────────────────────────────────────────────────
def test_only_floor_reason_keeps_the_promise(client):
    a = _amber(_get(client, "lag_1"))
    assert "확인 전까지 예상낙찰가·추천 전략은 내지 않습니다" in a and "최저가를 확인해도" not in a


@pytest.mark.parametrize("vid,msg", [
    ("stop_1", "최저가를 확인해도 시동·운행 불가라 판정은 보류됩니다."),
    ("lowc_1", "최저가를 확인해도 시세 신뢰도가 낮아 판정은 보류됩니다."),
    ("nomed_1", "최저가를 확인해도 시세가 산정되지 않아 예상낙찰가는 내지 않습니다."),
    ("nomkt_1", "최저가를 확인해도 동급 시세가 없어 예상낙찰가는 내지 않습니다."),
    ("flood_1", "최저가를 확인해도 침수·전손 의심이라 입찰 보류입니다."),
])
def test_other_blocking_reason_is_said_instead_of_the_promise(client, vid, msg):
    a = _amber(_get(client, vid))
    assert msg in a, (vid, a)
    assert "확인 전까지 예상낙찰가" not in a, f"{vid}: 최저가를 확인해도 풀리지 않는데 풀릴 것처럼 약속한다"
    if vid == "stop_1":
        assert "판정 보류가 풀린 뒤에" in a and "입찰 전" not in a, "시동 불가는 '입찰 전 확인'이 할 일이 아니다"
    else:
        assert "입찰 전" in a


@pytest.mark.parametrize("vid", ("stop_1", "lowc_1"))
def test_report_says_the_same_reason(client, vid):
    t = _text(_get(client, vid, "report"))
    assert "최저가를 확인해도 " + {"stop_1": "시동·운행 불가라", "lowc_1": "시세 신뢰도가 낮아"}[vid] + " 판정은 보류됩니다." in t
    assert "확인 전까지 예상낙찰가는 내지 않습니다" not in t


def test_hold_wording_is_true_after_the_floor_is_confirmed(client, monkeypatch):
    """문구 근거: 시동 불가·신뢰도 낮음(시세 있음)은 최저가가 확인되면 예상낙찰가가 **나온다**(판정만 보류) —
    '예상낙찰가는 내지 않습니다'라고 쓰면 거짓이다. 시세 없음·동급 시세 없음은 확인해도 나오지 않는다."""
    monkeypatch.setattr(service, "floor_unconfirmed", lambda v: False)
    for vid in ("stop_1", "lowc_1"):
        v = db.get_vehicle(vid)
        assert service.expected_for(v, BT), vid
        assert service.bid_state(v, BT)["label"].endswith("판정 보류"), vid
    for vid in ("nomed_1", "nomkt_1"):
        assert service.expected_for(db.get_vehicle(vid), BT) is None, vid


@pytest.mark.parametrize("vid", ("lag_1", *HOLD))
def test_hold_reason_matches_bid_state_for_pending_guard(client, vid):
    """드리프트 가드 — app.py _floor_hold 는 bid_state 의 기일과 무관한 분기를 따른다(입찰 전 가드에서 라벨과 대조)."""
    import web.app as A
    v = db.get_vehicle(vid)
    st = service.bid_state(v, BT)
    hold = A._floor_hold(v)
    assert hold == HOLD.get(vid), (vid, hold)
    # 사유 없음 = 최저가 지연만 — 원천 라벨은 backend 가 옮길 수 있어(2회차 §6-1) 옮기기 전·후 둘 다 받는다
    expect = {None: ("wait", (A.FLOOR_WAIT_LABEL_SRC, A.FLOOR_CHECK_LABEL)),
              "stop": ("lowconf", ("시동·운행 불가 — 판정 보류",)),
              "lowconf": ("lowconf", ("시세 신뢰도 낮음 — 판정 보류",)),
              "nomed": ("lowconf", ("시세 신뢰도 낮음 — 판정 보류",)),
              "nomarket": ("nomarket", ("동급 시세 없음",)),
              "flood": ("blocked", ("침수·전손 의심 — 입찰 보류",))}[hold]
    assert st["state"] == expect[0] and st["label"] in expect[1], (vid, st["state"], st["label"])


# ── 6. 가드 상세 상한선 행 ─────────────────────────────────────────────────────────
def test_guard_ceiling_row_says_whose_line_and_its_basis(client):
    html = _get(client, "lag_1")
    i = html.index('aria-label="입찰 상한선 —')
    dt = _text(html[i:html.index("</dt>", i)])
    assert "(직접 탈 목적)" in dt
    dd = _text(html[html.index("<dd", i):html.index("</dd>", html.index("<dd", i))])
    prov = service.market_provenance(db.get_vehicle("lag_1"))
    assert "근거: 사고 감가 30%" in dd and prov["grade_ko"] in dd


# ── 7. qa N6 생존 변이 ──────────────────────────────────────────────────────────────
def test_closed_sale_is_never_guarded(client):
    """F_unconf_keep_closed — 매각 종료 물건에 '가격 확인 필요'를 내지 않는다."""
    import web.app as A
    v = db.get_vehicle("closed_s")
    assert not A._floor_unconf(v) and A._floor_guard(v, service.next_min_sale(v), TODAY) is None
    t = _text(_get(client, "closed_s"))
    assert "가격 확인 필요" not in t and "이번 회차 최저가 확인 필요" not in t


def test_today_after_bid_time_is_not_pending(client):
    """F_pending_ignore_bidtime — 오늘 입찰이 끝난 물건에게 '입찰 전 확인하세요'·추정값·조건문을 말하지 않는다."""
    import web.app as A
    v = db.get_vehicle("today_over")
    assert not A._floor_pending(v, TODAY)
    a = _amber(_get(client, "today_over"))
    assert "다음 기일이 잡히면" in a and "입찰 전" not in a and "(추정)" not in a
    r = _text(_get(client, "today_over", "report"))
    assert "이번 기일 공고 최저가가" not in r and "(추정)" not in r


def test_today_before_bid_time_is_pending(client):
    """F_pending_today_excluded — 오늘 기일도 입찰 시각 전이면 '이번 기일'이다."""
    import web.app as A
    v = db.get_vehicle("today_open")
    assert A._floor_pending(v, TODAY)
    html = _get(client, "today_open")
    a = _amber(html)
    assert "입찰 전" in a and "6,860,000원 (추정)" in a
    assert "이번 기일 예상 최저가" in _text(html)
    mb = service.bid_state(v, BT)["max_bid"]
    assert f"이번 기일 공고 최저가가 {mb:,}원을 넘으면" in _text(_get(client, "today_open", "report"))


def test_past_guard_gets_no_estimate_or_condition(client):
    """F_est_not_pending · R_ceiling_sentence_not_pending — 기일이 지난 가드에 이번 기일 추정값·상한선 조건문 없음."""
    import web.app as A
    v = db.get_vehicle("past_1")
    assert A._floor_guard(v, service.next_min_sale(v), TODAY)["est"] is None
    r = _text(_get(client, "past_1", "report"))
    assert "(추정)" not in r and "이번 기일 공고 최저가가" not in r
    assert "다음 기일이 잡히면" in r


def test_strategy_reference_only_when_the_section_exists(client):
    """D_strategy_ref_always — 추천 입찰 전략 섹션이 없는(매각 종료) 비가드 물건에서 '위 추천 입찰 전략'을 가리키지 않는다."""
    html = _get(client, "closed_r")
    assert service.expected_band(db.get_vehicle("closed_r"), BT), "전제: 예상가가 있어 _strategy 가 거짓인 이유는 매각 종료뿐"
    assert 'whitespace-nowrap">추천 입찰 전략 <span' not in html, "전제: 추천 입찰 전략 섹션이 없다"
    i = html.index("재판매 손익분기 <span")
    box = _text(html[i:html.index("입찰 메모", i)])
    assert "되팔이 목적이면 이 값 이하 로 낙찰돼야 차익." in box, "전제: 재판매 상자가 그려진다"
    assert "위 추천 입찰 전략" not in box


def test_guard_resale_box_keeps_its_own_sentence(client):
    """D_resale_old_text_on_guard · D_resale_green_on_guard — 가드 재판매 상자는 이유를 말하고 초록을 쓰지 않는다."""
    html = _get(client, "lag_1")
    i = html.index("재판매 손익분기 <span")
    t = _text(html[i:i + 1500])
    assert "표시된 최저가가 이번 회차 값으로 확인되지 않아 예상낙찰가·추천 입찰 전략은 내지 않았습니다" in t
    assert "실제 입찰가는 위" not in t
    assert "text-emerald-700" not in html[i:html.index("원 이하", i)], "이번 기일 최저가를 모르는데 초록 숫자"
