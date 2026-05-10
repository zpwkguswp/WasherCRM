# 🚀 WasherCRM AWS Startup & Maintenance Guide

본 문서는 WasherCRM의 AWS EC2 인프라 구축 정보와 서버 유지보수 방법을 설명합니다.

## 1. 서버 인프라 정보 (Current State)
*   **Public IP**: `13.124.100.75`
*   **Region**: `ap-northeast-2 (Seoul)`
*   **Instance Type**: `t3.micro` (Ubuntu 22.04 LTS)
*   **Security Group**: `WhiteOn-SG`
    *   Open Ports: 22 (SSH), 80 (HTTP), 443 (HTTPS), 8000 (Backend API)
*   **SSH Key**: `AWS_accesskey/WhiteOn-Key.pem`
*   **SSH User**: `ubuntu`

## 2. 서버 접속 방법 (SSH)
터미널(또는 PowerShell)에서 아래 명령어를 사용하여 접속할 수 있습니다.
```bash
ssh -i AWS_accesskey/WhiteOn-Key.pem ubuntu@13.124.100.75
```

## 3. 서비스 구성 및 경로
*   **Frontend (Static)**: `/home/ubuntu/www` (Nginx 호스팅)
*   **Backend (FastAPI)**: `/home/ubuntu/backend`
*   **Nginx Config**: `/etc/nginx/sites-available/washercrm`
*   **Backend Logs**: `/home/ubuntu/backend/uvicorn.log`

## 4. 유지보수 명령어 (SSH 접속 후 실행)

### 백엔드 서버 재시작
소스 코드를 수정하여 다시 배포한 경우 아래 명령어로 재시작합니다.
```bash
# 실행 중인 프로세스 종료
pkill -f uvicorn

# 백그라운드 재실행
cd /home/ubuntu/backend && nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > uvicorn.log 2>&1 &
```

### 로그 확인
실시간 에러나 접속 기록을 확인하고 싶을 때 사용합니다.
```bash
# 백엔드 로그 확인
tail -f /home/ubuntu/backend/uvicorn.log

# Nginx 에러 로그 확인
sudo tail -f /var/log/nginx/error.log
```

### Nginx 재시작
웹 서버 설정 변경 시 실행합니다.
```bash
sudo systemctl restart nginx
```

## 5. 데이터베이스 관리
*   **DB 경로**: `/home/ubuntu/backend/washer_crm.db` (SQLite)
*   로컬 데이터와 동기화가 필요한 경우 SCP를 사용하여 다운로드/업로드 하십시오.

---
**Last Updated**: 2026-05-10
**Owner**: WhiteOn HQ Admin
