# -*- coding: utf-8 -*-
"""정규화 제조사명 → 브랜드 로고(web/static/brands/{slug}.svg) 매핑.
로고 미보유 브랜드는 이니셜+색상 배지로 폴백(오프라인 안전·CDN 미사용)."""

# simple-icons 기반 로컬 SVG 보유 브랜드
BRAND_SLUG = {
    "현대": "hyundai", "기아": "kia", "BMW": "bmw", "벤츠": "mercedes",
    "쉐보레(GM대우)": "chevrolet", "볼보": "volvo", "아우디": "audi",
    "포르쉐": "porsche", "포드": "ford", "닛산": "nissan", "시트로엥": "citroen",
    "푸조": "peugeot", "르노삼성": "renault", "르노코리아": "renault", "르노": "renault",
    "미니": "mini", "폭스바겐": "volkswagen", "스카니아": "scania", "MAN": "man",
    "토요타": "toyota", "혼다": "honda", "지프": "jeep", "테슬라": "tesla",
}

# 로고 미보유 → 이니셜+색상 폴백
BRAND_FALLBACK = {
    "KG모빌리티(쌍용)": ("KG", "#8b0000"),
    "랜드로버": ("LR", "#2e5e3f"),
    "레인지로버": ("RR", "#2e5e3f"),
    "재규어": ("JAG", "#1a1a1a"),
    "제네시스": ("G", "#1a1a1a"),
    "렉서스": ("LEX", "#1a1a1a"),
}


def brand_asset(maker: str) -> dict:
    """{'logo': path|None, 'initial': str|None, 'color': str|None}."""
    slug = BRAND_SLUG.get(maker)
    if slug:
        return {"logo": f"/static/brands/{slug}.svg", "initial": None, "color": None}
    fb = BRAND_FALLBACK.get(maker)
    if fb:
        return {"logo": None, "initial": fb[0], "color": fb[1]}
    # 기타(트럭·건설기계·수입차 등): 앞 두 글자 이니셜
    return {"logo": None, "initial": (maker[:2] if maker else "?"), "color": "#64748b"}
