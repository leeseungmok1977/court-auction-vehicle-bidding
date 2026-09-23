# -*- coding: utf-8 -*-
"""`tools/capture_store_shots.py` — **문서가 코드보다 앞서지 못하게** 잡아 둔다.

2026-09-24 실측: 파일 첫머리 독스트링이 `--all` 을 안내하는데 argparse 에는 `--slide5`·
`--audit` 둘뿐이었다. 그래서 홈·적중률·소개를 찍을 경로가 저장소에 **아예 없었고**, 그 세 장이
9/22 촬영본인 채로 제출 후보에 남아 라이브와 수치가 갈렸다(평균 오차 ±9.3 vs ±9.5,
검증 표본 249 vs 275, 라벨 '평균 오차' vs '전체 평균 오차').

소스를 **실행하지 않고 ast 로 읽는다** — 임포트만 해도 stdout 을 감싸고 playwright 를
끌어오므로 테스트가 도구의 부작용에 물들면 안 된다.
"""
from __future__ import annotations

import ast
import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[1] / "tools" / "capture_store_shots.py"
TREE = ast.parse(SRC.read_text(encoding="utf-8"))
TEXT = SRC.read_text(encoding="utf-8")


def _flags_in_docstring() -> set[str]:
    doc = ast.get_docstring(TREE) or ""
    return set(re.findall(r"(--[a-z0-9]+)", doc))


def _flags_in_argparse() -> set[str]:
    return set(re.findall(r'add_argument\(\s*"(--[a-z0-9]+)"', TEXT))


def _func(name: str) -> ast.FunctionDef:
    for node in TREE.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name}() 가 {SRC.name} 에 없다")


def _strings(fn: str) -> list[str]:
    """함수 **본문의 문자열 상수**만 모은다.

    ⚠ 독스트링은 뺀다. 독스트링에는 "9/22 판은 `낙찰 100건` 이라 적혀 있었다" 처럼
    **왜 이 검사가 생겼는지**를 적으므로 옛 수치가 인용된다. 그건 검사에 값을 박은 게
    아니라 사고 경위를 남긴 것이다 — 그걸 막으면 기록을 지우게 된다.
    """
    node = _func(fn)
    body = node.body[1:] if (node.body and isinstance(node.body[0], ast.Expr)
                             and isinstance(getattr(node.body[0], "value", None), ast.Constant)
                             and isinstance(node.body[0].value.value, str)) else node.body
    out = []
    for stmt in body:
        for n in ast.walk(stmt):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                out.append(n.value)
    return out


def test_독스트링이_안내하는_인자는_전부_실제로_있다():
    doc, real = _flags_in_docstring(), _flags_in_argparse()
    missing = doc - real
    assert not missing, (
        f"독스트링이 없는 인자를 안내한다: {sorted(missing)} — "
        f"실제 인자는 {sorted(real)}. 구현하든 안내를 지우든 둘 중 하나를 해야 한다."
    )


SHOOTERS = ("shoot_landing", "shoot_home", "shoot_accuracy", "shoot_detail",
            "shoot_slide5", "shoot_report", "shoot_hexa", "shoot_calendar")


def test_여덟_장을_찍는_함수가_전부_있고_SHOTS_에_연결돼_있다():
    """2026-09-24 2차: 네 장만 있던 표를 **제출 8장 전부**로 넓혔다.

    07·08·09·10·05 를 찍을 경로가 저장소에 없어서, `09_report.png` 는 우리가 스스로
    틀렸다고 판정해 고친 표기(`실측 평균오차`)를 그대로 단 채, `05_calendar.png` 는
    모수를 잘못 적은 표기(`낙찰 N건`)를 단 채 제출 후보로 남아 있었다.
    """
    for fn in SHOOTERS:
        _func(fn)
    names = re.findall(r'\(\s*"([a-z0-9]+)"\s*,\s*(shoot_[a-z0-9_]+)\)', TEXT)
    assert len(names) == 8, f"SHOTS 표가 제출 8장을 담고 있지 않다: {names}"
    real = _flags_in_argparse()
    for flag, _ in names:
        assert f"--{flag}" in real, f"SHOTS 의 '{flag}' 에 대응하는 인자가 없다"


def test_제출_여덟_장_파일명을_도구가_직접_들고_있다():
    """`audit()` 이 '있는 파일'만 훑으면 **없는 장은 조용히 통과한다.**

    그래서 제출 목록을 코드가 상수로 들고 있어야 하고, 그 목록이 여덟이어야 한다.
    """
    m = re.search(r"SUBMIT\s*=\s*\(([^)]*)\)", TEXT, re.S)
    assert m, "SUBMIT 목록이 없다 — 제출 8장이 다 있는지 검사할 근거가 사라진다"
    pngs = re.findall(r'"([0-9_a-z]+\.png)"', m.group(1))
    assert len(pngs) == 8, f"SUBMIT 이 8장이 아니다: {pngs}"
    for png in ("06_landing.png", "01_home.png", "02_accuracy.png", "07_detail.png",
                "08_detail_lower.png", "09_report.png", "10_report_lower.png",
                "05_calendar.png"):
        assert png in pngs, f"{png} 가 제출 목록에 없다"
        assert TEXT.count(png) >= 2, f"{png} 를 **찍는** 경로가 없다(목록에만 있다)"


def test_기대_문구에_움직이는_숫자를_박지_않는다():
    """검사 문구는 **라벨**이어야 한다.

    값(±9.5% · 275건)을 박으면 값이 움직이는 순간 촬영이 실패하는데, 그건 화면이 낡은 게
    아니라 **검사가 낡은 것**이다. `±20% 이내 적중` 처럼 라벨에 붙박인 정수는 값이 아니므로
    허용하고, 소수점 오차(`±9.5`)와 건수(`275건`)만 막는다.
    """
    moving = re.compile(r"±\s*\d+\.\d|\d+\s*건")
    for fn in SHOOTERS:
        for s in _strings(fn):
            assert not moving.search(s), (
                f"{fn}() 의 문구 '{s}' 에 움직이는 값이 박혀 있다"
            )


def test_금지_문구_검사가_준비중과_관리자_UI_를_함께_본다():
    """'준비 중'(미출시 기능 광고)과 관리자 UI 누수 둘 다 막아야 한다.

    전례 ①: `보관·구매 (준비 중)` 칩이 리포트 캡처에 찍혀, 앱에서 칩을 지워도 스토어 이미지가
    준비 중을 광고하는 상태가 될 뻔했다.
    전례 ②: 로컬 직결로 찍으면 관리자로 판정돼 '다시 분석' 같은 운영 버튼이 섞인다.
    """
    m = re.search(r"FORBIDDEN\s*=\s*\(([^)]*)\)", TEXT, re.S)
    assert m, "FORBIDDEN 목록이 사라졌다"
    body = m.group(1)
    for word in ("준비 중", "다시 분석", "운영 도구"):
        assert word in body, f"FORBIDDEN 에서 '{word}' 가 빠졌다"


def test_외부_요청_전_지연을_지킨다():
    """C.4 ②: 모든 외부 요청 전 5~10초 대기. 우리 서버라도 지킨다."""
    m = re.search(r"POLITE_SEC\s*=\s*(\d+)", TEXT)
    assert m, "POLITE_SEC 이 없다 — 지연 없이 외부 요청을 보내게 된다"
    assert 5 <= int(m.group(1)) <= 10, f"지연이 5~10초 밖이다: {m.group(1)}초"
    # 직접 goto 로 우회하면 지연이 통째로 새어 나간다.
    raw = [ln for ln in TEXT.splitlines()
           if "pg.goto(" in ln and "def polite_goto" not in ln]
    assert len(raw) == 1, f"polite_goto() 밖에서 pg.goto 를 쓴 곳이 있다: {raw}"


def test_기준_커밋을_남긴다():
    """PANEL-45: 찍는 사람과 보는 사람 사이에 커밋이 끼면 아무도 모른다."""
    _func("stamp_head")
    assert 'rev-parse' in TEXT and '"HEAD"' in TEXT


def test_리포트_촬영이_상한선과_유형별_오차를_둘_다_요구한다():
    """6번 캡션은 '한 장짜리 종합 분석 리포트' 다 — **결론 숫자와 그 오차**가 같이 있어야 한다.

    ★ 공허 통과 방지: 아무 물건이나 찍으면 상한선이 없는 물건이 걸리고, 그러면 캡션이
    그림을 앞선다. 값이 아니라 **라벨**로 요구한다.
    """
    s = _strings("shoot_report")
    assert "입찰 상한선" in s, "shoot_report() 가 입찰 상한선을 요구하지 않는다"
    assert "실측 오차" in s, "shoot_report() 가 유형별 실측 오차를 요구하지 않는다"


def test_리포트_하단_촬영이_여섯_축을_전부_요구한다():
    """7번 캡션은 여섯 축을 **이름으로 센다.** 그림이 5/6 이면 캡션이 그림을 앞선다.

    9/22 판 `10_report_lower.png` 가 실제로 '사고·상태 미산출' 이었다.
    """
    for axis in ("가격 메리트", "시세 신뢰도", "사고·상태", "주행 적정성", "잔존가치", "유동성"):
        assert axis in TEXT, f"육각형 검사에서 '{axis}' 축이 빠졌다"
    src = ast.get_source_segment(TEXT, _func("shoot_hexa")) or ""
    # ⚠ `'!= 6' in src` 로만 보면 **축 이름 개수 검사**(`len(h["axes"]) != 6`)에 걸려
    #   산출 축 수 검사를 통째로 지워도 통과한다. 변이 시험에서 실제로 새어 나갔다.
    assert re.search(r'h\[\s*"avail"\s*\]\s*!=\s*6', src), (
        "shoot_hexa() 가 '6축 전부 산출'을 확인하지 않는다 — 미산출 축이 찍혀 나간다")
    assert re.search(r'len\(\s*h\[\s*"axes"\s*\]\s*\)\s*!=\s*6', src), (
        "shoot_hexa() 가 축 이름 6개를 확인하지 않는다")


def test_대상_물건을_캡션_조건으로_고른다():
    """★ '그 분기가 실제로 렌더되는 물건'이어야 한다 — 아니면 공허 통과다."""
    src = ast.get_source_segment(TEXT, _func("hero_ok")) or ""
    for need in ("감정가", "유찰횟수", "당시 출시가", "입찰 상한선", "실측 오차"):
        assert need in src, f"hero_ok() 가 '{need}' 렌더 여부를 안 본다"
    assert "axes" in src, "hero_ok() 가 육각형 산출 축 수를 안 본다"
    # 탐색도 외부 요청이다(C.4 ①) — 상한이 없으면 목록 전체를 순회하게 된다.
    m = re.search(r"HERO_SCAN_MAX\s*=\s*(\d+)", TEXT)
    assert m and 0 < int(m.group(1)) <= 20, "대상 탐색에 요청 상한이 없다"


def test_달력_촬영이_오늘_날짜와_고친_모수_표기를_검사한다():
    """달력은 **날짜가 곧 내용**이다 — 이 한 장만은 촬영일이 화면에 그대로 드러난다.

    9/22 판은 '오늘' 강조가 22일에 박힌 채 이틀을 넘겼고, 같은 장이 `낙찰 100건` 이라
    적혀 있었다(실제로는 낙찰 193건 중 100건 · `6b04e6d`/PANEL-17 에서 '시세 확인 N건'
    으로 고쳤다).
    """
    src = ast.get_source_segment(TEXT, _func("shoot_calendar")) or ""
    assert "date.today()" in src, "shoot_calendar() 가 '오늘' 강조를 오늘 날짜와 대조하지 않는다"
    assert "시세 확인" in src, "shoot_calendar() 가 고쳐진 모수 표기를 요구하지 않는다"


def test_폐기된_표기가_화면에_다시_보이면_저장을_막는다():
    """우리가 스스로 '틀렸다'고 판정해 고친 표기는 **낡은 숫자보다 무겁다.**

    `09_report.png`(9/22 촬영)에 `실측 평균오차 ±9.3%` 가 픽셀로 박혀 있었다 —
    `69e1c47`(PANEL-01)이 유형별로 고치기 15시간 전 캡처였다.
    """
    m = re.search(r"RETIRED\s*=\s*\(([^)]*)\)", TEXT, re.S)
    assert m, "RETIRED(폐기 표기) 목록이 없다"
    assert "평균오차" in m.group(1), "RETIRED 에서 '평균오차'(전체평균 표기)가 빠졌다"
    src = ast.get_source_segment(TEXT, _func("no_forbidden")) or ""
    assert "RETIRED" in src, "no_forbidden() 이 RETIRED 를 보지 않는다 — 목록만 있고 검사가 없다"


def test_장별_기준_커밋을_남긴다():
    """한 줄짜리 HEAD 는 **디렉터리 전체가 한 커밋에서 나왔을 때만** 참말이다.

    2026-09-24 실측: 세 장은 `7b78b2e`(01:49)에, 다섯 장은 `931a134`(07:12~07:26)에
    찍혔는데 그 사이 커밋 둘이 들어왔다. 한 줄 파일은 여덟 장 전부를 마지막 커밋에서
    찍은 것처럼 말한다 — PANEL-45 가 막으려던 바로 그 상황을 덮어 버린다.
    """
    _func("git_head")
    src = ast.get_source_segment(TEXT, _func("guard_and_save")) or ""
    assert "_STAMPS" in src and "git_head()" in src, (
        "저장 시점에 그 장의 기준 커밋을 적지 않는다 — 회차 끝에 몰아 적으면 "
        "먼저 찍은 장까지 나중 커밋으로 적힌다")
    assert re.search(r'MANIFEST\s*=\s*"[^"]+"', TEXT), "장별 기록 파일 이름이 없다"


def test_값_블록을_본문_산문으로_대신_통과시키지_않는다():
    """실측 회귀: `입찰 상한선`·`판정` 을 기대 라벨로 쓰면 **산문에도 걸린다.**

    `한줄 판정` 문단이 "입찰 상한선은 1,420만원입니다" 라고 말하고, `판정` 은 `사고판정`
    에도 들어 있다. 둘 다 통과시켜 놓고 정작 값 블록은 프레임 밖일 수 있다 —
    5번 캡션('입찰 상한선까지 계산해 드립니다')이 또 그림을 앞서게 된다.
    그래서 5번은 **값 블록에만 있는 문구**로 가리킨다.
    """
    s = _strings("shoot_slide5")
    assert "여기까지만" in s, "shoot_slide5() 가 상한선 **값 블록**을 가리키지 않는다"
    assert "산정 기준" in s, "shoot_slide5() 가 AI 카드의 끝을 가리키지 않는다"
    assert "판정" not in s, (
        "shoot_slide5() 가 '판정' 을 기대 라벨로 쓴다 — '사고판정' 에도 걸려 헛통과한다")
