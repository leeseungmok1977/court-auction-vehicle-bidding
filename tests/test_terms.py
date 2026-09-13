"""용어 통일 — 같은 값은 화면 어디서나 같은 철자·같은 이름 (2026-09-14 디자인 검수 후속).

실측: 한 목록 카드 안에 'AI 예상 낙찰가'(띄어쓰기)와 '예상낙찰가'(붙여쓰기)가 60px 간격으로 공존했고, 최저가는 목록이
'최저입찰가', 홈은 '최저매각가'였다. 판정 칩은 '재판매 차익 가능'(초록)인데 40px 아래 태그는 '되팔아도 남음'(앰버) —
한 사실을 두 이름·두 색으로. 데이터 신뢰가 1순위인 제품에서 표기가 갈리면 다른 숫자로 오해된다.

정본: 최저매각가 · 예상낙찰가(AI 예상낙찰가) · 시세중앙값 · 되팔아도 남음(PICK_LABELS) · 지금 사면 이득(USE_TIER_LABELS).
"""
from pathlib import Path

import pytest

from web import service
from tests.test_personal_use import BT, v

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "web" / "templates"

# 변형 → 정본. 산문·라벨 가리지 않고 화면에 나가는 파일 전부에서 금지한다.
FORBIDDEN = {"예상 낙찰가": "예상낙찰가", "최저입찰가": "최저매각가", "최저 입찰가": "최저매각가",
             "시세 중앙값": "시세중앙값", "AI 예상 낙찰가": "AI 예상낙찰가"}


@pytest.mark.parametrize("path", sorted(p.relative_to(ROOT).as_posix() for p in TPL.glob("*.html")))
def test_templates_use_one_spelling_per_term(path):
    src = (ROOT / path).read_text(encoding="utf-8")
    bad = {k: src.count(k) for k in FORBIDDEN if k in src}
    assert not bad, f"{path}: 변형 표기 {bad} → {dict((k, FORBIDDEN[k]) for k in bad)}"


def test_service_user_facing_strings_use_one_spelling():
    """plain_verdict 등 화면 문장을 만드는 코드도 같은 철자 — 리포트·상세가 다른 말을 하지 않게."""
    src = (ROOT / "web" / "service.py").read_text(encoding="utf-8")
    for k in ("예상 낙찰가", "시세 중앙값"):
        assert k not in src, f"service.py 에 '{k}' 잔존 → '{FORBIDDEN[k]}'"


def test_resale_chip_says_the_same_thing_as_the_home_tag():
    """판정 칩 '재판매 차익 가능' ≠ 홈 태그 '되팔아도 남음' 이던 것을 한 이름으로."""
    car = v(min_sale_price=10_000_000, median_price=13_000_000, upper_bid=12_000_000, sale_date="2999-01-01")
    st = service.bid_state(car, BT)
    assert st["state"] == "resale" and st["label"] == service.PICK_LABELS["resale"] == "되팔아도 남음" and st["tone"] == "ok"
    src = (ROOT / "web" / "service.py").read_text(encoding="utf-8")
    assert '"재판매 차익 가능"' not in src


def test_usepick_chip_uses_the_tier_word_only_when_the_gain_is_significant():
    """'실사용이면 이득'(초록)이 오차 안 이득에도 켜져 '싸게 낙찰되면 이득'(주황) 태그와 한 카드에 놓였다.
    절감 폭 > 오차면 '지금 사면 이득'(초록, 갈래와 같은 말), 아니면 주황 '이득 불확실 — 오차 범위 안'."""
    strong = v(sale_date="2999-01-01")                          # 최저 2,200만 · 시세 4,000만 → 절감 15%p, 유의
    st = service.bid_state(strong, BT)
    assert st["state"] == "usepick" and st["label"] == service.USE_TIER_LABELS["now"] and st["tone"] == "ok"
    weak = v(min_sale_price=28_000_000, sale_date="2999-01-01")   # 예상 3,164만 ≤ 손익분기 · 이득 83만 < 오차 316만
    st2 = service.bid_state(weak, BT)
    assert st2["state"] == "usepick" and st2["tone"] == "caution" and "오차 범위 안" in st2["label"]
    # 상세 히어로의 초록 체크(opp)는 tone ok 일 때만 — 템플릿 조건 고정
    d = (TPL / "detail.html").read_text(encoding="utf-8")
    assert "bidst.state in ('resale', 'usepick') and bidst.tone == 'ok'" in d


def test_plain_verdict_admits_when_the_gain_is_within_error():
    weak = v(min_sale_price=28_000_000, sale_date="2999-01-01")
    st = service.bid_state(weak, BT)
    exp = {"price": st["exp"]}
    out = service.plain_verdict(weak, exp, st)
    assert out["tone"] == "caution" and "오차" in out["text"]
    strong = v(sale_date="2999-01-01")
    st2 = service.bid_state(strong, BT)
    out2 = service.plain_verdict(strong, {"price": st2["exp"]}, st2)
    assert out2["tone"] == "ok" and "오차 범위 안" not in out2["text"]


# ── 주황 '실사용 이득' 칩의 이유 3종 — 모르는 것을 아는 척하지 않는다 ─────────────────────
def test_weak_usepick_names_the_reason_not_a_guess():
    """오차를 모르는 유형(검증 표본 부족)에 '오차 범위 안'이라 쓰면 거짓이다. 이유별로 다른 이름."""
    weak = v(min_sale_price=28_000_000, sale_date="2999-01-01")
    st = service.bid_state(weak, BT)                                  # 절감 83만 < 오차 316만
    assert st["weak"] == "within_error" and st["label"] == service.USEPICK_WEAK_LABELS["within_error"]
    no_pool = {k: val for k, val in BT.items() if k != "pred_pool"}   # 층별 오차를 낼 표본이 없다
    st2 = service.bid_state(weak, no_pool)
    assert st2["state"] == "usepick" and st2["tone"] == "caution"
    assert st2["weak"] == "no_error_stat" and "검증 표본 부족" in st2["label"] and "범위 안" not in st2["label"]
    mism = v(min_sale_price=28_000_000, sale_date="2999-01-01", appraisal_value=100_000_000)  # 시세 4,000만 = 감정가의 40%
    st3 = service.bid_state(mism, BT)
    assert st3["state"] == "usepick" and st3["tone"] == "caution" and st3["weak"] == "saving_unverified"
    assert "시세 확인 필요" in st3["label"]
    strong = v(sale_date="2999-01-01")
    assert service.bid_state(strong, BT)["weak"] is None            # 초록엔 이유가 없다
    # 머리말은 상태('이득 불확실') — '실사용 이득 — 시세 확인 필요'는 이득을 단정하고 근거를 의심하는 자기모순(검수)
    for lab in service.USEPICK_WEAK_LABELS.values():
        assert lab.startswith("이득 불확실 — ") and "실사용 이득" not in lab, lab


def test_plain_verdict_sentence_follows_the_weak_reason(monkeypatch):
    weak = v(min_sale_price=28_000_000, sale_date="2999-01-01")
    no_pool = {k: val for k, val in BT.items() if k != "pred_pool"}
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: no_pool)
    st = service.bid_state(weak, no_pool)
    out = service.plain_verdict(weak, {"price": st["exp"]}, st)
    assert out["tone"] == "caution" and "검증 표본이 부족" in out["text"] and "오차 범위 안" not in out["text"]
    assert "입찰할 수 있고" in out["text"]                             # 판정문은 여전히 '입찰 가능'을 말한다
    mism = v(min_sale_price=28_000_000, sale_date="2999-01-01", appraisal_value=100_000_000)
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    st3 = service.bid_state(mism, BT)
    out3 = service.plain_verdict(mism, {"price": st3["exp"]}, st3)
    assert out3["tone"] == "caution" and "오매칭" in out3["text"]


def test_suspect_market_never_shows_a_green_cap(monkeypatch):
    """'시세 확인 필요' 물건의 입찰 상한선은 바로 그 의심스러운 시세로 계산한 값 — 초록·확정형으로 두지 않는다(검수 1순위).
    판정문도 의심을 먼저 말하고 상한선을 그 조건 아래 둔다("…확인하세요. 입찰 상한선 300만원도 이 시세로 계산한 값입니다")."""
    mism = v(min_sale_price=28_000_000, sale_date="2999-01-01", appraisal_value=100_000_000)
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    st = service.bid_state(mism, BT)
    out = service.plain_verdict(mism, {"price": st["exp"]}, st)
    t = out["text"]
    assert "이 시세로 계산한 값" in t and "입찰 상한선은" not in t
    assert t.index("오매칭") < t.index("입찰 상한선"), t
    d = (TPL / "detail.html").read_text(encoding="utf-8")
    assert "'text-amber-300' if bidst.weak == 'saving_unverified' else 'text-emerald-300'" in d
    assert "시세 확인 전 참고" in d


def test_detail_hero_wraps_the_chip_only_after_the_dash():
    """큰글씨 320px에서 칩이 "…시세 확인 / 필요"로 낱말 중간에 접혔다 → ' — ' 앞뒤를 각각 nowrap 조각으로(ui.judge_label).
    게이지 중앙 라벨은 주황일 때 이유만("⚠ 오차 범위 안") — 같은 문장이 한 히어로에 네 번 있었다."""
    d = (TPL / "detail.html").read_text(encoding="utf-8")
    assert "ui.judge_label(bidst.label)" in d and "flex-wrap items-center gap-x-1 px-2.5" in d
    assert "_gl.split(' — ', 1)[-1]" in d
    m = (TPL / "_macros.html").read_text(encoding="utf-8")
    assert "macro judge_label(label)" in m and "label.split(' — ', 1)" in m
    # 갈래 줄은 알약이 아니라 칩의 부제 — 배경·테두리 없음
    assert "bg-amber-400/20 text-amber-200 border" not in d


def test_gauge_row_stacks_the_judgement_when_the_card_is_narrow():
    """큰글씨 320·360px에서 게이지 아래 가운데 판정이 낱말마다 접혀 4줄 — 컨테이너 쿼리로 둘째 줄 전체 폭에.
    새 CSS 는 `npm run build:css` 전엔 app.css 에 없다 — 빌드 산출물까지 확인한다."""
    d = (TPL / "detail.html").read_text(encoding="utf-8")
    assert 'class="nc-gaugerow-host relative mt-4"' in d and 'class="nc-gaugerow flex' in d and 'class="nc-gauge-judge ' in d
    css = (ROOT / "web" / "static" / "app.css").read_text(encoding="utf-8")
    assert ".nc-gaugerow-host" in css and ".nc-gauge-judge" in css and "@container" in css
