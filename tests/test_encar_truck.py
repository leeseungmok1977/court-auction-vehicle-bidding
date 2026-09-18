"""엔카 화물 조회 — 포터·봉고가 '동급 표본 없음'이던 진짜 원인과 그 경계.

2026-09-19에 알아낸 것: 엔카는 **승용과 화물이 다른 API**다.
나는 승용 엔드포인트만 두드려 놓고 "이 경로에 포터·봉고 매물이 없다 → 고칠 수 없다"고
결론냈다. 대조군(현대/쏘나타 5,071건)까지 세웠는데도 틀렸다 — 대조군이 정상이어도
**"다른 카테고리가 있을 수 있다"** 를 확인하지 않으면 "없다"가 아니라 "내가 안 찾았다"가 된다.

브라우저로 직접 확인한 값(capture/E4_truck_general.txt):
  · 엔드포인트  /search/truck/list/general   (승용은 /search/car/…)
  · CarType 축이 **없다** — 엔드포인트가 차종을 가른다
  · 모델 축 이름이 ModelGroup 이 아니라 **Model**
  · 표기는 규칙이 아니라 개별값: '포터 Ⅱ'(공백 있음) · '봉고Ⅲ'(공백 없음)
  · 괄호는 닫기 전에 `_`: 기아(아시아_) · 카고(화물_)트럭
  · 형식(Form)으로 카고/탑을 가를 수 있다 — 포터 Ⅱ 5,141 = 카고 3,240 + 윙바디/탑 1,729

이 파일이 지키는 경계는 둘이다.
  ① 포터·봉고는 화물 경로로 **정확한 표기**로 나간다.
  ② 형식을 모르면 **매핑하지 않는다** — 카고와 탑이 섞인 시세를 내느니 시세 없음이 낫다.
"""
import pytest

from src.collect import encar


# ── 표기·엔드포인트 ────────────────────────────────────────────────
@pytest.mark.parametrize("maker,model,man,mg", [
    ("현대자동차", "포터Ⅱ 냉동탑차 (PORTERⅡ)", "현대", "포터 Ⅱ"),
    ("현대", "포터II냉통탑차 (PORTER II)", "현대", "포터 Ⅱ"),        # 법원 오타 '냉통'
    ("현대자동차(주)", "포터Ⅱ내장탑차(PORTER Ⅱ)", "현대", "포터 Ⅱ"),
    ("현대", "포터11하이냉동탑차 (P0RTER 11)", "현대", "포터 Ⅱ"),     # 숫자 11 · 'P0RTER' 오타
    ("(주)기아", "봉고III 플러스냉동차", "기아(아시아)", "봉고Ⅲ"),
    ("기아자동차", "봉고Ⅲ 1톤 냉동탑차", "기아(아시아)", "봉고Ⅲ"),
])
def test_포터봉고는_화물_표기로_매핑된다(maker, model, man, mg):
    r = encar.truck_map(maker, model)
    assert r is not None, f"매핑 실패: {maker} | {model}"
    assert r["truck"] is True
    assert r["manufacturer"] == man
    assert r["model_group"] == mg, "표기가 한 글자만 달라도 0건이 난다"


def test_화물_질의는_CarType_없이_Model_축을_쓴다():
    q = encar.build_q("현대", "포터 Ⅱ", truck=True, form="카고(화물)트럭")
    assert "CarType" not in q, "화물에는 CarType 축이 없다 — 넣으면 0건"
    assert "Model.포터 Ⅱ." in q, "모델 축 이름은 ModelGroup 이 아니라 Model"
    assert "Form.카고(화물_)트럭." in q, "괄호는 닫기 전에 _ 를 넣어야 한다"
    assert q.startswith("(And.Hidden.N._.")


def test_승용_질의는_예전_그대로다():
    """화물을 추가하면서 승용 경로를 건드리면 멀쩡하던 시세가 다 깨진다."""
    q = encar.build_q("현대", "쏘나타")
    assert q == "(And.Hidden.N._.(C.CarType.Y._.(C.Manufacturer.현대._.ModelGroup.쏘나타.)))"


def test_연식범위는_양쪽_모두에_붙는다():
    for kw in ({}, {"truck": True, "form": "카고(화물)트럭"}):
        q = encar.build_q("현대", "포터 Ⅱ", year_from=202301, year_to=202512, **kw)
        assert "Year.range(202301..202512)." in q


def test_괄호_이스케이프():
    assert encar.q_escape("기아(아시아)") == "기아(아시아_)"
    assert encar.q_escape("카고(화물)트럭") == "카고(화물_)트럭"
    assert encar.q_escape("쏘나타") == "쏘나타"


# ── 형식 판별 ────────────────────────────────────────────────
@pytest.mark.parametrize("model,form", [
    ("포터Ⅱ 냉동탑차 (PORTERⅡ)", "윙바디/탑"),
    ("포터Ⅱ내장탑차(PORTER Ⅱ)", "윙바디/탑"),
    ("포터Ⅱ하이냉동탑차 (PORTER Ⅱ)", "윙바디/탑"),
    ("봉고III 플러스냉동차", "윙바디/탑"),
    ("포터Ⅱ 카고 1톤", "카고(화물)트럭"),
])
def test_모델명에_적힌_형식을_읽는다(model, form):
    assert encar.truck_form(model) == form


@pytest.mark.parametrize("model", [
    "포터Ⅱ (PORTERⅡ)", "포터II (PORTER II)", "포터Ⅱ(PORTER Ⅱ)",
    "봉고Ⅲ 1톤", "봉고3 1톤", "봉고 III 1톤 EV", "포터Ⅱ 일렉트릭 (PORTERⅡ ELECTRIC)",
])
def test_형식을_모르면_매핑하지_않는다(model):
    """'1톤'은 적재량이지 형식이 아니다 — 냉동탑차도 1톤이다.

    이걸 카고로 단정했다가는 탑차를 카고 시세로 평가한다(초안에서 실제로 저지른 실수).
    형식이 안 적혀 있으면 조회하지 않고 시세 없음으로 남긴다.
    """
    assert encar.truck_form(model) is None
    assert encar.truck_map("현대", model) is None


# ── 경계: 중장비·특장은 계속 막는다 ────────────────────────────────
@pytest.mark.parametrize("maker,model", [
    ("에이치디건설기계(주)", "굴착기"),
    ("두산밥캣코리아(주)", "지게차"),
    ("만트럭버스코리아(주)", "덤프트럭"),
    ("(주)삼부", "삼부5.5톤냉장윙바디트럭"),     # '윙바디'가 들어 있어도 포터·봉고가 아니다
    ("MAN", "정우32KL탱크로리"),
    ("현대자동차", "쏘나타"),                    # 승용은 화물 매핑 대상이 아니다
    ("", ""),
])
def test_중장비와_승용은_화물_매핑에_들어오지_않는다(maker, model):
    assert encar.truck_map(maker, model) is None
