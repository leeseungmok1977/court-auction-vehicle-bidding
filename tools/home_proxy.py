#!/usr/bin/env python3
"""집 회선 경유 프록시(F안) — 엔카 전용 HTTP CONNECT 프록시.

배경: 2026-09 엔카(api.encar.com)가 AWS 서버 IP를 HTTP 407로 차단해 시세 수집이 멈췄다.
이 스크립트를 **한국 가정용 회선의 PC**에서 띄우고, home_tunnel.bat의 역방향 SSH 터널로
EC2의 127.0.0.1:18080 → 이 프록시(127.0.0.1:8888)를 연결하면, 서버의 **엔카 요청만** 집 IP로
나간다. 사이트 IP·DNS·법원 수집은 전혀 건드리지 않는다(무중단).

보안:
- 127.0.0.1에만 바인딩 — LAN·인터넷에 노출되지 않는다(EC2는 SSH 터널을 통해서만 도달).
- 허용 호스트(encar.com 계열)만 중계 — 다른 곳으로의 중계 요청은 403.
- 표준 라이브러리만 사용(설치 불필요), 저장·로깅 최소.
"""
import select
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BIND = ("127.0.0.1", 8888)
ALLOWED_SUFFIXES = ("encar.com",)          # api.encar.com, www.encar.com …


def _allowed(host: str) -> bool:
    h = host.lower().strip("[]")
    return any(h == s or h.endswith("." + s) for s in ALLOWED_SUFFIXES)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):   # 한 줄 요약만
        sys.stderr.write("[proxy] " + (fmt % args) + "\n")

    def do_CONNECT(self):
        host, _, port = self.path.partition(":")
        if not _allowed(host):
            self.send_error(403, "host not allowed")
            return
        try:
            remote = socket.create_connection((host, int(port or 443)), timeout=30)
        except OSError as e:
            self.send_error(502, f"connect failed: {e}")
            return
        self.send_response(200, "Connection Established")
        self.end_headers()
        self.close_connection = True
        self._pipe(self.connection, remote)

    def do_GET(self):   # 엔카는 HTTPS(CONNECT)만 사용 — 평문 중계는 열지 않는다
        self.send_error(405, "CONNECT only")

    @staticmethod
    def _pipe(a: socket.socket, b: socket.socket) -> None:
        socks = [a, b]
        try:
            while True:
                r, _, x = select.select(socks, [], socks, 90)
                if x or not r:
                    return
                for s in r:
                    data = s.recv(65536)
                    if not data:
                        return
                    (b if s is a else a).sendall(data)
        except OSError:
            pass
        finally:
            for s in socks:
                try:
                    s.close()
                except OSError:
                    pass


if __name__ == "__main__":
    srv = ThreadingHTTPServer(BIND, Handler)
    srv.daemon_threads = True
    print(f"[proxy] listening on {BIND[0]}:{BIND[1]}  allowed={ALLOWED_SUFFIXES}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
