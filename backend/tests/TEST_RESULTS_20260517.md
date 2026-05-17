# WhiteOn 백엔드 전수 품질 점검 — 실행 결과 (2026-05-17)

- **실행일시**: 2026-05-17 16:24 ~ 16:28 (약 3분 38초)
- **실행 환경**: 로컬 `http://localhost:8000/api/v1`, 로컬 DB(docker `washer_db`, postgres:15)
- **실행 명령**: `backend/` 에서 `venv_win/Scripts/python.exe tests/test_e2e.py`
- **테스트 스크립트**: `tests/test_e2e.py` (115개 케이스)
- **원시 로그**: `tests/TEST_RESULTS_LATEST.txt` (스크립트가 매 실행 시 덮어씀)

---

## 0. BUG-001 수정 경과 (2026-05-17, 메인 세션 후속)

- **BUG-001 수정 완료** — `create_request()`가 `RequestCreate.metadata`를
  `ServiceRequest.metadata_json`으로 명시 매핑하도록 변경 (`requests.py`).
- **수정 후 `test_e2e.py` 재실행 → 115개 전부 PASS, FAIL 0** (소요 217초).
  FAIL이던 TC-506·TC-603·TC-702·TC-703 4건 모두 PASS로 전환 — 회귀 검증 통과.
- **AWS 운영 서버에도 동일 수정 배포 완료** (dev=AWS md5 동일, 재기동 정상).
- 아래 §1~§3은 **수정 전(as-found) 기록**으로 보존한다.

---

## 1. 종합 결과 (수정 전 — as-found 기록)

| 항목 | 값 (수정 전) | 값 (수정 후 재실행) |
|---|---|---|
| 총 케이스 | **115** | 115 |
| PASS | **111** | **115** |
| FAIL | **4** | **0** |
| 통과율 | 96.5% | **100%** |
| 정리(cleanup) | 정상 — 종료 후 테스트 데이터 잔여 0건, 로컬 DB 빈 상태 복원 (TC-999 PASS) | 정상 |

FAIL 4건은 **서로 독립한 버그가 아니라, 단일 근본 원인에서 파생된 연쇄 실패**였다.
BUG-001 하나를 고쳐 4건이 모두 해소됐다.

---

## 2. 발견된 버그 / 이상 동작

### BUG-001 (심각도: 높음 — 홍보 전 반드시 수정) — 요청 생성 시 `metadata`가 통째로 유실됨

**증상**
`POST /api/v1/requests/` 호출 시 body에 `metadata`(예: `{"requested_amount": 130000}`)를
넣어도, 생성된 요청의 `metadata`는 항상 빈 `{}`로 저장된다.

**재현 방법**
```
POST /api/v1/requests/
{ "restaurant_id": "<식당 UUID>", "category": "WATER_LEAK",
  "metadata": {"requested_amount": 130000, "priority": "high"} }
-> 201 응답의 metadata 가 {} 로 비어 있음
```
DB 직접 검증 결과:
```
RequestCreate(...).model_dump() 의 키 = ['restaurant_id','category','description','metadata']
ServiceRequest(**model_dump()) 후 .metadata_json = {}   <-- 유실
```

**근본 원인**
- `RequestCreate` 스키마의 필드명은 `metadata` (`backend/app/schemas/domain.py:11`).
- `ServiceRequest` 도메인 모델의 필드명은 `metadata_json` (DB 컬럼 alias만 `metadata`)
  (`backend/app/models/domain.py:59`).
- `create_request()`가 `ServiceRequest(**data.model_dump())`로 생성하는데
  (`backend/app/api/v1/endpoints/requests.py:144`), `model_dump()`는 `metadata` 키를
  내보내고 SQLModel 생성자는 모델에 없는 `metadata` 인자를 **조용히 무시**한다.
  → 생성 시점의 `metadata`가 전부 사라진다.
- 참고: `update_request()`(PATCH)는 `key == "metadata"`를 명시적으로 받아 `metadata_json`에
  병합하므로 정상 동작한다. **버그는 생성(POST) 경로에만 있다.**

**연쇄 영향 — 이 한 버그가 FAIL 4건의 원인**
- **TC-506 FAIL**: 요청 생성 시 넣은 `requested_amount`가 처음부터 저장되지 않으므로,
  나중에 metadata를 PATCH해도 그 값이 보존될 리 없다(애초에 없었음).
- **TC-603 FAIL**: 요청 완료(COMPLETED) 시 `update_request()`가
  `db_request.metadata_json.get("requested_amount", 0)`로 결제 금액을 읽는데
  (`requests.py:432`), metadata가 비어 있어 **금액 0원짜리 Payment가 자동 생성**된다.
- **TC-702 FAIL**: 결제 금액이 0이므로 정산서 `gross_amount`도 0.
- **TC-703 FAIL**: gross가 0이므로 본사 수수료(`hq_commission`)도 0
  (기대값 13,000원).

**비즈니스 위험**
수리 완료 시 **실제 청구 금액이 0원으로 결제·정산에 기록**된다. 식당이 앱에서 요청 시
금액을 함께 보내는 흐름이라면, 6월 홍보 후 실제 매출이 전부 0으로 집계되어
정산이 무력화된다. 결제·정산 모듈은 blueprint §7에서 "잘못되면 되돌리기 어려운 영역"으로
지정된 곳이므로, 홍보 전 최우선 수정 대상.

**수정 방향 (참고용 — 본 QA 세션은 코드 수정 안 함)**
`create_request()`에서 `ServiceRequest(**data.model_dump())` 대신 PATCH 경로처럼
`metadata` 키를 `metadata_json`으로 매핑해 넣어야 한다. `RequestUpdate` 처리 로직과
동일한 패턴. 메인 세션에서 `backend-db` + `finance` 에이전트가 함께 판단할 것.

---

## 3. 케이스별 상세 결과

### 통과 (111건) — 주요 확인 사항

- **가입(1번대)**: 식당 자동 승인, 지사 미승인 시작, 이름·전화·주소 3중 중복 차단,
  지사-식당 교차 중복 차단, 필수항목 누락 거부 — 전부 정상.
- **로그인(2번대)**: 본사 id/pw, 식당·지사 PIN, 미등록 번호 거부, **PIN 5회 실패 시
  423 잠금 + 잠금 중 정상 PIN도 거부** 정상 동작 (TC-210~212 PASS).
- **수리 요청(3번대)**: notified_at 기록(SLA 시작점), 후보 지사 존재 시 OPEN,
  후보 0곳 시 즉시 ESCALATED — 정상.
- **배차(4번대)**: claim 선착순 원자성(재-claim·타 지사 claim 모두 409),
  release 후 REASSIGNING/cancel_count, 3회 취소 ESCALATED, 본사 rebroadcast,
  HQ_ASSIGN, sweep, 역할별 권한(BRANCH/HQ 전용) — 전부 정상.
- **상태 전이(5번대)**: PENDING→IN_PROGRESS→PAYMENT_REQUESTED→COMPLETED,
  SUSPENDED 중단/재진행, assigned_at·completed_at 기록 — 정상.
  (단 TC-506 metadata 병합 검증은 BUG-001 영향으로 FAIL)
- **완료·결제(6번대)**: COMPLETED 시 Payment 자동 생성·PAID 상태 — 정상.
  (단 TC-603 금액 검증은 BUG-001 영향으로 FAIL)
- **정산(7번대)**: generate 멱등성, 잘못된 기간 거부, 상태전이 머신
  (정상 체인 통과 + 역방향/미지 상태 거부), 지사 본인 정산서만 조회(타 지사 403) — 정상.
  (단 TC-702/703 금액 검증은 BUG-001 영향으로 FAIL)
- **회계 리포트(8번대)**: CSV 다운로드, month 범위 검증, 무인증 거부 — 정상.
- **권한(9번대)**: 무인증 401, 타 역할 403, 본사 전용 필드 보호, 타 지사·타 식당
  자원 수정 차단 — 전부 정상.
- **만족도·토큰(10번대)**: survey metadata 저장(PATCH 경로라 정상), 디바이스 토큰
  업서트 및 platform 갱신 — 정상.
- **엣지(11번대)**: 404/422/400 응답, 연관 데이터 있는 식당·지사 삭제 차단 — 정상.
- **SLA(12번대)**: notified_at·accepted_at 기록, delta ≥ 0 측정 가능,
  본사 `GET /requests/sla/summary` 조회(accepted_count·avg_accept_minutes 포함) — 정상.

### 실패 (4건)

| ID | 케이스 | 원인 |
|---|---|---|
| TC-506 | metadata 병합 보존 (기존 requested_amount 유지) | BUG-001 |
| TC-603 | 자동 생성 Payment 금액 = requested_amount | BUG-001 (금액 0원으로 생성됨) |
| TC-702 | 정산 gross_amount = 결제 합계 | BUG-001 (결제가 0이라 정산도 0) |
| TC-703 | 정산 본사수수료 = gross×10% | BUG-001 (gross 0 → 수수료 0) |

---

## 4. 관찰된 비-차단 이슈 (버그 아님 — 점검 권고)

다음 항목은 테스트는 통과했으나, 홍보 전 메인 세션에서 한 번 검토할 가치가 있다.

- **N-1. 가입 중복 규칙이 여전히 "이름+전화+주소 전체 유일"**: CLAUDE.md / workplan §3.4가
  이 규칙은 너무 엄격하다(공동 운영 사업장 차단)고 지적하며 `(business_number, phone)`로
  교체 예정이라 명시. 현재 코드(`branches.py`/`restaurants.py`)는 아직 옛 규칙.
  홍보 전 정책 확정 필요.
- **N-2. `init_db()` 하드코딩 데이터 패치**: 매 부팅마다 특정 결제 ID 대상 SQL이 실행됨
  (CLAUDE.md 명시). 로컬 빈 DB에서는 무해하나, 운영에서 의도치 않은 동작 가능성.
- **N-3. SLA 시작점 용어**: 모델 주석상 `notified_at`(지사 브로드캐스트 시각)이 SLA
  시작점이고 `accepted_at`이 종료점이다. QA 산출물 요구의 `created_at`/`assigned_at`과
  필드명이 다르므로, 정기 점검 시 혼동 주의(테스트는 notified_at/accepted_at 기준으로
  올바르게 검증함).
- **N-4. 없는 restaurant_id로 요청 생성(TC-305)**: 201이 아닌 응답을 반환해 테스트는
  통과하나, FK 위반이 500으로 떨어지는지 명시적 404/400인지 메인 세션 확인 권장
  (사용자 친화적 에러 메시지 측면).

---

## 5. 수동 확인 잔여 항목

`TEST_CASES.md` §2 "수동 확인 체크리스트"의 M-1xx ~ M-4xx 항목은 이번 자동 점검에서
**확인하지 못했다**. 프론트엔드 화면(`www/restaurant.html`, `manager.html`, `admin.html`)과
안드로이드 Capacitor 빌드에서 사람이 직접 확인해야 한다. 특히 홍보 전 우선순위:

- M-105 / M-404 — 푸시 알림 수신·딥링크 (실기기 필요)
- M-202 / M-203 / M-204 — 지사 수락·방문일정·취소사유 UI (지사 사용자 핵심 흐름)
- M-305 — 회계 리포트 CSV 한글 Excel 호환
- M-401 / M-403 — 안드로이드 빌드 레이아웃·한글 인코딩
- M-405 — 약관·개인정보 footer (legal-compliance 확인 필요)

---

## 6. 다음 점검 시 재실행 안내

- 로컬 서버 기동 후 `backend/` 에서 `venv_win/Scripts/python.exe tests/test_e2e.py` 실행.
- 스크립트는 시작·종료 시 `E2ETEST_` 접두사 데이터를 자동 정리하므로 반복 실행 안전.
- BUG-001 수정 후 재실행하면 4건의 FAIL이 PASS로 전환되어야 한다(회귀 검증 지점).
- `requests` / `settlements` / `auth` 엔드포인트를 수정할 때마다 이 스크립트를 1회 돌릴 것.
