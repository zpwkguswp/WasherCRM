#!/bin/bash
# Alembic 마이그레이션 파일 수정 + 재적용 (plan_phase4.1 후속)
# 문제:
#  1. import sqlmodel 누락 → NameError
#  2. branches.settlement_cycle NOT NULL + default 미설정 → ALTER 실패

set -e

cd /home/ubuntu/backend
source venv/bin/activate

MIG_FILE=$(ls alembic/versions/*settlement_redesign*.py | head -1)
echo "수정 대상: ${MIG_FILE}"
cp "${MIG_FILE}" "${MIG_FILE}.bak"

echo ""
echo "## [1/4] import sqlmodel 추가"
# import sqlalchemy as sa 아래에 import sqlmodel 추가 (없을 때만)
if ! grep -q "^import sqlmodel" "${MIG_FILE}"; then
  sed -i '/^import sqlalchemy as sa$/a import sqlmodel' "${MIG_FILE}"
  echo "import sqlmodel 추가됨"
else
  echo "import sqlmodel 이미 있음"
fi

echo ""
echo "## [2/4] branches.settlement_cycle에 server_default 추가"
# op.add_column('branches', sa.Column('settlement_cycle', ..., nullable=False))
# → server_default='WEEKLY' 추가
sed -i "s|sa.Column('settlement_cycle', sqlmodel.sql.sqltypes.AutoString(), nullable=False)|sa.Column('settlement_cycle', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='WEEKLY')|" "${MIG_FILE}"

echo "변경 결과 확인:"
grep "settlement_cycle" "${MIG_FILE}"

echo ""
echo "## [3/4] Alembic upgrade head 재시도"
alembic upgrade head 2>&1 | tail -15
echo ""
echo "현재 리비전:"
alembic current

echo ""
echo "## [4/4] DB 검증"
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
echo "--- branches.settlement_cycle 컬럼 + 기존 row 값 ---"
sudo -u postgres psql washercrm -c "SELECT column_name, data_type, column_default, is_nullable FROM information_schema.columns WHERE table_name='branches' AND column_name='settlement_cycle';"
sudo -u postgres psql washercrm -c "SELECT id, name, settlement_cycle FROM branches;"

echo ""
echo "## 백엔드 재기동"
truncate -s 0 /home/ubuntu/backend/uvicorn.log
sudo systemctl restart washercrm-backend
sleep 4
sudo systemctl status washercrm-backend --no-pager | head -10

echo ""
echo "--- API 호출 ---"
sleep 2
curl -sS -o /dev/null -w "GET /api/v1/branches/    → HTTP %{http_code}\n" http://127.0.0.1/api/v1/branches/
curl -sS -o /dev/null -w "GET /api/v1/restaurants/ → HTTP %{http_code}\n" http://127.0.0.1/api/v1/restaurants/
curl -sS -o /dev/null -w "GET /api/v1/payments/    → HTTP %{http_code}\n" http://127.0.0.1/api/v1/payments/

echo ""
echo "--- 백엔드 에러 검색 ---"
if grep -i "error\|exception\|traceback" /home/ubuntu/backend/uvicorn.log | grep -v "ROLLBACK\|sqlalchemy.engine" | head -5; then
  echo "⚠️  위 에러 라인 확인 필요"
else
  echo "✅ 에러 없음"
fi

echo ""
echo "===================================================="
echo "✅ 마이그레이션 수정 + 재적용 완료"
echo "===================================================="
