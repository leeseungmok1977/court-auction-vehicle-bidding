# -*- coding: utf-8 -*-
"""`tools/store_final.py` — 스토어 최종 산출 파이프라인이 **손으로 적는 것 없이** 8장을 낸다를 잡아 둔다.

지시서 2026-09-24-15. 다섯 가지를 본다.
  (a) `--dry-run` 이 촬영(외부 요청)을 우회한다 — ast 로 `run_capture()` 호출이 `if not a.dry_run` 안에만 있는지,
      그리고 실제로 불러서 촬영 함수가 호출되지 않는지.
  (b) `ALT_TEXT.txt` 가 `docs/STORE_LISTING.md` "제출할 8장" 표와 같다 — **문서를 여기서 따로 읽어** 대조한다.
  (c) 기준월이 하드코딩이 아니다 — 코드 문자열에 `YYYY년 M월` 이 없고, 오버레이에 넘기는 값이 변수다.
  (d) 검사에 걸리면 종료코드 1 — ast 와 실제 호출 둘 다.
  (e) `capture_store_shots.SUBMIT_TARGETS` 가 두 역할(4·5번 G90 / 6·7번 SM6)을 들고 있고 촬영 함수가 역할을 쓴다.

파이프라인 자체는 **합성 원본**(단색 1080×1920 8장 + HEAD.json)으로 tmp 에서 끝까지 돌린다 — 실제
`screenshots/store/` 는 git 밖(이 PC 에만)이고 촬영·대조는 서브프로세스라 monkeypatch 로 막는다.

변이 시험(보고서 §변이 시험 절에 기록):
  ① main() 의 `if not a.dry_run:` 가드를 지우면 → (a) 두 테스트 FAIL
  ② `basis = "2026년 9월 기준"` 으로 박으면 → (c) FAIL
  ③ `return 1 if violations else 0` → `return 0` 이면 → (d) FAIL
  ④ SUBMIT_TARGETS["report"] 를 G90 으로 바꾸면 → (e) FAIL
  ⑤ ALT_TEXT 에 쓰는 캡션에서 대시를 빼면 → (b) FAIL
"""
from __future__ import annotations

import ast
import importlib.util
import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "tools" / "store_final.py"
CAPTURE_SRC = ROOT / "tools" / "capture_store_shots.py"
LISTING = ROOT / "docs" / "STORE_LISTING.md"
TEXT = SRC.read_text(encoding="utf-8")
TREE = ast.parse(TEXT)
CAP_TEXT = CAPTURE_SRC.read_text(encoding="utf-8")
CAP_TREE = ast.parse(CAP_TEXT)

_WOFF2 = ROOT / "web" / "static" / "fonts" / "Pretendard-Bold.woff2"
needs_fonts = pytest.mark.skipif(not _WOFF2.exists() or importlib.util.find_spec("fontTools") is None,
                                 reason="리포 Pretendard woff2 또는 fontTools 없음")


def _load():
    """경로로 읽는다 — 임포트 부작용 없음(stdout 재설정은 main 안, 촬영 도구는 서브프로세스)."""
    spec = importlib.util.spec_from_file_location("store_final_under_test", SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _func(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name}() 가 없다")


def _parents(tree):
    par = {}
    for node in ast.walk(tree):
        for ch in ast.iter_child_nodes(node):
            par[ch] = node
    return par


def _code_strings(tree: ast.Module) -> list[str]:
    """독스트링을 뺀 **코드 안** 문자열 상수. 독스트링은 사고 경위(옛 기본값 등)를 인용하므로 검사에서 뺀다."""
    doc_nodes = set()
    for node in [tree, *[n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))]]:
        body = getattr(node, "body", [])
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            doc_nodes.add(body[0].value)
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n not in doc_nodes]


# ── 문서(표)를 **여기서** 읽는다 — 도구의 파서를 믿지 않는다 ─────────────────────────
def _doc_rows() -> list[tuple[int, str, str]]:
    text = LISTING.read_text(encoding="utf-8")
    i = text.index("### 제출할 8장")
    rows = re.findall(r"^\|\s*(\d)\s*\|\s*`([0-9a-z_]+\.png)`\s*\|\s*(.+?)\s*\|\s*$", text[i:], re.M)
    rows = [(int(a), b, c) for a, b, c in rows][:8]
    assert [r[0] for r in rows] == list(range(1, 9)), f"문서 표가 1..8 이 아니다: {rows}"
    return rows


# ── 합성 원본 ───────────────────────────────────────────────────────────────
def _synth(tmp_path: pathlib.Path, at_by_file: dict[str, str] | None = None, break_md5: str | None = None):
    """단색 8장 + HEAD.json. `at_by_file` 로 촬영 시각을, `break_md5` 로 한 장의 기록 md5 를 틀리게 한다."""
    import hashlib
    from PIL import Image
    src = tmp_path / "src"
    src.mkdir()
    man = {}
    colors = [(20 * i + 10, 255 - 20 * i, 90 + 10 * i) for i in range(8)]
    for (slide, fname, _), col in zip(_doc_rows(), colors):
        Image.new("RGB", (1080, 1920), col).save(src / fname)
        m = hashlib.md5((src / fname).read_bytes()).hexdigest()
        if break_md5 == fname:
            m = "0" * 32
        man[fname] = {"commit": f"c{slide:07d}", "md5": m, "size": "1080x1920",
                      "at": (at_by_file or {}).get(fname, "2027-03-05T10:00:00+09:00")}
    (src / "HEAD.json").write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
    return src, tmp_path / "final"


@pytest.fixture(scope="session")
def font_cache(tmp_path_factory):
    """Pretendard woff2 → TTF 변환은 **58초**(2026-09-24 실측, 캐시 적중 0.2초)라 세션에 한 번만 한다.

    이미 변환된 캐시(`screenshots/store/final/_fonts` 또는 `overlay-draft/_fonts`)가 이 PC 에 있으면 그걸 복사해
    그 한 번도 아낀다. 각 파이프라인 테스트는 `_prime_fonts()` 로 `out/_fonts` 에 복사해 재변환을 피한다.
    """
    import shutil
    d = tmp_path_factory.mktemp("fonts")
    names = ("Pretendard-Bold", "Pretendard-Medium")
    for cand in (ROOT / "screenshots" / "store" / "final" / "_fonts",
                 ROOT / "screenshots" / "store" / "overlay-draft" / "_fonts"):
        hits = [next(cand.glob(f"{n}.[ot]tf"), None) for n in names] if cand.exists() else [None]
        if all(hits):
            for h in hits:
                shutil.copy2(h, d / h.name)
            return d
    mod = _load()
    mod.store_overlay.ensure_fonts(d)
    return d


def _prime_fonts(out: pathlib.Path, font_cache: pathlib.Path) -> None:
    """`ensure_fonts()` 는 캐시가 woff2 보다 새것이면 변환을 건너뛴다 — 복사 뒤 mtime 을 지금으로 맞춘다."""
    import os
    import shutil
    (out / "_fonts").mkdir(parents=True, exist_ok=True)
    for f in font_cache.iterdir():
        dst = out / "_fonts" / f.name
        shutil.copy2(f, dst)
        os.utime(dst, None)


def _quiet_subprocesses(mod, monkeypatch, capture_rc=None):
    """촬영(외부 요청)은 **호출되면 안 된다**는 걸 기록하고, 대조는 합격으로 둔다."""
    calls = {"capture": 0, "audit": 0}

    def fake_capture(hd, hr):
        calls["capture"] += 1
        if capture_rc is None:
            raise AssertionError("--dry-run 인데 run_capture() 가 불렸다 — 외부 요청이 나간다")
        return capture_rc

    def fake_audit():
        calls["audit"] += 1
        return 0

    monkeypatch.setattr(mod, "run_capture", fake_capture)
    monkeypatch.setattr(mod, "run_audit", fake_audit)
    return calls


# ══════════════════════════════════════════════════════════════════════════
# (a) --dry-run 이 촬영을 우회한다
# ══════════════════════════════════════════════════════════════════════════
def test_a_촬영_호출은_dry_run_가드_안에만_있다():
    main = _func(TREE, "main")
    par = _parents(main)
    calls = [n for n in ast.walk(main) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "run_capture"]
    assert calls, "main() 이 run_capture() 를 부르지 않는다 — 촬영 경로가 없다"
    for c in calls:
        node, guarded = c, False
        while node in par:
            node = par[node]
            if isinstance(node, ast.If) and isinstance(node.test, ast.UnaryOp) \
                    and isinstance(node.test.op, ast.Not) and isinstance(node.test.operand, ast.Attribute) \
                    and node.test.operand.attr == "dry_run":
                guarded = True
                break
        assert guarded, f"run_capture() 호출이 `if not a.dry_run:` 밖에 있다: {ast.unparse(c)}"
    assert "--dry-run" in TEXT


@needs_fonts
def test_a_dry_run_은_촬영을_부르지_않고_끝까지_간다(tmp_path, monkeypatch, font_cache):
    mod = _load()
    src, out = _synth(tmp_path)
    _prime_fonts(out, font_cache)
    calls = _quiet_subprocesses(mod, monkeypatch)          # run_capture 가 불리면 AssertionError
    rc = mod.main(["--dry-run", "--src", str(src), "--out", str(out)])
    assert rc == 0
    assert calls["capture"] == 0 and calls["audit"] == 1, calls
    assert len(list(out.glob("*__B1.png"))) == 8


@needs_fonts
def test_a_dry_run_이_아니면_촬영을_먼저_부르고_실패하면_대조도_안_한다(tmp_path, monkeypatch):
    mod = _load()
    src, out = _synth(tmp_path)
    calls = _quiet_subprocesses(mod, monkeypatch, capture_rc=1)
    rc = mod.main(["--src", str(src), "--out", str(out)])
    assert rc == 1
    assert calls["capture"] == 1 and calls["audit"] == 0, "촬영 실패 뒤에도 계속 갔다"


# ══════════════════════════════════════════════════════════════════════════
# (b) ALT_TEXT = STORE_LISTING 표
# ══════════════════════════════════════════════════════════════════════════
def test_b_도구의_캡션_파서가_문서_표와_같다():
    mod = _load()
    assert mod.listing_captions() == _doc_rows()
    # 그림에 그리는 캡션(store_overlay.CAPTIONS)과도 같아야 한다 — 스크린리더와 그림이 다른 말을 하면 안 된다
    assert mod.check_captions_against_overlay(_doc_rows()) == []
    # 1번 캡션은 대시(" — ")를 **포함**한 확정본이다 — 그림에서는 줄바꿈이 대신하지만 alt text 는 원문 그대로
    assert " — " in _doc_rows()[0][2]


@needs_fonts
def test_b_ALT_TEXT_가_표_순서_그대로_8줄_LF_이고_140자_이하(tmp_path, monkeypatch, font_cache):
    mod = _load()
    src, out = _synth(tmp_path)
    _prime_fonts(out, font_cache)
    _quiet_subprocesses(mod, monkeypatch)
    assert mod.main(["--dry-run", "--src", str(src), "--out", str(out)]) == 0
    raw = (out / "ALT_TEXT.txt").read_bytes()
    assert b"\r" not in raw and not raw.startswith(b"\xef\xbb\xbf"), "CRLF 또는 BOM — 콘솔에 붙여 넣을 때 헛 문자가 생긴다"
    lines = raw.decode("utf-8").split("\n")
    assert lines[-1] == "" and len(lines) == 9, "8줄 + 끝 개행이어야 한다"
    assert lines[:8] == [cap for _, _, cap in _doc_rows()]
    assert all(len(x) <= 140 for x in lines[:8])


_REAL_ALT = ROOT / "screenshots" / "store" / "final" / "ALT_TEXT.txt"


@pytest.mark.skipif(not _REAL_ALT.exists(), reason="이 PC 에 final/ALT_TEXT.txt 가 없다(screenshots 는 git 밖)")
def test_b_실제_final_ALT_TEXT_가_문서_표와_같다():
    lines = _REAL_ALT.read_text(encoding="utf-8").split("\n")[:8]
    assert lines == [cap for _, _, cap in _doc_rows()]


def test_b_alt_text_140자_초과는_위반이다(tmp_path):
    mod = _load()
    rows = [(1, "x.png", "가" * 141)] + [(i, f"{i}.png", "짧다") for i in range(2, 9)]
    bad = mod.write_alt_text(tmp_path, rows)
    assert len(bad) == 1 and "141자" in bad[0]


# ══════════════════════════════════════════════════════════════════════════
# (c) 기준월은 손으로 적지 않는다
# ══════════════════════════════════════════════════════════════════════════
def test_c_코드에_YYYY년_M월_문자열이_없다():
    month = re.compile(r"\d{4}\s*년\s*\d{1,2}\s*월")
    hits = [s for s in _code_strings(TREE) if month.search(s)]
    assert not hits, f"기준월이 코드에 박혀 있다: {hits} — 촬영 월에서 만들어야 한다"


def test_c_오버레이에_넘기는_basis_는_변수다():
    # run_overlay(): "--basis" 다음 원소가 Name 이어야 한다(문자열 상수면 손으로 적은 것)
    fn = _func(TREE, "run_overlay")
    lists = [n for n in ast.walk(fn) if isinstance(n, ast.List)]
    found = False
    for lst in lists:
        elts = lst.elts
        for i, e in enumerate(elts[:-1]):
            if isinstance(e, ast.Constant) and e.value == "--basis":
                found = True
                assert isinstance(elts[i + 1], ast.Name), f"--basis 뒤가 변수가 아니다: {ast.unparse(elts[i + 1])}"
    assert found, "run_overlay() 가 --basis 를 넘기지 않는다"
    # main(): basis 는 basis_from_manifest() 에서 나와야 한다
    main = _func(TREE, "main")
    assigns = [n for n in ast.walk(main) if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Tuple) and any(isinstance(e, ast.Name) and e.id == "basis" for e in t.elts)
                       for t in n.targets)]
    assert assigns and all(isinstance(a.value, ast.Call) and isinstance(a.value.func, ast.Name)
                           and a.value.func.id == "basis_from_manifest" for a in assigns), \
        "main() 의 basis 가 basis_from_manifest() 에서 나오지 않는다"


def test_c_basis_from_manifest_는_가장_최근_촬영_월을_쓰고_갈리면_경고한다():
    mod = _load()
    names = ["a.png", "b.png", "c.png"]
    man = {"a.png": {"at": "2027-03-05T10:00:00+09:00"},
           "b.png": {"at": "2027-03-01T09:00:00+09:00"},
           "c.png": {"at": "2027-03-04T23:59:59+09:00"}}
    basis, latest, warns = mod.basis_from_manifest(man, names)
    assert basis == "2027년 3월 기준" and latest.day == 5 and warns == []
    # 11월 → 앞자리 0 없이 'M월'
    man["a.png"]["at"] = "2027-11-30T00:00:00+09:00"
    basis, _, warns = mod.basis_from_manifest(man, names)
    assert basis == "2027년 11월 기준" and len(warns) == 1 and "갈린다" in warns[0]
    # 시간대 없는 옛 기록도 섞여서 터지지 않는다
    man["b.png"]["at"] = "2027-03-01T09:00:00"
    assert mod.basis_from_manifest(man, names)[0] == "2027년 11월 기준"
    # 촬영 시각이 없는 장이 있으면 지어내지 않는다
    with pytest.raises(SystemExit):
        mod.basis_from_manifest({"a.png": {}}, ["a.png"])


@needs_fonts
def test_c_합성_원본의_촬영_월이_그림과_metrics_에_들어간다(tmp_path, monkeypatch, font_cache):
    mod = _load()
    src, out = _synth(tmp_path, at_by_file={"05_calendar.png": "2028-07-02T12:00:00+09:00"})
    _prime_fonts(out, font_cache)
    _quiet_subprocesses(mod, monkeypatch)
    assert mod.main(["--dry-run", "--src", str(src), "--out", str(out)]) == 0
    head = json.loads((out / "HEAD.json").read_text(encoding="utf-8"))
    assert head["_meta"]["basis"] == "2028년 7월 기준"      # 가장 최근 장(05_calendar)의 월
    assert head["_meta"]["basis_warnings"], "8장의 월이 갈리는데 경고가 없다"
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["basis"] == "2028년 7월 기준"


# ══════════════════════════════════════════════════════════════════════════
# (d) 검사 실패 시 종료코드 1
# ══════════════════════════════════════════════════════════════════════════
def test_d_main_은_위반이_있으면_1_을_돌려준다_ast():
    main = _func(TREE, "main")
    # ⚠ ast.walk 는 너비 우선이라 [-1] 이 본문 마지막 return 이 아니다 — 줄 번호로 마지막을 고른다
    last = max((n for n in ast.walk(main) if isinstance(n, ast.Return)), key=lambda n: n.lineno)
    tail = ast.unparse(last.value)
    assert tail == "1 if violations else 0", f"main() 의 마지막 return 이 위반을 보지 않는다: {tail}"


def test_d_검사_함수가_위반을_내면_main_이_1(tmp_path, monkeypatch):
    mod = _load()
    src, out = _synth(tmp_path)
    _quiet_subprocesses(mod, monkeypatch)
    monkeypatch.setattr(mod, "run_overlay", lambda *a, **k: 0)
    monkeypatch.setattr(mod, "validate_finals", lambda *a, **k: (["규격 위반(모의)"], {}))
    assert mod.main(["--dry-run", "--src", str(src), "--out", str(out)]) == 1
    head = json.loads((out / "HEAD.json").read_text(encoding="utf-8"))
    assert head["_meta"]["violations"] == ["규격 위반(모의)"]


@needs_fonts
def test_d_원본_md5_가_HEAD_json_기록과_다르면_1(tmp_path, monkeypatch, font_cache):
    """도구 밖에서 바뀐 원본은 어느 커밋에서 나온 장인지 모른다(PANEL-45) — 조용히 통과하면 안 된다."""
    mod = _load()
    src, out = _synth(tmp_path, break_md5="07_detail.png")
    _prime_fonts(out, font_cache)
    _quiet_subprocesses(mod, monkeypatch)
    assert mod.main(["--dry-run", "--src", str(src), "--out", str(out)]) == 1
    head = json.loads((out / "HEAD.json").read_text(encoding="utf-8"))
    assert any("07_detail.png" in v and "기준 커밋" in v for v in head["_meta"]["violations"])


def test_d_validate_finals_는_규격_모드_중복을_본다(tmp_path):
    from PIL import Image
    mod = _load()
    rows = [(1, "a.png", "A"), (2, "b.png", "B"), (3, "c.png", "C")]
    src, out = tmp_path / "s", tmp_path / "o"
    src.mkdir(), out.mkdir()
    man = {}
    for _, f, _ in rows:
        Image.new("RGB", (1080, 1920), (1, 2, 3)).save(src / f)        # 원본 셋이 같은 그림 → 중복
        man[f] = {"md5": mod.md5(src / f), "commit": "x", "at": "2027-01-01T00:00:00+09:00"}
    Image.new("RGB", (1080, 1900), (9, 9, 9)).save(out / mod.final_name("a"))     # 규격 미달
    Image.new("RGBA", (1080, 1920), (9, 9, 9, 255)).save(out / mod.final_name("b"))  # 알파
    # c 는 최종 파일 없음
    bad, shots = mod.validate_finals(out, src, rows, man)
    joined = "\n".join(bad)
    assert "1080x1900" in joined and "RGBA" in joined and "최종 파일이 없다" in joined and "두 번 올라간다" in joined
    assert set(shots) == {mod.final_name(s) for s in "abc"}


# ══════════════════════════════════════════════════════════════════════════
# (e) SUBMIT_TARGETS — 두 역할, 두 물건
# ══════════════════════════════════════════════════════════════════════════
def test_e_SUBMIT_TARGETS_가_G90_과_SM6_를_역할별로_든다():
    m = re.search(r"SUBMIT_TARGETS[^=]*=\s*\{(.*?)\n\}", CAP_TEXT, re.S)
    assert m, "capture_store_shots.py 에 SUBMIT_TARGETS 가 없다"
    body = m.group(1)
    assert re.search(r'"detail"\s*:\s*"/vehicle/2025타경34553_1"', body), "4·5번 대상이 G90(2025타경34553_1)이 아니다"
    assert re.search(r'"report"\s*:\s*"/vehicle/2026타경3364_1"', body), "6·7번 대상이 SM6(2026타경3364_1)가 아니다"
    # 두 역할이 **다른** 물건이어야 한다 — 같으면 --hero 하나로 족했다
    hrefs = re.findall(r'"/vehicle/[^"]+"', body)
    assert len(hrefs) == 2 and hrefs[0] != hrefs[1]


def test_e_촬영_함수가_역할을_쓴다():
    for fn, role in (("shoot_detail", "detail"), ("shoot_slide5", "detail"),
                     ("shoot_report", "report"), ("shoot_hexa", "report")):
        src = ast.get_source_segment(CAP_TEXT, _func(CAP_TREE, fn)) or ""
        assert f'pick_hero_vehicle(pg, "{role}")' in src, f"{fn}() 이 역할 {role!r} 로 대상을 받지 않는다"


def _body_src(text: str, fn: ast.FunctionDef) -> str:
    """독스트링을 뺀 함수 **본문** 소스 — 독스트링이 `_scan_pick()` 을 먼저 언급해 find 가 엉뚱한 곳을 잡는다."""
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return "\n".join(ast.get_source_segment(text, s) or "" for s in body)


def test_e_지정_대상이_있으면_탐색하지_않는다():
    src = _body_src(CAP_TEXT, _func(CAP_TREE, "pick_hero_vehicle"))
    i_res, i_scan = src.find("resolve_target("), src.find("_scan_pick(")
    assert i_res != -1 and i_scan != -1 and i_res < i_scan, "지정 대상을 보기 전에 탐색부터 한다"
    assert "return hero" in src[i_res:i_scan], "지정 대상이 있어도 돌아가지 않고 탐색으로 간다"
    r = ast.get_source_segment(CAP_TEXT, _func(CAP_TREE, "resolve_target")) or ""
    assert "SUBMIT_TARGETS" in r and "_PICK_ONLY" in r


def test_e_store_final_이_두_대상을_촬영_도구에_그대로_넘긴다():
    src = ast.get_source_segment(TEXT, _func(TREE, "run_capture")) or ""
    assert '"--all"' in src and '"--hero-detail"' in src and '"--hero-report"' in src
    m = ast.get_source_segment(TEXT, _func(TREE, "main")) or ""
    assert "run_capture(a.hero_detail, a.hero_report)" in m
