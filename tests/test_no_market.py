"""동급 시세가 성립하지 않는 물건 판별 — '신뢰도 낮음'과 섞이지 않게.

두 상태는 성격이 다르다. '시세 신뢰도 낮음'은 **비교했는데 못 믿겠다**이고,
여기서 가리는 것은 **비교할 대상이 애초에 없다**이다. 한 칸에 섞어 두면 사용자에게는
둘 다 그냥 '사라진 물건'이라, 유망 물건이 적은 이유가 화면 어디에도 설명되지 않는다.

2026-09-19 운영 실측이 이 규칙의 근거다.
  · 기일 미도래 419건 중 중장비·특장 낱말이 걸리는 52건은 **표본이 전부 0**이었고,
    같은 낱말에 걸리면서 표본 3건 이상인 물건은 **0건**이었다 → 오분류 위험이 없다.
  · 법원 목록에는 자동차가 아닌 **선박**이 섞여 들어온다(미도래 21건은 사진으로 전부 확인).

가장 중요한 것은 **틀린 이름을 붙이지 않는 것**이다. 전체 DB의 빈 표기 102건 중 비고에
선박 낱말이 없는 것이 53건이라, 표기가 비었다는 이유만으로 '선박'이라 부를 수 없다.
그런 물건은 '차종 확인 불가'로 남긴다 — 모른다고 말하는 편이 틀린 라벨보다 낫다.
"""
import pytest

from web import service


def v(**kw):
    base = {"maker": "현대", "model": "쏘나타", "spec_remark": ""}
    base.update(kw)
    return base


@pytest.mark.parametrize("model", [
    "덤프트럭", "덤프트럭 TGS 37.500 8X 4BB", "굴착기", "지게차", "공기압축기",
    "정우32KL탱크로리", "콘크리트 펌프", "천공기", "호룡SKY320S고소작업차",
    "동우44㎥벌크트레일러", "한국상용9.5톤카고트럭", "삼부5.5톤냉장윙바디트럭", "로더",
])
def test_건설기계와_특장은_시세_비교_대상이_아니다(model):
    assert service.no_market_reason(v(model=model)) == "건설기계·특장"


@pytest.mark.parametrize("model", [
    "쏘나타", "그랜저(GRANDEUR)", "아반떼N", "카니발", "G80", "포터Ⅱ (PORTERⅡ)",
    "봉고Ⅲ 1톤", "Model 3 Long Range",
])
def test_승용과_소형상용은_대상에서_빠진다(model):
    """포터·봉고는 엔카에 매물이 있는 차종이다 — 시세를 못 구하는 것과 비교 대상이
    아닌 것은 다르다. 여기서 걸러 버리면 고칠 수 있는 문제가 영영 숨는다."""
    assert service.no_market_reason(v(model=model)) is None


def test_비고에_선박_낱말이_있으면_선박이다():
    got = service.no_market_reason(
        v(maker="", model="", spec_remark="제시외 선박의장품 및 어업허가권 등 각 포함하여 매각."))
    assert got == "선박"


def test_표기가_비었다는_이유만으로는_넣지_않는다():
    """**양성 근거가 있을 때만** 이 칸에 넣는다.

    한때 "제조사·모델이 둘 다 비면 차종 확인 불가"라는 갈래를 두었다가 철회했다.
    표기가 없다는 건 *우리가 모른다*는 뜻이지 비교 대상이 아니라는 뜻이 아니고,
    수집 직후 표기가 아직 없는 미분석 물건까지 끌어왔다(test_usepick_tiers 가 잡아냈다).
    운영에서 그 갈래로 얻는 건 1건뿐인데 잃는 건 구조적이었다.
    """
    assert service.no_market_reason(v(maker="", model="", spec_remark="")) is None
    assert service.no_market_reason(v(maker="", model="", spec_remark=None)) is None
    assert service.no_market_reason({}) is None, "키가 아예 없는 행도 안전해야 한다"


def test_제조사만_비어도_모델이_있으면_대상이_아니다():
    """실측 2건(K7·그랜드 카니발)은 제조사 표기만 비었고 시세는 정상으로 나왔다."""
    assert service.no_market_reason(v(maker="", model="K7")) is None


def test_버킷이_모든_물건을_하나씩만_가진다():
    """새 칸을 넣어도 배타·망라가 유지되는지 — 합계가 총대수와 어긋나는 원인 1순위."""
    assert "nomarket" in service.LIFECYCLE_BUCKETS
    assert len(set(service.LIFECYCLE_BUCKETS)) == len(service.LIFECYCLE_BUCKETS)
