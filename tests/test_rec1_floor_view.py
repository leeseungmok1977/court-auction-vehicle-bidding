# -*- coding: utf-8 -*-
"""REC-1 2회차(지시서 2026-09-29-28) — 최저가 지연 가드 상태의 **화면**.

1회차는 판정만 고쳤다(부푼 예상낙찰가 제거). 화면은 그대로여서 세 곳이 사용자에게 틀린 행동을 시켰다.
  · qa F1   리포트가 가드 물건 59대 중 26대에 '이번 기일은 어떤 금액을 써도 손해'·'써낼 수 없는 금액' —
            상세는 같은 물건을 '공고 대기'로 말했다(반대 판정). 사유는 59대 모두 '표본·조건 불충족'(거짓).
  · qa F2   다회차 지연 물건의 상세에 설명이 없다 — 회색 칩 하나, 낡은 최저가가 화면에서 가장 큰 숫자.
  · 교차검수 '약 N회 추가 유찰 예상'(낡은 출발선으로 셈) · '위 추천 입찰 전략'(없는 섹션) · '다음 기일 예상
            최저가'(사실상 이번 기일 값) · 입찰 상한선까지 사라짐 · 보험이력 '?'(=의심으로 읽힘).
Steward 결정: 칩 문구는 지연 가드·stale_floor 공통 **'이번 회차 최저가 확인 필요'**(법원은 이미 공고했다).

가리킬 때는 줄 번호가 아니라 **앵커 문자열**로 가리킨다(CLAUDE.md 규칙 8).
외부 요청 0 — 루프백 밖 소켓 연결을 막는다(TEST-1: 전역 가드 없음).
"""
import hashlib
import re
import socket
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from web import db, service
from tests.test_render_smoke import BT

ROOT = Path(__file__).resolve().parents[1]
_PUB = {"x-forwarded-for": "203.0.113.7"}
FAR = "2999-01-01"                       # 기일이 남은 물건(날짜가 바뀌어도 렌더 바이트가 같게 — 아래 md5 대조용)
PAST = "2020-01-01"

_BASE = {"court": "수원지방법원", "maker": "현대", "model": "쏘나타", "year": 2020, "item_no": "1",
         "sale_date": FAR, "sale_time": "10:00", "status": "완료", "market_confidence": 78,
         "market_confidence_label": "높음", "sample_count": 12, "photo_count": 3, "judgment": "유찰 대기"}

VEH = {
    # 520d 꼴: 감정 2,000만 · 최저 980만(=0.7², 저감 2회) · 유찰 3회 → 한 단계 지연. 사고이력 '내차 8회'.
    "lag_1": dict(case_no="2026타경90101", appraisal_value=20_000_000, min_sale_price=9_800_000, fail_count=3,
                  median_price=20_795_000, upper_bid=7_525_950, accident_grade="accident",
                  insurance_history={"own_damage": 8, "opp_damage": 2}),
    # 여러 단계 지연: 최저가 = 감정가(저감 0회)인데 유찰 3회 → 추정값을 쓰지 않는다.
    "multi_1": dict(case_no="2026타경90102", appraisal_value=13_000_000, min_sale_price=13_000_000, fail_count=3,
                    median_price=9_900_000, upper_bid=4_294_000),
    # 카니발 꼴: 낡은 최저가(1,120만)가 입찰 상한선보다 높다 → 가드가 없으면 리포트가 '어떤 금액을 써도 손해'라고 했다.
    "carn_1": dict(case_no="2026타경90103", model="카니발", appraisal_value=16_000_000, min_sale_price=11_200_000,
                   fail_count=2, median_price=11_500_000, upper_bid=5_832_000),
    # 가드가 아닌 물건 두 대(G90·SM6 꼴) — 렌더가 예전과 같아야 한다.
    "g90_1": dict(case_no="2026타경90104", model="G90", appraisal_value=29_000_000, min_sale_price=16_240_000,
                  fail_count=2, median_price=34_050_000, upper_bid=17_818_000),
    "sm6_1": dict(case_no="2026타경90105", model="SM6", appraisal_value=20_000_000, min_sale_price=14_000_000,
                  fail_count=1, median_price=18_000_000, upper_bid=12_000_000),
    # 기일이 지난 1회 지연(stale_floor) — '입찰 전 이번 기일' 문장은 쓰지 않는다(할 수 없는 일).
    "past_1": dict(case_no="2026타경90106", appraisal_value=20_000_000, min_sale_price=20_000_000, fail_count=1,
                   median_price=18_000_000, upper_bid=9_000_000, sale_date=PAST),
}
GUARD = ("lag_1", "multi_1", "carn_1")
PLAIN = ("g90_1", "sm6_1")


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


def seed(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "floor_view.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    monkeypatch.setattr(service, "get_daily_picks", lambda n=5: [])
    db.init_db()
    for vid, kw in VEH.items():
        db.upsert_vehicle({**_BASE, "id": vid, "folder_key": vid, **kw})
    import web.app as A
    return TestClient(A.app)


@pytest.fixture
def client(tmp_path, monkeypatch):
    return seed(tmp_path, monkeypatch)


def _text(html: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))


def _get(client, vid, kind="detail"):
    path = f"/vehicle/{vid}" + ("/report" if kind == "report" else "")
    r = client.get(path, headers=_PUB)
    assert r.status_code == 200, (path, r.status_code)
    return r.text


# ── 픽스처가 그 분기를 **실제로** 만드는지(공허 통과 방지) ─────────────────────────────
def test_fixtures_really_hit_the_guard(client):
    for vid in GUARD:
        v = db.get_vehicle(vid)
        assert service.floor_unconfirmed(v), f"{vid}: 가드 픽스처인데 floor_unconfirmed 가 거짓"
        st = service.bid_state(v, BT)
        assert st["state"] == "wait" and st["exp"] is None, (vid, st["state"], st["exp"])
        assert st["max_bid"], f"{vid}: 입찰 상한선이 없으면 '상한선 유지' 검사가 공허하다"
    assert service.floor_lagging(db.get_vehicle("lag_1"))
    assert service.implied_reductions(20_000_000, 9_800_000) == 2
    carn = service.bid_state(db.get_vehicle("carn_1"), BT)
    assert carn["max_bid"] < 11_200_000, "카니발 픽스처 전제: 낡은 최저가 > 상한선(=가드 없으면 '손해' 판정)"
    for vid in PLAIN:
        assert not service.floor_unconfirmed(db.get_vehicle(vid)), vid
    assert service.stale_floor(db.get_vehicle("past_1"))


# ── 상세: 낡은 최저가로 만든 문장이 없다 ────────────────────────────────────────────
_DETAIL_BANNED = ("추가 유찰 예상", "다음 기일 예상 최저가", "위 추천 입찰 전략", "공고 대기", "자동 반영",
                  "써낼 수 없는 금액", "어떤 금액을 써도 손해", "이번 기일에 이 금액 이상 써내야")


@pytest.mark.parametrize("vid", GUARD)
def test_guard_detail_drops_sentences_built_on_the_stale_floor(client, vid):
    t = _text(_get(client, vid))
    for ph in _DETAIL_BANNED:
        assert ph not in t, f"{vid}: 가드 상태 상세에 '{ph}'"


@pytest.mark.parametrize("vid", GUARD)
def test_guard_detail_says_why_what_to_do_and_keeps_the_ceiling(client, vid):
    html = _get(client, vid)
    t = _text(html)
    mb = service.bid_state(db.get_vehicle(vid), BT)["max_bid"]
    assert "이번 회차 최저가 확인 필요" in t, "칩 문구(Steward 결정)"
    assert "가격 확인 필요" in t, "설명 행"
    assert "기일내역" in t and "입찰 전" in t, "할 일"
    assert "예상낙찰가·추천 전략은 내지 않습니다" in t, "예상낙찰가를 내지 않는 이유"
    # 입찰 상한선 — 최저가와 무관한 값이라 가드 상태에서도 보인다(조건문으로)
    assert f"{mb:,} 원" in t, f"{vid}: 입찰 상한선 {mb:,} 이 상세에 없다"
    assert "이번 기일 공고 최저가가 이 금액을 넘으면" in t
    # 낡은 최저가는 '이번 기일에 이 금액 이상'이라는 말풍선 없이, 대표 숫자처럼 보이지 않게(본문 단계)
    i = html.index('aria-label="최저매각가 —')
    j = html.index("<dd", i)
    assert "법원 목록에 표시된 금액이에요" in html[i:j]
    dd = html[j:html.index("</dd>", j)]
    assert "text-lg" not in dd, "가드 상태의 최저매각가가 여전히 가장 큰 숫자다"


def test_one_step_lag_shows_this_sale_estimate_multi_step_does_not(client):
    t = _text(_get(client, "lag_1"))
    compact = t.replace(" ", "")
    assert "직전 회차 값" in t and "유찰3회인데최저가가감정가의49%(저감2회분)" in compact
    assert "이번 기일 예상 최저가" in t and "(공고 확인 전)" in t
    assert "6,860,000" in t, "한 단계 지연 = 기존 next_min_sale 값(980만×0.7)"
    m = _text(_get(client, "multi_1"))
    assert "이전 회차 값" in m and "여러 회차가 빠져 있어" in m
    assert "이번 기일 예상 최저가" not in m, "여러 단계 지연 물건에 추정값을 쓰면 이번 기일보다 높은 값이 된다"
    assert "감정가와 같음" not in m, "'감정가와 같음'은 다회차 지연에 쓰지 않는다"


def test_520d_ceiling_reflects_the_30pct_accident_rate(client):
    """사고 '내차 8회' → 사고 감가 30%가 반영된 상한선이어야 한다(값은 service 가 낸다 — 화면은 그 값을 그대로)."""
    v = db.get_vehicle("lag_1")
    rate, assumed = service.use_accident_rate(v)
    assert rate == pytest.approx(0.30) and not assumed
    mb = service.bid_state(v, BT)["max_bid"]
    assert f"{mb:,}" in _text(_get(client, "lag_1"))


# ── 리포트: 상세와 반대 판정을 내지 않는다(qa F1) ──────────────────────────────────
_REPORT_BANNED = ("어떤 금액을 써도 손해", "써낼 수 없는 금액", "표본·조건 불충족", "다음 기일 예상 최저가",
                  "추가 유찰 대기 권장", "공고 대기")


@pytest.mark.parametrize("vid", GUARD)
def test_guard_report_does_not_contradict_detail(client, vid):
    t = _text(_get(client, vid, "report"))
    for ph in _REPORT_BANNED:
        assert ph not in t, f"{vid}: 가드 상태 리포트에 '{ph}'"
    mb = service.bid_state(db.get_vehicle(vid), BT)["max_bid"]
    assert "이번 회차 최저가 확인 필요" in t
    assert f"이번 기일 공고 최저가가 {mb:,}원을 넘으면" in t, "상한선 조건문 — 상세와 같은 값"
    assert "이번 회차 최저가가 확인되지 않아" in t, "미산출 사유는 표본이 아니라 최저가 미확인"


def test_carnival_report_used_to_say_loss_now_does_not(client):
    """픽스처 전제(낡은 최저가 > 상한선)가 그대로인데 '손해' 문장이 없어야 한다 — 비교 대상이 이번 기일 값이 아니다."""
    html = _get(client, "carn_1", "report")
    head = html[html.index('id="sec01"'):html.index('id="sec02"')]
    assert "chip risk" not in head


# ── 목록 카드: 같은 칩 문구 · 낡은 최저가 기준 로즈 없음 ────────────────────────────
def test_list_card_uses_the_same_chip_and_no_stale_rose(client):
    html = client.get("/vehicles?q=" + "카니발", headers=_PUB).text
    assert "이번 회차 최저가 확인 필요" in html
    assert "다음 기일 최저가 공고 대기" not in html
    i = html.index("입찰 상한 <b")
    span = html[html.rindex("<span", 0, i):i]
    assert "text-rose-600" not in span, "낡은 최저가 > 상한선 이라는 이유로 상한을 로즈로 칠했다"


# ── 기일이 지난 1회 지연: 할 수 없는 일을 시키지 않는다 ─────────────────────────────
def test_past_stale_floor_does_not_ask_to_check_before_bidding(client):
    t = _text(_get(client, "past_1"))
    assert "가격 확인 필요" in t and "다음 기일이 잡히면" in t
    # ⚠ '자동 반영' 전체가 아니라 **최저가**에 대한 약속만 본다 — 매각 일시 칸의 '법원 재공고 후 자동 반영'은
    #   날짜 이야기라(목록 갱신이 기일을 옮긴다) 이 티켓 범위 밖이다.
    for ph in ("입찰 전 법원경매정보", "이번 기일 예상 최저가", "다음 기일 예상 최저가", "공고되면 자동 반영"):
        assert ph not in t, ph
    r = _text(_get(client, "past_1", "report"))
    assert "어떤 금액을 써도 손해" not in r and "다음 기일 예상 최저가" not in r


# ── 보험이력: '?' 대신 '기재 없음', 횟수엔 '회' ───────────────────────────────────
def test_insurance_history_says_not_recorded_instead_of_question_mark(client):
    html = _get(client, "lag_1")
    i = html.index(">보험이력</dt>")
    dd = _text(html[i:html.index("</dd>", i)])
    assert "전손 기재 없음" in dd and "침수 기재 없음" in dd and "소유자변경 기재 없음" in dd
    assert "내차피해8회" in dd.replace(" ", "")
    assert "?" not in dd


# ── 홈 '오늘의 추천 5대 제외' 고정값 ─────────────────────────────────────────────
def test_no_hard_coded_carousel_count():
    for name in ("dashboard.html", "vehicles.html"):
        src = (ROOT / "web" / "templates" / name).read_text(encoding="utf-8")
        assert "5대 제외" not in src and "추천 5대 외에" not in src and "홈의 8대는" not in src, name
    src = (ROOT / "web" / "templates" / "dashboard.html").read_text(encoding="utf-8")
    assert "daily_picks|length" in src, "장수는 실제 캐러셀에서 센다"


# ── 가드가 아닌 물건은 예전과 같은 바이트 ──────────────────────────────────────────
# 변경 **전** 렌더에서 잰 md5 — 기준: 저장소 8073a3d 템플릿 + REC-1 1회차 작업 트리 app.py(가드는 있고 화면 분기는 없던 상태),
# 이 파일의 픽스처(g90_1·sm6_1), BT=tests.test_render_smoke.BT, config.yaml(작업 트리). 구역은 앵커 문자열로 자른다.
# ⚠ 이 구역을 **의도적으로** 바꾸면 이 값을 다시 재야 한다 — 가드 분기를 건드리다 비가드 물건이 바뀌는 사고를 잡는 자리다.
_REGIONS = {
    "detail:물건정보": ('<dl class="nc-kv', "</dl>"),
    "detail:산정근거": (">입찰가 산정 근거</h3>", "입찰 메모"),
    "report:01": ('id="sec01"', 'id="sec02"'),
}
_PLAIN_MD5 = {   # 측정: 변경 전 트리에서 이 파일의 seed()·_region_md5() 를 그대로 돌린 값(보고서 §테스트)
    "g90_1": {"detail:물건정보": "fb500dcd49e54d85e2f4ecb8045d2b4e",
              "detail:산정근거": "fb1000134e61cd35e5c28dd86cfb125c",
              "report:01": "45cc954fee7d5b6fbcd9538e08d02a35"},
    "sm6_1": {"detail:물건정보": "81728f9087954a2575134954b3984b40",
              "detail:산정근거": "9b3532ef020026e0cde7c73e620d05d6",
              "report:01": "13a5a9d90dcbe87754944214a243262c"},
}


def _region_md5(client, vid):
    out = {}
    for key, (a, b) in _REGIONS.items():
        kind = key.split(":")[0]
        html = _get(client, vid, kind)
        i = html.index(a)
        seg = html[i:html.index(b, i)]
        out[key] = hashlib.md5(seg.encode("utf-8")).hexdigest()
    return out


@pytest.mark.parametrize("vid", PLAIN)
def test_non_guard_render_is_byte_identical_to_before(client, vid):
    got = _region_md5(client, vid)
    assert got == _PLAIN_MD5[vid], f"{vid}: 가드가 아닌 물건의 렌더가 바뀌었다 {got}"


@pytest.mark.parametrize("vid", PLAIN)
def test_non_guard_keeps_the_old_wording(client, vid):
    t = _text(_get(client, vid))
    assert "이번 기일에 이 금액 이상 써내야" in t, "확인된 최저가의 말풍선은 그대로"
    assert "다음 기일 예상 최저가" in t
    assert "가격 확인 필요" not in t and "이번 회차 최저가 확인 필요" not in t
