#!/bin/bash
# WasherCRM AWS EC2 상태 점검 스크립트 (2026-05-12)
# 사용법:
#   1) PowerShell에서 SSH 접속:
#        ssh -i AWS_accesskey/WhiteOn-Key.pem ubuntu@13.124.100.75
#   2) 접속 후 아래 블록 전체를 복사해서 터미널에 붙여넣기
#   3) 출력 결과 전체를 복사해서 Claude에게 붙여넣기

echo "===================================================="
echo "WasherCRM EC2 Audit Report"
echo "Date: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "Host: $(hostname) / $(whoami)"
echo "===================================================="

echo ""
echo "## 1. OS & Resources"
echo "--- uname ---"
uname -a
echo "--- uptime ---"
uptime
echo "--- disk (df -h) ---"
df -h / /home 2>/dev/null
echo "--- memory (free -m) ---"
free -m
echo "--- cpu count ---"
nproc

echo ""
echo "## 2. Backend Process (uvicorn / fastapi)"
echo "--- ps aux | grep uvicorn ---"
ps aux | grep -i uvicorn | grep -v grep
echo "--- ps aux | grep python ---"
ps aux | grep -i python | grep -v grep | head -10
echo "--- listening ports ---"
sudo ss -tlnp 2>/dev/null | head -20 || ss -tln | head -20

echo ""
echo "## 3. Backend Files"
echo "--- /home/ubuntu structure ---"
ls -la /home/ubuntu/ 2>/dev/null
echo "--- /home/ubuntu/backend (if exists) ---"
ls -la /home/ubuntu/backend/ 2>/dev/null | head -30
echo "--- backend .env (sensitive lines masked) ---"
if [ -f /home/ubuntu/backend/.env ]; then
  sed -E 's/(SECRET|KEY|PASSWORD|TOKEN)=.*/\1=***MASKED***/I' /home/ubuntu/backend/.env
else
  echo "(no .env found at /home/ubuntu/backend/.env)"
fi

echo ""
echo "## 4. Database"
echo "--- SQLite file present? ---"
ls -la /home/ubuntu/backend/*.db 2>/dev/null || echo "(no .db file)"
echo "--- PostgreSQL service status ---"
systemctl is-active postgresql 2>/dev/null && echo "postgresql: active (system service)" || echo "postgresql system service: inactive or not installed"
echo "--- Postgres process? ---"
ps aux | grep -i postgres | grep -v grep | head -5
echo "--- Docker containers (if any) ---"
docker ps 2>/dev/null || echo "(docker not running or not installed)"
echo "--- docker compose files in /home/ubuntu ---"
find /home/ubuntu -maxdepth 3 -name 'docker-compose*.yml' 2>/dev/null

echo ""
echo "## 5. Nginx / Web Server"
echo "--- nginx status ---"
systemctl is-active nginx 2>/dev/null
echo "--- nginx config (washercrm site) ---"
ls -la /etc/nginx/sites-available/ 2>/dev/null
echo "--- enabled sites ---"
ls -la /etc/nginx/sites-enabled/ 2>/dev/null
echo "--- nginx config dump (washercrm only) ---"
sudo cat /etc/nginx/sites-available/washercrm 2>/dev/null | head -60

echo ""
echo "## 6. Static Frontend"
echo "--- /home/ubuntu/www ---"
ls -la /home/ubuntu/www/ 2>/dev/null | head -20

echo ""
echo "## 7. SSL / HTTPS"
echo "--- certbot certs (if any) ---"
sudo ls -la /etc/letsencrypt/live/ 2>/dev/null || echo "(no letsencrypt certs)"
echo "--- listening on 443? ---"
sudo ss -tlnp 2>/dev/null | grep ':443 ' || echo "(nothing on 443)"

echo ""
echo "## 8. Logs (last 20 lines)"
echo "--- uvicorn.log tail ---"
tail -n 20 /home/ubuntu/backend/uvicorn.log 2>/dev/null || echo "(no uvicorn.log)"
echo "--- nginx error tail ---"
sudo tail -n 10 /var/log/nginx/error.log 2>/dev/null

echo ""
echo "===================================================="
echo "End of Audit. Copy all output back to Claude."
echo "===================================================="
