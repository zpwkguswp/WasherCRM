#!/bin/bash
# WasherCRM DB 마이그레이션 스크립트 (plan_phase2.2)
# SQLite → 네이티브 PostgreSQL + Alembic 셋업
# 실행: ssh로 ubuntu@13.124.100.75 접속 후 본 스크립트 실행

set -e
DATE_STR=$(date '+%Y%m%d_%H%M%S')

echo "===================================================="
echo "WasherCRM DB Migration — $(date '+%Y-%m-%d %H:%M:%S')"
echo "===================================================="

cd /home/ubuntu/backend

#######################################
# Step 1. SQLite 백업 및 현황 캡처
#######################################
echo ""
echo "## [1/9] SQLite 백업 및 현황 캡처"
mkdir -p /home/ubuntu/backend/backup
if [ -f /home/ubuntu/backend/washer_crm.db ]; then
  cp /home/ubuntu/backend/washer_crm.db "/home/ubuntu/backend/backup/washer_crm_${DATE_STR}.db"
  echo "백업 완료: /home/ubuntu/backend/backup/washer_crm_${DATE_STR}.db"

  # sqlite3 도구 (없으면 설치)
  if ! command -v sqlite3 >/dev/null 2>&1; then
    sudo apt install -y sqlite3 >/dev/null 2>&1 || true
  fi

  echo "--- 기존 SQLite 테이블 row 수 ---"
  for table in branches restaurants service_requests payments request_media settlements; do
    count=$(sqlite3 /home/ubuntu/backend/washer_crm.db "SELECT COUNT(*) FROM ${table}" 2>/dev/null || echo "N/A")
    printf "  %-20s : %s\n" "${table}" "${count}"
  done
else
  echo "(SQLite 파일 없음 — fresh 설치로 진행)"
fi

#######################################
# Step 2. PostgreSQL 설치
#######################################
echo ""
echo "## [2/9] PostgreSQL 설치"
if dpkg -l | grep -q "^ii  postgresql "; then
  echo "이미 설치됨 — 스킵"
else
  sudo apt update -qq
  sudo apt install -y postgresql postgresql-contrib libpq-dev
fi
sudo systemctl enable postgresql >/dev/null 2>&1
sudo systemctl start postgresql
sudo systemctl is-active postgresql

#######################################
# Step 3. DB 및 사용자 생성
#######################################
echo ""
echo "## [3/9] DB 및 사용자 생성"
PG_PASS=$(openssl rand -hex 24)

# 기존 객체 있으면 정리 (멱등)
sudo -u postgres psql -tAc "DROP DATABASE IF EXISTS washercrm;" >/dev/null
sudo -u postgres psql -tAc "DROP USER IF EXISTS whiteon;" >/dev/null

sudo -u postgres psql <<EOF
CREATE USER whiteon WITH PASSWORD '${PG_PASS}';
CREATE DATABASE washercrm OWNER whiteon ENCODING 'UTF8' LC_COLLATE='C.UTF-8' LC_CTYPE='C.UTF-8' TEMPLATE template0;
GRANT ALL PRIVILEGES ON DATABASE washercrm TO whiteon;
EOF

# uuid-ossp 확장 활성화 (plan_phase1.1에서 사용)
sudo -u postgres psql -d washercrm -c 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp";' >/dev/null
echo "DB 'washercrm', 사용자 'whiteon' 생성 완료"

# 연결 검증
PGPASSWORD="${PG_PASS}" psql -h 127.0.0.1 -U whiteon -d washercrm -c "SELECT version();" | head -3

#######################################
# Step 4. .env 업데이트
#######################################
echo ""
echo "## [4/9] .env 업데이트"
if [ ! -f /home/ubuntu/backend/.env.sqlite.bak ]; then
  cp /home/ubuntu/backend/.env /home/ubuntu/backend/.env.sqlite.bak
  echo ".env.sqlite.bak 백업 생성"
else
  echo ".env.sqlite.bak 이미 존재 — 유지"
fi

NEW_URL="postgresql+psycopg2://whiteon:${PG_PASS}@127.0.0.1:5432/washercrm"
# DATABASE_URL 라인 교체 (없으면 추가)
if grep -q '^DATABASE_URL=' /home/ubuntu/backend/.env; then
  sed -i.tmp "s|^DATABASE_URL=.*|DATABASE_URL=${NEW_URL}|" /home/ubuntu/backend/.env
  rm -f /home/ubuntu/backend/.env.tmp
else
  echo "DATABASE_URL=${NEW_URL}" >> /home/ubuntu/backend/.env
fi
chmod 600 /home/ubuntu/backend/.env
echo "현재 .env (DB URL 마스킹):"
sed -E 's/(DATABASE_URL=postgresql[^@]*@)/\1***MASKED***/' /home/ubuntu/backend/.env | grep -v -E '^(PORTONE|AWS_SECRET)' | head -10

#######################################
# Step 5. Alembic 셋업
#######################################
echo ""
echo "## [5/9] Alembic 셋업"
cd /home/ubuntu/backend
source venv/bin/activate

if [ ! -d alembic ]; then
  alembic init alembic
  echo "alembic 디렉토리 생성됨"
else
  echo "alembic 디렉토리 이미 존재 — 유지"
fi

# alembic.ini의 sqlalchemy.url을 비워서 env.py가 .env에서 읽도록
sed -i 's|^sqlalchemy.url = .*|sqlalchemy.url =|' alembic.ini

# env.py 덮어쓰기
cat > alembic/env.py << 'PYEOF'
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from dotenv import load_dotenv
from sqlmodel import SQLModel

# 모델 import — metadata에 등록
from app.models import domain  # noqa: F401

load_dotenv()

config = context.config
db_url = os.getenv("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
PYEOF
echo "alembic/env.py 작성 완료"

#######################################
# Step 6. 초기 마이그레이션 생성
#######################################
echo ""
echo "## [6/9] 초기 마이그레이션 생성"
# 기존 versions 정리 (재실행 대응)
rm -f alembic/versions/*.py 2>/dev/null
alembic revision --autogenerate -m "initial schema from models" 2>&1 | tail -20

echo ""
echo "생성된 마이그레이션:"
ls -la alembic/versions/

#######################################
# Step 7. 마이그레이션 적용
#######################################
echo ""
echo "## [7/9] 마이그레이션 적용 (alembic upgrade head)"
alembic upgrade head 2>&1 | tail -10
echo ""
echo "현재 리비전:"
alembic current

#######################################
# Step 8. 테이블 검증
#######################################
echo ""
echo "## [8/9] 테이블 검증"
PGPASSWORD="${PG_PASS}" psql -h 127.0.0.1 -U whiteon -d washercrm -c "\dt"
echo ""
echo "주요 테이블 row 수 (모두 0이어야 정상):"
for table in branches restaurants service_requests payments; do
  count=$(PGPASSWORD="${PG_PASS}" psql -h 127.0.0.1 -U whiteon -d washercrm -tAc "SELECT COUNT(*) FROM ${table}" 2>/dev/null || echo "N/A")
  printf "  %-20s : %s\n" "${table}" "${count}"
done

#######################################
# Step 9. 백엔드 재기동 및 검증
#######################################
echo ""
echo "## [9/9] 백엔드 재기동 및 검증"
sudo systemctl restart washercrm-backend
sleep 4
sudo systemctl status washercrm-backend --no-pager | head -12

echo ""
echo "--- API 호출 테스트 ---"
sleep 2
curl -sS -o /dev/null -w "GET /api/v1/branches/ → HTTP %{http_code}\n" http://127.0.0.1/api/v1/branches/ || true
curl -sS -o /dev/null -w "GET /api/v1/restaurants/ → HTTP %{http_code}\n" http://127.0.0.1/api/v1/restaurants/ || true
curl -sS -o /dev/null -w "GET / → HTTP %{http_code}\n" http://127.0.0.1/ || true

echo ""
echo "--- 최근 백엔드 로그 (마지막 15줄) ---"
tail -n 15 /home/ubuntu/backend/uvicorn.log 2>/dev/null || echo "(로그 없음)"

echo ""
echo "===================================================="
echo "✅ DB 마이그레이션 완료"
echo ""
echo "📌 백업 위치 (롤백 시 사용):"
echo "    SQLite: /home/ubuntu/backend/backup/washer_crm_${DATE_STR}.db"
echo "    .env:   /home/ubuntu/backend/.env.sqlite.bak"
echo ""
echo "📌 PostgreSQL 접속 (디버깅용):"
echo "    sudo -u postgres psql washercrm"
echo "===================================================="
