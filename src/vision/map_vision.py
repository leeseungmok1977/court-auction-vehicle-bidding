"""지도 이미지에서 보관장소 주소를 **비전 LLM으로** 읽는다 (OCR 실패분 한정).

## 왜 필요한가

Tesseract는 이 지도들을 못 읽는다. 원본이 663px 래스터이고 라벨 글자가 12~16px,
동 이름은 8~10px다. 실측 수율 1.9%(972장 중 12건). 실패의 78%는 '보관장소' 라벨
자체를 못 찾은 것이었다.

비전 LLM은 같은 이미지에서 지명과 라벨을 읽는다. **OCR이 실패한 건에만** 쓴다.

## 안전 규칙 (CLAUDE.md C.4)

· 키는 `docs/.env`(gitignore)에서 읽는다. 하드코딩·로그 출력 금지.
· 외부 요청 전 5~10초 대기. 재시도 최대 2회, 간격 30초.
· 429/403/비정상 응답이 **3회 연속**이면 즉시 중단하고 보고한다.
· 런당 호출 상한을 반드시 건다(무한 순회 금지).

## 신뢰 규칙

지어내기를 막는 것이 이 모듈의 핵심이다. 모델에게 **이미지에서 실제로 읽은 글자**를
`evidence` 로 함께 내게 하고, 그게 없으면 채택하지 않는다. 지형·도로 모양으로
"아마 여기일 것"이라고 추론한 답은 거부한다 — 사용자를 엉뚱한 도시로 보낸다.
채택해도 `storage_conf` 로 정밀도(번지/동/구)를 구분해 화면에 적는다.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import time
from pathlib import Path
from typing import Optional

ENDPOINT = "https://api.openai.com/v1/chat/completions"
MODEL = os.environ.get("NC_VISION_MODEL", "gpt-4o-mini")
_ENV_PATH = Path(__file__).resolve().parents[2] / "docs" / ".env"

SYSTEM = (
    "당신은 한국 법원경매 감정평가서에 첨부된 지도 이미지를 읽는 도구입니다. "
    "이미지에 실제로 인쇄된 글자만 사용하세요. 지형·도로 모양·주변 정황으로 위치를 "
    "추론하지 마세요. 읽을 수 없으면 읽을 수 없다고 답하세요."
)

PROMPT = """이 지도 이미지에서 **글자를 읽어** 주세요. 위치를 추론하지 말고, 읽기만 하세요.

지도에는 보통 빨간 원·화살표·다각형으로 한 지점이 표시돼 있습니다.

두 가지를 뽑아 주세요.

A) printed_address — '보관장소' 같은 라벨과 함께 **주소 문자열이 통째로 인쇄돼**
   있으면 그대로 옮기세요. 없으면 null.

B) nearby_labels — 표시된 지점 **주변에 인쇄된 지명·시설명**을 읽은 그대로 최대 8개.
   행정구역 라벨(○○동/○○리/○○읍/○○구/○○시), 학교·병원·역·공단·차고지 등
   고유명사면 무엇이든 좋습니다. 지도 구석의 먼 것보다 표시 지점에 가까운 것부터.
   **글자를 그대로** 적으세요. 아는 지식으로 바꾸지 마세요
   ("개화역"을 "개화동"으로 바꾸지 말 것). 읽을 게 없으면 빈 배열.

label_kind — 표시 지점의 라벨이 '보관장소'류이면 "보관장소",
'본건'만 있으면 "본건", 아무 라벨도 없으면 "없음".
('본건' 지도는 차량 위치가 아니라 물건 소재지일 수 있어 구분이 필요합니다.)

JSON으로만 답하세요:
{
  "printed_address": "인쇄된 주소 또는 null",
  "nearby_labels": ["읽은 글자", "..."],
  "label_kind": "보관장소 | 본건 | 없음",
  "note": "특이사항(있으면)"
}"""

_SIDO = (r"(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|"
         r"경북|경남|제주)(?:특별자치시|특별자치도|특별시|광역시|도)?")
_GU_RE = re.compile(r"[가-힣]{1,5}(?:시|군|구)")


def _api_key() -> str:
    """키를 읽는다. 환경변수 우선, 없으면 docs/.env. 값은 절대 로그에 남기지 않는다."""
    key = (os.environ.get("GPT_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    if key:
        return key
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() in ("GPT_API_KEY", "OPENAI_API_KEY"):
                return v.strip().strip("\"'")
    return ""


def _encode(path: str, max_side: int = 1400) -> Optional[str]:
    """이미지를 PNG base64 로. 원본이 작으므로 **확대해서** 보낸다 —
    라벨 글자가 12~16px라 원본 크기로는 모델도 놓친다."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            im = im.convert("RGB")
            scale = min(max_side / max(im.size), 2.0)
            if scale > 1.0:
                im = im.resize((int(im.width * scale), int(im.height * scale)),
                               Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:            # noqa: BLE001 — 깨진 파일이 배치를 멈추면 안 된다
        return None


class VisionError(RuntimeError):
    """중단 조건(429/403/비정상)에 해당하는 응답."""


def read_map(path: str, timeout: int = 90) -> dict:
    """지도 한 장을 비전 LLM에 보내 보관장소 주소를 읽는다.

    반환: {"address", "level", "evidence", "label_kind", "note"}
    중단해야 할 응답(429/403/5xx)이면 VisionError 를 던진다.
    """
    import requests

    key = _api_key()
    if not key:
        raise VisionError("API 키 없음 (docs/.env 의 GPT_API_KEY)")
    b64 = _encode(path)
    if not b64:
        return {"address": None, "level": "none", "evidence": None,
                "label_kind": "없음", "note": "이미지를 열 수 없음"}

    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}},
            ]},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 300,
        "temperature": 0,
    }
    r = requests.post(ENDPOINT, timeout=timeout,
                      headers={"Authorization": f"Bearer {key}",
                               "Content-Type": "application/json"},
                      json=body)
    if r.status_code in (401, 403, 429) or r.status_code >= 500:
        # 키·권한·한도 문제는 재시도로 풀리지 않거나 부하를 더한다 — 위로 올려 중단시킨다
        raise VisionError(f"HTTP {r.status_code}")
    if r.status_code != 200:
        return {"address": None, "level": "none", "evidence": None,
                "label_kind": "없음", "note": f"HTTP {r.status_code}"}
    try:
        payload = r.json()
        txt = payload["choices"][0]["message"]["content"]
        got = json.loads(txt)
    except Exception:            # noqa: BLE001
        return {"address": None, "level": "none", "evidence": None,
                "label_kind": "없음", "note": "응답 파싱 실패"}
    usage = payload.get("usage") or {}
    labels = got.get("nearby_labels")
    if not isinstance(labels, list):
        labels = []
    return {
        "usage_in": usage.get("prompt_tokens", 0),
        "usage_out": usage.get("completion_tokens", 0),
        "printed_address": _clean_null(got.get("printed_address")),
        "nearby_labels": [str(x).strip() for x in labels if str(x).strip()][:8],
        "label_kind": (got.get("label_kind") or "없음"),
        "note": (got.get("note") or ""),
    }


def _clean_null(v) -> Optional[str]:
    """모델이 문자열 "null" 을 돌려주는 경우가 있다 — 그대로 두면 주소로 저장된다."""
    if v is None:
        return None
    t = str(v).strip()
    return None if t.lower() in ("", "null", "none", "n/a", "미상", "없음", "불명") else t


SIDO_RE = re.compile(
    r"(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충청북도|충북|충청남도|충남|"
    r"전라북도|전북|전라남도|전남|경상북도|경북|경상남도|경남|제주)")
_SIDO_CANON = {"충청북도": "충북", "충청남도": "충남", "전라북도": "전북",
               "전라남도": "전남", "경상북도": "경북", "경상남도": "경남"}


def sido_of(text: str) -> str:
    m = SIDO_RE.search(text or "")
    return _SIDO_CANON.get(m.group(1), m.group(1)) if m else ""


_DONG_RE = re.compile(r"[가-힣]{1,6}(?:동|리|읍|면)")
# 번지 모순 검사는 **3자리 이상**에만 건다. "22-11" 같은 짧은 번호는 다른 동네와
# 우연히 겹쳐 정상 주소를 떨어뜨린다(실측: 양주시 고읍동 건이 평택시와 충돌 판정).
_BUNJI_RE = re.compile(r"\d{3,5}-\d{1,4}")
_FACIL_RE = re.compile(r"[가-힣]{2,8}(?:주차장|물류|모터스|정비|공업사|산업|센터)")
# 모델이 라벨 문구를 주소 앞에 붙여 오는 경우가 있다
# ("보관장소 - 경상북도 안동시…", "어선 보관장소 여수시 국동항")
_PREFIX_RE = re.compile(r"^\s*(?:어선|선박|차량|대상물건|본건)?\s*보관\s*장소\s*[-:·\s]*")


def clean_address(addr: str) -> str:
    return re.sub(r"\s+", " ", _PREFIX_RE.sub("", addr or "")).strip(" .,·-")


def accept(result: dict, known_gu: Optional[set] = None,
           court_sido: Optional[set] = None,
           dong_by_gu: Optional[dict] = None,
           place_index: Optional[dict] = None,
           gu_sido: Optional[dict] = None) -> dict:
    """**인쇄된 주소만** 채택한다. 모델이 '읽었다'는 주변 지명은 쓰지 않는다.

    ⚠ 왜 주변 지명을 버리는가 — 실측에서 충남 서산시 지도를 주고 물었더니 모델이
      `서대문구`·`영천동`·`서대문역`(서울 지명)을 "읽었다"고 답했다. **근거(evidence)
      자체가 지어내진다.** 근거를 요구하는 것만으로는 막을 수 없다.
      큰 글씨로 인쇄된 주소 문자열을 옮기는 것은 정확하지만(전주 건 완벽),
      작은 글자를 "읽어 보라"고 하면 그럴듯한 한국 지명을 만들어 낸다.

    `court_sido` 를 주면 법원이 다루는 시·도와 어긋나는 답을 버린다. 위치를
    **추정**하는 데 쓰지 않고, 명백한 모순을 **반증**하는 데만 쓴다.
    """
    out = {"addr": "", "level": "", "evidence": "", "why": ""}
    # ⚠ '본건' 라벨을 배제하지 않는다. **자동차는 부동산과 다르다** — 소재지가 물건에
    #   고정돼 있지 않으므로 차량의 물건 소재지가 곧 보관장소다(사용자 지적).
    #   실측도 이를 뒷받침한다: 2024타경51422의 '본건' 지도는 감정서 본문의
    #   보관장소(동문동)와 일치했고, 오히려 법원 API 값(율지8로 52)이 달랐다.
    #   대신 다른 가드(지명 어휘·법원 시·도·번지 모순)는 그대로 태운다.

    printed = result.get("printed_address")
    if not printed:
        labels = result.get("nearby_labels") or []
        out["why"] = ("주소가 인쇄돼 있지 않음"
                      + (f" (읽은 지명 {len(labels)}개는 신뢰할 수 없어 쓰지 않음)"
                         if labels else ""))
        return out

    printed = clean_address(printed)
    gus = _GU_RE.findall(printed)
    if not gus:
        # "호계동 1101번지" 처럼 동+번지는 있고 시만 없는 경우. 법원 관할 시·도 안에서
        # 그 동을 가진 시·군·구가 **유일할 때만** 보완한다(실측: 동/리 이름의 77%가
        # 시·도를 알면 유일해진다). 둘 이상이면 지어내지 않고 포기한다.
        dongs = [d for d in _DONG_RE.findall(printed)]
        if not (dongs and dong_by_gu and court_sido and gu_sido):
            out["why"] = "인쇄된 문자열에 시·군·구가 없음"
            return out
        cands = {g for g, ds in dong_by_gu.items()
                 if any(d in ds for d in dongs) and gu_sido.get(g) in court_sido}
        # 시/구 계층 중복 제거는 하지 않는다 — 애매하면 버린다
        if len(cands) != 1:
            out["why"] = (f"시·군·구 없음 — 법원 관할에서 후보 {len(cands)}개라 특정 불가"
                          if cands else "인쇄된 문자열에 시·군·구가 없음")
            return out
        g = next(iter(cands))
        printed = f"{g} {printed}"
        gus = [g]
        out["completed"] = g
    if known_gu and not any(g in known_gu for g in gus):
        out["why"] = f"'{gus[0]}' 는 아는 시·군·구가 아님"
        return out
    sd = sido_of(printed)
    if court_sido and sd and sd not in court_sido:
        out["why"] = f"법원 관할 시·도({'/'.join(sorted(court_sido))})와 어긋남: {sd}"
        return out
    addr = printed

    # ⚠ 시·군·구가 실재하고 법원 시·도와 맞아도 틀릴 수 있다 — '안양시 백석동 방성리'는
    #   둘 다 통과했지만 실제는 '양주시 백석읍 방성리'였다. 그 시·군·구에 그런 동이
    #   있는지까지 봐야 걸린다. 어휘는 비전 결과를 뺀 소스로만 만든다(순환 금지).
    if dong_by_gu:
        for g in gus:
            vocab = dong_by_gu.get(g)
            if not vocab or len(vocab) < 3:
                continue                     # 어휘가 빈약한 시군구는 판정하지 않는다
            unseen = [d for d in _DONG_RE.findall(addr) if d not in vocab and d != g]
            if unseen:
                out["why"] = f"{g} 에 '{unseen[0]}' 은(는) 확인되지 않는 지명"
                return out

    # 같은 번지·같은 시설명이 신뢰 소스에선 다른 시·군·구로 돼 있으면 하나는 틀렸다
    if place_index:
        for key, table in (("bunji", _BUNJI_RE), ("facil", _FACIL_RE)):
            idx = place_index.get(key) or {}
            for tok in table.findall(addr):
                seen = idx.get(tok)
                if seen and not (seen & set(gus)):
                    out["why"] = f"'{tok}' 은 신뢰 소스에서 {sorted(seen)} 로 돼 있음"
                    return out

    out.update(addr=addr, level="full", evidence=printed)
    return out


CONF_LABEL = {"full": "추정", "dong": "동 단위 추정", "gu": "구 단위 추정"}


def polite_sleep(seconds: float = 6.0) -> None:
    """외부 요청 사이 대기 (C.4: 5~10초)."""
    time.sleep(seconds)
