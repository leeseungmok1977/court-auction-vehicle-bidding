"""버킷마다 **사람이 읽을 이름**이 있어야 한다 — 내부 키가 화면에 새지 않게.

2026-09-19 실제로 겪은 일: 라이프사이클에 버킷(`nomarket`)을 하나 추가하면서 목록 화면의
이름표 사전(`web/templates/vehicles.html` 의 `_bkl`)을 같이 채우지 못했다. 그 사전은
`_bkl.get(bucket, bucket)` 로 폴백하기 때문에 **영문 키 'nomarket' 이 그대로 칩에 찍혔다.**
홈에서 그 링크를 누르면 바로 보이는 자리였다.

문제의 본질은 오타가 아니라 **두 곳이 따로 관리된다는 것**이다. 버킷 목록은 service.py 에,
이름표는 템플릿에 있어서, 하나를 늘리면 다른 하나를 잊는다. 그래서 문구를 채워 넣는 것으로
끝내지 않고 여기서 고정한다 — 다음에 버킷이 늘 때 이 테스트가 먼저 깨진다.

검증 방식은 '사전에 키가 있는가'가 아니라 **실제로 렌더한 화면에 영문 키가 보이는가**다.
사전만 보면 템플릿을 다른 방식으로 고쳤을 때 조용히 공허해진다.
"""
import re

import pytest
from starlette.testclient import TestClient

from web import service
from tests.test_dashboard_link_parity import BT

_PUBLIC = {"x-forwarded-for": "203.0.113.7"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from web import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "b.db")
    monkeypatch.setattr(service, "backtest_stats", lambda *a, **k: BT)
    db.init_db()
    base = {"court": "수원지방법원", "maker": "현대", "model": "쏘나타", "item_no": "1",
            "year": 2020, "sale_date": "2999-01-01", "status": "완료", "fail_count": 1,
            "mileage_km": 50000, "photo_count": 3}
    rows = [
        dict(base, id="W1_1", case_no="2026타경31", judgment="유찰 대기",
             min_sale_price=39000000, appraisal_value=40000000, median_price=40000000,
             market_confidence_label="높음"),
        dict(base, id="L1_1", case_no="2026타경32", judgment="시세 신뢰도 낮음, 수동 검토",
             min_sale_price=10000000, appraisal_value=12000000, median_price=13000000,
             market_confidence_label="낮음"),
        dict(base, id="O1_1", case_no="2026타경33", judgment="입찰 보류",
             min_sale_price=10000000, appraisal_value=12000000, accident_grade="flood"),
        # 시세 비교 대상 아님(건설기계)
        dict(base, id="NM1_1", case_no="2026타경34", model="굴착기",
             judgment="시세 신뢰도 낮음, 수동 검토",
             min_sale_price=10000000, appraisal_value=12000000),
        dict(base, id="R1_1", case_no="2026타경35", judgment="입찰 검토 가능",
             min_sale_price=10000000, appraisal_value=12000000, median_price=13000000,
             market_confidence_label="높음"),
    ]
    for r in rows:
        db.upsert_vehicle(r)
    import web.app as A
    return TestClient(A.app)


def _visible_text(html: str) -> str:
    body = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    body = re.sub(r"<style.*?</style>", " ", body, flags=re.S)
    body = re.sub(r"<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", body)


# won·review 는 버킷 링크가 아니라 판정 필터로 열리므로 칩 대상이 아니다.
_CHIP_BUCKETS = [b for b in service.LIFECYCLE_BUCKETS if b not in ("won", "review", "usepick")]


@pytest.mark.parametrize("bucket", _CHIP_BUCKETS)
def test_버킷_칩에_영문_키가_노출되지_않는다(client, bucket):
    """`_bkl` 에 이름표가 없으면 폴백으로 영문 키가 그대로 찍힌다 — 실제로 그렇게 샜다."""
    html = client.get(f"/vehicles?bucket={bucket}", headers=_PUBLIC).text
    assert html, f"bucket={bucket} 페이지가 비어 있다"
    assert bucket not in _visible_text(html), (
        f"목록 화면 본문에 내부 키 '{bucket}' 이 그대로 보인다 — "
        f"vehicles.html 의 버킷 이름표 사전에 한글 이름을 넣어야 한다"
    )


@pytest.mark.parametrize("bucket", _CHIP_BUCKETS)
def test_버킷_칩으로_필터를_풀_수_있다(client, bucket):
    """이름표가 비어 칩이 통째로 사라지는 것도 같은 결함이다(해제할 방법이 없어진다).

    ⚠ 예전엔 아이콘 이름(`filter_alt`)이 있는지로 확인했는데, 그건 **장식**이라
      아이콘을 빼자 테스트가 무너졌다(2026-09-20). 320px 에서 칩이 길어 해제 버튼 ✕ 가
      화면 밖으로 밀리길래 아이콘을 뺀 것인데, 정작 지켜야 할 것은 아이콘이 아니라
      **"필터를 풀 손잡이가 화면에 있는가"** 다. 그래서 해제 링크 자체를 본다.
    """
    html = client.get(f"/vehicles?bucket={bucket}", headers=_PUBLIC).text
    text = _visible_text(html)
    assert "✕" in text, (
        f"bucket={bucket} 에 필터 해제 표시(✕)가 없다 — 사용자가 필터를 풀 방법이 사라진다")
    # 해제 링크는 bucket 파라미터가 빠진 /vehicles 로 가야 한다(다른 필터는 유지).
    assert re.search(r'href="/vehicles(?:\?(?![^"]*bucket=)[^"]*)?"[^>]*>[^<]*✕', html), (
        f"bucket={bucket} 해제 링크가 bucket 을 그대로 달고 있다 — 눌러도 안 풀린다")


def test_시세를_낼_수_없는_목록은_그_이유를_먼저_말한다(client):
    """이 목록은 예상 낙찰가가 전부 비어 있다 — 설명이 없으면 '앱이 고장났다'로 읽힌다.

    게다가 이 물건들의 판정은 여전히 '시세 신뢰도 낮음'이라, 화면 하단 판정 설명에는
    "표본이 부족해"가 붙는다. 실제로는 **비교 대상 자체가 없는** 것이라 뜻이 어긋난다.
    배너가 사라지면 그 어긋남만 남으므로 여기서 고정한다(2026-09-19 디자인 검수).
    """
    text = _visible_text(client.get("/vehicles?bucket=nomarket", headers=_PUBLIC).text)
    assert "동급 중고차가 없어" in text, "시세를 내지 않는 이유를 목록 상단에서 말하지 않는다"
    # 정본 표기는 '예상낙찰가'(붙여쓰기) — tests/test_terms.py 가 강제한다.
    assert "예상낙찰가를 내지 않습니다" in text, "무엇이 비어 있는지 명시하지 않는다"
    # 다른 목록에까지 이 배너가 새어 나가면 안 된다(엉뚱한 화면에서 거짓 설명이 된다).
    other = _visible_text(client.get("/vehicles?bucket=lowconf", headers=_PUBLIC).text)
    assert "동급 중고차가 없어" not in other, "다른 버킷 목록에 배너가 새어 나갔다"
