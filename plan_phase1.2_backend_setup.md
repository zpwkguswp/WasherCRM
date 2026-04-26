# 실행 계획서 1.2: FastAPI 백엔드 초기 세팅 및 DB 환경 구축

**상태**: 🏗️ 진행 중  
**담당**: Antigravity  
**작업 내용**: 백엔드 개발을 위한 기본 프로젝트 구조 설정 및 로컬 DB 환경(Docker) 구축

---

## 1. 목표
- FastAPI 기반의 확장 가능한 프로젝트 구조 구축.
- Docker를 이용한 독립적이고 재현 가능한 PostgreSQL 환경 설정.
- DB 마이그레이션(Alembic) 및 기본 API 뼈대 작성.

## 2. 프로젝트 디렉토리 구조
```text
WasherCRM/
├── backend/                # 백엔드 루트
│   ├── app/                # 어플리케이션 코드
│   │   ├── main.py         # 진입점
│   │   ├── core/           # 설정, 보안 등 핵심 로직
│   │   ├── db/             # DB 세션 및 엔진 설정
│   │   ├── models/         # SQLModel 정의
│   │   ├── api/            # API 엔드포인트 (v1, v2 등)
│   │   └── schemas/        # Pydantic 스키마
│   ├── tests/              # 테스트 코드
│   ├── alembic/            # DB 마이그레이션 파일
│   ├── requirements.txt    # 의존성 목록
│   └── .env                # 환경 변수
├── docker-compose.yml      # 인프라 구성 (Postgres)
└── blueprint.md            # 마스터 계획서
```

## 3. 주요 기술 스택 및 라이브러리
- **Framework**: FastAPI
- **Server**: Uvicorn
- **ORM**: SQLModel (SQLAlchemy + Pydantic)
- **DB Driver**: psycopg2-binary
- **Migration**: Alembic
- **Environment**: Docker (PostgreSQL 15)

## 4. 상세 실행 단계

### Step 1: Docker를 이용한 PostgreSQL 기동
- `docker-compose.yml` 파일을 작성하여 로컬에서 DB를 즉시 실행할 수 있게 함.
- 포트: 5432, 데이터 영속성을 위한 볼륨 설정 포함.

### Step 2: 의존성 설치 및 가상환경 세팅
- `requirements.txt` 작성 및 설치.

### Step 3: 백엔드 기본 구조 생성
- `main.py` 및 기본 디렉토리 생성.
- DB 연결 테스트용 헬스체크 API 구현.

---

## 5. 비고
- 고성능 로컬 서버(Ryzen 9 등) 환경을 고려하여 대량의 요청 처리가 가능하도록 최적화된 설정을 기본으로 함.
