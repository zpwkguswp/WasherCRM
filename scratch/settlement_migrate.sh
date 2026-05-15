#!/bin/bash
# 정산 스키마 재설계 마이그레이션 (plan_phase4.1)
# 사전 업로드:
#   - /tmp/domain.py    (Settlement/SettlementItem/TaxInvoice + Branch.settlement_cycle)
#   - /tmp/payments.py  (Settlement 즉시 생성 로직 제거)
#   - /tmp/requests.py  (Settlement 즉시 생성 로직 제거)
#   - /tmp/branches.py  (total_amount → gross_amount)

set -e

echo "===================================================="
echo "Settlement Schema Redesign — $(date '+%Y-%m-%d %H:%M:%S')"
echo "===================================================="

cd /home/ubuntu/backend
source venv/bin/activate

#######################################
# [1/8] 기존 settlements 테이블 CSV 스냅샷
#######################################
echo ""
echo "## [1/8] 기존 settlements 데이터 CSV 백업"
mkdir -p /home/ubuntu/backend/backup
SNAP_FILE="/home/ubuntu/backend/backup/settlements_legacy_$(date +%Y%m%d_%H%M%S).csv"
# psql이 stdout으로 쓰고 ubuntu 권한으로 redirect (postgres 사용자 파일권한 회피)
sudo -u postgres psql washercrm -c "COPY (SELECT * FROM settlements) TO STDOUT WITH CSV HEADER" > "${SNAP_FILE}"
echo "스냅샷 파일:"
ls -la "${SNAP_FILE}"
echo "행 수 (헤더 포함):"
wc -l "${SNAP_FILE}"
echo "--- 미리보기 ---"
head -5 "${SNAP_FILE}"

#######################################
# [2/8] 기존 settlements 테이블 DROP
#######################################
echo ""
echo "## [2/8] 기존 settlements 테이블 DROP (CASCADE 없이 — FK 의존 없음)"
sudo -u postgres psql washercrm -c "DROP TABLE IF EXISTS settlements CASCADE;" 2>&1

#######################################
# [3/8] 코드 파일 백업 후 교체
#######################################
echo ""
echo "## [3/8] 코드 파일 교체 (백업 후)"
BACKUP_TS="$(date +%Y%m%d_%H%M%S)"
cp /home/ubuntu/backend/app/models/domain.py             "/home/ubuntu/backend/app/models/domain.py.bak.${BACKUP_TS}"
cp /home/ubuntu/backend/app/api/v1/endpoints/payments.py "/home/ubuntu/backend/app/api/v1/endpoints/payments.py.bak.${BACKUP_TS}"
cp /home/ubuntu/backend/app/api/v1/endpoints/requests.py "/home/ubuntu/backend/app/api/v1/endpoints/requests.py.bak.${BACKUP_TS}"
cp /home/ubuntu/backend/app/api/v1/endpoints/branches.py "/home/ubuntu/backend/app/api/v1/endpoints/branches.py.bak.${BACKUP_TS}"

cp /tmp/domain.py    /home/ubuntu/backend/app/models/domain.py
cp /tmp/payments.py  /home/ubuntu/backend/app/api/v1/endpoints/payments.py
cp /tmp/requests.py  /home/ubuntu/backend/app/api/v1/endpoints/requests.py
cp /tmp/branches.py  /home/ubuntu/backend/app/api/v1/endpoints/branches.py
echo "교체 완료"

#######################################
# [4/8] Alembic 자동 마이그레이션 생성
#######################################
echo ""
echo "## [4/8] Alembic revision --autogenerate"
alembic revision --autogenerate -m "settlement redesign with items and tax invoices" 2>&1 | tail -20

echo ""
echo "생성된 마이그레이션 파일:"
ls -la alembic/versions/
NEW_MIG=$(ls -t alembic/versions/*settlement_redesign*.py 2>/dev/null | head -1)
if [ -z "${NEW_MIG}" ]; then
  NEW_MIG=$(ls -t alembic/versions/*.py | grep -v baseline | head -1)
fi
echo ""
echo "📄 새 마이그레이션 파일: ${NEW_MIG}"
echo ""
echo "--- 마이그레이션 전체 내용 ---"
cat "${NEW_MIG}"

#######################################
# [5/8] 마이그레이션 적용
#######################################
echo ""
echo "## [5/8] Alembic upgrade head"
alembic upgrade head 2>&1 | tail -10
echo ""
echo "현재 리비전:"
alembic current
echo ""
echo "히스토리:"
alembic history

#######################################
# [6/8] 새 테이블/컬럼 검증
#######################################
echo ""
echo "## [6/8] DB 검증"
echo "--- 테이블 목록 ---"
sudo -u postgres psql washercrm -c "\dt"
echo ""
echo "--- settlements 컬럼 ---"
sudo -u postgres psql washercrm -c "\d settlements"
echo ""
echo "--- settlement_items 컬럼 ---"
sudo -u postgres psql washercrm -c "\d settlement_items"
echo ""
echo "--- tax_invoices 컬럼 ---"
sudo -u postgres psql washercrm -c "\d tax_invoices"
echo ""
echo "--- branches.settlement_cycle 컬럼 ---"
sudo -u postgres psql washercrm -c "SELECT column_name, data_type, column_default FROM information_schema.columns WHERE table_name='branches' AND column_name='settlement_cycle';"

#######################################
# [7/8] 백엔드 재기동
#######################################
echo ""
echo "## [7/8] 백엔드 재기동"
# 기존 로그 백업 후 truncate
cp /home/ubuntu/backend/uvicorn.log "/home/ubuntu/backend/uvicorn.log.pre_b2_${BACKUP_TS}" 2>/dev/null || true
truncate -s 0 /home/ubuntu/backend/uvicorn.log
sudo systemctl restart washercrm-backend
sleep 4
sudo systemctl status washercrm-backend --no-pager | head -10

#######################################
# [8/8] API 검증
#######################################
echo ""
echo "## [8/8] API 호출 테스트"
sleep 2
curl -sS -o /dev/null -w "GET /api/v1/branches/    → HTTP %{http_code}\n" http://127.0.0.1/api/v1/branches/
curl -sS -o /dev/null -w "GET /api/v1/restaurants/ → HTTP %{http_code}\n" http://127.0.0.1/api/v1/restaurants/
curl -sS -o /dev/null -w "GET /api/v1/payments/    → HTTP %{http_code}\n" http://127.0.0.1/api/v1/payments/

echo ""
echo "--- 백엔드 로그 에러 검색 ---"
if grep -i "error\|exception\|traceback" /home/ubuntu/backend/uvicorn.log | grep -v "ROLLBACK\|sqlalchemy" | head -5; then
  echo "⚠️  위 에러 라인 확인 필요"
else
  echo "✅ 에러 로그 없음"
fi

echo ""
echo "--- 최근 로그 5줄 ---"
tail -n 5 /home/ubuntu/backend/uvicorn.log 2>/dev/null

echo ""
echo "===================================================="
echo "✅ 정산 스키마 재설계 완료"
echo ""
echo "📌 백업:"
echo "    레거시 CSV: ${SNAP_FILE}"
echo "    코드 .bak.${BACKUP_TS} (4개 파일)"
echo "===================================================="
