"""18인 페르소나 패널 2회차(2026-09-14) 지적 7건 조치 회귀 가드.

패널 지적을 그대로 믿지 않고 코드로 재검증한 뒤 고친 것들이다 — 8건 중 3건은 검증에서 뒤집혔고
(산식 중복은 요율이 우연히 같은 것이었고, 리포트 사진 누락은 우리 캡처 스크립트 문제였다),
남은 것과 새로 확인된 결함을 여기서 고정한다.

1. 기일 **시각**이 지난 물건이 '유찰 대기'로 남았다 — 판정이 날짜만 비교했다.
2. 화물차에 비영업용 승용 7% 취득세를 그대로 썼다 — 총액이 틀리면 상한선·마진이 전부 틀어진다.
3. 사진 정렬 폴백이 보관장소 지적도를 빼지 않아 미분류 물건은 지도부터 보였다.
4. 카드의 가장 큰 숫자가 '예상낙찰가'라 60·70대가 '써도 되는 금액'으로 읽었다.
5. 리포트 산식에 요율·기준이 없어 검산이 닫히지 않았다.
6. 정확도 지표가 세 곳에서 다른 얼굴로 나왔다 / 신뢰도 등급 경계가 비공개였다.
7. 큰글씨 모드에서 칩이 잘리고 리포트에 목차가 없었다.
"""
from datetime import date, datetime
from pathlib import Path

import pytest

from web import service
from tests.test_personal_use import BT, v

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "web" / "templates"


# ── 1. 기일 시각 ────────────────────────────────────────────────
def test_sale_time_is_read_as_a_time_not_just_a_date():
    """'10:00' 기일 물건이 같은 날 13:18에도 '유찰 대기'면 실무자는 기일 표기 전체를 못 믿는다."""
    car = {"sale_time": "10:00"}
    assert service.sale_time_passed(car, datetime(2026, 9, 14, 9, 59)) is False
    assert service.sale_time_passed(car, datetime(2026, 9, 14, 10, 0)) is True
    assert service.sale_time_passed(car, datetime(2026, 9, 14, 13, 18)) is True
    # 시각을 모르면 판단하지 않는다(지나지 않은 것으로 — 보수적)
    assert service.sale_time_passed({}, datetime(2026, 9, 14, 23, 0)) is False
    assert service.sale_time_passed({"sale_time": "오전 10시"}, datetime(2026, 9, 14, 23, 0)) is False
    assert service.sale_time_passed({"sale_time": "99:99"}, datetime(2026, 9, 14, 23, 0)) is False


def test_state_turns_to_elapsed_after_the_hour(monkeypatch):
    today = date.today().isoformat()
    car = v(sale_date=today, sale_time="10:00")
    monkeypatch.setattr(service, "sale_time_passed", lambda *a, **k: False)
    before = service.bid_state(car, BT)
    monkeypatch.setattr(service, "sale_time_passed", lambda *a, **k: True)
    after = service.bid_state(car, BT)
    assert after["state"] == "wait" and after["label"] == "기일 경과 — 결과 확인 전"
    assert before["label"] != after["label"], "시각이 지나도 같은 판정이면 고친 게 아니다"


# ── 2. 화물 취득세 ──────────────────────────────────────────────
def test_truck_does_not_get_the_passenger_car_tax_rate():
    """지방세법 제12조: 비영업용 승용 7% · 그 밖의 자동차(화물·특수) 5%. 승용 세율을 트럭에 쓰면
    총 취득원가가 틀리고, 그 아래 상한선·마진·시뮬레이션이 전부 같이 틀어진다."""
    cfg = service.load_config()
    car = service.tax_rate_for(v(model="쏘나타"), cfg)
    truck = service.tax_rate_for(v(model="포터2 초장축"), cfg)
    assert car["rate"] == 0.07 and "승용" in car["label"] and not car["assumed"]
    assert truck["rate"] == 0.05 and "화물" in truck["label"] and truck["assumed"]
    # 영업용 여부는 등록원부 값이라 우리가 모른다 — 가정했음을 화면에 적는다
    assert "영업용" in truck["note"] and "확인" in truck["note"]


def test_truck_tax_flows_into_the_total_and_the_resale_cap():
    """세율은 `tax_rate_for` 한 곳에서 정하고, 총 취득원가·재판매 상한가가 그 값을 쓴다.

    ⚠ 실사용 손익분기(`personal_use_max_bid`)는 세율에 거의 반응하지 않는다 — 취득세가 경매 쪽과
    소매 쪽에 **똑같이** 붙어 식에서 상쇄되기 때문이다(남는 건 부대비 항의 1/(1+t) 뿐). 그러므로
    세율 수정의 효과는 '얼마까지 써도 되나'가 아니라 **'총 얼마 드나'** 에서 확인해야 한다."""
    sedan = v(model="쏘나타")
    truck = v(model="포터2 초장축")
    cfg = service.load_config()
    a_sedan = service.allin_estimate(25_000_000, cfg, sedan)
    a_truck = service.allin_estimate(25_000_000, cfg, truck)
    assert a_sedan["tax"] == 1_750_000 and a_truck["tax"] == 1_250_000
    assert a_truck["total"] < a_sedan["total"], "세율이 총액에 안 먹었다"
    assert service.tax_config_for(truck, cfg)["acquisition_tax_rate"] == 0.05
    assert service.tax_config_for(sedan, cfg) is cfg, "승용은 config 를 복사하지 않는다"


def test_report_and_detail_print_which_tax_basis_was_used():
    r = (TPL / "report.html").read_text(encoding="utf-8")
    assert "report.tax_label" in r and "<b>낙찰가</b> 기준" in r
    assert "report.tax_note" in r and "용도 가정" in r, "가정으로 계산해 놓고 '세율확정' 태그를 달면 안 된다"
    d = (TPL / "detail.html").read_text(encoding="utf-8")
    assert "allin.tax_note" in d


# ── 3. 사진 폴백에서 지도 제외 ──────────────────────────────────
def test_photo_fallback_skips_the_storage_map(tmp_path, monkeypatch):
    """분류가 안 된 물건(기일 남은 440대 중 2대)은 원본 순서라 보관장소 지적도부터 나왔다.
    18인 중 13인이 '차 사진 대신 지도'를 지적했다."""
    import src.paths as paths
    folder = tmp_path / "V1" / "photos"
    folder.mkdir(parents=True)
    for n in ("01_map.gif", "02_front.gif", "03_side.gif"):
        (folder / n).write_bytes(b"x")
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    car = {"id": "V1", "folder_key": "V1", "map_photos": ["01_map.gif"]}
    url = service._pick_photo_url(car)
    assert url and url.endswith("02_front.gif"), f"지도가 대표 사진으로 뽑혔다: {url}"
    # 지도밖에 없으면 그거라도 보여준다(빈 카드보다 낫다)
    only_map = {"id": "V1", "folder_key": "V1", "map_photos": ["01_map.gif", "02_front.gif", "03_side.gif"]}
    assert service._pick_photo_url(only_map), "전부 지도면 빈 카드가 아니라 지도라도 보여준다"
    # 분류가 있으면 그 순서를 그대로 따른다
    ordered = {"id": "V1", "folder_key": "V1", "map_photos": ["01_map.gif"],
               "photo_order": ["03_side.gif", "02_front.gif"]}
    assert service._pick_photo_url(ordered).endswith("03_side.gif")


# ── 4. 카드·헤더의 대표 숫자 ────────────────────────────────────
def test_expected_price_pinned_to_the_court_floor_is_flagged():
    """예상낙찰가가 최저매각가에 걸린 값이면(로컬 실측 220대 중 53대 = 24%) 예측인 척하지 않는다."""
    pinned = v(median_price=20_000_000, min_sale_price=25_000_000)   # 소프트캡이 최저가보다 아래
    assert service.expected_floor_pinned(pinned, BT) is True
    assert service.expected_for(pinned, BT) == pinned["min_sale_price"]
    normal = v()                                                     # 시세 4,000만 · 최저 2,200만
    assert service.expected_floor_pinned(normal, BT) is False
    assert service.bid_state(pinned, BT)["exp_pinned"] is True
    assert service.bid_state(normal, BT)["exp_pinned"] is False


def test_the_biggest_number_on_the_detail_hero_is_the_ceiling():
    """60·70대 3인이 가장 큰 숫자(예상낙찰가)를 '써도 되는 금액'으로 읽었다 — 오독이 곧 과다 입찰이다."""
    d = (TPL / "detail.html").read_text(encoding="utf-8")
    i = d.index('class="nc-heronums')
    hero = d[i:i + 4200]
    big = hero.index("nc-heronum-lg")
    assert "bidst.max_bid|won" in hero[big:big + 400], "히어로의 가장 큰 숫자가 입찰 상한선이 아니다"
    assert "입찰 상한선" in hero[:big] and "여기까지만" in hero
    # 예상낙찰가는 그 다음 크기로 내려간다
    assert "nc-heronum-sm font-mono text-xl" in hero and "expected.price|won" in hero
    # 문구는 실패 고백('예측 불가')이 아니라 범위 선언 — 24% 물건에 붙으므로 앱 전체를 흔들면 안 된다(검수)
    assert "이 차는 최저매각가 아래로 내려가지 않습니다" in hero and "예측 불가" not in hero
    # 색은 크기와 다른 것을 말한다 — 초록은 tone == 'ok' 한 곳에만
    assert "else 'text-emerald-300' if bidst.tone == 'ok' else 'text-white'" in hero
    assert "bidst.floor > bidst.max_bid" in hero, "최저가가 상한선을 넘는 물건을 색으로 구분하지 않는다"
    # 같은 숫자가 한 화면에 두 번 나오지 않게 게이지 아래 상한선 블록은 없앴다
    assert d.count("원까지") == 0 or "bidst.max_bid|won }}<span class=\"text-xs" not in d


def test_list_card_shows_the_ceiling_and_the_pinned_label():
    s = (TPL / "vehicles.html").read_text(encoding="utf-8")
    assert "입찰 상한 <b" in s and "v.bidst.max_bid|won" in s,         "한 카드 안에서 최저매각가·예상낙찰가는 원, 상한선만 만원이면 표기가 또 갈린다"
    assert "최저가 기준 — 더 내려가지 않음" in s and "예측 불가" not in s
    # 목록도 상세와 같은 색 규칙 — 최저가가 상한선을 넘으면 로즈
    assert "v.bidst.floor > v.bidst.max_bid" in s


# ── 5. 산식 검산 · 표기 일원화 ──────────────────────────────────
def test_formula_rows_print_the_rate_and_the_basis():
    """4인이 '2·3단계 값이 같다'며 결론을 못 믿었는데 계산은 맞았다 — 요율이 우연히 같았다.
    금액만 나열하면 검산이 닫히지 않으므로 무엇에 몇 %를 곱했는지 옆에 적는다."""
    r = (TPL / "report.html").read_text(encoding="utf-8")
    i = r.index("− 수리비 − 사고감가 − 리스크프리미엄")
    two = r[i:i + 700]
    assert "bd['사고감가율']" in two and "report.risk_rate" in two, "2단계에 요율이 없다"
    j = r.index("− 취득세 − 고정부대비 − 목표마진")
    three = r[j:j + 700]
    assert "report.tax_rate" in three and "report.margin_rate" in three, "3단계에 요율이 없다"
    assert "이전 " in three and "탁송 " in three, "고정부대비의 내역이 없다"


def test_accuracy_has_one_headline_metric():
    """±10% 적중 62% / ±9% 예측 오차 / 실측 평균오차 ±9% 셋이 같은 톤으로 나열돼 어느 쪽이
    이 추정의 불확실성인지 고를 수 없었다(42·63세). 주지표는 평균오차 하나."""
    r = (TPL / "report.html").read_text(encoding="utf-8")
    assert "실측 ±10% 적중" not in r, "예상낙찰가 옆 주지표가 아직 적중률이다"
    # 2026-09-23 PANEL-01 — 주지표 이름이 '실측 평균오차'에서 상세와 같은
    # '이 유형(라벨, N건) 실측 오차'로 바뀌었다. 전체평균을 물건에 붙이던 것을
    # 유형별로 고치면서, 상세(detail.html:408)가 이미 쓰던 형식을 그대로 따랐다.
    assert r.count("실측 오차 ±") >= 2, "예상낙찰가 옆 주지표가 실측 오차가 아니다"


def test_confidence_cutoffs_are_published():
    """76도 '높음' 81도 '높음'인데 몇 점부터 높음인지 화면에 없었다. 출처가 아니라 경계라 공개해도 된다."""
    assert service.CONF_SCALE_TEXT == "70점 이상 높음 · 45~69점 보통 · 44점 이하 낮음"
    assert service.CONF_CUTOFFS[0] == (70, "높음")
    for name in ("detail.html", "report.html"):
        assert "conf_scale" in (TPL / name).read_text(encoding="utf-8"), name


def test_home_discount_badge_carries_its_basis():
    """'시세보다 −37%'의 분모가 화면에 없어 '이유가 없으면 안 싼 걸로 친다'(55세)."""
    d = (TPL / "dashboard.html").read_text(encoding="utf-8")
    assert "v.disc_base|man" in d and "대비" in d


# ── 6. 리포트 실사용 / 되팔기 모드 ──────────────────────────────
def test_report_hides_resale_sections_by_default():
    """되팔 생각이 없는 5인이 마진 계산에 파묻혀 자기 결론을 못 찾았다. 기본은 실사용."""
    r = (TPL / "report.html").read_text(encoding="utf-8")
    assert r.count("<section class=\"section\" data-resale>") == 3, "07·08·11 표시가 빠졌다"
    assert 'html:not(.rmode-resale) [data-resale]{display:none}' in r
    assert 'id="rptResale"' in r and "rptToggleResale" in r
    assert "naechaget:rmode" in r
    # 감춘 사실을 숨기지 않는다
    assert "되팔기 계산(07 수익 시뮬레이션 · 08 민감도 · 11 반복 매매)은 접었습니다" in r


# ── 7. 큰글씨 모드 ──────────────────────────────────────────────
def test_large_mode_unfolds_chip_rows_and_scales_the_hexagon():
    """도움이 가장 필요한 사용자가 가장 많이 잘리는 역전을 없앤다."""
    css = (ROOT / "web" / "static" / "app.css").read_text(encoding="utf-8")
    assert "html.nc-large .nc-chiprow" in css and "flex-wrap:wrap!important" in css.replace(" ", "")
    s = (TPL / "vehicles.html").read_text(encoding="utf-8")
    assert s.count("nc-chiprow") == 2, "필터 칩 줄 두 곳에 다 걸려야 한다"
    r = (TPL / "report.html").read_text(encoding="utf-8")
    # ⚠ 좁은 화면(≤640px)에는 걸지 않는다 — 2열을 되살리면 320px 에서 도형이 84px 로 찌그러진다(실측)
    assert "@media screen and (min-width:641px){ html.nc-large .hexa{grid-template-columns:minmax(0,320px) 1fr}" in r


def test_report_has_a_table_of_contents_for_all_twelve_sections():
    r = (TPL / "report.html").read_text(encoding="utf-8")
    assert 'class="rtoc no-print"' in r and "전체 목차 12개" in r
    # ⚠ .no-print{display:flex} 가 상속돼 목차가 오른쪽으로 밀렸다 — .rtop 과 같은 처방(CLAUDE.md 사고 재발)
    assert ".rtoc{display:block;" in r
    # '12개'라 써 놓고 9개만 보이면 또 다른 불일치 — 되팔기 3개는 지우지 않고 흐리게 남기고 누르면 켠다
    assert r.count('class="rtoc-resale"') == 3 and "rptShowResale()" in r
    assert "html.rmode-resale .rtoc-resale{opacity:1}" in r
    # 토글임을 '큰글씨' 버튼과 같은 체크 표시로 알린다
    assert '#rptResale[aria-pressed="true"]::before' in r
    for no in range(1, 13):
        assert f'href="#sec{no:02d}"' in r, f"목차에 sec{no:02d} 가 없다"
        assert f'id="sec{no:02d}"' in r, f"본문에 sec{no:02d} 앵커가 없다"
