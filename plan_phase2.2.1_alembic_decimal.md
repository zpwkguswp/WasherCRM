# 실행 계획서 2.2.1: Alembic 베이스라인 + Decimal 타입 보정

**상태**: 🏗️ 진행 중
**담당**: Sonnet
**작업일**: 2026-05-12
**선행**: §2.2 PostgreSQL 전환 완료
**참조**: harnes.md (Alembic 격차 항목), §2.2 출력 Pydantic 경고

---

## 1. 목표
1. 현재 PG DB 상태를 베이스라인으로 잡고 **Alembic 마이그레이션 체계**를 정식 도입한다.
2. 금액 필드(`Payment.amount`, `Settlement.*_amount`)의 Python 타입 힌트를 `float`에서 `Decimal`로 보정해 Pydantic 직렬화 경고를 해소한다.

## 2. 작업 범위

### 2.1 Alembic 베이스라인 셋업
- 서버에서 `alembic init alembic` 실행
- `alembic.ini`의 `sqlalchemy.url`은 비워두고 `env.py`가 `.env`에서 읽도록 구성
- `env.py`에서 SQLModel.metadata 사용
- 베이스라인 마이그레이션 생성 후 `alembic stamp head`로 마킹 (실제 SQL 실행은 없음 — 이미 테이블이 존재)
- 향후 모델 변경은 `alembic revision --autogenerate` → `alembic upgrade head`로 일원화

### 2.2 Decimal 타입 보정 (4개 필드)
- `Payment.amount`: `float` → `Decimal`
- `Settlement.total_amount`: `float` → `Decimal`
- `Settlement.hq_commission`: `float` → `Decimal`
- `Settlement.branch_settlement_amount`: `float` → `Decimal`
- import 추가: `from decimal import Decimal`
- 컬럼 타입(`DECIMAL(12, 2)`)은 이미 정확하므로 DB 마이그레이션 불필요

### 2.3 (제외) commission_rate
- `Branch.commission_rate: float`은 비율(%)이므로 그대로 유지. 정산 계산 시 코드에서 Decimal로 변환.
- 이 결정은 §4.2 정산 알고리즘 작업에서 재검토.

## 3. 작업 순서

1. 로컬 `backend/app/models/domain.py` 편집 (Decimal import + 4개 필드 수정)
2. 변경된 파일을 서버에 scp 업로드
3. 서버에서 Alembic 셋업 스크립트 실행:
   - `alembic init alembic`
   - `env.py` 작성
   - `alembic revision --autogenerate -m "baseline"`
   - 생성된 마이그레이션 파일 검토 → 빈 파일이면 stamp, 변경이 있으면 사용자 검토
   - `alembic stamp head`
4. systemd로 백엔드 재기동
5. API 호출 → 응답 정상 + 로그에 Pydantic 경고 없는지 확인

## 4. 완료 조건 (AC)
- [ ] 서버에 `/home/ubuntu/backend/alembic/` 디렉토리 존재
- [ ] `/home/ubuntu/backend/alembic.ini` 존재
- [ ] `alembic current` → 베이스라인 리비전 표시
- [ ] `alembic history` → 베이스라인 1개 표시
- [ ] 백엔드 로그에 `PydanticSerializationUnexpectedValue` 경고 없음 (재시작 후 API 호출 시점 기준)
- [ ] `curl /api/v1/branches/` → HTTP 200, 응답 데이터 정상

## 5. 롤백 계획
- Alembic 셋업이 어그러지면 `rm -rf /home/ubuntu/backend/alembic/ /home/ubuntu/backend/alembic.ini` (현 시점엔 마이그레이션 실행하지 않으므로 DB 영향 없음)
- Decimal 변경은 git revert 또는 수동 되돌림

## 6. 후속 작업
- §4.1 정산 DB 스키마 재설계 — `Settlement` 컬럼 구조를 blueprint §7.1 기준으로 정비(`vat_amount` 추가 등). 이때부터 Alembic 마이그레이션 정식 사용.
