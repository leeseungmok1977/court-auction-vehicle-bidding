"""손익분기 표의 뺄셈이 화면에서 닫히는지.

5회차 지적. 실측 결과 표가 그려지는 727건 중 **250건(34.4%)** 에서
`기준시세 − 항목들 != 손익분기 상한` 이었다. 최대 245만원 차이.

원인은 `상태정비추가`(자동차검사 유효기간 경과·시동 불가 등으로 붙는 추가
정비비)가 upper_bid 계산에는 들어가는데 표의 항목 목록에는 없던 것이다.
사용자에겐 두 가지로 보였다 — ① 계산이 틀렸다 ② 그리고 정비가 더 드는
이유(검사 경과·시동 불가)를 아예 못 봤다. 후자가 더 나쁘다.
"""
import json
import re

import pytest
from starlette.testclient import TestClient

from web import service

BT = {"discount_median": 0.74, "mae_pct": 9.2, "sample": 172, "within10_pct": 62,
      "within20_pct": 96, "pred_n": 135, "won_total": 172,
      "min_premium_median": 1.13, "min_premium_by_fail": {"0": 1.20, "1": 1.13, "2+": 1.06},
      "min_premium_p25": 1.05, "min_premium_p75": 1.22,
      "min_premium_pool": [round(1.00 + i * 0.004, 4) for i in range(60)],
      "discount_p25": 0.62, "discount_p75": 0.86, "discount_by_fail": {},
      "discount_by_model": {}, "upper_hit_rate": None, "upper_n": 0,
      "actual_mae_pct": None, "actual_sample": 0, "mae_baseline_pct": 12.0,
      "history_n": 0, "model_learned": False, "pred_pool": [], "comp_pool": []}

# 템플릿이 렌더하는 항목과 breakdown 키의 대응. 새 차감 항목을 계산에만 넣고
# 이 목록에 안 넣으면 아래 테스트가 실패한다 — 그게 이 파일의 존재 이유다.
STEP_KEYS = ["예상수리비", "상태정비추가", "사고감가", "리스크프리미엄",
             "취득세", "고정부대비", "마진"]


@pytest.fixture
def client_with_condition_costs(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "bd.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    bd = {"기준시세": 34_700_000, "플랫폼": "encar", "플랫폼가중": 1.0,
          "예상수리비": 500_000, "사고등급": "accident", "사고감가율": 0.15,
          "사고감가": 5_205_000, "리스크프리미엄": 2_429_000, "취득세": 2_429_000,
          "고정부대비": 500_000, "마진": 5_205_000,
          "상태정비추가": 1_750_000,
          "상태사유": ["자동차검사 유효기간 경과", "시동·운행 불가 언급"],
          "표본수": 21, "현재최저매각가": 32_000_000}
    upper = bd["기준시세"] - sum(bd[k] for k in STEP_KEYS)
    db.upsert_vehicle({
        "id": "BD_1", "folder_key": "BD_1", "case_no": "2026타경9001", "item_no": "1",
        "court": "수원지방법원", "maker": "현대", "model": "그랜저", "year": 2019,
        "min_sale_price": 32_000_000, "appraisal_value": 40_000_000, "fail_count": 1,
        "sale_date": "2999-01-01", "status": "완료", "judgment": "유찰 대기",
        "median_price": 34_700_000, "market_confidence": 78,
        "market_confidence_label": "높음", "sample_count": 21, "photo_count": 3,
        "breakdown": json.dumps(bd, ensure_ascii=False), "upper_bid": upper,
    })
    import web.app as A
    return TestClient(A.app), bd, upper


def _money_rows(html: str, start: str, end: str):
    """구간 안의 금액들을 등장 순서대로 정수로 뽑는다."""
    seg = html.split(start)[1].split(end)[0]
    return [int(m.replace(",", "")) for m in re.findall(r"\d{1,3}(?:,\d{3})+", seg)]


def test_detail_breakdown_arithmetic_closes(client_with_condition_costs):
    """상세 표에 찍힌 금액들만으로 뺄셈이 닫혀야 한다."""
    client, bd, upper = client_with_condition_costs
    html = client.get("/vehicle/BD_1").text
    assert "재판매 손익분기 산정" in html, "표가 안 그려지면 이 테스트는 공허하다"

    nums = _money_rows(html, "재판매 손익분기 산정", "= 손익분기 상한")
    base = bd["기준시세"]
    assert nums and nums[0] == base, f"첫 값이 기준시세여야 한다: {nums[:3]}"
    # 기준시세 뒤에 오는 차감 금액들의 합 == 기준시세 − 상한
    deducted = sum(n for n in nums[1:] if n != base)
    assert deducted == base - upper, (
        f"화면 항목합 {deducted:,} != 기준시세−상한 {base - upper:,} "
        f"— 표에 없는 차감 항목이 있다")


def test_detail_shows_why_extra_repair_was_added(client_with_condition_costs):
    """추가 정비비를 빼면서 그 사유를 안 보여주면 위험 고지가 사라진다."""
    client, bd, _ = client_with_condition_costs
    html = client.get("/vehicle/BD_1").text
    assert "상태 정비 추가" in html
    for reason in bd["상태사유"]:
        assert reason in html, f"사유 '{reason}'이 화면에 없다"


def test_report_breakdown_arithmetic_closes(client_with_condition_costs):
    """리포트 §재판매 상한가의 1·2·2′·3 단계 합도 ＝와 맞아야 한다."""
    client, bd, upper = client_with_condition_costs
    html = client.get("/vehicle/BD_1/report").text
    assert "재판매 상한가" in html
    seg = html.split("재판매 상한가 (마진 기준)")[1].split("모든 상수")[0]
    steps_sum = sum(bd[k] for k in STEP_KEYS)
    assert f"{steps_sum:,}" or True  # 각 줄이 아니라 합으로 검산한다
    shown = sum(int(m.replace(",", ""))
                for m in re.findall(r"−([\d,]+)</span>", seg))
    assert shown == bd["기준시세"] - upper, (
        f"리포트 차감합 {shown:,} != {bd['기준시세'] - upper:,}")


def test_every_breakdown_deduction_key_is_rendered():
    """계산에 쓰는 차감 키가 템플릿 목록에서 빠지지 않았는지 직접 대조.

    새 차감 항목을 calculator 에만 추가하고 화면에 안 넣는 것이 이번 결함의
    원인이었다. 템플릿 파일을 읽어 키가 실제로 등장하는지 본다.
    """
    import pathlib
    tpl = pathlib.Path("web/templates/detail.html").read_text(encoding="utf-8")
    block = tpl.split("{% set steps = [")[1].split("] %}")[0]
    for key in STEP_KEYS:
        assert key in block, f"detail.html 의 steps 목록에 '{key}' 가 없다"


# ── 목록 첫 화면에 물건이 보이는가 (5회차 지적) ──────────────────
def test_list_legend_is_collapsed_by_default():
    """판정 범례는 기본 접힘이어야 한다.

    실측: 범례가 펼쳐진 상태에서 첫 물건 카드가 top=563px 이었고 폴드가 743px
    이라 360px 폰에서 51%, 320px 폰에서는 0%만 보였다. 물건 목록의 첫 화면에
    물건이 없는 것보다 나쁜 것은 없다.

    `<details>` 에 `open` 이 붙으면 실패한다 — 재방문자의 선택은 localStorage
    로 복원하고, 서버가 내보내는 기본값은 접힘이다.
    """
    import pathlib
    import re
    src = pathlib.Path("web/templates/vehicles.html").read_text(encoding="utf-8")
    m = re.search(r'<details id="listLegend"([^>]*)>', src)
    assert m, "판정 범례가 <details id=\"listLegend\"> 로 감싸여 있지 않다"
    assert " open" not in m.group(1), "범례가 기본 펼침이면 첫 카드가 폴드 밖으로 밀린다"
    # 접힘 상태를 기억하지 않으면 매번 다시 접혀 오히려 성가시다
    assert "ncListLegend" in src, "접힘 상태를 기기에 기억하지 않는다"
