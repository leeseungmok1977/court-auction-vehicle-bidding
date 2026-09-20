"""판정이 목록 배너와 같은 말을 해야 한다 — '비교 대상 없음'과 '신뢰도 낮음'의 구분.

2026-09-19 디자인 검수에서 **스크린샷을 눈으로 보고** 발견했다. `/vehicles?bucket=nomarket`
목록 상단 배너는 *"동급 중고차가 없어 시세를 내지 않는다"* 인데, 바로 아래 첫 카드 배지는
*"시세 신뢰도 낮음 — 판정 보류"* 였다. 같은 물건에 **두 가지 다른 설명이 40px 간격**으로 놓인다.

원인은 배지 문구가 아니라 판정 엔진이었다. `bid_state()` 는 "이 물건에 대한 하나의 판정"을
책임지는 단일 진실원천인데, 거기에 *"비교할 대상이 없다"* 갈래가 없어서 `lowconf` 로 떨어졌다.

둘은 성격이 다르다.
  · 신뢰도 낮음 = 비교는 했는데 결과를 못 믿겠다  → 표본이 늘면 해결된다
  · 비교 대상 없음 = 비교할 대상이 애초에 없다    → 늘어날 표본이 없다
전자의 문구("표본이 부족해")를 후자에 쓰면 **곧 표본이 생길 것처럼** 읽힌다. 생기지 않는다.

톤을 wait(회색)으로 두는 것도 의도다. 경고가 아니라 **해당 없음**이고, 빨강·앰버를 쓰면
같은 화면의 실제 경고가 희석된다(과거 '빨간 칩 2개로 경고색 희석' 교훈).
"""
import pytest

from web import service
from tests.test_personal_use import BT


def v(**kw):
    base = {"maker": "현대", "model": "쏘나타", "sale_date": "2999-01-01",
            "min_sale_price": 10_000_000, "appraisal_value": 12_000_000,
            "median_price": 13_000_000, "market_confidence_label": "높음",
            "fail_count": 1, "year": 2020, "spec_remark": ""}
    base.update(kw)
    return base


@pytest.mark.parametrize("model,why", [
    ("굴착기", "건설기계·특장"),
    ("덤프트럭", "건설기계·특장"),
    ("정우32KL탱크로리", "건설기계·특장"),
    ("호룡SKY320S고소작업차", "건설기계·특장"),
])
def test_건설기계는_비교대상_없음으로_판정된다(model, why):
    st = service.bid_state(v(model=model, median_price=None), BT)
    assert st["state"] == "nomarket", f"신뢰도 낮음과 섞였다: {st['state']}"
    assert st["tone"] == "wait", "경고가 아니라 해당 없음이다 — 실제 경고를 희석하면 안 된다"
    # 이유는 **범위 층**(버킷 이름·목록 배너)에서만 쓴다. 물건 라벨에는 담지 않는다.
    assert service.no_market_reason({"model": model, "maker": "현대"}) == why


def test_물건_라벨은_분류를_단정하지_않는다():
    """'카고트럭' 낱말 하나로 4.5톤 화물차를 "건설기계·특장"이라 부르던 것을 막는다.

    2026-09-20 디자인 검수 실측: 상세 제목이 `대우자동차(타타대우) 삼부4.5톤극플러스카고트럭`
    인데 바로 아래 칩이 "건설기계·특장"이었다. 같은 화면에서 제품이 스스로 모순된 분류를
    말한 것이고, 이 앱은 차종 필터에 이미 '상용·화물'을 갖고 있다.

    분류는 틀릴 수 있어도 **"동급 시세가 없다"는 검증된 사실**이다 — 라벨은 사실만 말한다.
    """
    for model in ("삼부4.5톤극플러스카고트럭", "굴착기", "덤프트럭", "정우32KL탱크로리"):
        st = service.bid_state(v(model=model, median_price=None), BT)
        assert st["label"] == "동급 시세 없음", f"라벨이 분류를 단정한다: {st['label']}"
        for word in ("건설기계", "특장", "선박"):
            assert word not in st["label"]


def test_선박도_같은_판정을_받는다():
    st = service.bid_state(
        v(maker="", model="", median_price=None,
          spec_remark="제시외 선박의장품 및 어업허가권 등 각 포함하여 매각."), BT)
    assert st["state"] == "nomarket" and st["label"] == "동급 시세 없음"


def test_표본이_부족한_승용차는_여전히_신뢰도_낮음이다():
    """차단이 과해지면 '고칠 수 있는 문제'까지 '어쩔 수 없는 것'으로 감춘다 — 경계를 고정한다."""
    st = service.bid_state(v(market_confidence_label="낮음"), BT)
    assert st["state"] == "lowconf", "승용차의 표본 부족은 성격이 다르다(표본이 늘면 해결된다)"


def test_시세가_있으면_비교대상_없음이_아니다():
    """모델명이 중장비 낱말에 걸려도 **실제로 시세가 나왔다면** 그 사실이 우선이다."""
    st = service.bid_state(v(model="굴착기", median_price=13_000_000), BT)
    assert st["state"] != "nomarket", f"시세가 있는데 없다고 말한다: {st}"


def test_판정_문장이_배너와_같은_말을_한다():
    """리포트가 이 물건에서 말을 잃으면 안 된다 — plain_verdict 에도 문장이 있어야 한다."""
    st = service.bid_state(v(model="굴착기", median_price=None), BT)
    got = service.plain_verdict(v(model="굴착기"), {"price": 5_000_000}, st)
    assert got, "판정 문장이 없다"
    assert "비교할 중고차가 없어" in got["text"]
    assert "표본" not in got["text"], "표본 부족 문구를 쓰면 곧 표본이 생길 것처럼 읽힌다"
    assert got["tone"] == "wait"


def test_상태_목록에_등록되어_있다():
    """BID_STATES 에 빠지면 이 값을 쓰는 화면이 조용히 빈칸이 된다."""
    assert "nomarket" in service.BID_STATES
    assert len(set(service.BID_STATES)) == len(service.BID_STATES)
