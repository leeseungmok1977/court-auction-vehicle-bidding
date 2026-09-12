"""출시가(보배드림) 수집 대상 선별·우선순위 테스트 — 2026-09-12.

배경: 일일 갱신 ②-2가 매일 돌고 있었지만 입찰예정 428건 중 확보는 6건뿐이었고,
**홈에서 가장 먼저 보이는 추천 17건은 확보 0건**이었다(잔존가치 축이 전부 '미산출').
원인은 물건 구성 — (모델,연식) 320가지 중 270가지가 1건씩이라 캐시 이점이 안 생긴다.

대응 두 가지:
  ① 순서: 추천 → 매각 임박 순으로 채워 '보이는 화면'부터 살린다(요청량 증가 없음).
  ② 제외: 신차 가격표가 없는 중장비·특장만 좁게 걸러 예산 낭비를 막는다.
     ⚠ 상용차를 통째로 빼면 안 된다 — 포터2 일렉트릭은 실제로 매칭에 성공했다(4,060~4,274만원).

상한은 사용자 승인으로 300 → 1200으로 올렸다. **올린 만큼 나머지 안전장치는 반드시 유지**되어야
하므로 지연·물건당 상한·백오프를 이 테스트가 고정한다.
"""
import pytest

from web import service


def v(model, **kw):
    d = {"id": kw.pop("id", "X1"), "model": model, "year": kw.pop("year", 2020)}
    d.update(kw)
    return d


# ── ① 제외 규칙 ────────────────────────────────────────────────
@pytest.mark.parametrize("model", [
    "덤프트럭", "덤프트럭 TGS 37.500 8X4 BB", "굴착기", "지게차", "공기압축기",
    "콘크리트 펌프", "정우32KL탱크로리", "노바스스카이고소작업차",
    "대우25톤카고트럭", "한중4톤카고", "삼부5.5톤냉장윙바디트럭", "한국쓰리축6.5톤트럭",
])
def test_skip_heavy_equipment(model):
    """신차 가격표가 없는 중장비·특장은 건너뛴다(물건당 최대 45요청 낭비 방지)."""
    assert service.newcar_skip(v(model)) is True


@pytest.mark.parametrize("model", [
    "포터Ⅱ (PORTERⅡ)", "포터Ⅱ 일렉트릭 (PORTERⅡ ELECTRIC)", "포터 2 (PORTER2)",
    "봉고Ⅲ 1톤", "봉고3 1톤", "봉고III 플러스내장차", "마이티",
    "렉스턴스포츠", "렉스턴스포츠 칸", "카니발", "그랜저(GRANDEUR)", "G80",
])
def test_keep_light_commercial_and_passenger(model):
    """경상용·승용은 반드시 남긴다 — 포터2는 실제 매칭 성공 사례가 있다."""
    assert service.newcar_skip(v(model)) is False


def test_empty_model_not_skipped_here():
    """모델명이 없으면 앞단에서 요청 0으로 걸러지므로 여기서 막지 않는다."""
    assert service.newcar_skip(v("")) is False
    assert service.newcar_skip({"model": None}) is False


# ── ② 우선순위 ────────────────────────────────────────────────
def test_pool_puts_recommended_first():
    rows = [
        v("쏘나타", id="A", judgment="유찰 대기", sale_date="2026-09-20"),
        v("K5",     id="B", judgment="입찰 검토 가능", sale_date="2026-09-30"),
        v("그랜저", id="C", judgment="시세 신뢰도 낮음", sale_date="2026-09-15"),
        v("G80",    id="D", judgment="입찰 검토 가능", sale_date="2026-09-18"),
    ]
    order = [x["id"] for x in service.newcar_pool(rows, cutoff="2026-08-13")]
    assert order[:2] == ["D", "B"], "추천 물건이 먼저, 그중 매각 임박 순이어야 한다"
    assert order[2:] == ["C", "A"], "나머지도 매각 임박 순"


def test_pool_filters():
    rows = [
        v("쏘나타", id="ok"),
        v("쏘나타", id="no_year", year=None),
        v("덤프트럭", id="heavy"),
        v("K5", id="recent", newcar_checked_at="2026-09-01"),   # cutoff 이후 → 재시도 안 함
        v("K5", id="stale",  newcar_checked_at="2026-07-01"),   # cutoff 이전 → 재시도
    ]
    got = {x["id"] for x in service.newcar_pool(rows, cutoff="2026-08-13")}
    assert got == {"ok", "stale"}


def test_manual_pick_ignores_skip_rules():
    """관리자가 특정 물건을 콕 집으면 중장비라도 시도한다(사람의 판단 우선)."""
    rows = [v("덤프트럭", id="H"), v("쏘나타", id="S")]
    got = [x["id"] for x in service.newcar_pool(rows, cutoff="2026-08-13", vehicle_ids=["H"])]
    assert got == ["H"]


# ── ③ 상한을 올린 만큼 나머지 안전장치는 고정 ──────────────────
def test_safety_knobs_unchanged_after_cap_raise():
    from src.collect import bobae
    assert bobae.REQUEST_DELAY_SEC >= 5, "요청 간 지연은 5초 이상이어야 한다(C.4-2)"
    assert service.NEWCAR_MAX_REQ_PER_VEHICLE <= 45, "물건 하나가 일일 예산을 독식하면 안 된다"
    assert service.NEWCAR_RECHECK_DAYS >= 30, "실패 물건 재시도 백오프가 짧아지면 헛요청이 는다"
    assert 0 < service.NEWCAR_DAILY_CAP <= 2000, "런당 하드캡은 반드시 존재해야 한다(C.4-1)"


def test_cap_raised_as_approved():
    assert service.NEWCAR_DAILY_CAP == 1200, "2026-09-12 사용자 승인값"
