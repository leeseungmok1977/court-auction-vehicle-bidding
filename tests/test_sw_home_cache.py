"""서비스워커 홈 캐시 — 되풀이하기 쉬운 실수를 고정한다.

2026-09-18 실제로 겪은 일: 홈 문서를 캐시에 저장하는 코드가 **한 번도 성공하지 못했는데**
그 사실이 몇 시간 동안 드러나지 않았다. 원인은 딱 한 줄이었다.

    if (net && net.ok) e.waitUntil(putHome(net));   // putHome 안에서 뒤늦게 clone()
    return net;                                     // ← 본문이 페이지로 흘러가 버린다

Response 본문은 한 번만 읽을 수 있다. putHome 이 `await caches.open(...)` 을 먼저 하는 바람에
그 사이 본문이 소비돼 `clone()` 이 "Response body is already used" 로 던졌고, `catch {}` 가
그걸 삼켰다. 그래서 '캐시 우선'이라고 적혀 있는데 매번 서버를 기다렸다.

여기서 지키는 것은 셋이다.
  ① putHome 은 **내부에서 복제하지 않는다** — 전용 사본을 받는다.
  ② 호출부는 fetch 직후, 응답을 돌려주기 **전에** 복제를 뜬다.
  ③ 저장 실패를 침묵시키지 않는다.
동작이 아니라 구조를 고정하는 테스트다 — 브라우저 없이도 이 실수만은 다시 통과시키지 않는다.
"""
from pathlib import Path

import pytest

SW = Path(__file__).resolve().parents[1] / "web" / "static" / "sw.js"


@pytest.fixture(scope="module")
def src() -> str:
    return SW.read_text(encoding="utf-8")


def _body(src: str, header: str) -> str:
    """`header` 로 시작하는 함수 본문을 다음 최상위 선언 전까지 잘라 온다."""
    i = src.index(header)
    rest = src[i + len(header):]
    nxt = [p for p in (rest.find("\nasync function "), rest.find("\nfunction "),
                       rest.find("\nself.addEventListener")) if p != -1]
    return rest[:min(nxt)] if nxt else rest


def test_put_home_은_스스로_복제하지_않는다(src):
    body = _body(src, "async function putHome(")
    assert ".clone()" not in body, (
        "putHome 안에서 복제하면 안 된다 — 호출부가 응답을 페이지에 넘긴 뒤라 이미 늦다. "
        "전용 사본을 인자로 받아야 한다."
    )
    assert "resp.arrayBuffer()" in body, "전달받은 사본을 그대로 읽어야 한다"


def test_홈_네트워크_응답은_돌려주기_전에_복제된다(src):
    body = _body(src, "async function homeFirst(")
    clone_at = body.find("net.clone()")
    return_at = body.find("return net;")
    assert clone_at != -1, "네트워크 갈래에서 fetch 직후 복제를 떠야 한다"
    assert return_at != -1
    assert clone_at < return_at, (
        "복제가 `return net` 뒤에 오면 본문이 이미 소비돼 저장이 조용히 실패한다"
    )


def test_저장_실패를_침묵시키지_않는다(src):
    body = _body(src, "async function putHome(")
    assert "console.warn" in body, (
        "저장 실패를 조용히 삼키면 캐시가 비어 있어도 아무도 모른다 — 실제로 그렇게 놓쳤다"
    )


def test_홈_문서_분기가_살아있다(src):
    assert "req.mode === 'navigate'" in src and "url.pathname === '/'" in src, (
        "홈 문서를 캐시 우선으로 태우는 분기가 사라지면 이 최적화 전체가 무효다"
    )


def test_진단용_코드가_남아있지_않다(src):
    for leftover in ("__swtrace", "function trace(", "async function _trace("):
        assert leftover not in src, f"임시 진단 코드가 남았다: {leftover}"
