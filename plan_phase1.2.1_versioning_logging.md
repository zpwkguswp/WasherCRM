# 실행 계획서 1.2.1: 버저닝, 히스토리 관리 및 로그 시스템 구축

**상태**: 🏗️ 진행 중  
**담당**: Antigravity  
**작업 내용**: 코드 및 데이터의 이력 관리, 시스템 로그 및 DB 스키마 버저닝 체계 구축

---

## 1. 목표
- **코드 버저닝**: Git을 통한 버전 관리 외에, API 레벨에서의 버저닝(v1, v2) 체계 확립.
- **데이터 히스토리**: 주요 테이블의 변경 사항을 기록하는 `AuditLog` 시스템 구축.
- **DB 스키마 버저닝**: `Alembic`을 도입하여 DB 상태 변화를 추적하고 롤백 가능하게 함.
- **로그 관리**: 구조화된 로그(Structured Logging)를 통해 문제 발생 시 추적 용이성 확보.

## 2. 상세 설계

### 2.1 API 버저닝 전략
- URL 기반 버저닝 사용: `http://localhost:8000/api/v1/...`
- 새로운 요구사항 발생 시 v2 엔드포인트를 생성하여 하위 호환성 유지.

### 2.2 AuditLog (데이터 이력 관리)
- 모든 중요 엔티티의 CRUD 발생 시 변경 전/후 데이터를 `AuditLog` 테이블에 저장.
- 필드: `table_name`, `target_id`, `action (INSERT/UPDATE/DELETE)`, `payload (JSONB)`, `changed_by`, `created_at`.

### 2.3 Alembic (DB 마이그레이션)
- 테이블 구조 변경 시 SQL을 직접 날리지 않고, Alembic 스크립트를 통해 버전을 관리함.
- `alembic upgrade head`, `alembic downgrade -1` 명령어로 상태 제어.

### 2.4 로그 시스템
- Python `logging` 라이브러리를 확장하여 파일 및 콘솔에 로그 기록.
- 에러 발생 시 Traceback을 포함하여 상세 기록.

---

## 3. 테스트 및 검증 계획
- **Mock DB 테스트**: 실제 Postgres 연결 없이 SQLite(Memory)를 사용하여 모델과 로직의 정합성 검토.
- **인프라 검증**: 로컬 서버 환경에서의 성능 및 연결성 확인.
