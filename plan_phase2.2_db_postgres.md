# 실행 계획서 2.2: DB를 PostgreSQL로 통일 (네이티브 설치)

**상태**: 🏗️ 진행 중
**담당**: Sonnet
**작업일**: 2026-05-12
**선행**: §2.1 EC2 점검 완료, §2.1.5 보안 강화 완료
**관련 문서**: blueprint §3.2, harnes.md (Alembic 격차 항목)

---

## 1. 목표
- AWS EC2 백엔드의 DB를 SQLite에서 PostgreSQL로 전환한다.
- Alembic 마이그레이션 체계를 정식 도입한다 (현재 코드에 부재).
- 결제·정산 트래픽이 들어와도 안전한 동시성 구조를 갖춘다.

## 2. 방향 결정 근거
| 옵션 | 채택 여부 | 사유 |
| :--- | :--- | :--- |
| A. 네이티브 PostgreSQL (apt) | **✅ 채택** | t3.micro 914MB RAM에 최적. 외부 비용 없음. RDS는 결제 트래픽 시점에 재검토. |
| B. Docker 컨테이너 PostgreSQL | ❌ | Docker 데몬 메모리 오버헤드(100~200MB)가 부담. 사용자도 서버에 Docker 미사용. |
| C. AWS RDS db.t4g.micro | ❌ (현 시점) | 월 ~$15 비용, VPC 구성 추가. 트래픽 발생 시점에 이전. |

## 3. 작업 순서

### Step 1: SQLite 백업 & 현황 캡처
- `/home/ubuntu/backend/washer_crm.db` → `/home/ubuntu/backend/backup/washer_crm_20260512.db`
- 현재 테이블별 row 수 출력 (마이그레이션 전후 비교용)

### Step 2: PostgreSQL 설치 및 기동
```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable postgresql
sudo systemctl start postgresql
```

### Step 3: DB 및 사용자 생성
- DB명: `washercrm`
- 사용자: `whiteon` (제한된 권한)
- 비밀번호: 스크립트 실행 시 랜덤 생성 → .env에만 저장
```sql
CREATE USER whiteon WITH PASSWORD '<random>';
CREATE DATABASE washercrm OWNER whiteon ENCODING 'UTF8';
GRANT ALL PRIVILEGES ON DATABASE washercrm TO whiteon;
```

### Step 4: .env 업데이트
- 기존: `DATABASE_URL=sqlite:///washer_crm.db`
- 변경: `DATABASE_URL=postgresql+psycopg2://whiteon:<password>@localhost:5432/washercrm`
- 변경 전 `.env`도 `.env.sqlite.bak`로 백업

### Step 5: Alembic 셋업
```bash
cd /home/ubuntu/backend
source venv/bin/activate
alembic init alembic  # alembic 디렉토리 생성
```
- `alembic.ini`에 `sqlalchemy.url`을 `.env`에서 읽도록 수정
- `alembic/env.py`에 SQLModel metadata import 추가

### Step 6: 초기 마이그레이션 생성 및 적용
```bash
alembic revision --autogenerate -m "initial schema from models"
alembic upgrade head
```

### Step 7: 백엔드 재기동 및 검증
- `init_db()`의 `metadata.create_all` 호출은 Alembic으로 대체되므로 향후 제거 검토 (이번 단계에서는 유지하되 충돌 시 우회).
- `sudo systemctl restart washercrm-backend`
- API 호출 테스트

### Step 8: 데이터 이관 결정
- 현재 SQLite는 172KB로 거의 비어있고 테스트 데이터로 추정 → **PostgreSQL은 fresh 시작**, SQLite는 백업만 보존.
- 만약 실데이터가 발견되면 별도 단계로 처리(파이썬 스크립트로 직접 옮김).

## 4. 완료 조건 (AC)
- [ ] `sudo systemctl status postgresql` → active
- [ ] `psql -U whiteon -d washercrm -c "\\dt"` → branches, restaurants, service_requests, payments 등 테이블 존재
- [ ] `alembic current` → 초기 리비전 헤드 표시
- [ ] `curl http://13.124.100.75/api/v1/branches/` → HTTP 200 (빈 배열도 OK)
- [ ] 백엔드 로그(`/home/ubuntu/backend/uvicorn.log`)에 DB connection 에러 없음
- [ ] `/home/ubuntu/backend/backup/washer_crm_20260512.db` 백업 파일 존재
- [ ] `.env.sqlite.bak` 존재 (롤백용)

## 5. 롤백 계획
1. `cp .env.sqlite.bak .env` — DB URL을 SQLite로 복원
2. `sudo systemctl restart washercrm-backend`
3. PostgreSQL은 그대로 두어도 무해 (백엔드가 안 봄)

## 6. 위험 요소 및 대응
| 위험 | 영향 | 대응 |
| :--- | :--- | :--- |
| Alembic `--autogenerate`가 일부 컬럼 누락(특히 enum, JSONB) | 마이그레이션 후 컬럼 미존재 | 첫 적용 후 모든 테이블 컬럼을 `\\d+` 로 검증 |
| `init_db()`의 PG 전용 SQL(`split_part`)이 빈 DB에서 에러 | 첫 부팅 실패 | try/except로 이미 감싸져 있음. 로그 경고만 발생 |
| PostgreSQL 기본 인코딩이 UTF-8 아닐 경우 한글 깨짐 | 데이터 손실 | `CREATE DATABASE ... ENCODING 'UTF8' LC_COLLATE='C.UTF-8'` 명시 |
| 백엔드 메모리 + PG 메모리 합산이 914MB 초과 | OOM | swap 4GB가 받침. 초과 시 t3.small 업그레이드 (§2.4 앞당김) |

## 7. 후속 작업
- §2.3 HTTPS 적용 (도메인 확보 후)
- §2.4 t3.small 업그레이드 — 결제 모듈 도입 직전
- Phase B (인증 시스템) 진입 가능
