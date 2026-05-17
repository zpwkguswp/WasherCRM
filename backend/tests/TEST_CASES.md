# WhiteOn 백엔드 전수 품질 점검 — 테스트 케이스 문서

- **작성일**: 2026-05-17
- **작성**: QA-Analyst (멀티 에이전트)
- **목적**: 6월 중순 외부 홍보 전, 식당·지사·본사 전 사용 시나리오의 품질을 검증한다.
- **대상**: 로컬 백엔드 `http://localhost:8000/api/v1` (운영 서버 13.124.100.75는 절대 미사용)
- **자동 실행**: `backend/` 에서 `venv_win/Scripts/python.exe tests/test_e2e.py`
- **실행 결과**: `tests/TEST_RESULTS_20260517.md` 참조

이 문서는 두 부분으로 구성된다.
1. **API 자동 테스트 케이스** — `test_e2e.py`가 자동으로 검증하는 케이스(TC-xxx).
2. **수동 확인 체크리스트** — 사람이 프론트엔드 화면에서 눈으로 확인해야 하는 항목(M-xxx).

---

## 1. API 자동 테스트 케이스

각 케이스는 `test_e2e.py`의 `TC-xxx` ID와 1:1 대응한다.
케이스가 만든 데이터는 식별 접두사 `E2ETEST_`로 표시되며, 스크립트 종료 시 DB에서 전부 삭제된다(멱등).

### 0. 사전 점검

| ID | 목적 | 사전조건 | 단계 | 기대결과 |
|---|---|---|---|---|
| TC-000 | 서버 연결 확인 | 로컬 서버 기동 | `GET /branches/` | 200 |
| TC-010 | 본사 로그인 성공 | admin 계정 존재 | `POST /auth/login {admin/0000}` | 200, role=HQ_ADMIN, 토큰 발급 |
| TC-011 | 본사 로그인 실패 | - | `POST /auth/login {admin/wrong}` | 401 |

### 1. 가입 (식당·지사·중복·필수항목)

| ID | 목적 | 사전조건 | 단계 | 기대결과 |
|---|---|---|---|---|
| TC-100 | 식당 가입 성공 | - | `POST /restaurants/` (이름·전화·주소) | 201 |
| TC-101 | 식당 자동 승인 | TC-100 | 응답의 `is_approved` 확인 | True (2026-05-16 대표 지시) |
| TC-102 | 식당 이름 중복 차단 | 식당 A 존재 | 같은 이름·다른 전화·주소로 가입 | 400 |
| TC-103 | 식당 전화 중복 차단 | 식당 A 존재 | 같은 전화로 가입 | 400 |
| TC-104 | 식당 주소 중복 차단 | 식당 A 존재 | 같은 주소로 가입 | 400 |
| TC-105 | 식당 필수항목 누락 거부 | - | name만 보내고 가입 | 400 또는 422 |
| TC-110 | 지사 가입 성공 | - | `POST /branches/` (이름·지역·주소·전화) | 201 |
| TC-111 | 지사 가입 직후 미승인 | TC-110 | `is_approved` 확인 | False |
| TC-112 | 지사 이름 중복 차단 | 지사 A 존재 | 같은 이름으로 가입 | 400 |
| TC-113 | 지사-식당 이름 교차 중복 | 식당 A 존재 | 식당 이름으로 지사 가입 | 400 (플랫폼 전체 유일성) |
| TC-114 | 지사 필수항목 누락 거부 | - | manager_phone·address 없이 가입 | 400 |
| TC-115 | 본사 지사 승인 | 지사 A, HQ 토큰 | `PATCH /branches/{id} {is_approved:true}` | 200 |
| TC-116 | 승인 반영 확인 | TC-115 | 응답 `is_approved` | True |

### 2. 로그인 (PIN·잠금·미등록)

| ID | 목적 | 사전조건 | 단계 | 기대결과 |
|---|---|---|---|---|
| TC-200 | 식당 PIN 로그인 | 식당 A 존재 | `POST /auth/login/pin {phone, 0000, RESTAURANT}` | 200, role=RESTAURANT |
| TC-201 | 지사 PIN 로그인 | 지사 A 존재 | `POST /auth/login/pin {phone, 0000, BRANCH}` | 200, role=BRANCH |
| TC-202 | 미등록 번호 거부 | - | 등록되지 않은 번호로 PIN 로그인 | 401 |
| TC-203 | 잘못된 user_type 거부 | - | `user_type=INVALID` | 400 |
| TC-210 | PIN 1~4회 실패 | 잠금용 식당 | 틀린 PIN 4회 시도 | 매번 401 |
| TC-211 | PIN 5회 실패 시 잠금 | TC-210 | 5회째 틀린 PIN | 423 LOCKED |
| TC-212 | 잠금 중 정상 PIN도 거부 | TC-211 | 잠금 상태에서 올바른 PIN 0000 | 423 |

### 3. 수리 요청 생성·지역 매칭·브로드캐스트

| ID | 목적 | 사전조건 | 단계 | 기대결과 |
|---|---|---|---|---|
| TC-300 | 식당 수리 요청 생성 | 식당 A | `POST /requests/` | 201 |
| TC-301 | 신규 요청 상태 | TC-300 | `status` | PENDING |
| TC-302 | notified_at 기록 (SLA 시작점) | TC-300 | `notified_at` | not null |
| TC-303 | 후보 지사 존재 시 OPEN | 승인 지사 A 동일 지역 | `dispatch_status` | OPEN |
| TC-304 | 후보 0곳 즉시 ESCALATED | 매칭 지사 없는 지역 | 요청 생성 후 `dispatch_status` | ESCALATED |
| TC-305 | 없는 식당 id 요청 거부 | - | 임의 UUID로 요청 생성 | 201이 아님 (4xx/5xx) |
| TC-306 | category 누락 거부 | 식당 A | category 없이 요청 생성 | 422 |

### 4. 배차 (claim·release·rebroadcast·HQ_ASSIGN·권한)

| ID | 목적 | 사전조건 | 단계 | 기대결과 |
|---|---|---|---|---|
| TC-400 | 지사 수락 claim | 요청 OPEN, 지사 토큰 | `POST /requests/{id}/claim` | 200 |
| TC-401 | claim 후 상태 | TC-400 | `dispatch_status` | CLAIMED |
| TC-402 | claim 후 배정 | TC-400 | `assigned_branch_id` | 해당 지사 |
| TC-403 | accepted_at 기록 (SLA 종료점) | TC-400 | `accepted_at` | not null |
| TC-404 | 재-claim 거부 (원자성) | TC-400 | 같은 지사 다시 claim | 409 CONFLICT |
| TC-405 | 타 지사 claim 거부 | TC-400 | 지사 B가 claim | 409 |
| TC-406 | 무인증 claim 거부 | - | 토큰 없이 claim | 401 |
| TC-407 | 본사 토큰 claim 거부 | - | HQ 토큰으로 claim | 403 (BRANCH 전용) |
| TC-410 | 담당 지사 취소 release | claim된 요청 | `POST /requests/{id}/release {reason}` | 200 |
| TC-411 | release 후 상태(1회) | TC-410 | `dispatch_status` | REASSIGNING |
| TC-412 | release 후 배정 해제 | TC-410 | `assigned_branch_id` | null |
| TC-413 | release 후 취소 카운트 | TC-410 | `cancel_count` | 1 |
| TC-414 | 담당 아닌 지사 release 거부 | TC-410 | 지사 B가 release | 403 |
| TC-415 | 3회 취소 시 ESCALATED | claim/release 3회 | 3번째 release 후 `dispatch_status` | ESCALATED (재배포 한계) |
| TC-416 | 본사 재배포 rebroadcast | ESCALATED 요청 | `POST /requests/{id}/rebroadcast` | 200 (OPEN으로) |
| TC-417 | 비-ESCALATED 재배포 거부 | OPEN 요청 | rebroadcast | 409 |
| TC-418 | 지사 토큰 rebroadcast 거부 | - | 지사가 rebroadcast | 403 (HQ 전용) |
| TC-420 | 본사 직접 배정 HQ_ASSIGN | 미배정 요청, HQ 토큰 | `PATCH /requests/{id} {assigned_branch_id}` | 200 |
| TC-421 | HQ 배정 후 상태 | TC-420 | `dispatch_status` | HQ_ASSIGNED |
| TC-422 | 타임아웃 sweep | HQ 토큰 | `POST /requests/dispatch/sweep` | 200, escalated_count |
| TC-423 | 무인증 sweep 거부 | - | 토큰 없이 sweep | 401 |

### 5. 수리 진행 상태 전이

| ID | 목적 | 사전조건 | 단계 | 기대결과 |
|---|---|---|---|---|
| TC-500 | PENDING → IN_PROGRESS | claim된 요청 | `PATCH {status:IN_PROGRESS}` | 200 |
| TC-501 | IN_PROGRESS 시 assigned_at | TC-500 | `assigned_at` | not null |
| TC-502 | IN_PROGRESS → PAYMENT_REQUESTED | TC-500 | `PATCH {status:PAYMENT_REQUESTED}` | 200 |
| TC-503 | → SUSPENDED 수리 중단 | - | `PATCH {status:SUSPENDED}` | 200 |
| TC-504 | SUSPENDED → IN_PROGRESS 재진행 | TC-503 | `PATCH {status:IN_PROGRESS}` | 200 |
| TC-505 | 수리 리포트(metadata) 작성 | - | `PATCH {metadata:{report,parts}}` | 200 |
| TC-506 | metadata 병합 보존 | TC-300에서 requested_amount 포함 생성 | TC-505 후 응답 metadata | 기존 키 + 새 키 모두 존재 |

### 6. 완료 → 결제 자동 생성

| ID | 목적 | 사전조건 | 단계 | 기대결과 |
|---|---|---|---|---|
| TC-600 | → COMPLETED | 진행 중 요청 | `PATCH {status:COMPLETED}` | 200 |
| TC-601 | completed_at 기록 | TC-600 | `completed_at` | not null |
| TC-602 | Payment 자동 생성 | TC-600 | `GET /payments/`에서 해당 요청 검색 | 1건 이상 |
| TC-603 | 자동 Payment 금액 | TC-602 | `amount` | requested_amount(130000)와 일치 |
| TC-604 | 자동 Payment 상태 | TC-602 | `status` | PAID |

### 7. 정산 (generate·멱등·상태전이·권한)

| ID | 목적 | 사전조건 | 단계 | 기대결과 |
|---|---|---|---|---|
| TC-700 | 정산서 생성 generate | 완료 결제 존재, HQ 토큰 | `POST /settlements/generate {기간}` | 200 |
| TC-701 | 활동 지사 정산서 생성 | TC-700 | 응답 목록 | 1건 이상 |
| TC-702 | 정산 gross_amount | TC-701 | `gross_amount` | 결제 합계(130000) |
| TC-703 | 본사수수료 계산 | TC-701 | `hq_commission` | gross×10% = 13000 |
| TC-704 | 신규 정산서 상태 | TC-701 | `status` | DRAFT |
| TC-705 | generate 멱등성 | TC-700 | 같은 기간 재호출 | 신규 0건 |
| TC-706 | 잘못된 기간 거부 | HQ 토큰 | end < start로 generate | 400 |
| TC-710 | 본사 정산서 목록 | HQ 토큰 | `GET /settlements/` | 200, 배열 |
| TC-711 | 정산서 상세 조회 | 정산서 존재 | `GET /settlements/{id}` | 200, items 포함 |
| TC-720 | 정상 상태전이 체인 | 정산서 DRAFT | DRAFT→REVIEW→APPROVED→PAID→INVOICED | 전 단계 200 |
| TC-721 | 허용 안 된 전이 거부 | INVOICED 정산서 | INVOICED → DRAFT | 400 |
| TC-722 | 알 수 없는 상태값 거부 | - | `status:BOGUS` | 400 |
| TC-730 | 지사 본인 정산서 목록 | 지사 토큰 | `GET /settlements/my` | 200, 배열 |
| TC-731 | 타 지사 정산서 접근 거부 | 지사 B 토큰 | 지사 A 정산서 상세 조회 | 403 |
| TC-732 | 무인증 정산 목록 거부 | - | `GET /settlements/` | 401 |
| TC-733 | 지사 토큰 본사 정산목록 거부 | 지사 토큰 | `GET /settlements/` | 403 (HQ 전용) |

### 8. 월별 회계 리포트 CSV

| ID | 목적 | 사전조건 | 단계 | 기대결과 |
|---|---|---|---|---|
| TC-800 | 회계 리포트 CSV 다운로드 | HQ 토큰 | `GET /settlements/report/monthly?year&month` | 200 |
| TC-801 | CSV 헤더 포함 | TC-800 | 본문에 '지사명' 등 헤더 | 존재 |
| TC-802 | 잘못된 month 거부 | HQ 토큰 | `month=13` | 400 |
| TC-803 | 무인증 리포트 거부 | - | 토큰 없이 호출 | 401 |

### 9. 권한 검증

| ID | 목적 | 사전조건 | 단계 | 기대결과 |
|---|---|---|---|---|
| TC-900 | 무인증 결제 목록 거부 | - | `GET /payments/` | 401 |
| TC-901 | 무인증 감사 로그 거부 | - | `GET /audit-logs/` | 401 |
| TC-902 | 무인증 토큰 목록 거부 | - | `GET /notifications/tokens` | 401 |
| TC-903 | 무인증 실적 메트릭 거부 | - | `GET /branches/metrics/performance` | 401 |
| TC-910 | 지사 토큰 결제 목록 거부 | 지사 토큰 | `GET /payments/` | 403 |
| TC-911 | 지사 토큰 감사 로그 거부 | 지사 토큰 | `GET /audit-logs/` | 403 |
| TC-912 | 지사 토큰 실적 메트릭 거부 | 지사 토큰 | `GET /branches/metrics/performance` | 403 |
| TC-913 | 식당이 본사 전용 필드 변경 거부 | 식당 토큰 | `PATCH /restaurants/{id} {is_approved}` | 403 |
| TC-914 | 지사가 본사 전용 필드 변경 거부 | 지사 토큰 | `PATCH /branches/{id} {commission_rate}` | 403 |
| TC-915 | 지사가 타 지사 정보 수정 거부 | 지사 A 토큰 | `PATCH /branches/{지사 B}` | 403 |
| TC-916 | 식당이 타 식당 정보 수정 거부 | 식당 A 토큰 | `PATCH /restaurants/{식당 B}` | 403 |

### 10. 만족도 조사·디바이스 토큰

| ID | 목적 | 사전조건 | 단계 | 기대결과 |
|---|---|---|---|---|
| TC-1000 | 만족도 조사 metadata 저장 | 완료 요청 | `PATCH {metadata:{survey:{rating}}}` | 200 |
| TC-1001 | survey 저장 확인 | TC-1000 | 응답 metadata.survey.rating | 5 |
| TC-1010 | 디바이스 토큰 등록 | - | `POST /notifications/register` | 200 |
| TC-1011 | 동일 토큰 재등록(업서트) | TC-1010 | 같은 토큰 다시 등록 | 200 |
| TC-1012 | 재등록 시 platform 갱신 | TC-1011 | `platform` | ios (변경 반영) |
| TC-1013 | 본사 토큰 목록 조회 | HQ 토큰 | `GET /notifications/tokens` | 200, 배열 |

### 11. 엣지 케이스 (404·400·422)

| ID | 목적 | 사전조건 | 단계 | 기대결과 |
|---|---|---|---|---|
| TC-1100 | 없는 요청 조회 | - | `GET /requests/{임의 UUID}` | 404 |
| TC-1101 | 없는 지사 조회 | - | `GET /branches/{임의 UUID}` | 404 |
| TC-1102 | 없는 식당 조회 | - | `GET /restaurants/{임의 UUID}` | 404 |
| TC-1103 | 없는 정산서 조회 | HQ 토큰 | `GET /settlements/{임의 UUID}` | 404 |
| TC-1104 | 없는 요청 수정 | HQ 토큰 | `PATCH /requests/{임의 UUID}` | 404 |
| TC-1105 | 잘못된 UUID 형식 | - | `GET /requests/not-a-uuid` | 422 |
| TC-1106 | 빈 body 요청 생성 | - | `POST /requests/ {}` | 422 |
| TC-1107 | 연관 요청 있는 식당 삭제 차단 | 요청 있는 식당 | `DELETE /restaurants/{id}` | 400 |
| TC-1108 | 연관 요청 있는 지사 삭제 차단 | 배정 요청 있는 지사 | `DELETE /branches/{id}` | 400 |

### 12. SLA 측정 (필수 항목)

> QA 의무 항목: 요청 생성 → 배정까지 `created_at`/`assigned_at`(여기서는 `notified_at`/`accepted_at`)이
> 기록되고, 그 경과 시간이 본사 HQ API로 조회 가능한지 검증한다.

| ID | 목적 | 사전조건 | 단계 | 기대결과 |
|---|---|---|---|---|
| TC-1200 | 요청 생성 시 notified_at | - | 요청 생성 후 `notified_at` | not null |
| TC-1201 | claim 시 accepted_at | TC-1200 | claim 후 `accepted_at` | not null |
| TC-1202 | SLA delta 측정 가능 | TC-1201 | accepted_at − notified_at | ≥ 0 |
| TC-1203 | 본사 SLA 요약 API | HQ 토큰 | `GET /requests/sla/summary` | 200, accepted_count 포함 |
| TC-1204 | SLA 평균 수락시간 | TC-1203 | 응답에 avg_accept_minutes | 존재 |

---

## 2. 수동 확인 체크리스트 (프론트엔드 화면)

API 자동 테스트로는 검증할 수 없는, 사람이 직접 화면에서 눈으로 확인해야 하는 항목.
대상 화면: `www/restaurant.html`(식당), `www/manager.html`(지사), `www/admin.html`(본사+관리자 통합).
지사 사람들이 실제로 앱을 쓰기 전에 반드시 1회 이상 통과 확인할 것.

### M-1. 식당 화면 (restaurant.html)

| ID | 확인 항목 | 통과 기준 |
|---|---|---|
| M-101 | 가입 화면이 긴 텍스트 폼이 아닌지 | harnes.md §3 — 항목별 선택형/짧은 입력 위주여야 함 |
| M-102 | 수리 요청 시 카테고리 선택이 버튼/칩 형태 | 자유 입력 텍스트 박스로만 받지 않음 |
| M-103 | 사진 첨부(업로드) 동작 | 사진 선택 → 미리보기 → 업로드 성공 표시 |
| M-104 | 요청 진행 상태가 단계별로 시각 표시 | PENDING/IN_PROGRESS/COMPLETED 등이 한눈에 보임 |
| M-105 | 푸시 알림 수신 (수리 상태 변경 시) | 안드로이드 기기에서 알림 도착 확인 |
| M-106 | 완료 후 만족도(별점) 입력 화면 노출 | 별점 + 짧은 코멘트, 긴 폼 아님 |
| M-107 | PIN 로그인/PIN 변경 화면 동작 | 4자리 숫자만 입력, 잠금 시 안내 문구 노출 |

### M-2. 지사 화면 (manager.html)

| ID | 확인 항목 | 통과 기준 |
|---|---|---|
| M-201 | 신규 요청 브로드캐스트 목록 표시 | 자기 지역 미배정 요청이 목록에 보임 |
| M-202 | 수락(claim) 버튼 동작 | 누르면 즉시 내 배정으로, 이미 잡힌 건은 회색/거부 안내 |
| M-203 | 수락 시 방문일정 지정 UI | 날짜·시간 선택기 정상 동작 |
| M-204 | 취소(release) 시 사유 선택 | 버튼 선택형(일정 불가/지역 밖/인력 부족/기타) |
| M-205 | 상태 전이 버튼 (진행/중단/완료) | 각 단계 버튼이 적절한 시점에만 활성화 |
| M-206 | 수리 리포트 작성 화면 | 부품/내용 입력 후 저장 반영 |
| M-207 | 본인 정산 명세서 조회 | 자기 지사 정산서만 보임, 타 지사 안 보임 |
| M-208 | 검색·필터 기능 (기존 기능 보존 확인) | harness_rules.md — 기존 필터/검색 정상 동작 |

### M-3. 본사 화면 (admin.html)

| ID | 확인 항목 | 통과 기준 |
|---|---|---|
| M-301 | 지사 승인 처리 UI | 미승인 지사 목록 → 승인 버튼 → 반영 |
| M-302 | 배차 타임라인 보기 | 한 요청의 BROADCAST/CLAIM/RELEASE 등 시간순 표시 |
| M-303 | ESCALATED 요청 재배포 버튼 | 본사 배정 대기 건 → 재배포 동작 |
| M-304 | 정산서 생성/상태 전이 UI | 기간 입력 → 생성 → 검토/승인/지급/계산서 버튼 |
| M-305 | 월별 회계 리포트 CSV 다운로드 | 다운로드 → 한글 Excel에서 깨짐 없이 열림 |
| M-306 | 지사 실적 보드 표시 | 매출/완료건수/등급/만족도 표시 (대시보드 우선개발 금지 — 데이터 흐름 후) |
| M-307 | 감사 로그 조회 화면 | 변경 이력 최신순 표시, 필터 동작 |
| M-308 | 결제 내역 목록·필터 | 상태/기간 필터 동작 |

### M-4. 공통·크로스 체크

| ID | 확인 항목 | 통과 기준 |
|---|---|---|
| M-401 | 안드로이드 Capacitor 빌드에서 화면 정상 | 모바일 래퍼에서 레이아웃 깨짐 없음 |
| M-402 | 하단 네비게이션(모바일) 동작 | 탭 전환 정상 |
| M-403 | 한글 인코딩 (UI 텍스트·에러 메시지) | 모든 화면에서 한글 깨짐 없음 |
| M-404 | 푸시 알림 딥링크 | 알림 탭 시 해당 요청 화면으로 이동 |
| M-405 | 약관·개인정보 footer 노출 | 통신판매업·개인정보 안내 링크 (legal-compliance 확인 필요) |

---

## 부록. 정기 점검 운용

- 이 테스트 묶음은 **다음 점검에서도 그대로 재실행**할 수 있다.
  `test_e2e.py`는 시작·종료 시 테스트 데이터를 정리하므로 반복 실행해도 DB가 오염되지 않는다.
- 코드 변경(특히 `requests`/`settlements`/`auth`) 후에는 이 스크립트를 반드시 1회 돌릴 것.
- 자동 테스트가 다루지 못하는 PortOne 결제 webhook, Popbill 세금계산서, FCM 실발송은
  별도 통합 환경에서 `finance`/`devops-security` 에이전트와 함께 점검한다.
