"""케이카(K Car) 2차 시세 소스 — Playwright 네트워크 인터셉션 방식.

엔카 단일 소스의 공통 편향(게시가 vs 실거래가, 동일 딜러망)을 걸러내기 위해
독립 2차 소스(케이카)의 동급 중앙값과 교차검증한다(→ market_match.cross_source_check).

**수집 방식(참조: github.com/gohard-lab/kcar_crawler)**: 케이카는 SPA로 검색 payload를
브라우저에서 암호화(enc)해 전송하므로 정적 재현이 불가하다. 대신 실제 브라우저를 구동하고
서버 응답 JSON(`**/search/list**`)을 중간에서 가로챈다. UI가 바뀌어도 견고하다.

**확정 스펙 출처**:
  - 엔드포인트/진입/응답구조/필드: 참조 repo 코드(공개) — `/search/list`, `data.rows[]`,
    `mnuftrNm`(브랜드)·`grdNm`/`carNm`(모델)·`mfgDt`/`mnfctYy`(연식)·`prc`(가격)
  - `carCd`(차량ID)·`api.kcar.com`·응답 래퍼: 본 프로젝트 발견 세션(kcar_probe) 실측
  - 주행거리·연료 키: repo 미추출 → 실제 `/search/list` 응답에서 **패턴 매칭**으로 잡고
    매칭된 키를 로깅(임의 지정 금지, C.4-3). `discover()`로 확인 가능.

**안전(C.4)**: 요청 전 5~10초 지연, 소량(기본 40건 1페이지), 차단 감지 시 중단.
실행은 사용자 환경(터미널)에서 이뤄진다(엔카와 동일 강행 승인).
"""

from __future__ import annotations

import re
import time
from typing import Optional

REQUEST_DELAY_SEC = 6          # C.4-2 (엔카와 동일 저속)
ENABLED = True                 # 사용자 승인(엔카와 동일). 실제 실행은 사용자 터미널.
LIST_URL_MARK = "/search/list"
SEARCH_PLACEHOLDER = "차량을 검색하세요."

# 실응답에서 확인/매칭된 키를 담아 로깅(데이터 신뢰 검증). discover()/normalize()가 채운다.
DISCOVERED_KEYS: dict = {}

# 필드 키(실측 확정 — run_kcar_discover.py 응답의 row_keys 기준). 변형 대비 후보 병기.
_ID_KEYS = ("carCd", "carCode", "carId")
_BRAND_KEYS = ("mnuftrNm", "brandNm", "makerNm")
# 모델은 그룹명(쏘렌토/토레스) 우선 — carNm은 실응답에 없음. grdNm은 트림이므로 모델 아님.
_MODEL_KEYS = ("modelGrpNm", "modelNm", "carWhlNm")
# 트림/등급 — 마이바흐·AMG 등 매칭용. 전체 차명(carWhlNm)이 트림 토큰을 가장 많이 포함.
_BADGE_KEYS = ("carWhlNm", "grdNm", "grdDtlNm")
_YEAR_KEYS = ("mfgDt", "prdcnYr", "mnfctYy", "yy", "carYy")
_PRICE_KEYS = ("prc", "sellAmt", "salePrc", "price", "amt")
_MILEAGE_PAT = re.compile(r"(milg|mlge|mileage|travl|trvl|dstnc|driv|주행)", re.I)
_FUEL_PAT = re.compile(r"(fuel|gas|yuel|yunl|ftype|연료|oil)", re.I)
_FUEL_WORDS = ("가솔린", "디젤", "하이브리드", "전기", "LPG", "수소", "가스")


def _digits(v) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = re.sub(r"[^\d]", "", str(v))
    return int(s) if s else None


def _first(row: dict, keys) -> Optional[object]:
    for k in keys:
        if k in row and row[k] not in (None, "", "-"):
            return row[k]
    return None


def _year_from(v) -> Optional[int]:
    """'202206'/'2022'/'2022-06'/'20220601' → 2022 (연식 4자리)."""
    d = _digits(v)
    if d is None:
        return None
    s = str(d)
    if len(s) >= 4 and s[:4].isdigit():
        y = int(s[:4])
        if 1990 <= y <= 2100:
            return y
    return None


def _price_won(v) -> Optional[int]:
    """케이카 가격 → 원. 값이 만원 단위(<100000)면 ×10000로 환산(휴리스틱, 로깅)."""
    d = _digits(v)
    if d is None or d <= 0:
        return None
    if d < 100000:                 # 자동차가는 원 단위면 >=100만 — 만원 단위로 판단
        DISCOVERED_KEYS["price_unit"] = "만원(×10000 적용)"
        return d * 10000
    DISCOVERED_KEYS["price_unit"] = "원"
    return d


def _find_mileage(row: dict) -> Optional[int]:
    """주행거리 → km 정수. ① 확정 키(milg) 우선 → ② 패턴 매칭. 매칭 키 로깅."""
    for k in ("milg", "mileage", "mlge"):        # 실측 확정 키 우선
        if k in row:
            km = _digits(row[k])
            if km is not None and 0 <= km <= 2_000_000:
                DISCOVERED_KEYS["mileage_key"] = k
                return km
    for k, v in row.items():                       # 변형 대비 패턴 매칭
        if _MILEAGE_PAT.search(k):
            km = _digits(v)
            if km is not None and 0 <= km <= 2_000_000:
                DISCOVERED_KEYS["mileage_key"] = k
                return km
    return None


def _find_fuel(row: dict) -> Optional[str]:
    """연료 '이름' 탐색. ① fuelNm 등 이름 키 우선 → ② 패턴(단 코드키 fuelCd 제외) → ③ 값에서 단어.

    실측: fuelCd="001"(코드), fuelNm="가솔린"(이름). 매칭엔 사람이 읽는 이름이 필요하므로
    코드 키(…Cd/…Code)는 건너뛴다. 트림/등급명(예: '2.2 디젤 시그니처')에 연료어가
    섞인 경우 값 스캔은 매칭 단어만 반환한다(오염 방지)."""
    for k in ("fuelNm", "fuelName", "fuelKindNm"):        # 이름 전용 키 우선
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            DISCOVERED_KEYS["fuel_key"] = k
            return v.strip()
    for k, v in row.items():                                # 패턴 매칭(코드 키 제외)
        if (_FUEL_PAT.search(k) and not k.lower().endswith(("cd", "code"))
                and isinstance(v, str) and v.strip()):
            DISCOVERED_KEYS["fuel_key"] = k
            return v.strip()
    for k, v in row.items():                                # 값에서 연료 단어 추출
        if isinstance(v, str):
            for w in _FUEL_WORDS:
                if w in v:
                    DISCOVERED_KEYS["fuel_key"] = k
                    return w
    return None


def normalize(results: list) -> list:
    """케이카 원행(rows) → 공통 매물 스키마 (엔카 normalize와 동일 형태)."""
    out = []
    for row in results or []:
        if not isinstance(row, dict):
            continue
        price = _price_won(_first(row, _PRICE_KEYS))
        if price is None:
            continue
        brand = _first(row, _BRAND_KEYS)
        model = _first(row, _MODEL_KEYS)
        badge = _first(row, _BADGE_KEYS)
        out.append({
            "platform": "kcar",
            "form_year": _year_from(_first(row, _YEAR_KEYS)),
            "mileage_km": _find_mileage(row),
            "price_won": price,
            "model": (str(model).strip() if model else (str(brand).strip() if brand else None)),
            "badge": (str(badge).strip() if badge else None),
            "fuel": _find_fuel(row),
            "id": _first(row, _ID_KEYS),
        })
    return out


def _find_car_list(obj, depth: int = 0):
    """응답 어디에 있든 '매물 배열'(carCd를 가진 dict 리스트)을 재귀로 찾는다.
    통합검색 등 엔드포인트마다 중첩 구조가 달라도 견고하게 매물을 잡기 위함."""
    if depth > 6:
        return None
    if (isinstance(obj, list) and obj and isinstance(obj[0], dict)
            and "carCd" in obj[0]):
        return obj
    if isinstance(obj, dict):
        for key in ("rows", "list", "carList", "items", "result", "cars"):
            v = obj.get(key)
            if isinstance(v, list) and v and isinstance(v[0], dict) and "carCd" in v[0]:
                return v
        for v in obj.values():
            r = _find_car_list(v, depth + 1)
            if r:
                return r
    return None


def _extract_rows(body) -> list:
    """응답 래퍼에서 매물 배열(carCd 보유)을 재귀 탐색. 없으면 data 하위 첫 리스트."""
    rows = _find_car_list(body)
    if rows:
        return rows
    if isinstance(body, dict):
        data = body.get("data", body)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("rows", "list", "carList", "items", "result"):
                if isinstance(data.get(key), list):
                    return data[key]
    return body if isinstance(body, list) else []


class KcarSession:
    """Playwright 브라우저 1개를 유지하며 여러 검색을 재사용(효율)."""

    def __init__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(channel="chrome")
        self._page = self._browser.new_page(viewport={"width": 1400, "height": 900})
        self._last = 0.0

    def _throttle(self):
        wait = REQUEST_DELAY_SEC - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def close(self):
        try:
            self._browser.close()
        finally:
            self._pw.stop()


def new_session() -> KcarSession:
    if not ENABLED:
        raise RuntimeError("kcar.ENABLED=False — 케이카 수집 비활성")
    return KcarSession()


def _priced_count(rows: list) -> int:
    """가격(prc 등)이 실제로 있는 행 수 — 판매목록 vs '준비중(PREPARE)' 위젯 구분용."""
    return sum(1 for r in rows if isinstance(r, dict) and _digits(_first(r, _PRICE_KEYS)))


def _model_of(row: dict) -> str:
    m = _first(row, _MODEL_KEYS) or _first(row, _BADGE_KEYS) or ""
    return str(m)


def _kw_match(rows: list, keyword: str) -> int:
    """키워드 토큰 중 하나라도 모델/차명에 포함된 행 수(키워드 필터 목록 판별용)."""
    toks = [t for t in (keyword or "").split() if t]
    if not toks:
        return 0
    n = 0
    for r in rows:
        if isinstance(r, dict):
            name = _model_of(r) + " " + str(_first(r, _BADGE_KEYS) or "")
            if any(t in name for t in toks):
                n += 1
    return n


def _gen_year_range(text: str) -> tuple:
    """자동완성 세대 텍스트의 연식 범위. '20년~23년'→(2020,2023), '23년~'→(2023,9999)."""
    def y4(v):
        v = int(v)
        return 2000 + v if v <= 79 else 1900 + v
    ys = [y4(x) for x in re.findall(r"(\d{2})\s*년", text)]
    if not ys:
        return (0, 9999)
    lo = ys[0]
    hi = ys[1] if len(ys) >= 2 else 9999
    return (lo, hi)


def _pick_generation(cands: list, year: Optional[int], hybrid: bool) -> Optional[int]:
    """세대 후보[(li_index, text)]에서 물건 연식·하이브리드 여부에 맞는 세대를 고른다."""
    # ① 연식 범위 포함 + 하이브리드 일치
    for i, t in cands:
        lo, hi = _gen_year_range(t)
        if year is not None and not (lo <= year <= hi):
            continue
        if hybrid != ("하이브리드" in t):
            continue
        return i
    # ② 연식 범위만 포함(하이브리드 무관)
    for i, t in cands:
        lo, hi = _gen_year_range(t)
        if year is None or (lo <= year <= hi):
            return i
    # ③ 첫 후보
    return cands[0][0] if cands else None


def search(session: "KcarSession", keyword: str, limit: int = 40,
           year: Optional[int] = None, hybrid: bool = False) -> dict:
    """케이카 검색 → 자동완성에서 **세대별 모델 항목**을 선택해 모델 필터 목록(/drct)을 띄우고
    그 응답을 가로챈다. year가 있으면 연식 범위가 맞는 세대를 골라 세대까지 매칭한다.

    반환: {"count","results","priced","kw_match","reached","final_url","variants"}. 차단 시 예외.
    """
    if not keyword or not keyword.strip():
        return {"count": 0, "results": [], "priced": 0, "kw_match": 0,
                "reached": False, "final_url": None, "variants": []}
    keyword = keyword.strip()
    session._throttle()
    page = session._page
    responses = []
    blocked = []

    def on_resp(resp):
        try:
            if "kcar.com" in resp.url and resp.status in (403, 429):   # C.4-5 차단 감지
                blocked.append(resp.status)
                return
            # 통합검색 매물 그리드는 /search/list가 아닌 다른 엔드포인트로 올 수 있으므로,
            # api.kcar.com JSON 응답 중 carCd를 가진 매물 배열이 있으면 모두 후보로 수집.
            # (광고/랭킹/찜 응답도 carCd가 있으나, 아래 선택이 '키워드매칭 우선'이라 자동 배제)
            if "api.kcar.com" in resp.url and "json" in (resp.headers.get("content-type") or "").lower():
                rows = _find_car_list(resp.json())
                if rows:
                    responses.append({"url": resp.url, "rows": rows})
        except Exception:
            pass

    page.on("response", on_resp)
    final_url = None
    try:
        page.goto("https://www.kcar.com", wait_until="domcontentloaded", timeout=30000)
        box = page.get_by_placeholder(SEARCH_PLACEHOLDER)
        box.wait_for(timeout=15000)
        responses.clear()                       # 검색 전 홈 위젯 제외
        # 자동완성 트리거 토큰: 한글 모델명 우선(국산은 브랜드 뒤 모델이 한글),
        # 한글이 없으면 첫 토큰(수입차는 모델이 앞: A7·E220·528i 등)
        toks = keyword.split()
        def _hangul(s):
            return sum(1 for c in s if "가" <= c <= "힣")
        kor = [t for t in toks if _hangul(t) > 0]
        fill_tok = max(kor, key=_hangul) if kor else (toks[0] if toks else keyword)
        box.click()
        box.fill(fill_tok)
        page.wait_for_timeout(2600)             # 자동완성 렌더 대기
        # 자동완성의 '세대별 모델' li(예: '쏘렌토 4세대 20년~23년')를 연식에 맞춰 선택 →
        # 모델+세대 필터 목록(/bc/search/list/drct) 트리거. (Enter는 통합검색=무필터라 부적합)
        selected = False
        try:
            texts = page.locator("li").evaluate_all(
                "els => els.map(e => (e.innerText||'').trim())")
            # 세대 항목만: 연식 패턴(\\d{2}년) + 키워드 토큰 공유 + 짧은 텍스트
            cands = [(i, t) for i, t in enumerate(texts)
                     if len(t) < 70 and re.search(r"\d{2}\s*년", t)
                     and any(tok in t for tok in toks)]
            idx = _pick_generation(cands, year, hybrid)
            if idx is not None:
                page.locator("li").nth(idx).click(timeout=3000)
                selected = True
        except Exception:
            pass
        if not selected:                        # 세대 항목 못 찾으면 Enter(통합검색) 폴백
            try:
                box.press("Enter")
            except Exception:
                pass
        try:                                     # 결과/필터 목록 로딩 대기
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(1500)
        try:                                     # 지연 로딩·다음 페이지 유도(사용자 실행, 분류기 무관)
            page.mouse.wheel(0, 2600)
            page.wait_for_timeout(1200)
            page.mouse.wheel(0, 2600)
            page.wait_for_timeout(1800)
        except Exception:
            pass
        final_url = page.url
        # CAPTCHA/차단 인터스티셜 감지(C.4-5). 단, reCAPTCHA v3 배지(거의 모든 페이지 상존)
        # 오탐 방지 — 매물 데이터를 하나도 못 받았을 때만 + 실제 차단 문구가 있을 때만 판정.
        if not responses:
            try:
                html = page.content() or ""
                markers = ("보안문자를 입력", "비정상적인 접근", "접근이 차단",
                           "unusual traffic", "자동입력 방지문자를 입력")
                if any(m in html for m in markers):
                    blocked.append("captcha")
            except Exception:
                pass
    finally:
        page.remove_listener("response", on_resp)

    if blocked:   # 403/429/CAPTCHA → 즉시 중단·전파(엔카와 동일, C.4-5)
        raise RuntimeError(f"케이카 차단 감지({blocked[0]}) — 수집 중단(C.4-5)")

    # 후보에서 준비중(rdy/PREPARE) 위젯 제외 → 가격없는 위젯이 판매목록으로 오선택되지 않게
    candidates = [r for r in responses if "/rdy" not in r["url"]]
    # 선택 우선순위: ① 키워드 매칭 행 최다 → ② 가격 있는 행 최다 → ③ 전체 행 최다
    best = max(candidates,
               key=lambda x: (_kw_match(x["rows"], keyword), _priced_count(x["rows"]), len(x["rows"])),
               default=None)
    rows = best["rows"] if best else []
    priced = _priced_count(rows)
    reached = priced > 0            # 가격 있는 판매목록에 실제 도달했는가(검색실패/미도달 구분)
    if rows and isinstance(rows[0], dict):
        DISCOVERED_KEYS["list_url"] = best["url"]
        DISCOVERED_KEYS["row_keys"] = sorted(rows[0].keys())
    DISCOVERED_KEYS["final_url"] = final_url
    variants = [{"url": r["url"], "rows": len(r["rows"]), "priced": _priced_count(r["rows"]),
                 "kw_match": _kw_match(r["rows"], keyword)} for r in responses]
    return {"count": len(rows), "results": rows[:limit], "priced": priced,
            "kw_match": _kw_match(rows, keyword), "reached": reached,
            "final_url": final_url, "variants": variants}


def discover_autocomplete(keyword: str = "쏘렌토") -> list:
    """[사용자 실행] 검색창에 키워드를 입력한 뒤 뜨는 **자동완성 드롭다운의 클릭 요소**를
    덤프한다. 어떤 요소를 눌러야 모델 필터(/drct)가 걸리는지 셀렉터를 확정하기 위함.

    실행:  python run_kcar_discover.py --dom 쏘렌토
    """
    from playwright.sync_api import sync_playwright
    tok = max(keyword.split(), key=len) if keyword.split() else keyword
    js = r"""(kw) => {
      const out = [];
      const els = document.querySelectorAll('a,li,button,[role=option],[class*=result],[class*=auto],[class*=sch],[class*=srch],[class*=layer]');
      for (const el of els) {
        const t = (el.innerText||'').trim();
        if (t && t.includes(kw) && t.length < 70 && el.offsetParent !== null) {
          out.push({tag: el.tagName, cls: (el.className||'').toString().slice(0,60),
                    href: el.getAttribute('href')||'', role: el.getAttribute('role')||'',
                    dataset: JSON.stringify(el.dataset||{}).slice(0,80), text: t.replace(/\s+/g,' ').slice(0,55)});
        }
      }
      return out.slice(0, 30);
    }"""
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=False)
        pg = b.new_page(viewport={"width": 1400, "height": 950})
        try:
            pg.goto("https://www.kcar.com", wait_until="domcontentloaded", timeout=30000)
            box = pg.get_by_placeholder(SEARCH_PLACEHOLDER)
            box.wait_for(timeout=15000)
            box.click()
            box.fill(keyword)
            pg.wait_for_timeout(2800)          # 자동완성 렌더
            cands = pg.evaluate(js, tok)
        finally:
            b.close()
    print(f"=== 자동완성 클릭 후보('{tok}' 포함, 보이는 요소) {len(cands)}개 ===")
    for i, c in enumerate(cands):
        print(f"[{i}] <{c['tag'].lower()}> text='{c['text']}'")
        print(f"     class='{c['cls']}' href='{c['href']}' role='{c['role']}' data={c['dataset']}")
    if not cands:
        print("(후보 없음 — 자동완성이 안 떴거나 구조가 다름. --manual 로 직접 필터해 주세요)")
    print("\n※ 위 목록에서 '모델 쏘렌토'로 보이는 항목의 번호/class/href 를 알려주시면 정확한 셀렉터로 클릭하게 합니다.")
    return cands


def discover_manual(keyword: str = "쏘렌토", wait_sec: int = 90) -> list:
    """[사용자 실행] 보이는 브라우저로 **직접** 모델 필터 매물목록까지 이동 → 그 실제
    요청/응답(엔드포인트·파라미터)을 기록한다. 자유검색이 모델 필터를 안 하므로,
    실제 필터 API를 추측 없이(C.4-3) 확인하기 위함.

    실행:  python run_kcar_discover.py --manual 쏘렌토
    브라우저가 열리면 kcar에서 **제조사→모델(예: 기아→쏘렌토)** 필터를 눌러 매물목록을
    띄운다. wait_sec초간 요청을 기록한 뒤 결과(키워드매칭>0인 요청=모델필터)를 출력한다.
    """
    from playwright.sync_api import sync_playwright
    captured = []
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=False)
        pg = b.new_page(viewport={"width": 1400, "height": 950})

        def on_resp(resp):
            try:
                if "api.kcar.com" in resp.url and "json" in (resp.headers.get("content-type") or "").lower():
                    rows = _find_car_list(resp.json())
                    if rows:
                        captured.append({
                            "url": resp.url, "method": resp.request.method,
                            "post": (resp.request.post_data or "")[:600],
                            "rows": len(rows), "priced": _priced_count(rows),
                            "kw": _kw_match(rows, keyword),
                            "sample_model": _model_of(rows[0]) if rows else ""})
            except Exception:
                pass

        pg.on("response", on_resp)
        try:
            pg.goto("https://www.kcar.com/bc/search", wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass
        print(f"\n>>> 브라우저가 열렸습니다. kcar에서 직접 '{keyword}' 매물목록으로 이동하세요.")
        print(">>> (제조사→모델 필터 클릭, 또는 검색 후 모델 선택). 매물 그리드가 보이게 하세요.")
        print(f">>> {wait_sec}초간 요청을 기록합니다. 그동안 다른 모델도 눌러보셔도 됩니다...\n")
        pg.wait_for_timeout(wait_sec * 1000)
        b.close()

    # 키워드매칭 > 0 = 모델 필터가 걸린 실제 매물 요청
    hits = [c for c in captured if c["kw"] > 0]
    print("=== 기록된 매물 API 요청(중복 URL 병합) ===")
    seen = set()
    for c in sorted(captured, key=lambda x: -x["kw"]):
        base = c["url"].split("?")[0] + "|" + str(c["kw"])
        if base in seen:
            continue
        seen.add(base)
        flag = "   ★모델필터로 보임" if c["kw"] > 0 else ""
        print(f"\n{c['method']} {c['url'][:180]}{flag}")
        if c["post"]:
            print(f"    POST body: {c['post']}")
        print(f"    행 {c['rows']} · 가격보유 {c['priced']} · 키워드매칭 {c['kw']} · 예시모델 {c['sample_model']}")
    if not hits:
        print("\n(키워드매칭 요청 없음 — 모델 필터 목록까지 도달했는지, 검색어와 모델이 맞는지 확인)")
    print("\n※ ★ 표시된 요청의 URL 전체(쿼리 포함) 또는 POST body를 붙여주시면 필터 API를 확정합니다.")
    return captured


def discover(keyword: str = "쏘렌토") -> dict:
    """[사용자 실행용] 실제 `/search/list` 응답의 엔드포인트·필드를 확인(발견용, 1회).

    사용자 터미널에서 실행 → 매칭된 키/샘플을 출력. 이 결과로 normalize 필드매핑을 검증한다.
    """
    import json
    s = new_session()
    try:
        res = search(s, keyword, limit=5)
    finally:
        s.close()
    norm = normalize(res["results"])
    print("final_url(검색 후 페이지):", res.get("final_url"))
    print("\n=== /search/list* 응답 목록(검색 이후) ===")
    for v in res.get("variants", []):
        flag = "  ← 선택" if v["url"] == DISCOVERED_KEYS.get("list_url") else ""
        print(f"  {v['url']}  · 행 {v['rows']} · 가격보유 {v['priced']} · 키워드매칭 {v.get('kw_match', '?')}{flag}")
    print("\nlist_url    :", DISCOVERED_KEYS.get("list_url"))
    print("row_keys    :", DISCOVERED_KEYS.get("row_keys"))
    print("mileage_key :", DISCOVERED_KEYS.get("mileage_key"))
    print("fuel_key    :", DISCOVERED_KEYS.get("fuel_key"))
    print("price_unit  :", DISCOVERED_KEYS.get("price_unit"))
    print("선택 목록 행수:", res["count"], "· 가격보유:", res.get("priced"),
          "· 판매목록도달:", res.get("reached"))
    if res["results"]:
        print("\n첫 원행(raw):")
        print(json.dumps(res["results"][0], ensure_ascii=False, indent=1)[:1500])
    print("\n정규화 결과(normalize) — 상위 5건:")
    for n in norm[:5]:
        print(" ", n)
    if not norm:
        print("  (가격 있는 매물 없음 — variants에서 '가격보유'>0 인 목록이 있는지 확인)")
    return {"raw": res, "normalized": norm, "keys": dict(DISCOVERED_KEYS)}
