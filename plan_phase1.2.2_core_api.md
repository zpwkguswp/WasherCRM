# 실행 계획서 1.2.2: 코어 API 엔드포인트 개발 (FastAPI)

**상태**: 🏗️ 진행 중  
**담당**: Antigravity  
**작업 내용**: 식당의 A/S 접수 및 상태 관리를 위한 핵심 REST API 개발

---

## 1. 목표
- 식당 점주가 고장 증상을 접수할 수 있는 API 구현.
- 서비스 요청의 상태(접수, 출동, 완료)를 변경하는 로직 구현.
- 지사가 자신에게 할당된 요청 목록을 조회하는 기능 구현.
- 모든 데이터 변경 시 `AuditLog`에 이력을 자동 기록.

## 2. 개발 상세

### 2.1 Pydantic 스키마 정의 (`app/schemas/`)
- **RequestCreate**: 접수 시 필요한 필드 (restaurant_id, category, description 등).
- **RequestRead**: 클라이언트에게 응답할 필드 (상태, 시간 포함).
- **StatusUpdate**: 상태 변경 시 필요한 필드.

### 2.2 API 엔드포인트 설계 (`app/api/v1/`)
- `POST /api/v1/requests`: A/S 접수.
- `GET /api/v1/requests`: 목록 조회 (상태별, 식당별 필터링 포함).
- `GET /api/v1/requests/{id}`: 상세 조회.
- `PATCH /api/v1/requests/{id}`: 상태 변경 및 지사 배정.

### 2.3 핵심 로직 (CRUD)
- `AuditLog` 연동: 상태가 변경될 때마다 `AuditLog` 테이블에 스냅샷 저장.
- SLA 추적: 상태가 `ASSIGNED` 또는 `COMPLETED`로 변경될 때 해당 타임스탬프 업데이트.

---

## 3. 테스트 계획
- **Postman/Swagger 테스트**: 서버 기동 후 `/docs`를 통해 API 직접 호출 및 DB 데이터 확인.
- **단위 테스트**: `test_models.py`를 확장하여 API 요청 시나리오 테스트.

---

## 5. 시행착오 및 해결 (Troubleshooting)

작업 중 발생한 주요 문제와 해결 방법을 기록하여 향후 인프라 구축 시 참고합니다.

### 5.1 인프라 및 환경 관련
*   **문제 1 (Docker 인식)**: CMD에서 `docker` 명령어가 인식되지 않음.
    *   **해결**: 윈도우 환경 변수 설정에 따라 PowerShell에서는 정상 작동함을 확인. 이후 모든 인프라 작업은 **PowerShell**에서 수행.
*   **문제 2 (포트 충돌 - WinError 10013)**: 8000번 포트 사용 시 권한 에러 발생.
    *   **해결**: 윈도우 시스템(WSL2/Hyper-V) 예약 포트 문제로 판단되어, 서버 포트를 **8888**로 변경하여 해결.
*   **문제 3 (파이썬 버전 혼선)**: MSYS2 파이썬이 우선순위를 점유하여 패키지 설치 에러 발생.
    *   **해결**: 윈도우 파이썬 런처인 `py` 명령어를 사용하여 표준 Python 3.12를 명시적으로 실행.

### 5.2 코드 및 DB 관련
*   **문제 1 (JSONB 호환성)**: SQLite 테스트 환경에서 PostgreSQL 전용 `JSONB` 타입을 지원하지 않음.
    *   **해결**: `sqlalchemy.dialects.postgresql.JSONB` 대신 범용 `sqlalchemy.JSON`으로 변경하여 SQLite와 PostgreSQL 모두 호환되도록 수정.
*   **문제 2 (패키지 누락)**: `python-dotenv` 등 필수 라이브러리 미설치로 서버 기동 실패.
    *   **해결**: `py -m pip install -r requirements.txt` 명령을 통해 의존성 전체 설치.
