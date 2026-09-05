# AWS EC2 배포 — 서울 리전 (경매로 내차GET)

무료 조건: **t3.micro(1GB)는 12개월 무료**, 이후 유료(~월 $8~9). 평생 무료가 필요하면 Oracle([DEPLOY_ORACLE.md](DEPLOY_ORACLE.md)).
더 간단한 대안: **Lightsail**(고정IP 포함, 월 $5, 첫 3개월 무료) — 아래는 EC2 기준.

역할: **당신 = EC2 생성·접속·데이터 업로드** / **나 = 설치 자동화 스크립트 `deploy/vm_setup.sh`**(AWS Ubuntu에서 그대로 동작).

---

## STEP 1. EC2 인스턴스 시작
콘솔 → **EC2 → 인스턴스 시작(Launch instance)** (리전: **아시아 태평양(서울) ap-northeast-2**)
- **이름**: `naechaget`
- **AMI**: **Ubuntu Server 24.04 LTS** (64비트 x86)
- **인스턴스 유형**: **t3.micro** (프리 티어 사용 가능)

## STEP 2. 키 페어(로그인)
- **"새 키 페어 생성"** → 이름 `naechaget`, 유형 **ED25519**, 형식 **.pem** → 생성 시 `.pem` 자동 다운로드.
- 이 파일로 SSH 접속(잘 보관, 재발급 불가). 예: `C:\Users\14ZB95N\Downloads\naechaget.pem`

## STEP 3. 네트워크(보안 그룹)
"편집" → 인바운드 규칙:
- **SSH (22)** — 소스: 내 IP
- **HTTP (80)** — 소스: Anywhere(0.0.0.0/0)
- **HTTPS (443)** — 소스: Anywhere(0.0.0.0/0)

## STEP 4. 스토리지
- **30 GiB, gp3** (프리티어 범위)

→ **인스턴스 시작**.

## STEP 5. ⭐ 고정 IP (탄력적 IP) — 필수
EC2 → **탄력적 IP(Elastic IP)** → **할당** → 그 IP를 방금 인스턴스에 **연결**.
- 안 하면 인스턴스 중지/시작 때 공인IP가 바뀌어 도메인·앱이 깨집니다.
- 실행 중 인스턴스에 연결돼 있으면 **무료**.

## STEP 6. 접속 + 설치 (SSH, 복붙)
```bash
# 윈도우 PowerShell/터미널에서 (.pem 경로는 본인 다운로드 위치로)
icacls C:\Users\14ZB95N\Downloads\naechaget.pem /inheritance:r /grant:r "%USERNAME%:R"   # 키 권한(윈도우)
ssh -i C:\Users\14ZB95N\Downloads\naechaget.pem ubuntu@<탄력적IP>

# VM 안에서:
git clone https://github.com/leeseungmok1977/court-auction-vehicle-bidding.git app
cd app && bash deploy/vm_setup.sh naechaget.duckdns.org      # 도메인 없으면 인자 생략
```
스크립트가 파이썬·nginx·상시실행(systemd)·방화벽까지 자동 구성. 끝나면 `http://<탄력적IP>/` 접속 확인.

## STEP 7. 데이터 업로드 (로컬 PC에서)
```bash
# DB(2MB) — 필수. 이것만 올려도 목록·분석·시세 나옴
scp -i <키.pem> data\auction.db ubuntu@<탄력적IP>:/home/ubuntu/app/data/
# 사진(~1.2GB) — WinSCP GUI로 data 폴더 업로드 권장(_photo_work 폴더는 제외)
```
업로드 후: `ssh -i <키.pem> ubuntu@<탄력적IP> "sudo systemctl restart naechaget"`

## STEP 8. 도메인 + HTTPS
1. **DuckDNS**([duckdns.org](https://www.duckdns.org)) 서브도메인 → **탄력적 IP** 지정(예: `naechaget.duckdns.org`).
2. VM에서 HTTPS 발급:
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d naechaget.duckdns.org
```
→ `https://naechaget.duckdns.org` 완성 → [ANDROID.md](ANDROID.md)의 PWABuilder에 넣어 안드로이드 앱(.aab) 생성.

---

## 운영 메모
- 코드 업데이트: `ssh ... "cd app && git pull && sudo systemctl restart naechaget"`
- 로그: `sudo journalctl -u naechaget -f`
- 비용주의: 12개월 후 t3.micro 과금 시작 → 필요 시 Lightsail 전환/중지. 데이터 이탈(egress)은 월 100GB 무료.
- 케이카 수집은 제가 이 개발환경에서 돌려 DB에 반영 → t3.micro(1GB)로도 웹 서빙 충분.
- ⚠️ 준법: 공개 URL은 엔카/케이카 시세 상시노출 사안 → 필요 시 접근제한 검토([compliance-review.md](compliance-review.md)).
