# 📅 WasherCRM 개발 작업 일정표 (Work Schedule)

이 문서는 프로젝트의 진행 상황을 추적하기 위한 체크리스트입니다. 각 단계 완료 시 `[x]`로 표시합니다.

---

## 🛠️ Phase 0: 기반 인프라 구축 (완료)
- [x] PostgreSQL 마이그레이션 (SQLite → PostgreSQL)
- [x] Docker 기반 DB 컨테이너 환경 구축
- [x] HQ 대시보드 성과 지표 소수점 포맷팅 최적화
- [x] 불필요한 대용량 파일 정리 및 용량 확보

## 🚨 Phase 0.5: SLA 측정 시스템 (긴급 백로그 — Phase 1과 병행)
> [!IMPORTANT]
> 현재 `backend/app/api/v1/endpoints/requests.py:175-176`은 `assigned_at` 타임스탬프만 기록하며, 경과시간 계산·HQ 조회용 엔드포인트·임계치 경고 로직이 전부 없음. `harnes.md` 금기사항 #4를 직접적으로 위반하는 상태. 인증 시스템(Phase 1) 작업 중 함께 마무리할 것.

- [ ] **[AI/backend-db]** `service_requests`에 `acknowledged_at` 필드 추가 (push 수신 vs 수락 분리 측정용) — Alembic migration 포함
- [ ] **[AI/backend-db]** SLA 계산 헬퍼: `(assigned_at − created_at)`, `(completed_at − assigned_at)` 컬럼 또는 view 제공
- [ ] **[AI/backend-db]** `GET /api/v1/requests/sla` HQ 전용 엔드포인트 — 지사별/지역별/카테고리별 평균·중위·90분위 SLA 반환
- [ ] **[AI/backend-db]** SLA 임계치(예: 30분) 초과 시 `AuditLog`에 자동 경고 이벤트 기록
- [ ] **[AI/frontend-mobile]** `www/hq.html`에 SLA 현황 카드 + 임계치 초과 건 리스트 표시
- [ ] **[AI/qa-analyst]** SLA 측정 회귀 테스트: 접수 → 배정 → 완료 시나리오에서 타임스탬프 누락이 발생하면 fail

## 🔐 Phase 1: 보안 및 인증 시스템 (진행 예정)
- [ ] **[AI]** 통합 로그인 페이지 UI 디자인 및 개발 (`/login.html`)
- [ ] **[AI]** JWT 기반 인증 시스템 및 권한(Admin, Branch, Restaurant) 분리 로직
- [ ] **[사람]** PortOne(PASS) 본인확인 서비스 가입 및 API 키 발급
- [ ] **[AI]** 본인인증 API 연동 및 프로필 정보 자동 완성 기능

## 💰 Phase 2: 회계 및 정산 시스템 개발
- [ ] **[AI]** 정산(Settlement) 전용 DB 테이블 모델링
- [ ] **[AI]** 수수료 및 부가세 자동 계산 알고리즘 개발
- [ ] **[AI]** HQ용 미정산/정산완료 내역 관리 대시보드 기능
- [ ] **[AI]** 지사용 정산 명세서 조회 페이지 개발

## 💳 Phase 3: 실거래 결제 및 세무 자동화
- [ ] **[사람]** PG사(포트원) 실거래 심사 및 계약 완료
- [ ] **[AI]** 실거래 환경용 PG 결제 모듈 연동 (신용카드, 간편결제 등)
- [ ] **[사람]** 전자세금계산서(팝빌) 서비스 가입 및 인증서 등록
- [ ] **[AI]** 정산 확정 시 전자세금계산서 자동 발행 기능 연동

## 🚀 Phase 4: 최종 검수 및 AWS 배포
- [ ] **[AI]** 전체 통합 테스트 및 버그 수정
- [ ] **[AI]** AWS 환경 최적화 배포 (Docker Compose 적용)
- [ ] **[사람]** 실서비스 운영 시작
