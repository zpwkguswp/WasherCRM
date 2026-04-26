# 실행 계획서 1.2.3: 지사 및 식당 관리 기능 개발

**상태**: 🏗️ 준비 중  
**담당**: Antigravity  
**작업 내용**: 서비스 운영의 핵심 주체인 지사(Branch)와 식당(Restaurant)을 관리하는 API 구축

---

## 1. 목표
- 전국 지사 정보를 등록, 수정, 조회할 수 있는 기능 구현.
- 서비스를 이용하는 식당 정보를 관리하는 기능 구현.
- 고장 접수 시 식당의 정보를 바탕으로 관할 지사를 식별할 수 있는 기초 데이터 확보.

## 2. 개발 상세

### 2.1 API 엔드포인트 설계

#### 지사 관리 (`/api/v1/branches`)
- `POST /api/v1/branches`: 신규 지사 등록 (이름, 지역 코드, 수수료율 등).
- `GET /api/v1/branches`: 전체 지사 목록 조회.
- `GET /api/v1/branches/{id}`: 특정 지사 상세 정보.
- `PATCH /api/v1/branches/{id}`: 지사 정보 수정 (매니저 연락처, 수수료율 등).

#### 식당 관리 (`/api/v1/restaurants`)
- `POST /api/v1/restaurants`: 신규 식당 등록 (이름, 주소, 연락처 등).
- `GET /api/v1/restaurants`: 식당 목록 조회.
- `GET /api/v1/restaurants/{id}`: 식당 상세 정보 및 해당 식당의 과거 A/S 이력 포함 조회.

### 2.2 핵심 구현 포인트
- **데이터 이력 관리**: 지사의 수수료율 변경이나 식당의 주소 변경 등 모든 수정 사항은 `AuditLog`에 자동 기록.
- **관계형 데이터 응답**: 식당 상세 조회 시, 해당 식당이 이전에 접수한 A/S 요청(`ServiceRequest`) 목록을 함께 반환하여 히스토리 파악 가능케 함.

---

## 3. 작업 순서
1.  **Schemas 추가**: `app/schemas/domain.py`에 Branch와 Restaurant를 위한 Create/Update 스키마 정의.
2.  **Endpoints 구현**:
    *   `app/api/v1/endpoints/branches.py` 생성 및 구현.
    *   `app/api/v1/endpoints/restaurants.py` 생성 및 구현.
3.  **Router 등록**: `app/api/v1/api.py`에 새로운 라우터들 연결.
4.  **검증**: Swagger UI(http://127.0.0.1:8888/docs)에서 실제 데이터 등록 테스트.

---

## 5. 지사 삭제 가이드 (Safety Guide)

데이터의 중요성을 고려하여 지사 삭제 시에는 강력한 안전장치가 적용되어 있습니다.

### 5.1 삭제 조건 및 방법
- **API**: `DELETE /api/v1/branches/{id}`
- **안전 코드**: 요청 시 `confirmation_code` 파라미터에 반드시 **`DELETE_CONFIRM`**을 입력해야 합니다.
- **제한 사항**: 해당 지사에 할당된 A/S 요청(`ServiceRequest`) 내역이 하나라도 남아있다면 삭제가 불가능합니다. (데이터 무결성 보호)

---

## 6. 문제점 및 해결 방법 (Retrospective)

이 단계 진행 중 발생한 주요 이슈와 해결 방법입니다.

### 6.1 `Optional` 임포트 누락으로 인한 서버 다운
- **문제**: API 인자에 `Optional` 타입을 사용하면서 상단에 `from typing import Optional`을 누락하여 `NameError` 발생.
- **해결**: 모든 API 파일 상단에 필요한 타입 도구들을 미리 체크하고 임포트함.

### 6.2 검색 필터의 필요성 (UUID의 한계)
- **문제**: 지사를 찾을 때 긴 UUID를 매번 복사해야 하는 번거로움 발생.
- **해결**: 지사명(name)과 매니저 전화번호(phone)로 검색할 수 있는 기능을 백엔드와 Admin UI에 추가하여 편의성 대폭 개선.

### 6.3 Admin UI의 데이터 반영 지연
- **문제**: 수정 후 성공 메시지는 뜨지만 화면에 즉시 반영되지 않아 혼란 발생.
- **해결**: 수정 성공 시 서버로부터 받은 최신 데이터를 화면에 즉시 덮어씌우는 로직을 추가하여 '즉각적인 피드백' 확보.
