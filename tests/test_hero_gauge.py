"""상세 히어로 가격 게이지·금액 줄바꿈, 목록 카드 사진 하단 줄 (2026-09-14 디자인 검수 후속 3건).

1. **축이 0원부터였다.** 최저매각가 3,010만이 막대의 73% 지점에 그려지는데 라벨 '최저 3010만'은 막대
   왼쪽 끝에 있어, 81% 의 예상 마커를 사용자는 3,360만이 아니라 훨씬 큰 값으로 읽었다. 세 값의 대소
   순서는 물건마다 다르다(로컬 220대 중 최저>시세 76 · 예상>시세 105) — '최저=왼쪽, 시세=오른쪽'은
   그 자체가 거짓일 수 있다. 축을 세 값의 최소~최대로 잡고 이름은 값 오름차순 범례로 옮겼다.
2. 큰글씨·OS 확대 320px 에서 히어로 금액의 단위 '원'이 다음 줄로 떨어졌다(37.5px × 10자 > 안폭 230px).
3. 목록 카드 사진 하단에서 왼쪽 정보가 길면 카메라 아이콘이 카드 밖으로 밀려 잘렸다.
"""
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from web import service

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "web" / "templates"
_PUBLIC = {"x-forwarded-for": "203.0.113.7"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db
    from tests.test_dashboard_link_parity import BT as BT2
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT2)
    db.init_db()
    base = {"court": "수원지방법원", "maker": "현대", "model": "쏘나타", "item_no": "1", "year": 2020,
            "sale_date": "2999-01-01", "status": "완료", "fail_count": 1, "market_confidence_label": "높음",
            "judgment": "유찰 대기", "photo_count": 12, "mileage_km": 243365}
    # 세 가지 대소 순서를 모두 만든다 — 어느 값이 축의 끝에 오든 라벨이 따라가야 한다.
    db.upsert_vehicle(dict(base, id="ORD_1", case_no="2026타경31", min_sale_price=16_000_000,
                           median_price=40_000_000, appraisal_value=30_000_000))          # 최저 < 예상 < 시세
    db.upsert_vehicle(dict(base, id="ORD_2", case_no="2026타경32", min_sale_price=39_000_000,
                           median_price=20_000_000, appraisal_value=40_000_000))          # 시세 < 최저 (예상은 그 사이·위)
    return TestClient(A_app())


def A_app():
    import web.app as A
    return A.app


def _gauge(html: str) -> dict:
    """게이지 막대의 표식 위치(%)와 범례(이름→만원)를 뽑는다."""
    i = html.index('h-2 rounded-full bg-white/10')   # 히어로 위쪽 알약도 bg-white/10 이다 — 트랙만 잡는다
    block = html[i:i + 3000]
    # 표식(틱·마커)만 — 구간 띠의 left 는 두 값 중 작은 쪽이라 위치 검사에 쓸 수 없다
    marks = [float(x) for x in re.findall(r"-top-1[^>]*?left:([\d.]+)%", block)]
    leg = re.findall(r"(최저|예상|시세) <b[^>]*>(?:([\d,]+)억)? ?(?:([\d,]+)만)?</b>", block)
    def _won(eok, man):      # '1억 420만' → 104_200_000
        return (int((eok or "0").replace(",", "")) * 100_000_000
                + int((man or "0").replace(",", "")) * 10_000)
    return {"marks": marks, "legend": [(n, _won(e, m)) for n, e, m in leg]}


def test_axis_starts_at_the_smallest_value_not_zero(client):
    """예전 축(0원~최대)에서 최저매각가는 40% 지점에 그려졌다 — 이제 왼쪽 끝(0%)이다."""
    g = _gauge(client.get("/vehicle/ORD_1", headers=_PUBLIC).text)
    assert len(g["marks"]) == 3, f"표식이 셋이 아니다: {g['marks']}"
    # 끝점 표식은 반쯤 잘리지 않게 2~98% 로 좁혀 그린다
    assert min(g["marks"]) <= 2.0, f"가장 작은 값이 왼쪽 끝에 없다: {g['marks']}"
    assert max(g["marks"]) >= 98.0, f"가장 큰 값이 오른쪽 끝에 없다: {g['marks']}"


def test_legend_lists_all_three_values_in_ascending_order(client):
    """이름을 양 끝에 고정하지 않는다 — 값 오름차순 범례라 막대 순서와 같다."""
    for vid in ("ORD_1", "ORD_2"):
        g = _gauge(client.get(f"/vehicle/{vid}", headers=_PUBLIC).text)
        names = [n for n, _ in g["legend"]]
        vals = [v for _, v in g["legend"]]
        assert set(names) == {"최저", "예상", "시세"}, f"{vid}: 범례 {g['legend']}"
        assert vals == sorted(vals), f"{vid}: 오름차순이 아님 {g['legend']}"


def test_marker_position_matches_the_value_it_stands_for(client):
    """마커 위치와 값이 같은 비율이어야 한다 — 이 검사가 0원 기준 축에서는 실패했다."""
    html = client.get("/vehicle/ORD_1", headers=_PUBLIC).text
    g = _gauge(html)
    vals = sorted(v for _, v in g["legend"])
    lo, mid, hi = vals
    want = round((mid - lo) / (hi - lo) * 100, 1)
    got = sorted(g["marks"])[1]
    assert abs(got - want) <= 1.0, f"가운데 값 {mid:,}원은 {want}% 인데 {got}% 에 그려졌다"


def test_no_gauge_when_all_three_values_are_equal(client, monkeypatch):
    """축 폭이 0이면 나눗셈이 터진다 — 그리지 않는다(0으로 나누기·표식 100% 방지). 페이지는 살아 있어야 한다."""
    real = service.expected_band
    monkeypatch.setattr(service, "expected_band",
                        lambda v, bt=None, *a, **k: dict(real(v, bt) or {}, price=v.get("min_sale_price")))
    from web import db
    db.upsert_vehicle({"id": "EQ_1", "case_no": "2026타경33", "item_no": "1", "court": "수원지방법원",
                       "maker": "현대", "model": "쏘나타", "year": 2020, "sale_date": "2999-01-01",
                       "status": "완료", "fail_count": 1, "market_confidence_label": "높음",
                       "judgment": "유찰 대기", "min_sale_price": 20_000_000, "median_price": 20_000_000,
                       "appraisal_value": 25_000_000})
    r = client.get("/vehicle/EQ_1", headers=_PUBLIC)
    assert r.status_code == 200
    assert "h-2 rounded-full bg-white/10" not in r.text, "값이 모두 같은데 게이지를 그렸다"


def test_marks_are_coded_by_shape_not_colour_alone(client):
    """판정색 구간(로즈·앰버) 위에 얹힌 시세 틱이 색만으로는 사라졌다 — 최저=꽉 참 · 시세=속 빔 · 예상=앰버 마커.
    막대 표식과 범례 점이 같은 규칙이어야 눈이 잇는다. 구간 색은 60%로 낮춰 마커가 '구간 끝 캡'으로 안 보이게."""
    html = client.get("/vehicle/ORD_1", headers=_PUBLIC).text
    i = html.index('h-2 rounded-full bg-white/10')
    block = html[i:i + 3000]
    assert "shadow-[inset_0_0_0_1.5px_rgba(255,255,255,.85)]" in block, "시세 틱이 속 빈 모양이 아니다"
    assert "shadow-[0_0_0_2px_rgba(11,23,48,.9)]" in block, "예상 마커에 배경색 갭이 없다"
    assert "bg-amber-400/60" in block or "bg-emerald-400/60" in block or "bg-rose-400/60" in block
    assert "ring-1 ring-white/80" in block, "범례의 시세 점이 속 빈 모양이 아니다"
    css = (ROOT / "web" / "static" / "app.css").read_text(encoding="utf-8")
    assert "0b1730" in css and "inset_0_0_0_1" in css, "새 임의값 클래스가 빌드에 없다(npm run build:css)"


def test_hundred_million_is_written_in_eok_not_ten_thousand():
    """범례가 '10420만'이면 바로 위 히어로의 '104,200,000 원'과 체계가 어긋나고, 옆 '9850만'과 자릿수가
    하나 달라 1,042만으로 오독된다(검수)."""
    from web.app import _man
    assert _man(104_200_000) == "1억 420만" and _man(100_000_000) == "1억"
    assert _man(98_500_000) == "9,850만" and _man(4_410_000) == "441만"
    assert _man(None) == "—" and _man(0) == "0만"


def test_hero_amounts_keep_the_unit_on_the_same_line():
    """단위 '원'이 숫자와 떨어지면 금액을 두 번 읽어야 한다. nowrap + rem 대비 칸 폭 단계."""
    src = (TPL / "detail.html").read_text(encoding="utf-8")
    assert 'class="nc-heronums relative flex flex-wrap items-end' in src
    assert "nc-heronum-lg font-mono text-3xl" in src and "nc-heronum-sm font-mono text-xl" in src
    css = (ROOT / "web" / "static" / "app.css").read_text(encoding="utf-8")   # 빌드 산출물(압축됨)
    assert ".nc-heronums{container-type:inline-size}" in css
    assert "white-space:nowrap" in css.split(".nc-heronums")[1][:200]
    assert "@container (max-width: 14rem)" in css and "@container (max-width: 11rem)" in css
    # 1차를 낮출 때 2차도 함께 — 안 그러면 큰글씨에서 두 금액이 같은 크기로 보여 위계가 사라진다(검수)
    step = css.split("@container (max-width: 14rem)")[1][:200]
    assert ".nc-heronum-lg" in step and ".nc-heronum-sm" in step


def test_card_photo_footer_never_pushes_the_camera_out():
    """왼쪽 정보(연식·주행·외관손상·사진 혼재)가 길면 카메라 아이콘이 카드 밖으로 밀렸다."""
    src = (TPL / "vehicles.html").read_text(encoding="utf-8")
    i = src.index("bg-gradient-to-t from-black/70")
    row = src[i:i + 400]
    assert "justify-between gap-2" in row, "오른쪽 아이콘과의 최소 간격이 없다"
    assert "flex flex-wrap items-center gap-1.5 min-w-0" in row, "왼쪽 묶음이 줄어들지 않는다"
    assert "shrink-0" in src[i:i + 1200], "카메라 아이콘이 줄어들 수 있다"
