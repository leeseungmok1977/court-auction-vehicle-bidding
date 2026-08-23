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
    "쌍용": "KG모빌리티(쌍용)",
}


def normalize_maker(court_maker: Optional[str]) -> Optional[str]:
    """법원경매 제조사명(예: '현대자동차(주)') → 엔카 표기(예: '현대'). 미상 시 None."""
    s = (court_maker or "").replace("(주)", "").replace("주식회사", "").replace(" ", "").lower()
    for key, val in MAKER_NORMALIZE.items():
        if key in s:
            return val
    return None


# 제네시스 브랜드 모델 (법원 제조사는 '현대'로 표기되나 엔카는 별도 제조사)
GENESIS_MODELS = {"G70", "G80", "G90", "GV60", "GV70", "GV80", "EQ900"}


# 첫 토큰 추출이 틀리는 다토큰 모델의 별칭 (공백 제거 키 → 엔카 모델그룹)
MODELGROUP_ALIAS = {
    "그랜드스타렉스": "스타렉스", "더뉴스타렉스": "스타렉스", "스타렉스": "스타렉스",
    "g4렉스턴": "G4 렉스턴", "렉스턴스포츠": "렉스턴 스포츠",
    "코란도스포츠": "코란도", "뉴코란도": "코란도",
    "더뉴카니발": "카니발", "그랜드카니발": "카니발",
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
    key = s.replace(" ", "").lower()
    if key in MODELGROUP_ALIAS:
        return MODELGROUP_ALIAS[key]
    return s.split(" ")[0]


# 수입 브랜드 감지 (법원 제조사/차명의 키워드 → 엔카 수입 제조사 표기)
IMPORT_BRANDS = [
    (("벤츠", "benz", "메르세데스", "mercedes"), "벤츠"),
    (("bmw", "비엠"), "BMW"),
    (("아우디", "audi"), "아우디"),
    (("폭스바겐", "volkswagen"), "폭스바겐"),
    (("미니", "mini"), "미니"),
    (("랜드로버", "랜드로바", "land rover", "landrover", "레인지로버", "디스커버리", "디펜더"), "랜드로버"),
    (("재규어", "jaguar"), "재규어"),
    (("포르쉐", "porsche", "카이엔", "파나메라", "마칸"), "포르쉐"),
    (("볼보", "volvo"), "볼보"),
    (("렉서스", "lexus"), "렉서스"),
    (("링컨", "lincoln"), "링컨"),
    (("지프", "jeep"), "지프"),
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
    s = ((court_maker or "") + " " + (car_nm or "")).lower()
    for kws, name in IMPORT_BRANDS:
        if any(k in s for k in kws):
            return name
    return None


def _benz_group(car_nm: str) -> Optional[str]:
    s = car_nm or ""; su = s.upper()
    for gl in ("GLC", "GLE", "GLA", "GLB", "GLS"):
        if gl in su:
            return gl + "-클래스"
    for cl in ("CLA", "CLS"):
        if cl in su:
            return cl
    if "마이바흐" in s or "MAYBACH" in su:
        return "S-클래스"
    m = re.search(r"\b([ABCESG])\s?-?\s?클래스", s) or re.search(r"\b([ABCESG])\d", su)
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
    return clean_model_group(car_nm)  # 아우디·포르쉐·랜드로버·렉서스 등은 첫 토큰이 대체로 일치


def auto_map(court_maker: Optional[str], car_nm: Optional[str],
             car_type: str = "Y") -> Optional[dict]:
    """법원 물건의 제조사·차명으로 엔카 매핑 자동 추정. 국산 우선, 이어서 수입."""
    mg = clean_model_group(car_nm)
    if not mg:
        return None
    # 1) 제네시스
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
    return None


def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Accept": "application/json",
        "Referer": "https://www.encar.com/",
        "Origin": "https://www.encar.com",
    })
    return s


def build_q(manufacturer: str, model_group: Optional[str] = None,
            car_type: str = "Y", year_from: Optional[int] = None,
            year_to: Optional[int] = None) -> str:
    """엔카 검색 쿼리 조립. year_from/to 는 YYYYMM(첫등록 기준)."""
    if model_group:
        maker_block = f"(C.Manufacturer.{manufacturer}._.ModelGroup.{model_group}.)"
    else:
        maker_block = f"Manufacturer.{manufacturer}."
    q = f"(And.Hidden.N._.(C.CarType.{car_type}._.{maker_block})"
    if year_from and year_to:
        q += f"_.Year.range({year_from}..{year_to})."
    q += ")"
    return q


def search(session: requests.Session, manufacturer: str,
           model_group: Optional[str] = None, car_type: str = "Y",
           year_from: Optional[int] = None, year_to: Optional[int] = None,
           limit: int = 100, offset: int = 0, premium: bool = False) -> dict:
    """동급 매물 목록 조회 (1회 호출). premium=True면 수입 엔드포인트 사용."""
    q = build_q(manufacturer, model_group, car_type, year_from, year_to)
    params = {"count": "true", "q": q, "sr": f"|ModifiedDate|{offset}|{limit}"}
    time.sleep(REQUEST_DELAY_SEC)
    r = session.get(API_PREMIUM if premium else API, params=params, timeout=25)
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
