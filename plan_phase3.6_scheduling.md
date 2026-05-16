# plan_phase3.6_scheduling — 방문 일정 관리 / 식당 예약 접수

> 작성일: 2026-05-16 · 작성: planner-strategist · 모델: Opus (스키마 결정 영역 — blueprint §9)
> 선행 규칙: harnes.md §5 (계획서 없는 개발 금지) · 금기 ③ (무한 타이핑 폼 금지)
> 상태: 📝 기획 단계 (사장님 승인 대기) — 코드 미착수

> **2026-05-16 대표 답변 반영 개정.** §11의 확인 질문 3건에 대표 답변이 확정되어 본 문서를 개정한다.
> 주요 변경 3가지:
> 1. **데이터 모델을 멀티방문 구조로 전면 재설계** — 한 수리 접수(`ServiceRequest`)가 부품 교체 등으로 방문 2회 이상으로 이어질 수 있다는 대표 확인에 따라, 초판이 권고했던 "안 A(`ServiceRequest`에 일정 컬럼 4개, 1요청=1방문)"를 **비채택으로 내리고**, 별도 방문 일정 테이블(`VisitSchedule`)을 두는 **"안 B"를 채택**한다. (§3)
> 2. **방문 임박 알림을 정식 기능으로 포함** — 단 예약된 "날짜·시간" 기준의 전일/당일 알림만이며, 기사 실시간 위치(GPS) 기반 "거리 임박" 알림은 본 계획서 범위에서 제외(별도 GPS 추적 인프라 필요 — blueprint §3.3). (§5)
> 3. **시간대 3분할(오전/오후/저녁) 확정** — 추가 분할 없음. (§4.1)
>
> 또한 같은 시기 작성된 **plan_phase3.7(배차 로직)** 과 용어·상태·착수 순서를 정합화했다(`dispatch_status` / `CLAIMED` 참조, 착수 순서 §11).

---

## 0. 착수 전 확인 — 현재 상태

지금 수리 요청에는 **"언제 방문할지"라는 개념이 전혀 없다.**

- `ServiceRequest` 타임스탬프는 `created_at`(접수) / `notified_at`(지사 알림, SLA 시작) / `assigned_at`(작업 시작) / `accepted_at`(지사 수락, SLA 종료) / `completed_at`(완료)뿐이다. 모두 **"이미 일어난 일"을 기록**하는 사후 필드다. **"앞으로 언제 갈 예정"인 미래 시각을 담을 칸이 없다.**
- 지사 화면(`www/manager.html`)은 배정된 요청을 목록으로만 본다. 날짜·시간 기준으로 정렬·배치하는 화면이 없다.
- 식당 접수(`www/restaurant.html`)는 카테고리·사진 위주이며 "원하는 방문 시각"을 받지 않는다.
- 상태 흐름: `PENDING → (배정) → IN_PROGRESS → PAYMENT_REQUESTED → COMPLETED`. 중간에 "방문 예정이 잡혔다"는 상태가 없다.

문제: 지사 처리 건수가 늘면 식당을 어떤 순서로 방문할지 사람 머릿속·전화로만 관리된다. 식당은 "오늘 오나? 내일 오나?"를 알 수 없다.

### 2026-05-16 추가 확인 — 한 수리 건이 방문 여러 번으로 이어진다

대표 확인 결과, **식당이 한 번 접수한 수리 건 하나가 방문 2회 이상으로 이어질 수 있다.** 전형적인 흐름은:

1. **1차 방문** — 기사가 현장에서 진단하고, 필요한 부품을 주문한다.
2. **2차 방문** — 부품이 도착하면 다시 방문해 교체·수리를 마친다.

즉 "수리 접수 1건"과 "방문 1건"은 1:1이 아니라 **1:N**이다. 1차·2차 방문은 각각 **별도의 날짜·시간**이 잡혀야 한다(부품 도착 시점이 다르므로). 따라서 일정 데이터를 `ServiceRequest`에 단일 컬럼으로 붙이면 2차 방문 일정이 1차를 덮어써 이력이 사라진다 — 초판 권고였던 안 A는 이 현실에 부적합하다(§3 참조).

---

## 1. 배경 · 목표

### 누구의 문제인가 (이해관계자)
- **지사(현장)** — 가장 큰 수혜자. 들어온 요청을 날짜·시간 슬롯에 배치해 동선·하루 일감을 관리한다.
- **식당(소비자)** — 접수할 때 원하는 방문 시간대를 고를 수 있어 "언제 오는지 모름" 불안이 해소된다.
- **본사(HQ)** — 부차적. 예약 대비 실제 방문 준수율(노쇼·지연)이 SLA 외 또 하나의 품질 지표가 된다. 단 harnes.md 금기 ①(대시보드 선행 금지)에 따라 **본사 일정 대시보드는 이번 단계 범위에서 제외**한다.

### 목표
1. 식당이 수리 요청 시 **달력·버튼 탭으로 희망 방문 날짜·시간대를 선택**할 수 있다. (자유 텍스트 금지 — 금기 ③)
2. 지사가 **수락(`dispatch_status=CLAIMED`)한 요청**에 대해 **날짜·시간 슬롯으로 방문 일정을 잡고**, 한 수리 건에 **1차·2차 방문을 각각 따로** 잡을 수 있다.
3. 지사가 **오늘/이번 주 방문 일정**을 달력·리스트로 본다.
4. 예약 확정·일정 변경·**방문 임박(전일/당일)** 시 식당에 FCM 푸시 알림이 간다.
5. 기존 SLA 측정(`notified_at`→`accepted_at`)·배차 로직(plan_phase3.7)·정산을 **건드리지 않는다**(harness_rules.md — 동작하는 기능 보존).

---

## 2. 동작 흐름

> **plan_phase3.7과의 접점**: 본 계획서의 일정 배치는 plan_phase3.7(배차)에서 어느 지사가 요청을 **수락(`dispatch_status=CLAIMED`)** 한 뒤에 시작한다. 즉 "담당 지사가 정해진 뒤 → 방문 일정을 잡는다"는 순서이며, 3.6은 3.7의 `CLAIMED`(또는 본사 강제 배정 `HQ_ASSIGNED`) 상태를 전제로 동작한다.

```
[식당]  수리 요청 작성
        └ 카테고리·사진 선택 (기존)
        └ 희망 방문 날짜 선택 (달력 탭)        ← 신규
        └ 희망 시간대 선택 (오전/오후/저녁 버튼) ← 신규
        └ 제출 → ServiceRequest 생성 (preferred_* 기록)
                                       │
                       [plan_phase3.7 배차]  후보 지사에 푸시 → 한 지사 수락
                                       │     dispatch_status: OPEN → CLAIMED
                                       │     accepted_at 기록 (기존 SLA 로직 그대로)
                                       ▼
[지사]  수락한 요청(CLAIMED)에 대해
        └ 일정 화면에서 1차 방문을 날짜·시간 슬롯에 배치           ← 신규
          (식당 희망 시각이 기본값으로 미리 채워짐)
        └ 배치 확정 → VisitSchedule(회차 1) 생성, status=SCHEDULED ← 신규
                                       │
                       FCM 푸시: "○월 ○일 오후 방문 예정입니다" → 식당
                                       │
                       (방문 하루 전·당일 아침) 방문 임박 알림 → 식당 ← 신규
                                       ▼
[지사]  1차 방문 → 현장 진단 → 작업 시작 status=IN_PROGRESS (기존)
        ├─[수리 완료]  → PAYMENT_REQUESTED → COMPLETED (기존)
        └─[부품 필요]  → 1차 방문을 "부품대기"로 마감하고
                         같은 요청 아래 2차 방문 일정을 새로 잡음     ← 신규(멀티방문)
                         → VisitSchedule(회차 2) 생성, 다시 SCHEDULED
                         → 식당에 2차 방문 예약 푸시 + 임박 알림
                                       │
                                       ▼
[지사]  2차 방문 → 부품 교체 → 수리 완료 → PAYMENT_REQUESTED → COMPLETED (기존)
```

핵심 원칙:
- **예약(식당 희망)과 확정 일정(지사 배치)을 분리**한다. 식당이 고른 건 "희망"일 뿐이고, 실제 일정은 지사가 슬롯에 배치할 때 확정된다. 지사가 식당 희망을 못 맞추면 다른 슬롯에 배치하고 알림으로 통보한다.
- **한 수리 접수 아래에 방문 일정이 여러 개 매달린다**(`ServiceRequest` 1 : `VisitSchedule` N). 1차 방문에서 수리가 끝나면 방문은 1건, 부품 교체로 재방문하면 2건 이상이 된다. 각 방문은 독립된 날짜·시간을 갖는다.

---

## 3. 데이터 모델 설계 — 멀티방문 구조 (2026-05-16 개정)

> **개정 사유**: 초판은 "1요청 = 1방문"을 전제로 `ServiceRequest`에 일정 컬럼 4개를 붙이는 **안 A를 권고**했다. 그러나 2026-05-16 대표 확인 결과 한 수리 건이 부품 교체로 방문 2회 이상으로 이어질 수 있음이 분명해졌다(§0). 따라서 안 A는 비채택으로 내리고, 초판이 "과설계"라며 비채택했던 **별도 방문 일정 테이블 방식(안 B)을 정식 채택**한다.

### 3.1 채택안 — `VisitSchedule` 별도 테이블 (안 B 채택 ✅)

한 수리 접수(`ServiceRequest`) 아래에 방문 일정 레코드(`VisitSchedule`)를 **여러 개 매다는 1:N 구조**로 한다.

**`VisitSchedule` 제안 스키마** (DDL은 backend-db가 Alembic로 확정):

```
VisitSchedule
  id               UUID      PK
  request_id       UUID      FK service_requests.id  (index)   # 어느 수리 접수의 방문인가
  branch_id        UUID      FK branches.id                    # 방문 담당 지사
  visit_no         int       default 1                         # 회차 — 1차 진단, 2차 교체, ...
  scheduled_start  datetime                                    # 방문 예정 시작 시각 (이 방문의 단일 진실원)
  scheduled_end    datetime  nullable                          # 방문 예정 종료 (MVP는 시작+기본 1시간)
  visit_status     str       # SCHEDULED | DONE | PARTS_WAIT | CANCELLED
  visit_purpose    str       nullable                          # 버튼 선택형 — DIAGNOSIS(진단)/REPLACEMENT(부품교체)/RECHECK(재점검). 자유 텍스트 금지(금기 ③)
  created_at       datetime
  updated_at       datetime
```

- `visit_no`는 회차 번호다. 1차 방문이 `1`, 부품 교체 재방문이 `2`. 한 요청 아래에서 1부터 증가한다.
- `visit_status`:
  - `SCHEDULED` — 일정이 잡혀 방문 예정.
  - `DONE` — 방문 완료(이 회차의 작업이 끝남).
  - `PARTS_WAIT` — 1차 방문은 했으나 부품 대기로 다음 회차가 필요한 상태(이 회차는 마감, 다음 `VisitSchedule`로 이어짐).
  - `CANCELLED` — 이 회차 방문이 취소됨.
- `Money` 필드 없음 → `Decimal` 이슈 무관.

**`ServiceRequest` 측 변경** — 컬럼 3개만 추가(일정 컬럼은 `VisitSchedule`로 빠지므로 최소화):

| 컬럼 | 타입 | 의미 |
| :-- | :-- | :-- |
| `preferred_date` | `date` (nullable) | 식당이 고른 희망 방문 날짜 (입력 힌트 — 1차 방문 배치 시 기본값으로만 사용) |
| `preferred_time_slot` | `str` (nullable) | 식당이 고른 희망 시간대 — `MORNING`/`AFTERNOON`/`EVENING` |
| `next_visit_at` | `datetime` (nullable) | **가장 가까운 미래 방문 시각** — `visit_status=SCHEDULED`인 `VisitSchedule` 중 최소 `scheduled_start`. 목록 정렬·방문 임박 알림 조회를 위한 비정규화(denormalized) 캐시 컬럼. `VisitSchedule` 추가·변경 시 함께 갱신 |

> `next_visit_at`을 두는 이유: 식당 목록·지사 목록에서 "다음 방문 언제?"를 매번 `VisitSchedule`를 조인·집계하지 않고 한 컬럼으로 읽기 위함이다. 단일 진실원은 어디까지나 `VisitSchedule.scheduled_start`이며, `next_visit_at`은 그 파생값임을 코드 주석에 명시한다.

**신규 상태 1개 추가**: `SCHEDULED` (담당 지사 확정 + 방문 일정이 1건 이상 잡힘 / `IN_PROGRESS` 직전 단계).
- 상태 흐름: `PENDING → (3.7 배차로 CLAIMED) → SCHEDULED → IN_PROGRESS → PAYMENT_REQUESTED → COMPLETED`.
- ※ `SCHEDULED`를 건너뛰고 바로 `IN_PROGRESS`로 가는 즉시 출동 케이스도 허용(일정 미입력 = 즉시 처리).
- ※ **부품 대기 재방문 케이스**: 1차 방문이 끝나 `IN_PROGRESS`로 들어갔다가 부품 대기로 2차 방문 일정을 새로 잡으면, 요청 `status`는 `IN_PROGRESS`를 유지한 채 새 `VisitSchedule`(회차 2)이 `SCHEDULED`로 추가된다. 즉 **요청 status는 "수리 작업 전체의 진행도", `VisitSchedule.visit_status`는 "개별 방문 회차의 상태"** — 두 축을 분리한다. (이는 plan_phase3.7이 `dispatch_status`를 `status`와 직교 축으로 둔 설계 정신과 같다.)

### 3.2 비채택안 — 안 A (`ServiceRequest` 일정 컬럼 확장) ❌

초판 권고였으나 **비채택**한다.

- 안 A는 `scheduled_start`/`scheduled_end`를 `ServiceRequest`에 단일 컬럼으로 두는 방식이다.
- **부적합 사유**: 한 요청에 방문이 2회 이상이면 2차 방문 일정이 1차 일정을 덮어쓰게 되어 **1차 방문 이력이 사라진다.** 부품 교체 재방문이 실제 업무 흐름이므로(§0) 이 손실은 허용할 수 없다.
- 초판이 안 A의 단점으로 적었던 "재방문 이력이 안 남는다 → MVP 범위 밖"이라는 가정 자체가 대표 확인으로 깨졌다.

### 3.3 채택의 트레이드오프 — 솔직한 명시

안 B(멀티방문)는 안 A보다 **구현이 무겁다.** 숨기지 않고 명시한다.

- **마이그레이션이 늘어난다**: 컬럼 추가뿐 아니라 `visit_schedules` **신규 테이블 생성**이 필요하다. `init_db()`의 `ALTER TABLE ADD COLUMN IF NOT EXISTS` 패턴만으로는 부족하고, 테이블 생성 + 정식 Alembic 리비전(현재 head `9ef3418df4f2` 다음)이 필요하다. plan_phase3.7의 `DispatchEvent` 신규 테이블과 같은 수준의 작업량이다.
- **조회 쿼리가 복잡해진다**: 지사 일정 화면은 `ServiceRequest` 한 테이블이 아니라 `VisitSchedule`를 `ServiceRequest`·`Restaurant`와 조인해 읽어야 한다.
- **얻는 것**: 1차·2차 방문을 **각각 따로 날짜·시간을 잡을 수 있고**, 회차별 이력이 그대로 남는다. 부품 교체 흐름이 실제 업무이므로 이 복잡도는 과설계가 아니라 **필수 비용**이다.
- 다행히 같은 시기 plan_phase3.7도 신규 테이블(`DispatchEvent`)을 도입하므로, 두 phase의 Alembic 리비전 작업을 **함께 묶어** 진행하면 추가 부담이 줄어든다(§11 착수 순서 참조).

---

## 4. 슬롯 · 용량 · 중복예약 처리 규칙

### 4.1 시간대(슬롯) 정의 — "시간대 3분할" 확정 (2026-05-16 대표 확정)

분 단위 정밀 예약은 고령 사장님 UX에 부담이고 지사 운영 현실과도 안 맞는다. **하루를 3개 시간대로 나누는 것으로 대표가 확정**했다(초판 §11 질문 3에 대한 답 — 추가 분할 없음).

| 슬롯 코드 | 표시명 | 시간 범위(기본값) |
| :-- | :-- | :-- |
| `MORNING` | 오전 | 09:00–12:00 |
| `AFTERNOON` | 오후 | 13:00–17:00 |
| `EVENING` | 저녁 | 17:00–20:00 |

- 식당은 `preferred_date` + `preferred_time_slot`(3택1)만 고른다 — 버튼 탭 3개.
- 지사가 슬롯에 방문을 배치할 때 `VisitSchedule.scheduled_start`를 슬롯 시작 시각으로 자동 설정하되, 지사가 30분 단위로 미세 조정 가능(예: 오전 슬롯 안에서 10:30).
- **3분할은 1차·2차 방문 모두에 동일하게 적용**된다 — 2차 방문 일정을 잡을 때도 같은 오전/오후/저녁 버튼을 쓴다.

### 4.2 용량(capacity) 제약

- `Branch`에 `daily_visit_capacity`(int, 기본값 8) 컬럼 추가 — 한 지사가 **하루에** 처리 가능한 방문 건수 상한.
- 슬롯별 세분 용량은 두지 않는다(과설계 회피). 하루 총량만 본다.
- 용량 집계 단위는 **`VisitSchedule` 행**이다 — 즉 같은 요청의 1차·2차 방문이 같은 날에 잡히면 **2건으로 센다**(현장 일감은 실제로 2번이므로). `ServiceRequest` 단위가 아니라 방문 단위로 센다는 점을 명시한다.
- 지사 일정 화면에서 특정 날짜의 `VisitSchedule`(visit_status=`SCHEDULED`) 건수가 `daily_visit_capacity`에 도달하면 해당 날짜를 "마감"으로 표시(시각적 경고). **하드 차단이 아닌 소프트 경고** — 지사가 판단해서 초과 배치 가능(현장 사정 우선).

### 4.3 중복예약 / 충돌 처리

- 같은 지사·같은 `scheduled_start`(30분 단위 동일)에 `VisitSchedule` 2건 이상이 배치되면 **경고 표시**만 한다. 물리적 차단은 안 한다 — 지사 2인 출동 등 정당한 케이스가 있다.
- 식당의 `preferred_*`는 어디까지나 "희망"이므로 식당끼리 같은 날짜·시간대를 골라도 충돌이 아니다. 충돌 개념은 **지사가 확정한 `VisitSchedule.scheduled_start` 사이에서만** 적용한다.
- 지사가 방문 일정을 변경하면(`VisitSchedule.scheduled_start` 수정) `AuditLog`에 before/after가 기록되고, `next_visit_at`을 재계산하며, 식당에 변경 푸시가 발송된다.

---

## 5. 기존 기능과의 연계 · 방문 임박 알림

### 5.1 기존 기능 연계

| 기존 기능 | 연계 방식 | 영향 |
| :-- | :-- | :-- |
| **SLA 측정** (plan_phase3.5) | `notified_at`→`accepted_at`은 "지사 수락까지의 시간"으로 그대로 유지. `VisitSchedule.scheduled_start`는 SLA 계산에 **들어가지 않는다**. | 영향 없음 (회귀 위험 0) |
| **배차 로직** (plan_phase3.7) | 일정 배치는 배차에서 지사가 **수락(`dispatch_status=CLAIMED`)** 또는 본사 강제 배정(`HQ_ASSIGNED`)한 **이후**의 별도 동작. 3.7의 `dispatch_status`·`accepted_at`·`assigned_branch_id`는 손대지 않음. 3.6은 3.7이 채운 담당 지사(`assigned_branch_id`)를 `VisitSchedule.branch_id`의 기본값으로 읽어 쓴다. | 영향 없음 (3.7과 직교) |
| **정산** (plan_phase4.1) | 정산은 `Payment`·`completed_at` 기준. `VisitSchedule`·`scheduled_*`와 무관. | 영향 없음 |
| **알림 인프라** (`send_push_notification`, FCM) | 신규 알림 3종에 재사용 — ① 예약 확정 ② 일정 변경 ③ 방문 임박(전일/당일). FCM 푸시 인프라는 **이미 구축돼 있음** — 신규 인프라 도입 없음. 토큰 조회는 기존 `DeviceToken`(user_type=`RESTAURANT`) 패턴 그대로. | 인프라 재사용, 신규 호출만 추가 |
| **상태 흐름** | `SCHEDULED` 상태 1개 신규 추가. 기존 `status` 문자열 값은 변경하지 않음. | 신규 상태 추가만 (기존 값 불변) |
| **AuditLog** | `VisitSchedule` 생성·변경·취소는 별도 AuditLog 기록(`table_name='visit_schedules'`). | 신규 기록 대상 추가 |

### 5.2 방문 임박 알림 — 정식 기능으로 포함 (2026-05-16 대표 확정)

초판 §11 질문 2에 대한 대표 답변에 따라, **방문 임박 알림을 정식 기능으로 포함**한다. 범위는 다음과 같이 명확히 한정한다.

**포함 — 날짜·시간 기준 임박 알림**:
- 각 `VisitSchedule`의 `scheduled_start`(예약된 방문 시각)를 기준으로:
  - **전일 알림 (D-1)**: 방문 전날 "내일 ○○ 방문 예정입니다" 푸시.
  - **당일 알림 (D-0)**: 방문 당일 아침 "오늘 ○○ 방문 예정입니다" 푸시.
- 1차·2차 방문 각각에 대해 따로 발송된다(각 `VisitSchedule` 단위).
- 발송 대상은 식당(`DeviceToken` user_type=`RESTAURANT`).

**제외 — 기사 위치(GPS) 기반 '거리 임박' 알림 (단, 인터페이스 자리는 미리 마련)**:
- "기사가 3km 앞" 같은 **실시간 위치 기반 거리 임박 알림 로직은 본 계획서 범위에서 제외**한다.
- 이유: 기사 단말의 실시간 GPS 위치 추적 인프라가 별도로 필요하며, 이는 blueprint §3.3의 별도 기능 영역이다. 본 phase는 FCM 푸시만으로 구현 가능한 "날짜·시간 기준" 알림에 한정한다.
- **2026-05-16 대표 확정 — 인터페이스 선마련**: 거리 기반 알림은 의사결정 시 바로 착수할 수 있도록 **자리(인터페이스)만 미리 뚫어 둔다.** 구체적으로 (1) 지사·식당 앱에 Capacitor Geolocation 위치 권한 요청 + 좌표 수집 배관을 깔고, (2) 수집한 좌표를 저장할 컬럼(예: `Branch`·`DeviceToken` 또는 별도 위치 테이블 — backend-db가 착수 시 확정)을 자리만 잡는다. 거리 계산·임박 판정 로직은 비워 두고, 의사결정 후 그 위에 얹는다. 위치 상시 수집은 개인정보 동의 고지가 필요하므로 legal-compliance와 함께 진행한다.

**알림을 누가 트리거하나 (경량 스케줄러)**:
방문 임박 알림은 정해진 시각에 주기적으로 "내일/오늘 방문" 대상을 골라 보내야 하므로 주기 실행이 필요하다. 단 정식 워커 신설은 과하므로 MVP는 경량 방식으로 시작한다:
- **권고**: 서버에 **일 1회(예: 매일 오전 8시) cron** 또는 FastAPI 기동 시 등록하는 가벼운 백그라운드 태스크가 `next_visit_at`/`VisitSchedule.scheduled_start`를 보고 D-1·D-0 대상을 조회해 발송.
- 이 sweep은 **plan_phase3.7의 타임아웃 점검(`POST /requests/dispatch/sweep`)과 같은 운영 패턴**이다. 정식 스케줄러 도입 시 3.6의 방문 임박 알림과 3.7의 배차 타임아웃 sweep을 **하나의 스케줄러로 묶어** 후속 phase에서 함께 처리한다(중복 인프라 방지).

---

## 6. 백엔드 변경 개요 (엔드포인트)

> 코드는 미작성. 아래는 backend-db가 후속 구현할 범위 정의.

1. **`domain.py`** — `VisitSchedule` 모델 신설(§3.1). `ServiceRequest`에 `preferred_date`, `preferred_time_slot`, `next_visit_at` 추가. `Branch`에 `daily_visit_capacity` 추가.
2. **마이그레이션** — `visit_schedules` 신규 테이블 생성 + `ServiceRequest`·`Branch` 컬럼 추가. 컬럼 추가는 `init_db()`의 `ALTER TABLE ADD COLUMN IF NOT EXISTS` 패턴을 쓰되, **테이블 생성은 정식 Alembic 리비전**으로 처리(현재 head `9ef3418df4f2` 다음). plan_phase3.7의 `dispatch_events` 테이블 생성과 **같은 리비전 작업으로 묶어** 진행 권고.
3. **`schemas/domain.py`** — `RequestCreate`에 `preferred_date`/`preferred_time_slot` 입력 필드 추가(둘 다 선택값). `RequestRead`에 `next_visit_at`과 해당 요청의 `VisitSchedule` 목록(회차·시각·상태)을 중첩 노출. `VisitScheduleCreate`/`VisitScheduleRead` 스키마 신설.
4. **`POST /requests/`** — 생성 시 `preferred_*`를 그대로 저장(기존 로직 유지, 필드만 추가). `VisitSchedule`은 이 시점에 만들지 않는다 — 일정은 지사 수락 후 배치된다.
5. **`POST /requests/{id}/visits`** (신규) — 지사가 한 요청에 방문 일정(회차)을 추가. body에 `scheduled_start`/`time_slot`/`visit_purpose`. 호출 시 `visit_no` 자동 증가, `VisitSchedule` 생성, 요청 `status`를 `SCHEDULED`로 전이(첫 회차일 때), `next_visit_at` 재계산, 식당에 "예약 확정" 푸시. **선행 가드**: 해당 요청이 `dispatch_status` 기준 담당 지사가 확정된 상태(`CLAIMED`/`HQ_ASSIGNED`)인지 확인.
6. **`PATCH /requests/{id}/visits/{visit_id}`** (신규) — 방문 일정 변경(`scheduled_start` 수정)·상태 변경(`DONE`/`PARTS_WAIT`/`CANCELLED`). 일정 변경 시 식당에 "일정 변경" 푸시, `next_visit_at` 재계산. `visit_status=PARTS_WAIT` 전이는 2차 방문 추가의 신호.
7. **`GET /requests/schedule`** (신규) — 지사용. `branch_id` + `date` 또는 `week_start` 파라미터로 해당 기간의 `VisitSchedule`(visit_status=`SCHEDULED`) 목록을 요청·식당 정보와 조인해 반환. 날짜별 방문 건수·`daily_visit_capacity` 비교 결과 포함.
8. **방문 임박 알림 sweep** — D-1·D-0 대상 `VisitSchedule`을 조회해 식당에 푸시. §5.2의 경량 방식(일 1회 cron 또는 기동 시 백그라운드 태스크). plan_phase3.7의 `dispatch/sweep`과 운영 패턴 공유.
9. 모든 `VisitSchedule` 생성·변경은 `AuditLog`(`table_name='visit_schedules'`) 1행을 남긴다.

---

## 7. 프론트엔드 변경 개요

> harness_rules.md 준수 — 기존 필터·검색·탭은 보존, **새 UI 블록을 추가**하는 방식.

### 7.1 식당 예약 UI (`www/restaurant.html`)
- 수리 요청 폼 하단에 "방문 희망일" 섹션 추가.
- **날짜**: 가로 스크롤 달력 또는 "오늘/내일/모레/이번 주" 버튼 — 탭으로만 선택. 자유 입력란 없음(금기 ③).
- **시간대**: `오전` / `오후` / `저녁` 큰 버튼 3개 — 1개 탭 선택.
- "아무 때나 괜찮아요" 버튼 1개 — `preferred_*`를 비워서 제출(지사가 알아서 배치).
- 글자 크기 크게, 버튼 터치 영역 넓게 — 고령 사용자 배려.

### 7.2 지사 일정 화면 (`www/manager.html`)
- 기존 요청 목록 탭 옆에 "일정" 탭 신규 추가.
- **오늘 보기**: 오늘 `scheduled_start`인 `VisitSchedule`을 시간순 리스트로. 식당명·주소·카테고리·시간·**회차 표시(예: "2차 방문")**.
- **이번 주 보기**: 7일 가로 달력, 날짜별 방문 건수 배지. 날짜 탭 시 해당 일 리스트.
- **미배치 요청 목록**: 수락(`CLAIMED`/`HQ_ASSIGNED`)했으나 아직 방문 일정(`VisitSchedule`)이 없는 요청 → 날짜·시간대 버튼으로 1차 방문 배치(식당 희망 시각이 기본값으로 표시).
- **부품 대기 재방문**: 1차 방문 상세에서 "부품 대기로 재방문 잡기" 버튼 → 같은 요청에 2차 방문 일정을 새 날짜·시간대로 추가. 1차 방문은 `PARTS_WAIT`로 마감 표시.
- 용량 초과 날짜는 색상 경고(§4.2 — 방문 건수 기준).

---

## 8. 단계별 롤아웃

### 8.1 MVP (Phase 3.6)
- `VisitSchedule` 신규 테이블 + `ServiceRequest` 컬럼 3개 + `Branch` 컬럼 1개 + `SCHEDULED` 상태.
- 식당 예약 UI(날짜·시간대 탭 선택).
- 지사 일정 화면(오늘/이번 주 리스트, 1차 방문 배치, 부품 대기 재방문(2차) 추가).
- 예약 확정·일정 변경 FCM 푸시.
- **방문 임박 알림(D-1·D-0, 날짜·시간 기준) — 경량 sweep 방식으로 포함**(§5.2).
- **GPS 위치 권한·좌표 수집 인터페이스 선마련** — 거리 계산·임박 판정 로직은 제외, 자리만(§5.2).
- 하루 총량 capacity 소프트 경고(방문 건수 기준).

### 8.2 고도화 (후속 — 별도 phase, 본 문서 범위 밖)
- 방문 임박 알림·배차 타임아웃 sweep을 묶은 정식 스케줄러(plan_phase3.7 §3.5와 통합).
- **기사 위치(GPS) 기반 거리 임박 알림** — 별도 GPS 추적 인프라 필요(blueprint §3.3).
- 슬롯별 세분 용량, 동선 최적화(지도 연동).
- 본사 일정 준수율 지표 — **실데이터 누적 후에만** (금기 ① 준수).

---

## 9. 리스크

| 리스크 | 대응 |
| :-- | :-- |
| `VisitSchedule` 신규 테이블로 마이그레이션·조인 부담 증가 | §3.3에서 솔직히 명시함. plan_phase3.7의 `dispatch_events` 테이블 생성과 Alembic 리비전을 묶어 작업량 절감. |
| `SCHEDULED` 상태 추가로 기존 상태 분기 코드 누락 | 신규 값 추가만 하고 기존 값 불변. 프론트 status 표시 매핑에 1줄 추가로 끝. 3.7의 `dispatch_status`와 직교하므로 충돌 없음. |
| `next_visit_at` 캐시 컬럼이 `VisitSchedule`와 불일치(stale) | 단일 진실원은 `VisitSchedule.scheduled_start`. `VisitSchedule` 생성·변경·취소 시 반드시 `next_visit_at` 재계산을 같은 트랜잭션에서 수행. |
| 부품 대기 재방문 시 요청 status를 잘못 전이 | 요청 `status`는 수리 전체 진행도, `VisitSchedule.visit_status`는 회차별 상태로 분리(§3.1). 2차 방문 추가가 요청 status를 되돌리지 않음. |
| 식당 희망 시각을 지사가 못 지켜 불만 발생 | UI에서 "희망일이며 지사 확정 후 알림"임을 명시. 일정 변경 시 반드시 푸시. |
| 방문 임박 알림용 스케줄러가 과설계로 번질 위험 | MVP는 경량 방식(일 1회 cron 또는 기동 시 백그라운드 태스크)으로 한정. 정식 워커는 3.7 sweep과 묶어 후속. |
| 시간대 3분할이 일부 지사엔 부족 | 대표가 3분할로 확정. 분 단위는 지사가 `scheduled_start` 30분 미세조정으로 보완. |
| `preferred_*`를 정렬·필터 조건으로 오용 | 일정의 단일 진실원은 `VisitSchedule.scheduled_start`임을 §3에 명시. `preferred_*`는 1차 방문 배치 시 기본값 힌트 전용. |

---

## 10. 완료 조건 (AC)

- 식당이 요청 작성 시 날짜·시간대를 **버튼 탭으로만** 선택해 제출할 수 있다(자유 텍스트 입력 없음 — 금기 ③).
- "아무 때나" 선택 시 `preferred_*` 없이 정상 접수된다.
- 지사가 수락한 요청(`dispatch_status=CLAIMED`/`HQ_ASSIGNED`)에 방문 일정(`VisitSchedule`)을 추가하면 회차·`scheduled_start`가 기록되고 첫 회차일 때 요청 status=`SCHEDULED`로 전이된다.
- **한 수리 접수에 1차·2차 방문을 각각 다른 날짜·시간으로 잡을 수 있다** — 2차 방문이 1차 일정을 덮어쓰지 않고 별도 회차로 누적된다.
- 1차 방문을 `PARTS_WAIT`로 마감하고 2차 방문을 추가해도 요청 status가 잘못 되돌아가지 않는다.
- 지사 일정 화면에서 오늘/이번 주 방문이 시간순으로(회차 표시 포함) 보인다.
- 예약 확정·일정 변경 시 식당에 FCM 푸시가 발송된다.
- **방문 전일(D-1)·당일(D-0)에 날짜·시간 기준 방문 임박 알림이 식당에 발송된다.** 기사 위치(GPS) 기반 거리 임박 알림은 본 phase에 포함되지 않는다.
- 날짜별 방문 건수가 `daily_visit_capacity` 초과 시 화면에 경고 표시(차단은 안 함).
- 기존 SLA 측정(`notified_at`→`accepted_at`)·배차(3.7)·정산·식당/지사 기존 화면이 모두 회귀 없이 동작한다(기존 `status` 값 불변).

---

## 11. 우선순위 권고 — 3.2b·3.7과의 선후 관계

**권고 착수 순서: `3.2b 인증 정비` → `3.7 배차` → `3.6 스케줄링(본 문서)`.** (plan_phase3.7 §10이 권고한 순서와 동일하게 정합화.)

근거:
1. **3.2b(인증)가 반드시 선행해야 한다** — 일정 배치는 "어느 지사가" 하는 행위다. 현재 식당·지사 로그인은 가짜 OTP(`111111`)이고 `PATCH /requests`가 무인증 개방 상태(plan_phase3.2 §6의 잔여 위험, harnes.md 2026-05-16 미결 이슈)다. 인증 없이 일정 기능을 올리면 아무나 남의 지사 일정을 바꿀 수 있다.
2. **3.7(배차)이 3.6보다 먼저다** — 본 계획서의 일정 배치는 "지사가 요청을 **수락(`dispatch_status=CLAIMED`)** 한 뒤 방문 일정을 잡는 흐름"이다(§2). 즉 3.7이 푸는 "담당 지사를 어떻게 정하나"가 먼저 서야, 3.6의 "확정된 담당 지사가 언제 갈지를 잡는다"가 의미를 갖는다. 3.7 §10도 같은 근거로 3.7→3.6 순서를 권고한다.
3. **3.5(SLA)와는 독립** — SLA는 이미 구현 완료됐고 본 기능과 코드 충돌이 없다. 3.6은 `notified_at`/`accepted_at`을 건드리지 않는다.
4. **3.7과 모순되지 않게 설계됨** — 3.6의 `SCHEDULED`는 기존 `status` 축, 3.7의 `dispatch_status`는 독립 축, 3.6의 `VisitSchedule.visit_status`는 회차별 축 — 세 축이 직교한다. 3.6은 3.7이 채운 `assigned_branch_id`·`CLAIMED`를 읽기만 한다.
5. **비용·리스크는 중간** — 멀티방문 채택으로 신규 테이블 1개(`VisitSchedule`) + 컬럼 4개. 3.7의 `dispatch_events` 테이블 작업과 Alembic 리비전을 묶으면 부담이 준다. 정산 같은 비가역 영역은 건드리지 않아 리스크는 낮다.

요약: **`3.2b 인증` → `3.7 배차` → `3.6 스케줄링(본 문서)`.** 정산(4.x)과는 독립이라 병행 가능.

> **확인 질문 — 2026-05-16 대표 답변으로 모두 종결됨**
> 1. 부품 교체 재방문 — **"있을 수 있음"으로 확정.** → §3 데이터 모델을 멀티방문(`VisitSchedule`) 구조로 재작성, 안 A 비채택.
> 2. 방문 임박 알림 — **포함하되 '날짜·시간' 기준만으로 확정.** GPS 거리 임박은 제외. → §5.2 반영.
> 3. 시간대 3분할 — **오전/오후/저녁 3분할로 확정.** → §4.1 반영.

## 12. 시행착오

*(착수 후 엔지니어가 기록)*

## 13. 참조

- harnes.md §5 (계획서 없는 개발 금지) · 금기 ① (대시보드 선행 금지) · 금기 ③ (무한 타이핑 폼 금지 — 시간대/방문목적 버튼 선택형)
- harness_rules.md (동작하는 기능 보존 — 기존 `status`·필터·탭 불변)
- plan_phase3.2_auth.md §6 (`PATCH /requests` 무인증 잔여 위험 — 3.6 선행 조건)
- plan_phase3.5_sla_measurement.md (`notified_at`/`accepted_at` — SLA와 독립)
- **plan_phase3.7_dispatch_assignment.md** (배차 — `dispatch_status`/`CLAIMED`/`HQ_ASSIGNED` 정의, 착수 순서 §10, sweep 운영 패턴 공유. 3.6은 3.7 수락 이후 동작)
- plan_phase4.1_settlement_schema.md (정산은 본 기능과 독립)
- blueprint.md §3.3 (기사 위치(GPS) 기반 거리 임박 알림 — 본 phase 범위 밖)
- backend/app/models/domain.py (`ServiceRequest`, `Branch`)
- backend/app/api/v1/endpoints/requests.py (`create_request`, `update_request`)
