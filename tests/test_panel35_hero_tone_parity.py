"""PANEL-35/37 회귀 — 히어로의 색은 **판정 칩과 같은 원천(bid_state().tone)** 하나에서 나온다.

원인(2026-09-23 교차검수, Steward 가 원문으로 재현):
  · 칩은 `bidst.tone`, 배너 아이콘은 `verdict.tone`(plain_verdict)을 봤다.
  · 여섯 상태 중 **lowconf 하나에서만** 갈라진다 — bid_state 는 wait/stop('…판정 보류'),
    plain_verdict 는 caution. 그래서 **회색·로즈 '판정 보류' 칩 + 앰버 '주의' 아이콘**이
    한 카드에 같이 떴다(라이브 2026타경70785_1 · 2026타경50032_1).
  · 지난 회차 캡처 3종(stop·wait·caution)은 **일치하는 상태만** 담겨 이 불일치를 못 봤다.
    그래서 이 파일은 lowconf 두 갈래를 **반드시** 포함하고, 포함됐는지까지 검사한다.

같은 계열로 대표 숫자(`_capcls`)도 state 가 아니라 tone 에서 파생한다(PANEL-37 ⑶).
"""
import re

import pytest
from starlette.testclient import TestClient

from web import service
from tests.test_render_smoke import BT, _BASE

_PUB = {"x-forwarded-for": "203.0.113.7"}

# 칩 색(app.py _TONE_CLS) · 아이콘 색(detail.html) → 톤. 두 사전이 같은 톤을 가리켜야 한다.
CHIP_TONE = {"bg-emerald-50": "ok", "bg-amber-50": "caution",
             "bg-rose-50": "stop", "bg-slate-100": "wait"}
ICON_TONE = {"text-emerald-300": "ok", "text-amber-300": "caution",
             "text-rose-300": "stop", "text-slate-300": "wait"}

# 상태 → 그 상태를 실제로 만드는 필드. 히어로는 detail.html:288 에서
# `median_price is not none and expected and expected.price` 로 막혀 있으므로
# **med·exp 가 둘 다 나오는 값**이어야 한다(아니면 아이콘이 아예 안 그려져 공허 통과).
CASES = {
    "resale":       dict(min_sale_price=10_000_000, appraisal_value=12_000_000,
                         median_price=13_000_000, upper_bid=14_000_000),
    "usepick":      dict(min_sale_price=28_000_000, appraisal_value=30_000_000,
                         median_price=40_000_000),
    # ⚠ 처음 쓴 값(최저 1,400만 / 시세 1,660만)은 실제로 **blocked** 로 떨어져
    #   over_market 이 한 번도 렌더되지 않았다 — ⑶(칩은 앰버인데 숫자는 로즈)이 났던
    #   **바로 그 상태**가 검사에서 통째로 빠져 있었던 것이다(공허 통과).
    #   아래 값은 최저매각가(950만) ≤ 상한선(1,040만) < 예상 경쟁가(1,070만) 창을 만든다.
    "over_market":  dict(min_sale_price=9_500_000, appraisal_value=12_350_000,
                         median_price=13_000_000),
    "blocked":      dict(min_sale_price=16_000_000, appraisal_value=20_000_000,
                         median_price=16_600_000),
    "flood":        dict(min_sale_price=9_000_000, appraisal_value=12_000_000,
                         median_price=13_000_000, accident_grade="flood",
                         judgment="입찰 보류"),
    # ↓ 불일치가 실제로 났던 두 갈래
    "lowconf":      dict(min_sale_price=9_000_000, appraisal_value=12_000_000,
                         median_price=13_000_000, market_confidence_label="낮음",
                         market_confidence=31),
    "not_runnable": dict(min_sale_price=10_000_000, appraisal_value=12_000_000,
                         median_price=15_000_000, runnable="no"),
    "past_date":    dict(min_sale_price=10_000_000, appraisal_value=12_000_000,
                         median_price=15_000_000, sale_date="2020-01-01"),
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tone.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    for i, (name, extra) in enumerate(CASES.items()):
        db.upsert_vehicle({**_BASE, "id": f"{name}_1", "folder_key": f"{name}_1",
                           "case_no": f"2026타경8{i:03d}", "judgment": "유찰 대기", **extra})
    import web.app as A
    return TestClient(A.app)


def _hero(html: str) -> dict:
    """히어로에서 아이콘·칩·대표 숫자·게이지 라벨을 뽑는다."""
    icon = re.search(r"material-symbols-outlined text-lg shrink-0 mt-px (text-[a-z]+-\d+)", html)
    chip = re.search(r'px-2\.5 py-1 rounded text-sm font-semibold ([^"]+)"', html)
    big = re.search(r'nc-heronum-lg font-mono text-3xl font-bold tnum (text-[a-z0-9/\-]+)', html)
    gauge = re.search(r'class="nc-gauge-judge[^"]*"[^>]*>(.*?)</div>', html, re.S)
    return {"icon": icon.group(1) if icon else None,
            "chip": chip.group(1) if chip else None,
            "big": big.group(1) if big else None,
            "gauge": re.sub(r"\s+", " ", gauge.group(1)).strip() if gauge else None}


def _state(name):
    from web import db
    return service.bid_state(db.get_vehicle(f"{name}_1"), BT)


@pytest.mark.parametrize("name", list(CASES))
def test_chip_and_icon_always_agree(client, name):
    """한 카드 안에서 칩과 아이콘이 **반대 색**을 말하지 않는다."""
    h = _hero(client.get(f"/vehicle/{name}_1", headers=_PUB).text)
    assert h["icon"] and h["chip"], f"{name}: 히어로가 렌더되지 않았다 — 이 검사가 공허하다"
    chip_tone = next((t for k, t in CHIP_TONE.items() if k in h["chip"]), None)
    assert chip_tone, f"{name}: 칩 색을 못 읽었다 ({h['chip']})"
    assert h["icon"] in ICON_TONE, f"{name}: 아이콘 색이 톤 체계 밖이다 ({h['icon']})"
    st = _state(name)
    assert ICON_TONE[h["icon"]] == chip_tone == st["tone"], (
        f"{name}: 판정 {st['state']}/{st['tone']} 인데 칩={chip_tone} 아이콘={ICON_TONE[h['icon']]}")


def test_the_lowconf_divergence_is_actually_in_this_fixture_set(client):
    """★ 이 파일이 공허하지 않음을 증명한다 — 아이콘이 `verdict.tone` 을 보던 시절
    **실제로 갈라졌던** 물건이 픽스처 안에 있어야 한다. 없으면 위 검사는 전부 통과하고도
    아무것도 지키지 않는다(지난 회차 캡처 3종이 바로 그랬다)."""
    from web import db
    split = []
    for name in CASES:
        v = db.get_vehicle(f"{name}_1")
        st = service.bid_state(v, BT)
        vt = (service.plain_verdict(v, service.expected_band(v, BT), st) or {}).get("tone")
        if vt and vt != st["tone"]:
            split.append((name, st["state"], st["tone"], vt))
    assert split, "bid_state 와 plain_verdict 가 갈라지는 물건이 하나도 없다 — 회귀를 못 잡는다"
    assert {s[1] for s in split} <= {"lowconf", "closed"}, f"새로운 갈래가 생겼다: {split}"
    assert any(s[1] == "lowconf" for s in split), f"lowconf 갈래가 사라졌다: {split}"


def test_all_four_tones_are_covered(client):
    """네 톤(ok·caution·stop·wait)이 모두 한 번씩은 렌더돼야 색 규칙 전체가 검사된다."""
    tones = {_state(n)["tone"] for n in CASES}
    assert tones == {"ok", "caution", "stop", "wait"}, f"톤 커버리지 부족: {tones}"


# ── PANEL-37 ⑶ 대표 숫자는 state 가 아니라 tone ────────────────────────────
def test_headline_number_follows_the_tone_not_the_state(client):
    """tone=caution 인 over_market 에서 **칩은 앰버인데 숫자만 로즈**였다.
    `_over`(최저매각가 > 상한선)일 때만 tone 과 무관하게 로즈로 남긴다."""
    from web import db
    seen = {}
    for name in CASES:
        st = _state(name)
        if not st.get("max_bid"):
            continue                      # 상한선이 없으면 대표 숫자가 예상낙찰가 자리다
        h = _hero(client.get(f"/vehicle/{name}_1", headers=_PUB).text)
        over = st.get("floor") and st["floor"] > st["max_bid"]
        seen[name] = (st["tone"], over, h["big"])
        if over:
            assert h["big"] == "text-rose-300", f"{name}: 써낼 수 없는 금액인데 로즈가 아니다"
        elif st["tone"] == "caution" and st.get("weak") != "saving_unverified":
            assert h["big"] == "text-amber-300", f"{name}: 칩은 앰버인데 숫자는 {h['big']}"
        elif st["tone"] == "ok":
            assert h["big"] == "text-emerald-300", f"{name}: {seen[name]}"
    assert seen, "상한선이 있는 물건이 하나도 없어 공허하다"


# ── PANEL-37 ⑵ 게이지는 기호 + 이유만 ─────────────────────────────────────
# 판정을 **선언하는** 낱말. 이것들은 칩의 몫이라 게이지에 두 번 나오면 안 된다
# (한 화면에 같은 판정이 두 번 = 이 저장소가 반복해 막아 온 '경고색 희석'의 문턱).
VERDICT_WORDS = ("판정 보류", "입찰 보류", "입찰 부적합", "입찰 비권장",
                 "이득 불확실", "되팔아도 남음", "지금 사면 이득")


@pytest.mark.parametrize("name", list(CASES))
def test_gauge_says_the_reason_not_the_verdict(client, name):
    """게이지는 **기호 + 이유**만 말한다 — 판정 이름은 바로 위 칩이 이미 말했다.

    ⚠ '이유'의 자리는 라벨마다 다르다: `이득 불확실 — 오차 범위 안`은 대시 **뒤**가 이유지만
      `시세 신뢰도 낮음 — 판정 보류`는 대시 **앞**이 이유다. 그래서 대시 라벨은 양쪽 중
      하나여야 하고, **라벨 전문 그대로**여서는 안 된다.
    ⚠ `예상 경쟁가가 상한선 초과`(over_market)처럼 라벨 자체가 이미 이유뿐인 경우는
      칩과 글자가 같아도 된다 — 반복되는 것이 '판정'이 아니기 때문이다. 그 경우까지
      금지하면 없는 낱말을 새로 지어내야 한다.
    """
    html = client.get(f"/vehicle/{name}_1", headers=_PUB).text
    h = _hero(html)
    if not h["gauge"]:
        return                             # 세 값이 같으면 게이지를 그리지 않는다(0 나누기 방지)
    label = _state(name)["label"]
    body = h["gauge"].lstrip("✓⚠✕↑ ").strip()
    assert body, f"{name}: 게이지에 이유가 비었다"
    bad = [w for w in VERDICT_WORDS if w in body]
    assert not bad, f"{name}: 게이지가 판정을 또 말한다{bad} — 칩이 이미 말했다({body!r})"
    if " — " in label:
        assert body != label, f"{name}: 게이지가 라벨 전문을 반복한다({body!r})"
        assert body in (label.split(" — ", 1)[0], label.split(" — ", 1)[-1]), (
            f"{name}: 이유가 라벨의 어느 쪽도 아니다 — {body!r} vs {label!r}")


def test_both_expected_price_captions_use_the_same_colour():
    """PANEL-37 ⑴ — 같은 낱말이 분기에 따라 앰버/흰색으로 갈리면 안 된다.
    앰버는 이 앱에서 '조건부 경고'라 캡션에 쓰면 없는 경고를 만든다."""
    import pathlib
    d = (pathlib.Path(__file__).resolve().parents[1] / "web" / "templates"
         / "detail.html").read_text(encoding="utf-8")
    caps = re.findall(r'<div class="text-xs ([^"]+?) mb-0\.5"[^>]*>'
                      r'<span class="whitespace-nowrap[^"]*">AI 예상낙찰가</span>', d)
    assert len(caps) == 2, f"'AI 예상낙찰가' 캡션 분기가 둘이 아니다: {caps}"
    assert caps[0] == caps[1] == "text-white/55", f"캡션 색이 갈린다: {caps}"
