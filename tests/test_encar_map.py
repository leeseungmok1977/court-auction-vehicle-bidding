"""엔카 제조사·모델그룹 매핑 — 법원 원문 표기 정규화(실측 실패 사례 기반 회귀 방지).

신뢰성 원칙: 잘못된 시세는 시세 없음보다 나쁘다. 승용 매칭이 불가능한 건설기계·상용트럭·
비차량은 **매핑되지 않아야** 한다(정상 실패). 아래 테스트가 그 경계를 고정한다.
"""
import pytest

from src.collect import encar


@pytest.mark.parametrize("maker,model,man,mg", [
    # 법인명·오타·영문 표기(운영 DB 실측 실패 사례)
    ("다임러 AG", "E300 4Matic", "벤츠", "E-클래스"),
    ("다임러AG", "E200", "벤츠", "E-클래스"),
    ("KGM", "렉스턴스포츠", "KG모빌리티(쌍용)", "렉스턴 스포츠"),
    ("기차", "K7", "기아", "K7"),                      # 제조사 '기아' 오타 → 차명으로 복구
    ("", "렉스턴스포츠 쿨멘", "KG모빌리티(쌍용)", "렉스턴 스포츠"),   # 제조사 빈값 → 차명으로 복구
    ("제너럴모터스", "CHEVROLET TRAVERSE AWD", "쉐보레(GM대우)", "트래버스"),
    ("Chrysler Group LLC", "짚 체로키 2.2", "지프", "체로키"),
    ("FCA", "짚 레니게이드 2.4 FWD", "지프", "레니게이드"),
    # 기존 동작 회귀 방지
    ("현대", "쏘나타", "현대", "쏘나타"),
    ("현대자동차(주)", "그랜저(GRANDEUR)", "현대", "그랜저"),
    ("기아", "K5", "기아", "K5"),
    ("BMW", "520d", "BMW", "5시리즈"),
    ("현대", "그랜드 스타렉스(GRAND STAREX)", "현대", "스타렉스"),
    ("현대", "제네시스 G80", "제네시스", "G80"),
    ("쌍용", "G4렉스턴", "KG모빌리티(쌍용)", "G4 렉스턴"),
    ("볼보", "XC60", "볼보", "XC60"),
])
def test_auto_map_resolves(maker, model, man, mg):
    r = encar.auto_map(maker, model)
    assert r is not None, f"매핑 실패: {maker} | {model}"
    assert r["manufacturer"] == man
    assert r["model_group"] == mg


@pytest.mark.parametrize("maker,model", [
    ("에이치디건설기계(주)", "굴착기"),
    ("두산밥캣코리아(주)", "지게차"),
    ("만트럭버스코리아(주)", "덤프트럭"),
    ("스카니아코리아그룹(주)", "덤프트럭"),
    ("(주)삼부", "삼부5.5톤냉장윙바디트럭"),
    ("전진건설로봇(주)", "콘크리트 펌프"),
    ("미상", "공장 및 광업재단 저당법 제6조 목록"),   # 차량이 아님
    ("", ""),
])
def test_auto_map_rejects_non_passenger(maker, model):
    """승용 시세로 매칭할 수 없는 건설기계·상용·비차량은 매핑하지 않는다(오매칭 방지)."""
    assert encar.auto_map(maker, model) is None


def test_maker_from_model_is_last_resort_only():
    """차명 추론은 제조사가 확인될 때는 개입하지 않는다(기존 매핑 우선)."""
    assert encar.maker_from_model("K7") == "기아"
    assert encar.maker_from_model("굴착기") is None
    # 제조사가 명확하면 그 값이 우선
    assert encar.auto_map("현대", "쏘나타")["manufacturer"] == "현대"
