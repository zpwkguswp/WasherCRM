# plan_phase3.2_auth — 인증 시스템 (JWT 로그인)

> 작성일: 2026-05-15 · 모델: Opus (blueprint §9 — 인증은 Opus 영역)
> 선행 규칙: harnes.md §5 (계획서 없는 개발 금지)
> **진행 현황**: Phase 3.2a(본사 로그인) 구현·자동 테스트 완료(`tests/test_auth.py` 14/14). 브라우저 실동작 확인은 서버 기동 시.
> **2026-05-16 결정** — 포트원 가입 전 배차(plan_phase3.7) 착수를 위해, 식당·지사에 **임시 토큰 로그인(§7)**을 먼저 도입한다(길 B). 정식 PASS 휴대폰 인증은 포트원 가입 후 §7.7 절차로 교체.

## 0. 착수 전 확인 — 현재 상태

진짜 인증이 **어디에도 없다.**

- **백엔드**: `api.py`에 auth/login 라우터 없음. JWT 없음. `users` 테이블·`password` 필드 없음. 6개 라우터(branches·restaurants·requests·payments·notifications·audit-logs) 전부 무인증 공개.
- **지사**(`www/manager.html`)·**식당**(`www/restaurant.html`): 로그인 *화면*은 존재하나, 인증번호(OTP)가 가짜(`"111111"` 고정)이고 전화번호로 명단을 조회해 일치하면 통과하는 클라이언트 사이드 흉내. 토큰 없음.
- **본사**(`www/admin.html`): 로그인 자체가 없음. URL만 알면 진입.

## 1. 범위 — 2단계 분리

사장님 결정(2026-05-15):

### Phase 3.2a (지금 진행) — 본사(HQ) 로그인
- 본사는 **id / 비밀번호** 방식. 임시 계정 `admin` / `0000`.
- `admin`·`0000`은 코드에 직접 박지 않고 **환경변수**(`HQ_ADMIN_ID`, `HQ_ADMIN_PASSWORD`)로 둔다. 기본값만 admin/0000.
- 로그인 성공 시 역할 `ROLE_HQ_ADMIN`을 담은 JWT 발급.

### Phase 3.2b (나중 — 포트원 PASS 가입 후) — 식당·지사 정식 인증
- 식당·지사는 휴대폰 본인인증(PASS)으로 정식 전환. `users` 테이블 신설, refresh 토큰 + rotate 도입.
- **지금은 식당·지사 로그인 화면을 건드리지 않는다** (사장님 지시 — 회귀 방지).

## 2. Phase 3.2a 단계별 작업

1. **JWT 유틸** (`backend/app/core/security.py` 신설) — 토큰 생성·검증. 시크릿은 `JWT_SECRET` 환경변수. 유효기간 12시간(간이 — refresh는 3.2b).
2. **auth 라우터** (`backend/app/api/v1/endpoints/auth.py` 신설) — `POST /api/v1/auth/login`: id/pw 확인 → 일치 시 `ROLE_HQ_ADMIN` JWT 발급, 불일치 시 401. `api.py`에 라우터 등록.
3. **권한 의존성** (`require_role`) — HQ 전용 엔드포인트 보호용 FastAPI dependency.
4. **보호 범위 (이번엔 최소)** — HQ 전용인 `audit-logs`에만 `require_role("HQ_ADMIN")` 적용. branches·restaurants·requests·payments·notifications는 식당·지사도 사용하므로 **그대로 둔다**(3.2b에서 정리). 향후 정산 엔드포인트는 HQ 전용으로 신설.
5. **본사 로그인 화면** — `www/admin.html`에 로그인 게이트 추가: 토큰 없으면 로그인 화면 표시, 성공 시 JWT를 `localStorage`에 저장하고 이후 API 호출 헤더에 첨부. 기존 admin.html 기능(필터·검색·탭)은 보존(harness_rules.md).
6. **환경변수** — 서버 `.env`에 `JWT_SECRET`, `HQ_ADMIN_ID`, `HQ_ADMIN_PASSWORD` 추가 (devops-security).

## 3. 완료 조건 (AC)

- `admin`/`0000`으로 본사 페이지 로그인 성공, 틀린 비밀번호는 거부(401).
- 로그인하지 않은 상태로 `audit-logs` API 호출 시 401.
- 식당·지사 기존 화면이 그대로 동작 (회귀 없음).
- 토큰 만료 후 재로그인 정상 동작.

## 4. 보안 주의 (중요)

- `admin`/`0000`은 **임시 비밀번호**다. 실서비스 오픈 전 강한 비밀번호로 반드시 교체 — harnes.md 미해결 이슈로 등록.
- `JWT_SECRET`은 코드·git에 절대 포함하지 않는다 (devops-security 규칙).

## 5. 참조

- workplan.md §3.2 · blueprint.md §3.4(보안)·§9(모델 정책)
- decision_log.md — 본 계획의 결정사항을 ADR로 등록 예정

---

## 6. Phase 3.2a-2 — API 잠금 확대 (2026-05-16)

코드 감사(2026-05-16) 결과 `audit-logs` 외 모든 엔드포인트가 무인증 공개임이 확인됨(감사 H1). 식당·지사는 아직 정식 인증이 없으므로(§3.2b 대기), **식당·지사가 사용하지 않는 본사 전용 엔드포인트만** `HQ_ADMIN`으로 잠근다. 식당·지사가 쓰는 엔드포인트는 §3.2b까지 개방 유지 (사용자 승인 2026-05-16).

### HQ_ADMIN 전용으로 잠그는 엔드포인트 (식당·지사 미사용 확인됨)
| 엔드포인트 | 이유 |
| :-- | :-- |
| `GET /branches/metrics/performance` | 본사 실적 대시보드 전용 |
| `DELETE /branches/{id}` | 지사 삭제 — 본사만 |
| `DELETE /restaurants/{id}` | 식당 삭제 — 본사만 |
| `DELETE /requests/{id}` | 수리요청 삭제 — 본사만 |
| `GET /payments/` | 전체 결제 목록 — 본사 회계용 |
| `GET /notifications/tokens` | 전체 기기토큰 목록 — 본사/디버그용 |
| `GET /audit-logs/` | (3.2a에서 적용 완료) |

### 개방 유지 (§3.2b에서 식당·지사 인증 도입 후 재정비)
- `POST` /branches·/restaurants·/requests (가입·접수), `POST /requests/{id}/media`, `POST /payments/verify`, `POST /notifications/register`
- `GET` 목록·상세 (branches/restaurants/requests)
- `PATCH` /branches·/restaurants·/requests — 본사 승인/수정과 지사 상태변경이 **같은 엔드포인트를 공유**하므로 역할 분리(§3.2b) 전까지 개방. → **알려진 잔여 위험** (harnes.md 등록).

---

## 7. Phase 3.2b-임시 — 식당·지사 임시 토큰 로그인 (2026-05-16)

> **결정 (2026-05-16, 길 B 채택)**: 정식 식당·지사 인증(PASS 휴대폰 본인인증)은 포트원 가입 후에야 가능하다. 그러나 배차(plan_phase3.7)는 "행위 주체가 누구인지 신뢰 가능"해야 성립하므로 인증을 무한정 기다릴 수 없다. 따라서 **포트원 이전 단계로, 본사(3.2a)와 동일한 JWT 토큰 방식의 "임시 로그인"을 식당·지사에 먼저 붙여** 무인증 개방(§6 잔여 위험)을 막고 배차를 착수한다. PASS는 포트원 가입 후 §7.7의 이행 절차로 교체한다.
>
> 이 결정은 §1의 "지금은 식당·지사 로그인 화면을 건드리지 않는다(2026-05-15 사장님 지시)"를 **갱신**한다 — 임시 토큰을 붙이려면 로그인 성공 처리에 최소 수정이 불가피하다. 기존 화면·UX는 harness_rules.md에 따라 보존한다.

### 7.1 현재 상태 (재확인)

- 식당(`restaurant.html`)·지사(`manager.html`) 로그인은 인증번호가 가짜(`111111` 고정)이고, 전화번호로 명단을 조회해 일치하면 통과하는 **클라이언트 사이드 흉내**다. 서버가 발급하는 토큰이 없다.
- 그 결과 `PATCH /branches`·`/restaurants`·`/requests`가 무인증 개방 상태다(§6 — 알려진 잔여 위험). 누구나 남의 요청을 수정·배정·취소할 수 있다.

### 7.2 설계 — 본사와 같은 JWT, 역할만 추가

- **토큰 구조는 3.2a의 것을 그대로 재사용**한다(`core/security.py`의 `create_access_token`/`decode_access_token`). 신규 인프라 없음.
- **역할(role) 2종 추가**: 기존 `HQ_ADMIN`에 더해 `BRANCH`(지사), `RESTAURANT`(식당).
- **토큰 subject**: 지사는 `branch.id`, 식당은 `restaurant.id`. 토큰만 보면 "누구의 무엇인지"를 알 수 있어 엔드포인트가 소유권을 검증할 수 있다(식당은 자기 요청만, 지사는 plan_phase3.7 claim/release 시 토큰의 branch_id 대조).
- 유효기간은 3.2a와 동일(12시간). refresh 토큰·rotate는 정식 3.2b로 미룬다.

### 7.3 로그인 방식 — 전화번호 + 4자리 PIN (2026-05-16 대표 확정)

임시 단계의 목적은 *정식 본인인증*이 아니라 **"역할이 담긴 진짜 토큰을 발급해 엔드포인트를 역할별로 잠그는 것"**이다. 신원확인은 고령 사용자에게 부담 없는 수준으로 가되, 토큰·세션은 정식으로 간다.

**확정 방식 — 전화번호 ID + 4자리 PIN**: 본사 `admin`/`0000`과 같은 정신의 식당·지사용 간이 PIN 방식.

- **아이디 = 전화번호.** 식당은 등록된 `phone`, 지사는 `manager_phone`. 새 아이디를 외울 필요 없음.
- **비밀번호 = 4자리 PIN.** 가입(본사 승인) 직후 **전원 기본값 `0000`**. 사용자는 로그인 후 자기 PIN을 4자리로 직접 변경할 수 있다(변경 강제는 하지 않음 — 임시 단계·테스트 편의 우선).
- 로그인: `POST /api/v1/auth/login`을 식당·지사용으로 확장 — body에 `전화번호 + PIN + user_type`. 명단 조회 + PIN 일치 시 역할 담은 JWT 발급.
- 기존 가짜 OTP(`111111`)는 제거하고 PIN 입력으로 대체한다.

**채택 이유**: ① 본사(`0000`)와 일관된 방식이라 운영·설명이 단순. ② 새 비밀번호를 외울 필요가 없고(전원 `0000` 시작), 원하면 쉬운 4자리로만 바꾸면 됨 — 고령 사용자 부담 최소. ③ 전원 `0000`이라 테스트가 쉽다. ④ 전화번호만 쓰는 방식보다 PIN이 한 겹 더 있어, 번호만 아는 사람의 사칭을 일부 막는다.

**데이터 모델**: `Branch`·`Restaurant`에 `pin_hash`(str) 컬럼 1개씩 추가. PIN은 **평문 저장 금지 — 해시로 저장**한다(4자리라도). 기본값은 `0000`의 해시. 컬럼 추가는 `init_db()`의 `ALTER TABLE ADD COLUMN IF NOT EXISTS` 패턴.

### 7.4 엔드포인트 잠금

§6에서 개방 유지했던 항목을 임시 토큰 기준으로 잠근다.

- `PATCH /requests/{id}` — 유효 토큰 필수. `HQ_ADMIN`은 전체 허용, `BRANCH`는 자기에게 배정된(또는 자기 지역) 요청만. plan_phase3.7의 `claim`/`release`도 토큰의 branch_id ↔ body branch_id 대조.
- `PATCH /branches/{id}`·`PATCH /restaurants/{id}` — 승인·수수료·등급 등 **본사 전용 필드는 `HQ_ADMIN`만**, 그 외 자기 정보 수정은 소유자(`BRANCH`/`RESTAURANT`)에게 허용.
- `POST` 가입 계열(`/branches`·`/restaurants`)·`POST /auth/login` — **개방 유지**(토큰을 받기 전 단계라 잠글 수 없다).
- `POST /requests`(접수)·`POST /requests/{id}/media`·`POST /notifications/register` — 식당 토큰 필수로 전환. 단 전화 접수 경로는 plan_phase8.5에서 별도 처리.

### 7.5 프론트엔드 변경 (최소)

- `restaurant.html`·`manager.html` — 로그인 성공 처리에 **토큰 수신·저장(localStorage) + fetch 래퍼의 Authorization 헤더 자동 첨부**를 추가한다. admin.html이 3.2a에서 받은 것과 동일한 패턴.
- 기존 로그인 화면 디자인·필터·탭·검색은 보존(harness_rules.md). 추가만 하고 재작성하지 않는다.

### 7.6 단계별 작업

1. [backend-db] `domain.py`·`init_db()` — `Branch`·`Restaurant`에 `pin_hash`·`failed_login_count`(int, 기본 0)·`lockout_until`(datetime, nullable) 컬럼 추가(`ALTER TABLE ADD COLUMN IF NOT EXISTS`). 기존 행의 `pin_hash`는 `0000`의 해시로 채움.
2. [backend-db] `auth.py` — `POST /auth/login`을 식당·지사로 확장(전화번호 + PIN + user_type → 명단·PIN 대조 → 역할 담은 JWT 발급). **로그인 실패 5회 연속 시 `lockout_until`로 일시 잠금(10분), 성공 시 카운터 리셋.** `POST /auth/pin` 신설 — 본인 PIN 4자리 변경(현재 토큰 필수).
3. [backend-db] `deps.py` — `require_role`에 `BRANCH`/`RESTAURANT` 사용. 소유권 검증 헬퍼(토큰 subject ↔ 리소스 소유자) 추가.
4. [backend-db] §7.4의 엔드포인트에 `require_role` + 소유권 가드 적용.
5. [frontend-mobile] `restaurant.html`·`manager.html` — 로그인 화면 OTP 입력란을 PIN 입력으로 교체, 토큰 저장·첨부(§7.5), PIN 변경 화면 1개 추가.
6. [qa-analyst] 무토큰 호출 401, 틀린 PIN 거부, 타 지사 요청 수정 차단, 식당의 타 식당 요청 접근 차단, PIN 변경 후 재로그인 회귀 테스트.

### 7.7 정식 3.2b로의 이행

포트원 PASS 가입 후 정식 전환 시 **교체되는 것은 §7.3의 로그인 입구뿐**이다 — 전화번호 명단 조회 → PASS 휴대폰 본인인증. §7.2의 토큰 구조·역할·subject, §7.4의 잠금, §7.5의 프론트 토큰 처리는 **그대로 재사용**된다. 즉 "두 번 손대지만" 두 번째는 입구 한 곳의 교체다. 정식 전환 시 `users` 테이블·refresh 토큰 rotate를 함께 도입한다(§3.2b 원안).

### 7.8 보안 한계 (명시)

임시 로그인은 **무인증 개방(§6 잔여 위험)을 막는 것**이 목적이며, 다음 한계를 분명히 한다.

- 기본 PIN이 전원 `0000`이므로, 사용자가 PIN을 바꾸기 전까지는 전화번호만 알면 사칭이 가능하다(본사 `admin`/`0000`과 동일한 임시 약점). 4자리 PIN은 경우의 수가 1만 가지뿐이라 무차별 대입에도 약하다.
- 완화: **로그인 실패 5회 연속 시 10분 일시 잠금**(2026-05-16 대표 확정 — 임시 단계에 포함)으로 무차별 대입을 차단한다. 근본 해소는 정식 PASS(§7.7) 전환.
- 지사·식당은 닫힌 거래처 집단이라 사칭 위험의 실질 크기는 작으나, **임시 단계임을 harnes.md "미해결·주의"에 등록**하고 포트원 가입 후 즉시 정식 전환한다.

### 7.9 확인 질문

1. ~~임시 로그인 신원확인 방식~~ → **2026-05-16 대표 확정: 전화번호 ID + 4자리 PIN, 기본값 `0000`, 본인 변경 가능.** §7.3 반영.
2. ~~로그인 실패 횟수 제한 포함 여부~~ → **2026-05-16 대표 확정: 임시 단계에 포함.** 5회 연속 실패 시 10분 일시 잠금. §7.6·§7.8 반영.
