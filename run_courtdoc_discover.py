"""법원 전자문서(감정평가서·현황조사서·매각물건명세서) 엔드포인트 발견 — 수동 캡처(강화판).

C.4-3(추측 금지): 문서 뷰어 경로를 임의 생성하지 않고, 실제 브라우저에서 문서를 열어
그 **응답(content-type: application/pdf 등)** 을 가로채 실제 다운로드 URL·파라미터를 확인한다.

사용자 터미널:  python run_courtdoc_discover.py
  1) 크롬이 열리면 법원경매정보에서 자동차 물건 상세(사건내역)로 이동
  2) 하단 [감정평가서] / [현황조사서] 버튼을 클릭해 PDF 모달을 띄운다
  3) (원하면 다른 물건도) 그러면 PDF를 내려준 요청이 캡처된다
  180초 뒤 결과를 출력한다. 그 출력을 붙여넣어 주면 다운로드+인앱 뷰어를 구현한다.
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

WAIT_SEC = 180
DOC_HINT = ("pdf", "ecdoc", "spcfc", "doc", "image", "nas_e_image", "octet",
            "file", "report", "print", "atch", "download", "retrieve")


def main():
    from playwright.sync_api import sync_playwright
    hits = []

    def on_resp(resp):
        try:
            u = resp.url
            if "courtauction.go.kr" not in u.lower() and "scourt" not in u.lower():
                return
            ct = (resp.headers.get("content-type") or "").lower()
            is_doc = ("pdf" in ct or "octet" in ct or ct.startswith("image/")
                      or "application/download" in ct
                      or any(t in u.lower() for t in DOC_HINT))
            if not is_doc:
                return
            clen = resp.headers.get("content-length") or "?"
            hits.append({"method": resp.request.method, "url": u[:220], "ct": ct or "?",
                         "len": clen, "post": (resp.request.post_data or "")[:400],
                         "status": resp.status})
        except Exception:
            pass

    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=False)
        ctx = b.new_context(viewport={"width": 1400, "height": 950}, accept_downloads=True)
        ctx.on("response", on_resp)   # 모든 페이지·팝업·새창의 응답 포착
        pg = ctx.new_page()
        try:
            pg.goto("https://www.courtauction.go.kr/pgj/index.on", wait_until="domcontentloaded", timeout=40000)
        except Exception:
            pass
        print("\n>>> 크롬이 열렸습니다. 자동차 물건 상세(사건내역)로 이동한 뒤")
        print(">>> 하단 [감정평가서]·[현황조사서] 버튼을 눌러 PDF를 띄우세요.")
        print(f">>> {WAIT_SEC}초간 요청을 기록합니다...\n")
        pg.wait_for_timeout(WAIT_SEC * 1000)
        b.close()

    print("=== 문서(PDF/이미지/전자문서) 응답 (중복 URL 병합) ===")
    seen = set()
    for h in sorted(hits, key=lambda x: ("pdf" not in x["ct"], x["url"])):
        key = h["url"].split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        print(f"\n[{h['status']}] {h['method']} ({h['ct']}, {h['len']}B)")
        print(f"  {h['url']}")
        if h["post"]:
            print(f"  POST: {h['post']}")
    if not hits:
        print("(문서 응답 미포착 — 버튼을 눌러 PDF가 실제로 떴는지, content-type 확인 필요)")
    print("\n※ content-type이 application/pdf 인 요청의 URL(과 POST body)을 알려주시면 다운로드+뷰어를 구현합니다.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"[중단] {type(e).__name__}: {e}")
