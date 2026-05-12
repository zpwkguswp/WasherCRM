#!/bin/bash
# DB 마이그레이션 마무리 (Step 5 이후를 대체)
# Python 헬퍼로 테이블 생성 + 데이터 이관 후 백엔드 재기동

set -e

echo "===================================================="
echo "WasherCRM DB Migration — FINISH"
echo "Date: $(date '+%Y-%m-%d %H:%M:%S')"
echo "===================================================="

cd /home/ubuntu/backend
source venv/bin/activate

#######################################
# Step A. python-dotenv 확인 및 마이그레이션 실행
#######################################
echo ""
echo "## [A] Python 마이그레이션 헬퍼 실행"
python /tmp/finish_db_migrate.py
RC=$?
if [ $RC -ne 0 ]; then
  echo "❌ Python 헬퍼 실패 (exit $RC) — 중단"
  exit $RC
fi

#######################################
# Step B. 백엔드 재기동 (PostgreSQL 연결)
#######################################
echo ""
echo "## [B] 백엔드 재기동 (systemd)"
sudo systemctl restart washercrm-backend
sleep 4
sudo systemctl status washercrm-backend --no-pager | head -12

#######################################
# Step C. API 검증
#######################################
echo ""
echo "## [C] API 호출 테스트"
sleep 2
curl -sS -o /dev/null -w "GET /api/v1/branches/    → HTTP %{http_code}\n" http://127.0.0.1/api/v1/branches/ || true
curl -sS -o /dev/null -w "GET /api/v1/restaurants/ → HTTP %{http_code}\n" http://127.0.0.1/api/v1/restaurants/ || true
curl -sS -o /dev/null -w "GET /                    → HTTP %{http_code}\n" http://127.0.0.1/ || true

# 실제 응답 내용 확인 (몇 줄만)
echo ""
echo "--- /api/v1/branches/ 응답 (처음 200자) ---"
curl -sS http://127.0.0.1/api/v1/branches/ 2>&1 | head -c 200
echo ""

#######################################
# Step D. 백엔드 로그 점검
#######################################
echo ""
echo "## [D] 백엔드 로그 (마지막 25줄)"
tail -n 25 /home/ubuntu/backend/uvicorn.log 2>/dev/null || echo "(로그 없음)"

#######################################
# Step E. 메모리·디스크 현황
#######################################
echo ""
echo "## [E] 시스템 현황"
free -m | head -2
df -h / | tail -1

echo ""
echo "===================================================="
echo "✅ DB 마이그레이션 완료"
echo ""
echo "📌 백업:"
echo "    SQLite: /home/ubuntu/backend/backup/washer_crm_*.db"
echo "    .env:   /home/ubuntu/backend/.env.sqlite.bak"
echo ""
echo "📌 PostgreSQL 직접 접속 (디버깅용):"
echo "    sudo -u postgres psql washercrm -c '\\dt'"
echo "===================================================="
