#!/bin/bash
# Alembic 베이스라인 셋업 + Decimal 모델 적용 (plan_phase2.2.1)
# 사전 업로드 필요:
#   - /tmp/domain.py        (수정된 모델 — Decimal 타입 적용)
#   - /tmp/alembic_env.py   (Alembic env.py 내용)

set -e

echo "===================================================="
echo "Alembic Baseline Setup — $(date '+%Y-%m-%d %H:%M:%S')"
echo "===================================================="

cd /home/ubuntu/backend
source venv/bin/activate

#######################################
# [1/7] 기존 모델 파일 백업 후 교체
#######################################
echo ""
echo "## [1/7] domain.py 교체 (Decimal 타입 적용)"
cp /home/ubuntu/backend/app/models/domain.py "/home/ubuntu/backend/app/models/domain.py.bak.$(date +%Y%m%d_%H%M%S)"
cp /tmp/domain.py /home/ubuntu/backend/app/models/domain.py
echo "domain.py 교체 완료"
diff_lines=$(diff /home/ubuntu/backend/app/models/domain.py.bak.* /home/ubuntu/backend/app/models/domain.py 2>/dev/null | wc -l || echo "0")
echo "변경된 라인 수: ${diff_lines}"

#######################################
# [2/7] Alembic init
#######################################
echo ""
echo "## [2/7] Alembic 초기화"
if [ ! -d alembic ]; then
  alembic init alembic
  echo "alembic 디렉토리 생성됨"
else
  echo "alembic 디렉토리 이미 존재 — 유지 (env.py만 재작성)"
fi

#######################################
# [3/7] alembic.ini 설정 (sqlalchemy.url 비우기)
#######################################
echo ""
echo "## [3/7] alembic.ini 조정"
# sqlalchemy.url 라인을 비워서 env.py가 .env에서 읽도록
sed -i 's|^sqlalchemy.url = .*|sqlalchemy.url =|' alembic.ini
grep '^sqlalchemy.url' alembic.ini

#######################################
# [4/7] env.py 교체
#######################################
echo ""
echo "## [4/7] alembic/env.py 교체"
cp /tmp/alembic_env.py /home/ubuntu/backend/alembic/env.py
echo "env.py 작성 완료"

#######################################
# [5/7] 베이스라인 마이그레이션 생성
#######################################
echo ""
echo "## [5/7] 베이스라인 마이그레이션 생성 (autogenerate)"
# 기존 versions 디렉토리 정리
rm -f alembic/versions/*.py 2>/dev/null
alembic revision --autogenerate -m "baseline from existing schema" 2>&1 | tail -15

echo ""
echo "생성된 마이그레이션 파일:"
ls -la alembic/versions/
echo ""
echo "--- 마이그레이션 내용 미리보기 ---"
MIG_FILE=$(ls alembic/versions/*.py | head -1)
echo "파일: ${MIG_FILE}"
echo ""
# upgrade() 함수 내용만 추출
awk '/^def upgrade/,/^def downgrade/' "${MIG_FILE}" | head -40

#######################################
# [6/7] stamp head (실제 SQL 실행 X — 베이스라인 마킹만)
#######################################
echo ""
echo "## [6/7] alembic stamp head (DB에는 SQL 적용 안 함)"
alembic stamp head
echo ""
echo "현재 리비전:"
alembic current

#######################################
# [7/7] 백엔드 재기동 및 검증
#######################################
echo ""
echo "## [7/7] 백엔드 재기동"
sudo systemctl restart washercrm-backend
sleep 4
sudo systemctl status washercrm-backend --no-pager | head -10

# uvicorn 로그를 새로 시작하기 위해 기존 로그 잘라내기 (백업)
echo "" >> /home/ubuntu/backend/uvicorn.log  # ensure file exists
cp /home/ubuntu/backend/uvicorn.log "/home/ubuntu/backend/uvicorn.log.pre_b4_$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
truncate -s 0 /home/ubuntu/backend/uvicorn.log

# API 호출
echo ""
echo "--- API 호출 ---"
sleep 2
curl -sS -o /dev/null -w "GET /api/v1/branches/    → HTTP %{http_code}\n" http://127.0.0.1/api/v1/branches/
curl -sS -o /dev/null -w "GET /api/v1/restaurants/ → HTTP %{http_code}\n" http://127.0.0.1/api/v1/restaurants/
# 모든 settlement 응답도 한 번 호출 (Decimal 경고 발생 지점)
curl -sS -o /dev/null -w "GET /api/v1/settlements/  → HTTP %{http_code}\n" http://127.0.0.1/api/v1/settlements/ 2>/dev/null || echo "(settlements 엔드포인트 없음)"
curl -sS -o /dev/null -w "GET /api/v1/payments/     → HTTP %{http_code}\n" http://127.0.0.1/api/v1/payments/ 2>/dev/null || echo "(payments 엔드포인트 없음)"

echo ""
echo "--- 백엔드 로그 (Pydantic 경고 검색) ---"
sleep 1
if grep -q "PydanticSerializationUnexpectedValue" /home/ubuntu/backend/uvicorn.log; then
  echo "⚠️  Pydantic 경고 여전히 존재:"
  grep "PydanticSerializationUnexpectedValue" /home/ubuntu/backend/uvicorn.log | head -5
else
  echo "✅ Pydantic 직렬화 경고 없음"
fi

echo ""
echo "--- 최근 로그 마지막 10줄 ---"
tail -n 10 /home/ubuntu/backend/uvicorn.log 2>/dev/null

echo ""
echo "===================================================="
echo "✅ Alembic 베이스라인 + Decimal 타입 적용 완료"
echo ""
echo "📌 향후 모델 변경 시 워크플로우:"
echo "    1) 모델 수정"
echo "    2) cd /home/ubuntu/backend && source venv/bin/activate"
echo "    3) alembic revision --autogenerate -m '변경 설명'"
echo "    4) 생성된 마이그레이션 파일 검토"
echo "    5) alembic upgrade head"
echo "    6) sudo systemctl restart washercrm-backend"
echo "===================================================="
