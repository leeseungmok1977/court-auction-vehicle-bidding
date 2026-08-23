"""운영 웹도구 실행 진입점.

    python run_web.py
    → 브라우저에서 http://127.0.0.1:8000 접속

포트 변경: python run_web.py 8080
"""

import sys

import uvicorn

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"\n  법원경매 차량 입찰가 산정 — 웹도구")
    print(f"  브라우저에서 http://127.0.0.1:{port} 접속\n")
    uvicorn.run("web.app:app", host="127.0.0.1", port=port, reload=False)
