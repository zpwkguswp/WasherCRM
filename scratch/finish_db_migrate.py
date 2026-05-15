"""
DB 마이그레이션 마무리 스크립트 (plan_phase2.2)
- 백업 SQLite에서 실데이터를 PostgreSQL로 복사
- SQLModel.metadata.create_all로 PG에 테이블 생성
- 멱등 실행 가능

실행: /home/ubuntu/backend 안에서 venv 활성화 후
    python /tmp/finish_db_migrate.py
"""
from __future__ import annotations

import os
import sys
import glob
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlmodel import Session, SQLModel, select
from dotenv import load_dotenv

# ------------------------------------------------------------
# 설정
# ------------------------------------------------------------
BACKEND_DIR = Path("/home/ubuntu/backend")
load_dotenv(BACKEND_DIR / ".env")

PG_URL = os.getenv("DATABASE_URL")
if not PG_URL or "postgresql" not in PG_URL:
    print(f"❌ DATABASE_URL이 PostgreSQL이 아닙니다: {PG_URL}", file=sys.stderr)
    sys.exit(1)

# 백업 SQLite 파일 자동 탐지 (가장 최근)
backup_files = sorted(glob.glob(str(BACKEND_DIR / "backup" / "washer_crm_*.db")))
if not backup_files:
    print("⚠️  SQLite 백업 파일 없음. fresh 스키마만 생성합니다.")
    SQLITE_URL = None
else:
    sqlite_path = backup_files[-1]
    SQLITE_URL = f"sqlite:///{sqlite_path}"
    print(f"📦 백업 소스: {sqlite_path}")

# ------------------------------------------------------------
# 모델 import (이때 SQLModel.metadata에 등록됨)
# ------------------------------------------------------------
sys.path.insert(0, str(BACKEND_DIR))
from app.models.domain import (  # noqa: E402
    Branch, Restaurant, ServiceRequest, RequestMedia, Payment, Settlement
)

# ------------------------------------------------------------
# 1. PostgreSQL에 테이블 생성
# ------------------------------------------------------------
print("\n## [Step A] PostgreSQL에 테이블 생성")
pg_engine = create_engine(PG_URL)
SQLModel.metadata.create_all(pg_engine)

# 생성된 테이블 확인
with pg_engine.connect() as conn:
    result = conn.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    ))
    tables = [row[0] for row in result]
print(f"  생성된 테이블 ({len(tables)}): {', '.join(tables)}")

# ------------------------------------------------------------
# 2. 데이터 마이그레이션
# ------------------------------------------------------------
print("\n## [Step B] 데이터 마이그레이션")

if SQLITE_URL is None:
    print("  (백업 없음 — 마이그레이션 스킵)")
    sys.exit(0)

sqlite_engine = create_engine(SQLITE_URL)

# 의존성 순서대로 마이그레이션
MODELS_IN_ORDER = [
    ("branches", Branch),
    ("restaurants", Restaurant),
    ("service_requests", ServiceRequest),
    ("request_media", RequestMedia),
    ("payments", Payment),
    ("settlements", Settlement),
]

# PG에 이미 데이터가 있는지 확인 (재실행 시 중복 방지)
with Session(pg_engine) as pg_session:
    existing_count = pg_session.exec(select(Branch)).all()
    if existing_count:
        print(f"  ⚠️  PostgreSQL에 이미 데이터 존재 (branches: {len(existing_count)}건). 마이그레이션 스킵.")
        print("     강제 재마이그레이션이 필요하면 모든 테이블을 TRUNCATE한 뒤 재실행하세요.")
        sys.exit(0)

total_migrated = 0
for table_name, ModelClass in MODELS_IN_ORDER:
    try:
        with Session(sqlite_engine) as src:
            rows = src.exec(select(ModelClass)).all()
        if not rows:
            print(f"  {table_name:20s}: 0건 (소스에 데이터 없음)")
            continue

        with Session(pg_engine) as dst:
            for row in rows:
                # SQLModel 객체를 dict로 풀어 새 객체 생성 (세션 충돌 회피)
                data = row.model_dump()
                new_row = ModelClass(**data)
                dst.add(new_row)
            dst.commit()
        print(f"  {table_name:20s}: {len(rows)}건 이관 완료 ✓")
        total_migrated += len(rows)
    except Exception as e:
        print(f"  {table_name:20s}: ❌ 실패 — {type(e).__name__}: {e}")
        # 다음 테이블 계속 시도 (부분 성공 허용)

print(f"\n✅ 총 {total_migrated}건 이관 완료")

# ------------------------------------------------------------
# 3. 최종 검증
# ------------------------------------------------------------
print("\n## [Step C] PostgreSQL row 수 검증")
with Session(pg_engine) as session:
    for table_name, ModelClass in MODELS_IN_ORDER:
        count = len(session.exec(select(ModelClass)).all())
        print(f"  {table_name:20s}: {count}건")

print("\n✅ 데이터 마이그레이션 완료")
