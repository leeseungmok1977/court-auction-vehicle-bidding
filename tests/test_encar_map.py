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
    # 렉스턴 계열: 엔카 ModelGroup 은 '렉스턴' 하나(승인 조회 실측 1,766건 — '렉스턴 스포츠'·'G4 렉스턴'은 Model).
    # 예전 값 '렉스턴 스포츠'/'G4 렉스턴'을 ModelGroup 자리에 넣어 19대 전부 0건이었다.
    ("KGM", "렉스턴스포츠", "KG모빌리티(쌍용)", "렉스턴"),
    ("기차", "K7", "기아", "K7"),                      # 제조사 '기아' 오타 → 차명으로 복구
    ("", "렉스턴스포츠 쿨멘", "KG모빌리티(쌍용)", "렉스턴"),   # 제조사 빈값 → 차명으로 복구
    ("KGM(구,쌍용)", "렉스턴스포츠 칸", "KG모빌리티(쌍용)", "렉스턴"),
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
    ("쌍용", "G4렉스턴", "KG모빌리티(쌍용)", "렉스턴"),
    ("볼보", "XC60", "볼보", "XC60"),
    # 2026-09-13 승인 조회(14회)로 확인한 엔카 계층·표기 — 실사용 추천 47대 조사에서 드러난 0건 원인들
    ("현대자동차(주)", "제네시스(GENESIS)", "현대", "제네시스"),   # DH 제네시스는 현대 밑(1,017건) — 브랜드로 보내면 0건
    ("현대", "제네시스 G80", "제네시스", "G80"),                 # 브랜드 제네시스는 그대로
    ("BMW AG 독일", "MINI Cooper D five-door", "미니", "쿠퍼"),  # 제조사가 BMW AG 라도 MINI 는 미니/쿠퍼(179건)
    ("비엠더블유코리아(주)", "MINI Cooper", "미니", "쿠퍼"),
    ("벤츠", "Mercedes-Benz E 250", "벤츠", "E-클래스"),         # 'E 250' 공백 — 전엔 모델그룹이 'Mercedes-Benz'
    ("벤츠", "CLS400 d 4Matic", "벤츠", "CLS-클래스"),          # 실측 'CLS-클래스 W218'(126건) — 'CLS'는 0건
    ("LAND ROVER", "디스커버리4 3.0D", "랜드로버", "디스커버리"),  # comps 실측: Model '디스커버리 4'
    ("토요타", "렉서스 RX350h", "렉서스", "RX"),                 # ModelGroup RX / Model 'RX350h 5세대'
    ("토요타", "토요타 RAV4 Hybrid 2WD", "도요타", "RAV4"),       # 영문이 정식(39건) — '라브4'는 0건
    ("포드", "Explorer 2.3", "포드", "익스플로러"),
    ("폭스바겐", "Passat 2.0 TSI", "폭스바겐", "파사트"),
    ("폭스바켄", "Tiguan 2.0 TDI", "폭스바겐", "티구안"),         # 법원 오타 제조사
    ("기아자동차", "레이EV", "기아", "레이"),                    # Model '더 뉴 기아 레이 EV'(연료 전기)
    ("쉐보레", "트랙스1.4", "쉐보레(GM대우)", "트랙스"),           # 배기량이 붙은 한 토큰
    ("현대자동차", "그랜드스타렉", "현대", "스타렉스"),            # 잘린 차명
    ("GENERAL MOTORS LLC", "COLORADO", "쉐보레(GM대우)", "콜로라도"),
    ("GM", "CHEVROLET TRAVERSE", "쉐보레(GM대우)", "트래버스"),
    ("BMW AG 독일", "BMW M4 Competition M xDrive", "BMW", "M4"),  # 실측 47건(Model 'M4 (G82)')
    ("마세라티", "마세라티 르반떼 디젤", "마세라티", "르반떼"),     # 실측 Model '르반떼'
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
