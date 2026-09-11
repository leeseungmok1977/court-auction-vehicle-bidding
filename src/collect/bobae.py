"""보배드림 신차가격표 수집 — 연식별 등급 출시가격의 최저~최고 범위(출고가 근사).

실측 근거(2026-09-11, 사용자 캡처 URL + 페이지 자체 JS, 추측 없음 C.4-3):
  GET https://m.bobaedream.co.kr/calculator/carinfo?maker_no=&model_no=&level_no=&level2_no=&year_no=
  - 각 단계 <select id=maker_no|model_no|level_no|level2_no|year_no>의 옵션이 URL 파라미터만으로 서버 렌더됨
    (제조사 89 · 현대 모델 213 · 세부모델 · 등급 · 연식). 옵션은 value='ID' 작은따옴표.
  - 출시가격: <div class="price-area"><span>3,294 만원</span>  ← **연식별로 다름**(2020 3,294 / 2021 3,303)
  - 출시일:   <p class="title">출시일</p><p class="value"> 19.11~21.05</p>
  - robots.txt 404(제한 선언 없음). 약관 검토: docs/compliance-review.md.

C.4 준수: 모든 요청 전 5초 지연, 런당 요청 예산(Budget), 403/429 즉시 중단(RuntimeError '차단'),
원본 페이지 저장·재배포 없음 — 등급별 출시가 숫자만 집계해 출처와 함께 표기.
"""
from __future__ import annotations

import re
import time
from typing import Optional

import requests

BASE = "https://m.bobaedream.co.kr/calculator/carinfo"
UA = ("Mozilla/5.0 (Linux; Android 13; SM-S918N) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36")
REQUEST_DELAY_SEC = 5
# 경매 승용차 기준을 왜곡하는 영업용 세부모델/등급은 범위에서 제외(리포트 각주에 명시)
EXCLUDE_TOKENS = ("택시", "렌터카", "장애인", "영업용")


class BudgetExhausted(Exception):
    """런당 요청 예산 소진 — 다음 런에서 캐시를 딛고 이어간다."""


class Budget:
    def __init__(self, max_requests: int):
        self.max, self.used = int(max_requests), 0

    def take(self) -> None:
        if self.used >= self.max:
            raise BudgetExhausted(f"요청 예산 {self.max} 소진")
        self.used += 1


def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    return s


def fetch(session: requests.Session, budget: Budget, **params) -> str:
    """carinfo 1회 조회(예산 차감 → 지연 → 요청). 403/429는 즉시 중단(C.4-5)."""
    budget.take()
    time.sleep(REQUEST_DELAY_SEC)                     # C.4-2
    r = session.get(BASE, params={k: v for k, v in params.items() if v is not None}, timeout=25)
    if r.status_code in (403, 429):
        raise RuntimeError(f"보배드림 차단 상태코드 {r.status_code} — 중단")
    r.raise_for_status()
    return r.content.decode("utf-8", "replace")       # charset 헤더가 없어 .text는 깨짐


# ── 파서(정적, 네트워크 없음) ──────────────────────────────────────────────
_OPT = re.compile(r"<option([^>]*)>(.*?)</option>", re.S | re.I)


def parse_options(html: str, select_id: str) -> list:
    """<select id=..>의 (value, label, selected) 목록. 빈 value(자리표시자)는 제외."""
    m = re.search(r"<select[^>]*id=[\"']" + re.escape(select_id) + r"[\"'][^>]*>(.*?)</select>", html, re.S | re.I)
    out = []
    for attrs, text in (_OPT.findall(m.group(1)) if m else []):
        v = re.search(r"value=[\"']([^\"']*)[\"']", attrs)
        if v and v.group(1):
            out.append((v.group(1), re.sub(r"\s+", " ", text).strip(), "selected" in attrs.lower()))
    return out


def parse_price(html: str) -> Optional[int]:
    """출시가격(만원). 미표시/0이면 None."""
    m = re.search(r"price-area.*?<span>\s*([\d,]+)\s*만원", html, re.S)
    if not m:
        return None
    n = int(m.group(1).replace(",", ""))
    return n or None


def parse_release(html: str) -> Optional[str]:
    m = re.search(r"출시일\s*</p>\s*<p[^>]*class=[\"']value[\"'][^>]*>\s*([^<]+?)\s*<", html, re.S)
    return m.group(1).strip() if m else None


def is_excluded(name: str) -> bool:
    return any(t in (name or "") for t in EXCLUDE_TOKENS)


def norm(s: Optional[str]) -> str:
    return re.sub(r"[\s\[\]\(\)\-_/·]", "", (s or "")).lower()


def rank_model_candidates(models: list, gen_names: list, group: Optional[str]) -> list:
    """보배 모델 목록(no, name)에서 후보를 점수순으로.

    gen_names = 엔카 동급 매물의 세대명들(예: '더 뉴 그랜저 IG', '그랜저 IG'), group = 우리 모델그룹('그랜저').
    같은 이름이 여러 model_no로 존재할 수 있어(예: '더 뉴 그랜저'×2) 최종 확정은 연식 검증(수집 단계)에서 한다.
    models 는 **사이트 표시 순서(최신 세대 먼저)** 로 넘긴다 — 동점이면 그 순서를 따른다(가나다순은 구형을 앞세움).
    실측 교훈(카니발 2023): 세대명 '카니발 4세대'의 2023년식은 보배드림에서 '더 뉴 카니발 4세대'로 분리돼 있고,
    접두어 규칙은 '카니발'(1998)·'카니발2'(2001)를 우대해 79요청을 낭비했다 → 포함 관계만 쓰고 접두어 규칙은 폐기.
    """
    g = norm(group)
    gens = [norm(x) for x in gen_names if x]
    scored = []
    for idx, (no, name) in enumerate(models):
        n = norm(name)
        if g and g not in n:
            continue
        best = 0
        for ge in gens:
            if n == ge:
                best = max(best, 100)
            elif ge in n:                                  # 보배명이 세대명을 포함('더 뉴 카니발 4세대' ⊃ '카니발 4세대')
                best = max(best, 90 + len(ge))
            elif n in ge and n != g:                       # 세대명이 보배명을 포함('더 뉴 그랜저 IG' ⊃ '더 뉴 그랜저'), 그룹명 단독은 제외
                best = max(best, 80 + len(n))
        if not best:
            best = 10                                      # 그룹명만 일치 → 사이트 순서(최신 먼저)
        scored.append((-best, idx, no, name))
    scored.sort()
    return [(no, name) for _, _, no, name in scored]


# ── 목록 조회 ───────────────────────────────────────────────────────────────
def list_makers(session, budget) -> list:
    return [(v, t) for v, t, _ in parse_options(fetch(session, budget), "maker_no")]


def list_models(session, budget, maker_no) -> list:
    return [(v, t) for v, t, _ in parse_options(fetch(session, budget, maker_no=maker_no), "model_no")]


def list_levels(session, budget, maker_no, model_no) -> list:
    return [(v, t) for v, t, _ in parse_options(fetch(session, budget, maker_no=maker_no, model_no=model_no), "level_no")]


def list_grades(session, budget, maker_no, model_no, level_no) -> list:
    html = fetch(session, budget, maker_no=maker_no, model_no=model_no, level_no=level_no)
    return [(v, t) for v, t, _ in parse_options(html, "level2_no")]


def grade_page(session, budget, maker_no, model_no, level_no, level2_no, year_no=None) -> dict:
    """등급 페이지: 연식 목록·선택 연식·출시가격(만원)·출시일."""
    html = fetch(session, budget, maker_no=maker_no, model_no=model_no, level_no=level_no,
                 level2_no=level2_no, year_no=year_no)
    years = parse_options(html, "year_no")
    sel = next((v for v, _, s in years if s), (years[0][0] if years else None))
    return {"years": [v for v, _, _ in years], "selected_year": sel,
            "price_manwon": parse_price(html), "release": parse_release(html)}
