"""SK엔카 동급 매물 시세 수집 (설계서 E1~E3/FLOW-03, TASK-05).

  GET https://api.encar.com/search/car/list/general?count=true&q=<쿼리>&sr=|ModifiedDate|0|N
  응답: { "Count": N, "SearchResults": [ {Manufacturer, Model, Badge, FuelType,
          Year(첫등록 YYYYMM), FormYear(연식), Mileage(km), Price(만원), ...} ] }

q 문법(실측): (And.Hidden.N._.(C.CarType.Y._.(C.Manufacturer.기아._.ModelGroup.카니발.))_.Year.range(202001..202212).)
  - CarType.Y=국산, N=수입 / Manufacturer·ModelGroup은 엔카 표기 그대로
  - Price 단위는 만원 → 원 환산은 ×10000

⚠️ 준법 주의: api.encar.com/robots.txt = 'Disallow: /'. 본 모듈의 자동 수집은
   사용자의 명시적 지시(2026-08-17)에 따른 것이며, 물건당 소량·저속(요청 간 지연)으로 제한한다.
"""

from __future__ import annotations

import re
import time
from typing import Optional

import requests

API = "https://api.encar.com/search/car/list/general"          # 국산
API_PREMIUM = "https://api.encar.com/search/car/list/premium"  # 수입
# 화물·특장·버스는 **엔드포인트가 다르다**(2026-09-19 브라우저 실측, capture/E4_truck_general.txt).
# 포터·봉고가 계속 '동급 표본 없음'이던 진짜 원인이 이것이다 — 승용 서랍만 열고 "없다"고 했다.
API_TRUCK = "https://api.encar.com/search/truck/list/general"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
REQUEST_DELAY_SEC = 5  # 저속


# 법원경매 제조사 표기 → 엔카 Manufacturer 표기 정규화
MAKER_NORMALIZE = {
    "현대": "현대", "기아": "기아", "제네시스": "제네시스",
    "르노코리아": "르노코리아(삼성)", "르노삼성": "르노코리아(삼성)",
    "르노": "르노코리아(삼성)", "삼성": "르노코리아(삼성)",
    "쉐보레": "쉐보레(GM대우)", "한국지엠": "쉐보레(GM대우)",
    "지엠대우": "쉐보레(GM대우)", "gm대우": "쉐보레(GM대우)", "대우": "쉐보레(GM대우)",
    "kg모빌리티": "KG모빌리티(쌍용)", "케이지모빌리티": "KG모빌리티(쌍용)",
    "쌍용": "KG모빌리티(쌍용)", "kgm": "KG모빌리티(쌍용)",
    # 법인명 표기(실측): '제너럴모터스', 'CHEVROLET …' 등도 엔카 쉐보레로
    "제너럴모터스": "쉐보레(GM대우)", "chevrolet": "쉐보레(GM대우)",
    "generalmotors": "쉐보레(GM대우)",   # 'GENERAL MOTORS LLC' (실측: COLORADO 미조회)
}


def normalize_maker(court_maker: Optional[str]) -> Optional[str]:
    """법원경매 제조사명(예: '현대자동차(주)') → 엔카 표기(예: '현대'). 미상 시 None."""
    s = (court_maker or "").replace("(주)", "").replace("주식회사", "").replace(" ", "").lower()
    if s in ("gm", "gmkorea", "한국gm"):          # 'GM' 단독 표기(실측: 'GM | CHEVROLET TRAVERSE')
        return "쉐보레(GM대우)"
    for key, val in MAKER_NORMALIZE.items():
        if key in s:
            return val
    return None


# 제네시스 브랜드 모델 (법원 제조사는 '현대'로 표기되나 엔카는 별도 제조사)
GENESIS_MODELS = {"G70", "G80", "G90", "GV60", "GV70", "GV80", "EQ900"}


# 첫 토큰 추출이 틀리는 다토큰 모델의 별칭 (공백 제거 키 → 엔카 모델그룹)
MODELGROUP_ALIAS = {
    "그랜드스타렉스": "스타렉스", "더뉴스타렉스": "스타렉스", "스타렉스": "스타렉스",
    "그랜드스타렉": "스타렉스",     # 법원 차명이 잘린 채 들어온 실측 사례
    # ⚠ 엔카는 ModelGroup(차종) → Model(세대) 두 단계다. 2026-09-13 승인 조회 실측:
    #   ModelGroup '렉스턴' 안에 Model '렉스턴 스포츠'·'렉스턴 스포츠 칸'·'G4 렉스턴'·'올 뉴 렉스턴'이 같이 있다.
    #   전에는 '렉스턴 스포츠'·'G4 렉스턴'을 ModelGroup 자리에 넣어 19대 전부 0건이었다.
    #   픽업/SUV 는 model_hint() 가 Model 명으로 가른다(같은 그룹에 섞여 있으므로 필수).
    "g4렉스턴": "렉스턴", "렉스턴스포츠": "렉스턴", "렉스턴스포츠칸": "렉스턴",
    "렉스턴스포츠쿨멘": "렉스턴", "더뉴렉스턴": "렉스턴", "올뉴렉스턴": "렉스턴",
    "코란도스포츠": "코란도", "뉴코란도": "코란도",
    "더뉴카니발": "카니발", "그랜드카니발": "카니발",
    "레이ev": "레이",               # 실측: ModelGroup '레이' 안에 Model '더 뉴 기아 레이 EV'(연료 전기)
    # 영문 표기 차명(실측: '제너럴모터스 | CHEVROLET TRAVERSE AWD') → 엔카 한글 모델그룹
    "traverse": "트래버스", "trailblazer": "트레일블레이저", "equinox": "이쿼녹스",
    "malibu": "말리부", "colorado": "콜로라도", "tahoe": "타호", "spark": "스파크", "trax": "트랙스",
    # 수입 ModelGroup 은 한글 음차가 원칙(실측 성공: 토러스·카이엔·레인지로버 / 승인 조회: 익스플로러·파사트·쿠퍼).
    # 영문 그대로 보내면 0건이라 '시세 없음'으로 굳는다. RAV4 처럼 영문이 정식인 것도 있다(실측 39건).
    "explorer": "익스플로러", "passat": "파사트", "cooper": "쿠퍼",
    # 컨트리맨·클럽맨은 프로덕션 재조회로 확인(Model '쿠퍼 컨트리맨' 37건·'쿠퍼 클럽맨' 12건).
    # 티구안·코세어는 미검증 — 틀리면 0건(=지금과 같음)이지 오매칭은 아니다.
    "coopercountryman": "컨트리맨", "cooperclubman": "클럽맨", "tiguan": "티구안", "corsair": "코세어",
}

# 차명 앞에 붙는 브랜드 토큰 — 모델그룹 추출 전에 제거한다.
# (실측: '짚 체로키 2.2'의 첫 토큰이 '짚'으로 잡혀 엔카 검색이 실패했음)
_BRAND_PREFIX = {
    "현대", "현대자동차", "기아", "기아자동차", "제네시스", "쌍용", "kg모빌리티", "kgm",
    "쉐보레", "chevrolet", "gm", "대우", "르노", "르노삼성", "삼성",
    "벤츠", "메르세데스", "mercedes", "benz", "mercedes-benz", "bmw", "아우디", "audi", "폭스바겐", "volkswagen",
    "폭스바켄", "peugoet",   # 법원 오타 실측('폭스바켄 | Tiguan', '푸조 | Peugoet 3008')
    "지프", "짚", "jeep", "포드", "ford", "볼보", "volvo", "렉서스", "lexus",
    "도요타", "토요타", "toyota", "혼다", "honda", "닛산", "nissan", "포르쉐", "porsche",
    "재규어", "jaguar", "랜드로버", "링컨", "lincoln", "캐딜락", "cadillac",
    "인피니티", "infiniti", "마세라티", "maserati", "벤틀리", "bentley", "푸조", "peugeot",
    "시트로엥", "citroen", "테슬라", "tesla", "미니", "mini",
}


def clean_model_group(car_nm: Optional[str]) -> Optional[str]:
    """법원 차명 → 엔카 모델그룹 추정. (영문 괄호 제거 후 별칭 우선, 없으면 첫 토큰)

    예: '그랜저(GRANDEUR)'→'그랜저', '쏘나타 뉴 라이즈'→'쏘나타',
        '그랜드 스타렉스(GRAND STAREX)'→'스타렉스', 'K8'→'K8'
    """
    if not car_nm:
        return None
    s = re.sub(r"\([^)]*\)", "", car_nm)          # (ENGLISH) 제거
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return None
    parts = s.split(" ")                          # 선행 브랜드 토큰 제거('짚 체로키'→'체로키')
    while len(parts) > 1 and parts[0].lower() in _BRAND_PREFIX:
        parts = parts[1:]
    s = " ".join(parts)
    key = s.replace(" ", "").lower()
    if key in MODELGROUP_ALIAS:
        return MODELGROUP_ALIAS[key]
    first = s.split(" ")[0]                       # 첫 토큰도 별칭 조회('TRAVERSE AWD'→트래버스)
    # '트랙스1.4'·'말리부1.5' — 차명에 배기량이 붙어 한 토큰이 된 실측 사례. 한글 차명 뒤의 'n.n'만 뗀다
    # (포터Ⅱ·봉고3 같은 세대 숫자는 건드리지 않는다 — 그 표기는 별개 문제).
    m = re.match(r"^([가-힣]+)\d\.\d$", first)
    if m:
        first = m.group(1)
    return MODELGROUP_ALIAS.get(first.lower(), first)


def model_hint(car_nm: Optional[str]) -> tuple:
    """엔카 Model(세대) 이름으로 차형을 가르는 키워드 — (포함 목록, 제외 목록).

    엔카는 같은 ModelGroup 안에 차형이 다른 Model 을 섞어 둔다(2026-09-13 승인 조회 실측):
      '렉스턴' = 렉스턴 스포츠(픽업) · 렉스턴 스포츠 칸 · G4 렉스턴(SUV) · 올 뉴 렉스턴
      '코란도' = 뷰티풀 코란도(SUV) · 더 뉴 코란도 스포츠(픽업)     '레이' = 레이 · 레이 EV
    실제 사고: 2022 렉스턴(SUV, 감정 3,100만)이 '더 뉴 렉스턴 스포츠' 6건으로 2,145만에 평가됐다.
    반환한 키워드로 summarize 가 Model 을 거른다(포함 표본 3건 미만이면 신뢰도 '낮음' 상한)."""
    s = re.sub(r"\([^)]*\)", "", car_nm or "").replace(" ", "").lower()
    inc, exc = [], []
    if "렉스턴" in s or "코란도" in s:
        if "스포츠" in s:
            inc.append("스포츠")
            (inc if "칸" in s else exc).append("칸")
        else:
            exc.append("스포츠")
    if s.startswith("레이"):
        (inc if "ev" in s else exc).append("EV")
    return inc, exc


# 수입 브랜드 감지 (법원 제조사/차명의 키워드 → 엔카 수입 제조사 표기)
IMPORT_BRANDS = [
    # 미니가 BMW 보다 먼저 — 법원 제조사가 'BMW AG'라 'MINI Cooper'가 BMW/Cooper 로 조회돼 10대 전부 0건이었다.
    # 엔카 실측(승인 조회): 제조사 '미니' · ModelGroup '쿠퍼'(Model 쿠퍼·쿠퍼 S·쿠퍼 D).
    (("미니", "mini"), "미니"),
    (("벤츠", "benz", "메르세데스", "mercedes", "다임러", "daimler"), "벤츠"),
    (("bmw", "비엠"), "BMW"),
    (("아우디", "audi"), "아우디"),
    (("폭스바겐", "volkswagen", "폭스바켄"), "폭스바겐"),
    (("랜드로버", "랜드로바", "land rover", "landrover", "레인지로버", "디스커버리", "디펜더"), "랜드로버"),
    (("재규어", "jaguar"), "재규어"),
    (("포르쉐", "porsche", "카이엔", "파나메라", "마칸"), "포르쉐"),
    (("볼보", "volvo"), "볼보"),
    (("렉서스", "lexus"), "렉서스"),
    (("링컨", "lincoln"), "링컨"),
    (("지프", "짚", "jeep"), "지프"),
    (("마세라티", "maserati"), "마세라티"),
    (("벤틀리", "bentley", "continental"), "벤틀리"),
    (("포드", "ford"), "포드"),
    (("푸조", "peugeot"), "푸조"),
    (("시트로엥", "citroen"), "시트로엥/DS"),
    (("인피니티", "infiniti"), "인피니티"),
    (("캐딜락", "cadillac"), "캐딜락"),
    (("테슬라", "tesla"), "테슬라"),
    (("도요타", "토요타", "toyota"), "도요타"),
    (("혼다", "honda"), "혼다"),
    (("닛산", "nissan"), "닛산"),
]


def detect_import(court_maker: Optional[str], car_nm: Optional[str]) -> Optional[str]:
    # 차명 먼저, 그다음 제조사+차명. 법인명이 두 브랜드를 품는 경우('제규어랜드로버코리아 | 재규어 F-PACE')
    # 제조사 문자열의 '랜드로버'가 차명의 '재규어'를 이겨 엉뚱한 제조사로 조회됐다(실측 2대).
    for s in ((car_nm or "").lower(), ((court_maker or "") + " " + (car_nm or "")).lower()):
        for kws, name in IMPORT_BRANDS:
            if name == "미니" and ("미니버스" in s or "미니밴" in s):
                continue                              # 국산 승합 '미니버스'는 브랜드가 아니다
            if any(k in s for k in kws):
                return name
    return None


def trim_hint(car_nm: Optional[str]) -> Optional[str]:
    """고가 서브트림(마이바흐·AMG)을 감지. 엔카 Badge에 이 토큰이 있는 매물로 좁혀
    상위 트림이 기본 트림 시세에 섞이지 않게 한다(예: 마이바흐 S580 ≠ 일반 S클래스).
    오탐 위험이 큰 토큰(BMW 'M', 현대 'N' 등 단문자)은 넣지 않는다."""
    s = car_nm or ""
    su = s.upper()
    if "마이바흐" in s or "MAYBACH" in su:
        return "마이바흐"
    if "AMG" in su:
        return "AMG"
    return None


def _benz_group(car_nm: str) -> Optional[str]:
    s = car_nm or ""; su = s.upper()
    for gl in ("GLC", "GLE", "GLA", "GLB", "GLS"):
        if gl in su:
            return gl + "-클래스"
    for cl in ("CLA", "CLS"):
        if cl in su:
            return cl + "-클래스"      # 실측(승인 조회): 'CLS-클래스 W218' — 접미 없이 'CLS'는 0건(7대)
    if "마이바흐" in s or "MAYBACH" in su:
        return "S-클래스"
    # 'E 250'(공백)·'E300' 둘 다 — 'Mercedes-Benz E 250'이 공백 때문에 못 잡혀 모델그룹이 'Mercedes-Benz'가 됐다
    m = re.search(r"\b([ABCESG])\s?-?\s?클래스", s) or re.search(r"\b([ABCESG])\s?\d", su)
    if m:
        L = m.group(1)
        return "G-클래스" if L == "G" else f"{L}-클래스"
    return clean_model_group(car_nm)


def _bmw_group(car_nm: str) -> Optional[str]:
    su = (car_nm or "").upper()
    m = re.search(r"\bX\s?(\d)", su)
    if m:
        return f"X{m.group(1)}"
    m = re.search(r"(?:M\s?)?(\d)\d\d", su)
    if m:
        return f"{m.group(1)}시리즈"
    return clean_model_group(car_nm)


def import_model_group(brand: str, car_nm: Optional[str]) -> Optional[str]:
    if brand == "벤츠":
        return _benz_group(car_nm)
    if brand == "BMW":
        return _bmw_group(car_nm)
    mg = clean_model_group(car_nm)  # 아우디·포르쉐·랜드로버·렉서스 등은 첫 토큰이 대체로 일치
    if brand == "렉서스" and mg:
        # 실측(승인 조회): ModelGroup 'RX' 안에 Model 'RX350h 5세대'·'RX450h+ 5세대' — 'RX350h'는 0건
        m = re.match(r"^([A-Z]{2})\d", mg.upper())
        if m:
            return m.group(1)
    if brand == "랜드로버" and mg:
        # 실측(comps): ModelGroup '디스커버리' 안에 Model '디스커버리 4'·'디스커버리 5' — '디스커버리4'는 0건
        return re.sub(r"^(디스커버리)\s?\d+$", r"\1", mg)
    return mg


# 국산 모델명 → 엔카 제조사. 법원 제조사가 비었거나 법인명·오타일 때 차명으로 추정한다.
# ⚠ 특장·개조 비율이 높아 시세가 왜곡되기 쉬운 상용차(포터·봉고·다마스·라보 등)는 일부러 제외한다
#   — 잘못된 시세는 시세 없음보다 나쁘다(신뢰성 원칙).
KOREAN_MODEL_MAKER = {
    "현대": ("쏘나타", "그랜저", "아반떼", "투싼", "싼타페", "팰리세이드", "코나", "캐스퍼",
             "베뉴", "스타렉스", "스타리아", "아이오닉", "넥쏘", "벨로스터", "맥스크루즈", "엑센트"),
    "기아": ("k3", "k5", "k7", "k8", "k9", "카니발", "쏘렌토", "스포티지", "셀토스", "니로",
             "모닝", "레이", "스토닉", "쏘울", "모하비", "오피러스", "카렌스"),
    "KG모빌리티(쌍용)": ("렉스턴", "코란도", "티볼리", "토레스", "액티언", "카이런", "체어맨",
                    "무쏘", "로디우스"),
    "쉐보레(GM대우)": ("스파크", "트랙스", "트래버스", "말리부", "이쿼녹스", "트레일블레이저",
                   "올란도", "캡티바", "크루즈", "아베오", "윈스톰", "라세티", "마티즈", "타호"),
    "르노코리아(삼성)": ("sm3", "sm5", "sm6", "sm7", "qm3", "qm5", "qm6", "xm3", "캡처",
                    "그랑콜레오스"),
}


# ── 화물(1톤 경상용) 매핑 ────────────────────────────────────────────────
# 포터·봉고는 **화물 엔드포인트**에 있다. 표기는 규칙이 아니라 개별 실측값이다
# (2026-09-19): 포터는 '포터 Ⅱ'(로마숫자 앞 **공백 있음**), 봉고는 '봉고Ⅲ'(**공백 없음**).
# 건수: 포터 Ⅱ 5,141(카고 3,240·윙바디/탑 1,729) · 봉고Ⅲ 1,691(카고 921·윙바디/탑 553).
#
# ⚠ 여기에 넣는 것은 **포터·봉고뿐**이다. 덤프트럭·굴착기·지게차·탱크로리 같은 중장비·특장은
#   계속 매핑하지 않는다 — 시세가 있어도 개체차가 커서 동급 비교가 성립하지 않는다는
#   기존 판단(tests/test_encar_map.py 가 고정)을 뒤집지 않는다.
TRUCK_MODELS = {
    "포터": ("현대", "포터 Ⅱ"),
    "porter": ("현대", "포터 Ⅱ"),
    "봉고": ("기아(아시아)", "봉고Ⅲ"),
    "bongo": ("기아(아시아)", "봉고Ⅲ"),
}
# 형식(Form) 판별 — 모델명에 적재함 형태가 적혀 있을 때만 쓴다.
# ⚠ '1톤'은 형식이 아니라 **적재량**이다. 냉동탑차도 1톤이라 이걸로 카고라 단정하면
#   탑차를 카고 시세로 평가하게 된다(초안에서 실제로 저지른 실수).
TRUCK_FORM_WORDS = (
    ("윙바디/탑", ("냉동탑", "냉통탑", "내장탑", "하이탑", "윙바디", "탑차", "냉동", "냉장", "보냉")),
    ("카고(화물)트럭", ("카고", "화물트럭", "평판")),
)


def truck_form(car_nm: Optional[str]) -> Optional[str]:
    """차명에서 적재함 형식을 읽는다. 적혀 있지 않으면 None(= 시세를 내지 않는다).

    형식을 모르는 채 모델만으로 조회하면 카고와 탑차가 섞인 시세가 나온다.
    잘못된 시세는 시세 없음보다 나쁘다 — 그래서 모르면 포기한다."""
    s = re.sub(r"\([^)]*\)", "", car_nm or "").replace(" ", "")
    for form, words in TRUCK_FORM_WORDS:
        if any(w in s for w in words):
            return form
    return None


def truck_map(court_maker: Optional[str], car_nm: Optional[str]) -> Optional[dict]:
    """포터·봉고면 화물 조회용 매핑을, 아니면 None.

    형식을 읽을 수 없으면 **매핑하지 않는다**(호출부는 '시세 없음'으로 남긴다)."""
    s = re.sub(r"\([^)]*\)", "", car_nm or "").replace(" ", "").lower()
    if not s:
        return None
    for key, (man, model) in TRUCK_MODELS.items():
        if key in s:
            form = truck_form(car_nm)
            if not form:
                return None
            return {"truck": True, "car_type": "Y", "manufacturer": man,
                    "model_group": model, "form": form}
    return None


def maker_from_model(car_nm: Optional[str]) -> Optional[str]:
    """차명으로 국산 제조사 추정 — 법원 제조사가 비었거나 법인명/오타일 때의 폴백.
    실측 예: '기차|K7'(오타)→기아, '(빈값)|렉스턴스포츠'→KG모빌리티."""
    s = re.sub(r"\([^)]*\)", "", car_nm or "").replace(" ", "").lower()
    if not s:
        return None
    for man, kws in KOREAN_MODEL_MAKER.items():
        if any(k in s for k in kws):
            return man
    return None


def auto_map(court_maker: Optional[str], car_nm: Optional[str],
             car_type: str = "Y") -> Optional[dict]:
    """법원 물건의 제조사·차명으로 엔카 매핑 자동 추정. 국산 우선, 이어서 수입."""
    # 0) 화물(포터·봉고) — **엔드포인트가 다르므로** 승용 매핑보다 먼저 가른다.
    #    그러지 않으면 clean_model_group 이 '포터Ⅱ'를 만들어 승용 경로로 새고 0건이 난다
    #    (2026-09-19 실측: 포터·봉고 21건이 전부 '동급 표본 없음'이던 원인).
    tm = truck_map(court_maker, car_nm)
    if tm:
        return tm
    mg = clean_model_group(car_nm)
    if not mg:
        return None
    # 1) 제네시스 — 단, 차명이 그냥 '제네시스'(2008~2016 현대 제네시스 DH·BH)면 엔카는 **현대/제네시스**다
    #    (승인 조회 실측: 현대/제네시스 2015 → 1,017건, Model '제네시스 DH'). 브랜드 쪽으로 보내면 0건(10대).
    if mg == "제네시스":
        return {"car_type": "Y", "manufacturer": "현대", "model_group": "제네시스"}
    if mg.upper() in GENESIS_MODELS or "제네시스" in (car_nm or ""):
        return {"car_type": "Y", "manufacturer": "제네시스", "model_group": mg}
    # 2) 국산 (미니버스 등 오탐 방지: 국산 제조사면 여기서 확정)
    man = normalize_maker(court_maker)
    if man:
        return {"car_type": car_type, "manufacturer": man, "model_group": mg}
    # 3) 수입 (premium 엔드포인트)
    brand = detect_import(court_maker, car_nm)
    if brand:
        img = import_model_group(brand, car_nm)
        if img:
            return {"car_type": "N", "manufacturer": brand, "model_group": img, "premium": True}
    # 4) 제조사 미상·법인명·오타 → 차명으로 국산 제조사 추정 (마지막 폴백)
    man2 = maker_from_model(car_nm)
    if man2:
        return {"car_type": car_type, "manufacturer": man2, "model_group": mg}
    return None


def new_session() -> requests.Session:
    import os
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Accept": "application/json",
        "Referer": "https://www.encar.com/",
        "Origin": "https://www.encar.com",
    })
    # 아웃바운드 경로 분리(F안): 2026-09 엔카가 서버(AWS) IP를 407로 차단 → ENCAR_PROXY가 있으면
    # **엔카 요청만** 그 경로로 보낸다(예: 집 회선 → 역방향 SSH 터널 http://127.0.0.1:18080).
    # 사이트 IP·DNS·법원 수집은 영향 없음. 요청 수·지연은 그대로(C.4 준수).
    proxy = os.environ.get("ENCAR_PROXY", "").strip()
    if proxy:
        s.proxies.update({"http": proxy, "https": proxy})
    return s


def q_escape(value: str) -> str:
    """질의 값에 괄호가 있으면 **닫는 괄호 앞에 `_`** 를 넣는다.

    실측(2026-09-19): `Manufacturer.기아(아시아_).` · `Form.카고(화물_)트럭.` ·
    `Model.포레스트 (포터Ⅱ_).` — 엔카 질의 문법에서 `)` 는 블록 종료라 그대로 두면 깨진다."""
    return (value or "").replace(")", "_)")


def build_q(manufacturer: str, model_group: Optional[str] = None,
            car_type: str = "Y", year_from: Optional[int] = None,
            year_to: Optional[int] = None, truck: bool = False,
            form: Optional[str] = None) -> str:
    """엔카 검색 쿼리 조립. year_from/to 는 YYYYMM(첫등록 기준).

    승용: (And.Hidden.N._.(C.CarType.Y._.(C.Manufacturer.현대._.ModelGroup.쏘나타.))_.Year.range(…).)
    화물: (And.Hidden.N._.(C.Manufacturer.현대._.Model.포터 Ⅱ.)_.Form.카고(화물_)트럭._.Year.range(…).)
      · 화물은 **CarType 축이 없다**(엔드포인트가 차종을 가른다)
      · 모델 축 이름이 ModelGroup 이 아니라 **Model**
      · 형식(Form)으로 카고/탑차를 가를 수 있다 — 섞으면 시세가 왜곡된다
    """
    man = q_escape(manufacturer)
    mg = q_escape(model_group) if model_group else None
    if truck:
        block = f"(C.Manufacturer.{man}._.Model.{mg}.)" if mg else f"Manufacturer.{man}."
        q = f"(And.Hidden.N._.{block}"
        if form:
            q += f"_.Form.{q_escape(form)}."
    else:
        maker_block = (f"(C.Manufacturer.{man}._.ModelGroup.{mg}.)" if mg
                       else f"Manufacturer.{man}.")
        q = f"(And.Hidden.N._.(C.CarType.{car_type}._.{maker_block})"
    if year_from and year_to:
        q += f"_.Year.range({year_from}..{year_to})."
    q += ")"
    return q


def search(session: requests.Session, manufacturer: str,
           model_group: Optional[str] = None, car_type: str = "Y",
           year_from: Optional[int] = None, year_to: Optional[int] = None,
           limit: int = 100, offset: int = 0, premium: bool = False,
           truck: bool = False, form: Optional[str] = None) -> dict:
    """동급 매물 목록 조회 (1회 호출).

    premium=True 면 수입 엔드포인트, truck=True 면 **화물 엔드포인트**를 쓴다.
    응답 키(Count·SearchResults)는 셋 다 같아서 이후 파싱은 공통이다."""
    q = build_q(manufacturer, model_group, car_type, year_from, year_to,
                truck=truck, form=form)
    params = {"count": "true", "q": q, "sr": f"|ModifiedDate|{offset}|{limit}"}
    time.sleep(REQUEST_DELAY_SEC)
    endpoint = API_TRUCK if truck else (API_PREMIUM if premium else API)
    r = session.get(endpoint, params=params, timeout=25)
    if r.status_code in (403, 429):
        raise RuntimeError(f"엔카 차단 상태코드 {r.status_code} — 중단")
    r.raise_for_status()
    j = r.json()
    return {"count": j.get("Count"), "results": j.get("SearchResults", []), "q": q}


def normalize(results: list[dict]) -> list[dict]:
    """엔카 원행 → 공통 매물 스키마(price_won, mileage_km, form_year)."""
    out = []
    for row in results:
        price_manwon = row.get("Price")
        mileage = row.get("Mileage")
        form_year = row.get("FormYear")
        try:
            price_won = int(float(price_manwon) * 10000) if price_manwon is not None else None
        except (TypeError, ValueError):
            price_won = None
        try:
            mileage_km = int(float(mileage)) if mileage is not None else None
        except (TypeError, ValueError):
            mileage_km = None
        try:
            fy = int(str(form_year)[:4]) if form_year else None
        except (TypeError, ValueError):
            fy = None
        out.append({
            "platform": "encar",
            "manufacturer": row.get("Manufacturer"),
            "model": row.get("Model"),          # 세대 구분 (예: '더 뉴 카니발' vs '카니발 4세대')
            "badge": row.get("Badge"),
            "fuel": row.get("FuelType"),        # 디젤/가솔린/LPG …
            "form_year": fy,
            "mileage_km": mileage_km,
            "price_won": price_won,
            "id": row.get("Id"),
        })
    return out


# 법원 연료코드 → 엔카 FuelType (동급 매칭용). 미상은 필터 안 함.
FUEL_CODE_TO_ENCAR = {"0001001": "가솔린", "0001002": "디젤", "0001003": "LPG"}


def encar_fuel(fuel_code) -> Optional[str]:
    return FUEL_CODE_TO_ENCAR.get(str(fuel_code or ""))
