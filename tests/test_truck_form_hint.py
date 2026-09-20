# -*- coding: utf-8 -*-
"""사진으로 읽은 적재함 형식(truck_form)이 시세 조회로 이어지는지 고정.

배경(2026-09-20 실측). 포터·봉고는 엔카 화물 쪽에 카고와 윙바디/탑이 따로 있어
**형식을 모르면 조회하지 않는다**(섞인 시세는 틀린 시세다). 그런데 법원 차명에 형식이
적힌 물건은 23건 중 7건뿐이었다 — 나머지 16건은 영원히 '동급 시세 없음'이었다.
사진에는 적재함이 그대로 찍혀 있으므로 비전 검수가 읽어 `vehicles.truck_form` 에 남기고,
매핑이 그 값을 받아 쓴다.

여기서 고정하는 것은 세 가지다.
  ① 힌트가 있으면 조회가 **열린다**       (없던 시세가 생긴다)
  ② 차명에 적힌 형식이 힌트보다 **앞선다** (법원 문서 > 사진 판독)
  ③ 허용 목록에 없는 값은 **무시한다**     (모르는 채로 두는 편이 틀린 시세보다 낫다)
"""
import pytest

from src.collect import encar


def test_힌트가_없으면_여전히_조회하지_않는다():
    """형식을 모르는 채 모델만으로 조회하면 카고와 탑차가 섞인다 — 기존 판단 유지."""
    assert encar.truck_map("현대", "포터Ⅱ") is None
    assert encar.auto_map("현대", "포터Ⅱ") is None


@pytest.mark.parametrize("model", ["포터Ⅱ", "포터 2", "봉고Ⅲ", "BONGO III"])
@pytest.mark.parametrize("form", ["카고(화물)트럭", "윙바디/탑"])
def test_사진이_읽은_형식으로_조회가_열린다(model, form):
    r = encar.truck_map("현대", model, form_hint=form)
    assert r and r["truck"] is True
    assert r["form"] == form, "사진이 읽은 형식이 그대로 조회에 쓰여야 한다"
    assert encar.auto_map("현대", model, form_hint=form)["form"] == form


def test_차명에_적힌_형식이_사진보다_앞선다():
    """법원 감정 문서에 '냉동탑차'라고 적혀 있으면 사진 판독이 그걸 뒤집지 못한다."""
    r = encar.truck_map("현대", "포터Ⅱ 냉동탑차", form_hint="카고(화물)트럭")
    assert r["form"] == "윙바디/탑"


@pytest.mark.parametrize("bad", ["", "카고", "탑차", "1톤", "모름", None, "윙바디/탑 "])
def test_허용되지_않는_형식_값은_무시한다(bad):
    """비전이 엉뚱한 문자열을 돌려줘도 그것으로 시세를 내지 않는다.

    `'카고'`·`'탑차'` 처럼 **그럴듯한데 엔카 표기가 아닌** 값이 특히 위험하다 —
    그대로 쿼리에 실리면 0건이 나오고, 0건은 '시세 없음'과 구별되지 않는다."""
    assert encar.truck_map("현대", "포터Ⅱ", form_hint=bad) is None


def test_포터봉고가_아니면_힌트가_있어도_화물로_보내지_않는다():
    """굴착기에 형식 값이 잘못 들어가도 화물 엔드포인트로 새지 않아야 한다."""
    assert encar.truck_map("현대", "굴착기", form_hint="카고(화물)트럭") is None
    assert encar.truck_map("현대", "쏘나타", form_hint="윙바디/탑") is None


def test_허용_형식_목록은_실제_조회에_쓰는_표기와_같다():
    """`TRUCK_FORMS` 가 따로 놀면 검증은 통과하는데 조회는 0건이 된다."""
    assert set(encar.TRUCK_FORMS) == {f for f, _ in encar.TRUCK_FORM_WORDS}
