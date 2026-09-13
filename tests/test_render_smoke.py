"""모든 판정 상태에서 상세·리포트가 실제로 렌더되는지 — 템플릿 500 방지.

2026-09-12 4회차: 전략 밴드에 `backtest.pred_n`을 참조했는데 그 변수는 리포트
컨텍스트에만 있었다. 결과는 **전략 밴드가 렌더되는 모든 상세가 HTTP 500** —
홈 추천 1번, 실사용 추천 1·2·3번이 전부 죽었다. 살아 있는 페이지는 "입찰하지
마세요"뿐이라, 이 앱이 하겠다고 한 단 하나의 일이 되는 물건만 골라서 죽은 셈이다.

기존 테스트가 못 잡은 이유는 픽스처의 backtest 표본이 비어 `win_probability`가
None을 돌려주고 템플릿이 **else 분기만** 탔기 때문이다. 그래서 이 파일은
**분기별 픽스처를 명시적으로 만들어** 전 상태를 한 번씩 렌더한다.
"""
import pytest
from starlette.testclient import TestClient

from web import service

BT = {"discount_median": 0.74, "mae_pct": 9.2, "sample": 172, "within10_pct": 62,
      "within20_pct": 96, "pred_n": 135, "won_total": 172,
      "min_premium_median": 1.13, "min_premium_by_fail": {"0": 1.20, "1": 1.13, "2+": 1.06},
      "min_premium_p25": 1.05, "min_premium_p75": 1.22,
      "min_premium_pool": [round(1.00 + i * 0.004, 4) for i in range(60)],
      "discount_p25": 0.62, "discount_p75": 0.86, "discount_by_fail": {},
      "discount_by_model": {}, "upper_hit_rate": None, "upper_n": 0,
      "actual_mae_pct": None, "actual_sample": 0, "mae_baseline_pct": 12.0,
      "history_n": 0, "model_learned": False, "pred_n2": 0, "pred_pool": [], "comp_pool": []}

_BASE = {"court": "수원지방법원", "maker": "현대", "model": "쏘나타", "year": 2020,
         "item_no": "1", "sale_date": "2999-01-01", "status": "완료", "fail_count": 1,
         "market_confidence": 78, "market_confidence_label": "높음", "sample_count": 12,
         "photo_count": 3}

# 상태 → 그 상태를 실제로 만들어내는 필드. 하나라도 렌더가 깨지면 실패한다.
CASES = {
    "resale":      dict(min_sale_price=10_000_000, appraisal_value=12_000_000,
                        median_price=13_000_000, upper_bid=14_000_000),
    "usepick":     dict(min_sale_price=28_000_000, appraisal_value=30_000_000,
                        median_price=40_000_000),
    "over_market": dict(min_sale_price=14_000_000, appraisal_value=16_000_000,
                        median_price=16_600_000),
    "blocked":     dict(min_sale_price=16_000_000, appraisal_value=20_000_000,
                        median_price=16_600_000),
    "flood":       dict(min_sale_price=9_000_000, appraisal_value=12_000_000,
                        median_price=13_000_000, accident_grade="flood",
                        judgment="입찰 보류"),
    "lowconf":     dict(min_sale_price=9_000_000, appraisal_value=12_000_000,
                        median_price=13_000_000, market_confidence_label="낮음",
                        market_confidence=31),
    "no_market":   dict(min_sale_price=9_000_000, appraisal_value=12_000_000,
                        median_price=None),
    "stale_floor": dict(min_sale_price=20_000_000, appraisal_value=20_000_000,
                        median_price=18_000_000),
    "past_date":   dict(min_sale_price=10_000_000, appraisal_value=12_000_000,
                        median_price=15_000_000, sale_date="2020-01-01"),
    "not_runnable": dict(min_sale_price=10_000_000, appraisal_value=12_000_000,
                         median_price=15_000_000, runnable="no"),
    "accident_many": dict(min_sale_price=10_000_000, appraisal_value=12_000_000,
                          median_price=15_000_000, accident_grade="accident",
                          insurance_history={"own_damage": 8, "opp_damage": 5}),
    "kcar_blend":  dict(min_sale_price=9_000_000, appraisal_value=11_000_000,
                        median_price=9_670_000, kcar_median=13_000_000, kcar_sample=9),
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "smoke.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    for i, (name, extra) in enumerate(CASES.items()):
        db.upsert_vehicle({**_BASE, "id": f"{name}_1", "folder_key": f"{name}_1",
                           "case_no": f"2026타경9{i:03d}", "judgment": "유찰 대기", **extra})
    import web.app as A
    return TestClient(A.app)


_PUB = {"x-forwarded-for": "203.0.113.7"}
_TUNNEL = {"host": "127.0.0.1"}


@pytest.mark.parametrize("name", list(CASES))
@pytest.mark.parametrize("suffix", ["", "/report"])
def test_detail_and_report_render(client, name, suffix):
    r = client.get(f"/vehicle/{name}_1{suffix}", headers=_PUB)
    assert r.status_code == 200, f"{name}{suffix} → {r.status_code}"
    assert "Traceback" not in r.text


@pytest.mark.parametrize("name", list(CASES))
def test_admin_view_renders_too(client, name):
    """관리자 화면은 가려진 블록이 더 많아 별도로 렌더해야 한다."""
    r = client.get(f"/vehicle/{name}_1", headers=_TUNNEL)
    assert r.status_code == 200, f"{name}(admin) → {r.status_code}"


@pytest.mark.parametrize("path", [
    "/", "/vehicles", "/vehicles?usepick=1", "/vehicles?bucket=wait",
    "/vehicles?sort=expected", "/calendar", "/courts", "/accuracy", "/watchlist",
    "/landing", "/privacy",
])
def test_all_pages_render(client, path):
    r = client.get(path, headers=_PUB)
    assert r.status_code == 200, f"{path} → {r.status_code}"


def test_every_case_actually_hits_its_state(client):
    """픽스처가 의도한 상태를 실제로 만드는지 — 아니면 이 파일 전체가 공허하다."""
    from web import db
    got = {n: service.bid_state(db.get_vehicle(f"{n}_1"), BT)["state"] for n in CASES}
    assert got["blocked"] == "blocked", got
    assert got["usepick"] in ("usepick", "resale"), got
    assert got["flood"] == "blocked", got
    assert got["lowconf"] == "lowconf", got
    assert got["past_date"] == "wait", got
    assert len(set(got.values())) >= 4, f"상태가 너무 몰려 있다: {got}"


def test_probability_branch_is_actually_rendered(client):
    """'낙찰 확률' 분기가 실제로 렌더돼야 이 파일이 500을 잡는다.

    4회차에 바로 이 분기가 렌더된 적이 없어 프로덕션 500이 나갔다."""
    html = client.get("/vehicle/usepick_1", headers=_PUB).text
    assert "낙찰 확률" in html, "확률 분기가 렌더되지 않아 500을 못 잡는다"


# ── 한글에 monospace를 걸지 않는다 (5회차 디자인 P0) ──────────────
# JetBrains Mono에는 한글 글리프가 없다. 한글이 들어간 요소에 mono를 걸면
# 글자마다 폴백이 일어나 "소 매 로  사 는  편 이  쌉 니 다"로 자간이 벌어진다.
# 큰글씨 모드에서 가장 심했다 — 접근성 옵션이 접근성을 떨어뜨렸다.
# CSS 계산값은 브라우저가 필요하므로, 여기서는 **템플릿 소스**에서 잡는다.
import pathlib
import re as _re

_TPL = pathlib.Path(__file__).resolve().parents[1] / "web" / "templates"
_HANGUL = _re.compile(r"[가-힣]")


# 한글을 담을 수 있는 변수들 — 런타임에 mono 안으로 들어가면 자간이 벌어진다
_HANGUL_VARS = ("case_no", "court", "model", "maker", "judgment", "sale_place",
                "storage_addr", "label")
_MONO_TAG = _re.compile(r"<(\w+)([^>]*?(?:font-mono|var\(--mono\))[^>]*?)>", _re.S)
_JINJA = _re.compile(r"\{\{.*?\}\}|\{%.*?%\}", _re.S)


def _mono_elements_with_hangul(path: pathlib.Path):
    """mono가 걸린 **그 요소 안**에 한글(리터럴 또는 한글 변수)이 있는지.

    요소 밖의 한글까지 세면 오탐이 쏟아진다(숫자 옆 '건'·'원' 라벨 등).
    여는 태그부터 다음 태그 시작까지의 직계 텍스트만 본다.
    """
    src = path.read_text(encoding="utf-8")
    bad = []
    for m in _MONO_TAG.finditer(src):
        inner = src[m.end():].split("<", 1)[0]
        line = src[:m.start()].count(chr(10)) + 1
        literal = _JINJA.sub("", inner)
        if _HANGUL.search(literal):
            bad.append((line, "리터럴 한글: " + literal.strip()[:40]))
            continue
        for var in _HANGUL_VARS:
            if _re.search(r"\{\{[^}]*\b" + var + r"\b", inner):
                bad.append((line, "한글 변수 " + var))
                break
    return bad

def test_case_number_is_not_monospaced():
    """사건번호는 '2026타경'이라 한글이 섞인다 — mono면 '2026타 경 30903'이 된다."""
    for f in sorted(_TPL.glob("*.html")):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if "case_no" not in line:
                continue
            if "font-mono" in line:
                raise AssertionError(f"{f.name}:{i} 사건번호에 font-mono가 걸렸다")


def test_no_multichar_hangul_inside_monospace():
    """mono 요소 안에 한글 단어가 들어가면 안 된다.

    ⚠ 이 파일에는 `_mono_elements_with_hangul()`이 **정의만 되어 있고 어떤
    테스트도 쓰지 않았다.** 그래서 상세의
    `<div class="text-xl font-semibold font-mono">산정 상한가(재판매) …</div>`
    가 그대로 배포됐고, 화면에 "산정  상한가(재판매)"로 자간이 벌어졌다.
    헬퍼를 만들어놓고 연결하지 않은 것이 원인이라, 여기서 연결한다.

    단위 한 글자(원·회·건·대)는 허용한다 — mono 스택에 Pretendard가 있어
    일관되게 폴백하고, 숫자 뒤 한 글자는 자간 붕괴로 읽히지 않는다.
    """
    offenders = []
    for f in sorted(_TPL.glob("*.html")):
        for line, why in _mono_elements_with_hangul(f):
            if why.startswith("리터럴 한글: "):
                literal = why[len("리터럴 한글: "):]
                if len(_HANGUL.findall(literal)) <= 1:
                    continue
            offenders.append(f"{f.name}:{line} {why}")
    assert not offenders, (
        "mono 안에 한글 단어가 있다 (라벨은 sans, 숫자만 mono로 분리하라):\n  "
        + "\n  ".join(offenders))


def test_report_scroll_hint_is_actually_in_the_markup():
    """CSS에만 있고 마크업에 없는 클래스 = 죽은 규칙.

    실측: 표 가로 스크롤 안내(.scroll-hint)를 CSS에 3번 정의해놓고 **마크업에는
    하나도 넣지 않았다.** `.tscroll + .scroll-hint{display:block}` 이 영영 발동하지
    않아, 사용자에게는 '밀 수 있다'는 안내가 끝내 안 보였다. 디자인 검수가 잡았다.
    """
    src = (_TPL / "report.html").read_text(encoding="utf-8")
    # ⚠ 이 템플릿에는 <style> 블록이 둘이다(base 미상속 단독 문서라 CSS를 복제해 쓴다).
    #   첫 블록만 보면 규칙을 못 찾아 멀쩡한 마크업을 실패로 판정한다 — 실제로 그랬다.
    styles = "".join(_re.findall(r"<style>(.*?)</style>", src, _re.S))
    body = _re.sub(r"<style>.*?</style>", "", src, flags=_re.S)
    assert ".scroll-hint" in styles, "CSS 규칙이 사라졌다"
    assert 'class="scroll-hint"' in body, "CSS만 있고 쓰는 곳이 없다(죽은 규칙)"
    # 가려진 열 이름을 적어야 '무엇이 더 있는지'를 알 수 있다
    assert body.count('class="scroll-hint"') >= 3, "넘치는 표 3개에 모두 붙어야 한다"


def test_report_print_does_not_rely_on_background_graphics():
    """크롬 인쇄의 '배경 그래픽'은 기본 해제다.

    마스트헤드가 남색 배경 + 흰 글자라, 배경을 끄고 뽑으면 **차량명·사건번호가
    백지에 흰 글자로 인쇄**된다. 의뢰인에게 내는 서면의 첫 페이지가 통째로 빈다.
    """
    src = (_TPL / "report.html").read_text(encoding="utf-8")
    pr = src[src.rindex("@media print{"):]
    assert ".masthead" in pr, "인쇄 시 마스트헤드 처리가 없다"
    assert "background:#fff" in pr.replace(" ", ""), "배경에 기대지 않는 처리가 없다"


# ── 판정을 못 해도 산술은 말한다 (18인 패널 재평가) ────────────────
def test_lowconf_verdict_still_states_the_price_ratio():
    """신뢰도가 낮아도 '시세 대비 몇 %'는 말할 수 있다 — 판단이 아니라 나눗셈이다.

    실측: 예상 낙찰가가 시세의 221%인 물건에 "참고용입니다"만 내보내, 초보가 그
    221%를 혼자 해석해야 했다("결국 사라는 건지 말라는 건지 모르겠어요", 24세).
    """
    from web import service as S
    st = {"state": "lowconf", "exp": 25_000_000, "med": 11_300_000,
          "floor": 25_000_000, "upper": 7_000_000, "max_bid": None}
    got = S.plain_verdict({}, {"price": 25_000_000}, st)
    assert "221%" in got["text"], f"시세 대비 비율을 말하지 않는다: {got['text']}"
    assert "비쌉니다" in got["text"]

    # 정상 범위면 굳이 붙이지 않는다 (문장이 길어지기만 한다)
    st2 = dict(st, exp=11_000_000)
    assert "%" not in S.plain_verdict({}, {"price": 11_000_000}, st2)["text"]


def test_stop_verdict_does_not_get_a_cheap_badge():
    """사지 말라고 판정한 물건에 '시세보다 −69% 싸다'를 붙이면 자기 말을 뒤집는다.

    실측: 할인 배지가 붙은 229건 중 11건이 stop 판정이었다.
    ('기일 대기'는 값이 싼 것 자체는 사실이므로 배지를 유지한다.)
    """
    import inspect
    from web import service as S
    src = inspect.getsource(S)
    i = src.index('d["disc_pct"]')
    seg = src[max(0, i - 400):i + 200]
    assert "bid_state" in seg and "stop" in seg, "배지가 판정을 보지 않는다"
