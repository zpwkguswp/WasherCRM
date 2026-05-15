#!/bin/bash
# WasherCRM 보안 강화 스크립트 (plan_phase2.1.5)
# 실행 위치: EC2 ubuntu@13.124.100.75
# 사용법:
#   type C:\Users\zpwkg\Documents\WasherCRM\scratch\harden_20260512.sh | `
#     ssh -i C:\Users\zpwkg\Documents\WasherCRM\AWS_accesskey\WhiteOn-Key.pem `
#         ubuntu@13.124.100.75 "tr -d '\r' | bash -s" | `
#     Out-File -Encoding utf8 C:\Users\zpwkg\Documents\WasherCRM\scratch\harden_20260512_output.txt

set -e  # 에러 발생 시 중단
echo "===================================================="
echo "WasherCRM Security Hardening — $(date '+%Y-%m-%d %H:%M:%S')"
echo "===================================================="

echo ""
echo "## [1/6] 기존 uvicorn 프로세스 종료"
pkill -f 'uvicorn app.main:app' 2>/dev/null || true
sleep 2
ps aux | grep -i uvicorn | grep -v grep || echo "(uvicorn 프로세스 없음 — 정상)"

echo ""
echo "## [2/6] systemd 서비스 파일 작성"
sudo tee /etc/systemd/system/washercrm-backend.service > /dev/null << 'EOF'
[Unit]
Description=WasherCRM FastAPI Backend
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/backend
Environment="PATH=/home/ubuntu/backend/venv/bin"
ExecStart=/home/ubuntu/backend/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
StandardOutput=append:/home/ubuntu/backend/uvicorn.log
StandardError=append:/home/ubuntu/backend/uvicorn.log
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
echo "systemd unit 파일 작성 완료"

echo ""
echo "## [3/6] systemd 서비스 활성화 및 기동"
sudo systemctl daemon-reload
sudo systemctl enable washercrm-backend.service
sudo systemctl start washercrm-backend.service
sleep 3
sudo systemctl status washercrm-backend.service --no-pager | head -15

echo ""
echo "## [4/6] 바인딩 확인 (127.0.0.1:8000 만 보여야 함)"
sudo ss -tlnp | grep ':8000' || echo "(8000 포트 LISTEN 없음 — 문제!)"

echo ""
echo "## [5/6] 권한 강화 및 정리"
echo "--- serviceAccountKey.json 권한 600 ---"
chmod 600 /home/ubuntu/backend/serviceAccountKey.json
ls -la /home/ubuntu/backend/serviceAccountKey.json
echo "--- trading_bot.zip 삭제 ---"
rm -f /home/ubuntu/trading_bot.zip
echo "삭제 완료"
echo "--- venv_win 삭제 ---"
rm -rf /home/ubuntu/backend/venv_win
echo "삭제 완료"

echo ""
echo "## [6/6] 로컬 헬스체크 (Nginx 경유)"
curl -sS -o /dev/null -w "HTTP code: %{http_code}\n" http://127.0.0.1/api/v1/branches/ 2>&1 || echo "(API 호출 실패 — 백엔드 또는 라우팅 확인 필요)"
curl -sS -o /dev/null -w "Frontend HTTP: %{http_code}\n" http://127.0.0.1/ 2>&1

echo ""
echo "## 정리 후 디스크 상태"
df -h / | tail -1
free -m | head -2

echo ""
echo "===================================================="
echo "✅ 서버 측 보안 강화 완료"
echo ""
echo "⚠️  남은 작업 (AWS 콘솔 또는 CLI):"
echo "  WhiteOn-SG 보안그룹에서 8000 inbound 규칙을 제거하세요."
echo "===================================================="
