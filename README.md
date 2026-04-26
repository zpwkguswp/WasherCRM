# WasherCRM - 전국 세척기 통합 관리 플랫폼

본 프로젝트는 전국 단위의 세척기 판매, 수리(A/S), 세제 공급 및 부품 관리를 위한 FSM(Field Service Management) 플랫폼입니다.

---

## 🚀 시작하기 (Local Setup)

### 1. 전제 조건 (Prerequisites)
- **Python 3.10+** 설치
- **Docker Desktop** 설치 (권장)

### 2. 데이터베이스(DB) 실행
Docker가 설치되어 있다면, 프로젝트 루트 폴더에서 다음 명령어를 실행하여 PostgreSQL을 기동합니다.
```bash
docker compose up -d
```
*DB 접속 정보는 `backend/.env` 파일에서 확인 가능합니다.*

### 3. 백엔드 서버 설정 및 실행
```bash
# 1. 백엔드 폴더로 이동
cd backend

# 2. 가상환경 생성 및 활성화 (선택 사항)
python -m venv venv
source venv/bin/activate  # Mac/Linux
venv\Scripts\activate     # Windows

# 3. 필수 라이브러리 설치
pip install -r requirements.txt

# 4. 서버 실행
uvicorn app.main:app --reload
```

### 4. 코드 정합성 테스트 (Dry Run)
실제 DB 연결 없이 코드의 논리적 구조와 모델 관계가 정상인지 확인하려면 다음 명령어를 실행합니다.
```bash
cd backend
python tests/test_models.py
```

---

## 📂 주요 문서 (Documentation)
- [마스터 실행 계획서 (blueprint.md)](./blueprint.md)
- [이슈 및 금기 사항 (harnes.md)](./harnes.md)
- [DB 설계 계획서 (plan_phase1.1_schema.md)](./plan_phase1.1_schema.md)

---

## 🚫 금기 사항 (Anti-Patterns)
1. **No Dashboard-First**: 현장 앱 데이터가 먼저 쌓여야 함.
2. **No In-App Purchase**: 외부 PG사(포트원 등) 연동 필수.
3. **No Plan-less Development**: 모든 세부 작업 전 `plan_phaseX.X.md` 작성 필수.
