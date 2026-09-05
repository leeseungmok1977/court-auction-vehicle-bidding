#!/usr/bin/env bash
# ── Ubuntu 24.04 VM 초기 설치 (경매로 내차GET) — AWS EC2 / Oracle 등 공용 ──
#  사용법(VM에 SSH 접속 후):
#     git clone https://github.com/leeseungmok1977/court-auction-vehicle-bidding.git app
#     cd app && bash deploy/oracle_setup.sh [도메인(선택)]
#  도메인 없이 실행하면 IP로만 접속(HTTP). 도메인 주면 nginx server_name에 반영(HTTPS는 certbot 별도).
set -euo pipefail
DOMAIN="${1:-_}"
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"     # 이 저장소 루트(=app)
DATA_DIR="${APP_DIR}/data"
USER_NAME="$(whoami)"

echo "== 1) 패키지 설치 =="
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git nginx

echo "== 2) 파이썬 가상환경 + 의존성 =="
python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install --upgrade pip
"${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"
# 케이카 수집용 Playwright(선택 — 실패해도 앱은 정상, 케이카 수집만 영향)
"${APP_DIR}/.venv/bin/pip" install playwright \
  && "${APP_DIR}/.venv/bin/python" -m playwright install --with-deps chromium \
  || echo "[경고] Playwright 설치 실패 — 케이카 수집만 제한됨(엔카·나머지는 정상)"

mkdir -p "${DATA_DIR}"

echo "== 3) systemd 서비스 등록(상시 실행·자동 재시작) =="
sudo tee /etc/systemd/system/naechaget.service >/dev/null <<UNIT
[Unit]
Description=naechaget (court auction FastAPI)
After=network.target
[Service]
User=${USER_NAME}
WorkingDirectory=${APP_DIR}
Environment=DATA_DIR=${DATA_DIR}
Environment=PYTHONIOENCODING=utf-8
ExecStart=${APP_DIR}/.venv/bin/uvicorn web.app:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now naechaget

echo "== 4) nginx 리버스 프록시 =="
sudo tee /etc/nginx/sites-available/naechaget >/dev/null <<NGINX
server {
    listen 80;
    server_name ${DOMAIN};
    client_max_body_size 20m;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 180s;
    }
}
NGINX
sudo ln -sf /etc/nginx/sites-available/naechaget /etc/nginx/sites-enabled/naechaget
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

echo "== 5) 인스턴스 방화벽(iptables) 80/443 허용 =="
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT  || true
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT || true
sudo netfilter-persistent save 2>/dev/null || (sudo apt-get install -y iptables-persistent && sudo netfilter-persistent save) || true

echo ""
echo "✅ 설치 완료."
echo "   - 서버 상태:  sudo systemctl status naechaget"
echo "   - 데이터 위치: ${DATA_DIR}  (여기에 로컬 data 폴더의 auction.db·사진 업로드)"
echo "   - 업로드 후:  sudo systemctl restart naechaget"
echo "   - 접속 확인:  http://<VM_공인IP>/"
echo "   - HTTPS(도메인 연결 후): sudo apt install -y certbot python3-certbot-nginx && sudo certbot --nginx -d ${DOMAIN}"
