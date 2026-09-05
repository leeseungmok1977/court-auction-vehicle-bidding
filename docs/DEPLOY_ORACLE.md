# Oracle Cloud "Always Free" VM 배포 — 무료·24시간·PC 무관

목표: 무료 상시 서버 + 고정 주소 확보 → 웹 상시 운영 + 안드로이드 앱(TWA)까지 연결.

역할 분담: **당신 = 오라클 가입·VM 생성·접속·데이터 업로드** / **나 = 서버 설치 자동화 스크립트**(`deploy/vm_setup.sh`) 제공.

---

## STEP 1. 오라클 클라우드 가입 (당신)
1. https://www.oracle.com/kr/cloud/free/ → "무료로 시작하기".
2. 이메일·전화 인증 + **신용/체크카드 인증**(본인확인용, **Always Free 자원은 청구 없음**).
3. 홈 리전(Region)은 가까운 곳(예: **South Korea Central (Chuncheon)** 또는 Seoul). ⚠️ 이후 무료 VM은 이 리전에서만.

## STEP 2. 무료 VM 생성 (당신)
콘솔 → **Compute → Instances → Create instance**
- **Image**: Canonical **Ubuntu 24.04**
- **Shape**: **VM.Standard.A1.Flex (ARM)** → OCPU **2**, 메모리 **12GB** (Always Free 범위: 4 OCPU·24GB)
  - ⚠️ A1이 "out of capacity"로 안 뜨면: 잠시 후 재시도하거나, 임시로 **VM.Standard.E2.1.Micro**(항상 가능하나 1GB로 케이카 수집엔 부족).
- **Boot volume**: 50GB
- **SSH keys**: "Paste public keys" 선택 → 내가 만들어 준 **공개키**(아래 STEP 5) 붙여넣기.
- Create → 잠시 후 인스턴스의 **Public IP** 확인.

## STEP 3. 네트워크 포트 열기 (당신)
인스턴스 → 서브넷 → **Security List** → **Add Ingress Rules**:
- Source `0.0.0.0/0`, TCP **80** (HTTP)
- Source `0.0.0.0/0`, TCP **443** (HTTPS)
(인스턴스 내부 iptables는 설치 스크립트가 자동 처리)

## STEP 4. (선택·권장) 무료 도메인 — DuckDNS
Play 스토어 앱(TWA)엔 고정 HTTPS 도메인이 필요. 도메인 구입이 부담되면 무료:
1. https://www.duckdns.org 로그인(구글 등) → 서브도메인 생성(예: `naechaget`).
2. current ip 칸에 **VM Public IP** 입력 → update. → `naechaget.duckdns.org` 로 접속 가능.
(도메인을 사면 그 도메인의 A레코드를 VM IP로 지정)

## STEP 5. 서버 접속 + 설치 (당신이 실행, 명령은 복붙)
```bash
# 내가 만들어 준 개인키로 접속 (키 파일 경로는 내가 알려줌)
ssh -i <개인키경로> ubuntu@<VM_공인IP>

# 저장소 받기 + 설치 스크립트 실행 (도메인 있으면 뒤에 붙임)
git clone https://github.com/leeseungmok1977/court-auction-vehicle-bidding.git app
cd app
bash deploy/vm_setup.sh naechaget.duckdns.org      # 도메인 없으면 인자 생략
```
스크립트가 파이썬·nginx·systemd·방화벽까지 자동 구성한다. 끝나면 `http://<VM_IP>/` 로 접속 확인.

## STEP 6. 데이터 업로드 (당신 — 로컬 PC에서)
서버는 처음엔 비어 있다. 로컬의 `data/`(DB·사진)를 VM으로 복사:
```bash
# DB(2MB) — 필수. 이것만 올려도 목록·분석·시세 나옴
scp -i <개인키경로> "data/auction.db" ubuntu@<VM_IP>:/home/ubuntu/app/data/

# 사진(~1.2GB) — 썸네일·뷰어용. _photo_work 제외하고 통째로
#  (windows면 WinSCP GUI로 data 폴더 업로드가 편함, _photo_work 폴더는 빼고)
```
업로드 후: `ssh ... "sudo systemctl restart naechaget"`

## STEP 7. HTTPS 발급 (도메인 있을 때)
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d naechaget.duckdns.org      # 이메일·약관 동의
```
→ `https://naechaget.duckdns.org` 완성. 이 주소로 [ANDROID.md](ANDROID.md)의 PWABuilder에 넣어 앱(.aab) 생성.

---

## 운영 메모
- 코드 업데이트:  `ssh ... "cd app && git pull && sudo systemctl restart naechaget"`
- 로그 보기:      `sudo journalctl -u naechaget -f`
- 케이카 수집:    VM에서 Playwright 설치가 됐으면 운영도구에서 실행 가능(1GB E2 micro면 메모리 부족 가능).
- 데이터 백업:    `data/auction.db` 를 주기적으로 로컬에 내려받아 보관.
- ⚠️ 준법: 공개 URL은 엔카/케이카 시세 상시 노출 사안 → 필요 시 로그인/접근제한 검토([compliance-review.md](compliance-review.md)).
