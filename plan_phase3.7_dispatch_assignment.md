# plan_phase3.7_dispatch_assignment — 배차 / 수리요청 지사 배정 로직

> 작성일: 2026-05-16 · 작성: planner-strategist · 모델: Opus (동시성·상태 머신 결정 영역 — blueprint §9)
> 선행 규칙: harnes.md §5 (계획서 없는 개발 금지) · 금기 ④ (SLA 대응시간 측정 누락 금지)
> 상태: ✅ 기획 확정 (2026-05-16 대표 §10 확인 질문 4건 답변 반영) — 코드 미착수, `3.2b 인증` 선행 대기

---

## 0. 착수 전 확인 — 현재 상태

수리 요청이 들어오면 **"어느 지사가 담당할지"를 정하는 규칙이 사실상 없다.**

- `create_request`(`requests.py`)는 요청 생성 시 식당 지역(`restaurant.region`)과 지사 `region_code`를 매칭해 후보 지사들에게 **FCM 푸시만 발송**한다. 푸시를 받은 지사가 그다음 무엇을 하는지에 대한 백엔드 규칙은 없다.
- 실제 배정은 `PATCH /requests/{id}`로 `assigned_branch_id`를 채우는 것이 전부다. 본사 화면(`admin.html`)이 이 PATCH를 호출해 **수동 배정**한다. 지사가 스스로 "수락"하는 정식 경로가 없다.
- `update_request`는 `assigned_branch_id`가 None→값으로 처음 바뀔 때 `accepted_at`을 기록한다(plan_phase3.5). 즉 **"배정 = 수락"으로 이미 코드가 가정**하고 있다 — 배차 로직은 이 가정 위에 얹어야 한다.
- 현재 `status`는 `PENDING → IN_PROGRESS → PAYMENT_REQUESTED → COMPLETED` 뿐이다. "여러 지사에 뿌려져 응답을 기다리는 중"이라는 상태가 없다.
- `PATCH /requests`는 아직 무인증 개방 상태다(plan_phase3.2 §6 — 알려진 잔여 위험). 누구나 남의 요청을 배정·취소할 수 있다.

핵심 문제: 대표가 말한 "후보 지사 A·B·C 중 먼저 수락한 곳이 담당" 방식을 그대로 구현하려면 **(1) 응답 대기 상태**, **(2) 동시 수락 시 한 곳만 이기게 하는 동시성 제어**, **(3) 수락 후 취소 시 재배포 흐름**, **(4) 아무도 안 받을 때의 타임아웃** — 이 4가지가 모두 없다.

---

## 1. 배경 · 목표

### 누구의 문제인가 (이해관계자)

- **지사(현장)** — 본 기능의 핵심 사용자. 내 지역 요청을 푸시로 받고 "수락" 한 번으로 담당이 된다. 처리 못 할 상황이면 "취소"로 되돌릴 수 있다.
- **식당(소비자)** — 부차적이지만 중요. 요청이 "접수만 되고 방치"되지 않고, 일정 시간 안에 담당 지사가 정해진다는 보장이 생긴다.
- **본사(HQ)** — 자동 배차로 수동 배정 부담이 줄어든다. 단 아무도 안 받을 때·반복 취소 시 **개입 권한은 본사가 끝까지 보유**한다(자동화가 본사 통제를 대체하지 않음).

### 목표

1. 수리 요청(앱·전화 양쪽)이 후보 지사들에게 뿌려지고, **가장 먼저 수락한 한 지사**가 담당이 된다(선착순).
2. 두 지사가 거의 동시에 수락해도 **DB 수준에서 한 곳만 성공**하고 나머지는 "이미 마감" 안내를 받는다 — 담당이 두 명이 되는 일이 절대 없다.
3. 담당 지사가 취소하면 요청이 **다시 후보 지사들에게 재배포**되고, 재알림이 간다.
4. 일정 시간 아무도 수락하지 않으면 **타임아웃 → 본사 개입**(수동 배정 또는 후보 확대)으로 넘어간다.
5. 기존 SLA 측정(`notified_at`→`accepted_at`)·본사 수동 배정·스케줄링(plan_phase3.6)과 **모순 없이** 맞물린다.
6. 모든 수락·취소·재배포·타임아웃은 `AuditLog`에 남는다(금기 ④의 정신 — 측정 가능해야 함).

### 비목표 (이번 범위 밖)

- 자동 우선순위 배차(지사 평점·거리순으로 한 곳만 콕 찍어 보내기). MVP는 **선착순만**. 우선순위 배차는 후속 phase.
- 본사 배차 현황 대시보드. 금기 ①(대시보드 선행 금지) — 실데이터 누적 후 검토.

---

## 2. 배차 상태 머신

### 2.1 설계 결정 — 배차 상태를 `status`로 표현할 것인가, 별도 컬럼인가

배차 진행 상태(뿌려짐/수락됨/재배포중)를 어디에 둘지 두 안을 비교한다.

- **안 A — 기존 `status`에 신규 값 추가**: `OPEN`, `CLAIMED`, `REASSIGNING` 등을 `status` enum에 넣는다.
  - 단점: `status`는 이미 식당 화면·지사 화면·정산 로직이 분기 조건으로 쓰는 **공유 컬럼**이다. 여기에 배차 전용 상태를 섞으면 "수락은 됐지만 작업은 시작 전"인 단계가 `IN_PROGRESS`도 `PENDING`도 아닌 모호한 값이 되어 기존 분기 코드가 줄줄이 깨진다(harness_rules.md 위반 위험).
- **안 B — `dispatch_status` 전용 컬럼 신설 (권고 ✅)**: 배차 진행 상태만 담는 별도 컬럼을 두고, 기존 `status`는 손대지 않는다.
  - 장점: 기존 `status` 값(`PENDING`/`IN_PROGRESS`/...)과 분기 코드를 **한 줄도 안 건드린다**. 배차는 `dispatch_status`라는 독립 축에서 돈다. plan_phase3.6이 `SCHEDULED` 1개만 조심스럽게 추가한 것과 같은 보존 정신.
  - `status`와의 관계: `status`는 "작업이 어디까지 진행됐나"(업무 생애주기), `dispatch_status`는 "담당 지사가 정해졌나"(배정 생애주기). 두 축은 직교한다.

**권고: 안 B 채택.** 아래 상태 머신은 모두 `dispatch_status` 기준이다.

### 2.2 `dispatch_status` 상태값

| 값 | 의미 | 진입 시점 |
| :-- | :-- | :-- |
| `OPEN` | 후보 지사들에게 뿌려져 수락 대기 중 | 요청 생성 직후(앱) / 지사가 전화접수 DRAFT를 확정한 직후 |
| `CLAIMED` | 한 지사가 수락해 담당 확정됨 | 지사가 수락 성공 |
| `REASSIGNING` | 담당 지사가 취소 → 재배포되어 다시 수락 대기 중 | 담당 지사 취소 |
| `ESCALATED` | 타임아웃 또는 반복 취소로 본사 개입 대기 | 타임아웃 만료 / 재배포 한계 초과 |
| `HQ_ASSIGNED` | 본사가 강제 배정해 담당 확정됨 | 본사가 수동 배정(`admin.html` PATCH) |
| `CANCELLED` | 요청 자체가 폐기됨(식당 철회·중복 등) | 본사/식당 취소 |

> `OPEN`과 `REASSIGNING`은 둘 다 "수락 대기 중"이지만 분리한다 — 재배포된 건은 "한 번 엎어진 건"이라 본사가 우선 살펴봐야 하고, 통계에서도 1차 배차와 재배차를 구분해야 하기 때문.

### 2.3 상태 전이 다이어그램

```
                      [요청 생성 / 전화접수 확정]
                                │
                                ▼
                          ┌──────────┐
                ┌────────▶│   OPEN   │◀─────────┐
                │         └──────────┘          │
                │            │   │              │
       (재배포)  │   (지사수락)│   │(타임아웃)     │
                │            ▼   │              │
                │      ┌──────────┐              │
                │      │ CLAIMED  │              │
                │      └──────────┘              │
                │       │       │                │
      (담당지사 │취소)  │       │(본사 강제배정)   │
                │       ▼       ▼                │
          ┌──────────┐    ┌──────────────┐       │
          │REASSIGNING│   │ HQ_ASSIGNED  │       │
          └──────────┘    └──────────────┘       │
            │  │  │              │               │
   (지사수락)│  │  │(재배포한계초과 │               │
            │  │  └──────────┐   │또는 타임아웃)   │
            │  │             ▼   ▼               │
            │  └────────▶┌──────────────┐         │
            │            │  ESCALATED   │─────────┘
            │            └──────────────┘  (본사가 후보 재확대)
            ▼                   │
       ┌──────────┐             │(본사 강제배정)
       │ CLAIMED  │             ▼
       └──────────┘      ┌──────────────┐
                         │ HQ_ASSIGNED  │
                         └──────────────┘

  ※ 어느 상태에서든 본사·식당은 요청을 CANCELLED(폐기)로 보낼 수 있다.
  ※ CLAIMED / HQ_ASSIGNED 이후 실제 작업 진행은 기존 status 축
    (IN_PROGRESS → PAYMENT_REQUESTED → COMPLETED)이 담당한다.
```

핵심 원칙:
- **수락 대기 상태(`OPEN`/`REASSIGNING`/`ESCALATED`)에서만 지사가 수락할 수 있다.** `CLAIMED` 상태의 요청에 수락 시도가 오면 "이미 마감"으로 거절한다 — 이것이 동시 수락 경합의 방어선(§4).
- **본사 강제 배정(`HQ_ASSIGNED`)은 어느 상태에서든 가능**하다. 자동 배차가 막혀도 본사는 항상 길을 뚫을 수 있어야 한다.
- `accepted_at`(SLA 종료점)은 **최초로 담당이 확정되는 순간**(`OPEN/REASSIGNING/ESCALATED → CLAIMED` 또는 `→ HQ_ASSIGNED`) 한 번만 기록하고 이후 재배포·재수락이 있어도 덮어쓰지 않는다 — plan_phase3.5의 "최초값 유지" 규칙을 그대로 지킨다(§5.3).

---

## 3. 시나리오별 처리 규칙

### 3.1 후보 지사 선정 (배포)

- 기존 `create_request`의 지역 매칭 로직을 **그대로 자산으로 재사용**한다: 식당 `region`과 일치하거나, 식당 주소(`address`)에 지사 `region_code`가 포함된 지사가 후보다.
- 요청 생성 시 `dispatch_status = OPEN`, `notified_at = now`(SLA 시작 — plan_phase3.5와 동일)로 시작하고 후보 지사 전원에게 FCM 푸시.
- **후보가 0곳인 경우**: 어떤 지사도 지역 매칭이 안 되면 즉시 `ESCALATED`로 보내고 본사에 알림. 식당을 응답 없는 `OPEN`에 방치하지 않는다.

### 3.2 선착순 수락 — 정상 케이스

- 후보 지사가 푸시를 보고 앱에서 "수락"을 누르면 `POST /requests/{id}/claim` 호출.
- 요청이 수락 대기 상태(`OPEN`/`REASSIGNING`/`ESCALATED`)이면: `assigned_branch_id` = 그 지사, `dispatch_status = CLAIMED`, `accepted_at` 최초 기록.
- 수락한 지사 외 나머지 후보들에게 "이 요청은 다른 지사가 맡았습니다" 푸시(또는 앱이 목록 새로고침 시 사라지게) — 헛걸음 방지.

### 3.3 동시 수락 경합 (가장 중요한 난점)

- 두 지사가 거의 동시에 `claim`을 누르면, **DB 수준 원자적 갱신**으로 정확히 한 요청만 성공한다(기술 방안은 §5 전체).
- **이긴 지사**: 200 OK + "배정 완료".
- **진 지사**: 409 Conflict + "이미 다른 지사가 수락했습니다" — 앱이 이 메시지를 받아 해당 요청 카드를 목록에서 제거.
- 절대 발생하면 안 되는 것: `assigned_branch_id`가 나중 지사 값으로 덮어써지는 것. → §5의 조건부 UPDATE로 원천 차단.

### 3.4 수락 후 취소 (re-broadcast)

- 담당 지사(`CLAIMED` 상태)가 처리 불가를 확인하면 `POST /requests/{id}/release`(취소) 호출.
- 처리: `assigned_branch_id = NULL`, `dispatch_status = REASSIGNING`, `cancel_count += 1`. `accepted_at`은 **지우지 않는다**(최초 수락 시각의 사실은 남김 — 다만 §5.3 주석 참조).
- 후보 지사들(취소한 지사 **포함** 여부는 정책 선택 — 아래)에게 재배포 푸시: "재배정 요청 — 이전 담당 지사가 처리를 취소했습니다".
- **취소 이력 기록**: 단순 카운터(`cancel_count`)만으로는 "누가·왜·언제" 취소했는지 안 남는다. 별도 이력이 필요하다 — §4(데이터 모델)에서 `DispatchEvent` 모델로 다룬다.
- **취소한 지사를 재배포 후보에서 뺄 것인가**: MVP는 **빼지 않는다**(다시 후보에 포함). 이유: 취소가 "지금은 바쁨" 같은 일시적 사유일 수 있고, 영구 배제는 작은 지역에서 후보 고갈을 부른다. 대신 §3.6의 반복 취소 패널티로 다룬다.

### 3.5 아무도 수락 안 함 (타임아웃)

- `OPEN`/`REASSIGNING` 상태가 **타임아웃 시간**(2026-05-16 대표 확정 — **60분(1시간)**, SLA 임계치와 통일)을 넘기면 `ESCALATED`로 전이하고 본사에 알림.
- 본사는 `ESCALATED` 요청에 대해 두 가지 중 택일:
  1. **수동 배정** — 특정 지사를 직접 지정(`HQ_ASSIGNED`).
  2. **후보 범위 확대 후 재배포** — 인접 지역 지사까지 후보에 넣어 다시 `OPEN`으로 — `dispatch_status`를 `OPEN`으로 되돌리고 재푸시.
- **타임아웃을 누가 감지하나 (스케줄러 문제)**: plan_phase3.6 §5와 동일한 고민. **2026-05-16 대표 확정 — MVP는 아래 방식 A(경량)로 가고, 정식 자동 실행(방식 B)은 plan_phase3.6 방문 임박 알림과 묶어 후속 통합**:
  - **방식 A (MVP 채택)**: 본사 화면(`admin.html`)이 열릴 때 / 주기 폴링 시 "타임아웃 후보"(수락 대기 + `dispatch_deadline` 경과)를 조회해 `ESCALATED`로 승격하는 가벼운 점검 엔드포인트(`POST /requests/dispatch/sweep`)를 호출. 추가로 FastAPI 기동 시 백그라운드 태스크로 한 번씩 호출.
  - **방식 B (후속)**: 서버에 1분~5분 간격 cron으로 같은 sweep을 자동 호출. plan_phase3.6의 방문 임박 알림 스케줄러와 **하나의 스케줄러로 묶어** 후속 phase에 도입.

### 3.6 반복 취소 지사 — 패널티 / 표시

- `cancel_count`와 `DispatchEvent` 이력으로 "특정 지사가 같은 요청을 반복 취소"하거나 "여러 요청을 자주 취소"하는 패턴을 식별할 수 있다.
- MVP 범위: **차단·자동 패널티는 두지 않는다.** 대신:
  - **2026-05-16 대표 확정 — 재배포 한계 2회**: 한 요청을 **2회까지 재배포**하고, **3번째 취소부터는** 더 이상 재배포하지 않고 즉시 `ESCALATED` → 본사 개입(무한 재배포 루프 방지).
  - 본사 화면에서 요청별 `cancel_count`와 취소 이력을 볼 수 있게 노출(단순 표시 — 대시보드 아님, 금기 ① 무관).
- **2026-05-16 대표 확정 — 반복 취소 지사 표시**: 차단·자동 페널티는 두지 않되, `DispatchEvent` 이력을 지사별로 집계해 본사 화면에 **"잦은 취소 지사"로 누적 표시**한다. 푸시 알람을 강제로 보내는 방식이 아니라, 본사가 화면에서 취소가 잦은 지사를 한눈에 식별할 수 있게 한다. 데이터(`DispatchEvent`)가 먼저 쌓이고 그 위에 표시가 올라가는 구조이므로 금기 ①(데이터 없이 평가 화면 선행)에 어긋나지 않는다.
- 지사별 취소율 등급·페널티(자동 제재)는 **실데이터가 쌓인 후** 별도 phase에서 검토.

### 3.7 본사 강제 배정과의 공존

- 현재 `admin.html`이 쓰는 `PATCH /requests/{id}`로 `assigned_branch_id`를 지정하는 경로는 **유지**한다. 단 배정 성공 시 `dispatch_status`를 `HQ_ASSIGNED`로 함께 세팅하도록 `update_request`에 분기 1개 추가.
- 본사 강제 배정은 우선권을 가진다 — `OPEN`이든 `CLAIMED`든 `ESCALATED`든 본사가 배정하면 그 지사가 담당이 된다. (단 `CLAIMED` 상태를 본사가 다른 지사로 바꿔치기하면 기존 담당 지사가 혼란하므로, 이 경우 양쪽 지사에 알림 — §5.4.)
- 선착순 자동 배차와 본사 수동 배정은 **같은 `accepted_at`·`assigned_branch_id` 필드를 공유**한다. 충돌 방지는 §5의 동시성 제어가 똑같이 적용된다(본사 PATCH도 조건부 UPDATE를 거치게).

### 3.8 앱 접수 / 전화 접수 양쪽 적용

- **앱 접수**: `create_request` 시점에 바로 `dispatch_status = OPEN` + 후보 푸시. 위 흐름 그대로.
- **전화 접수**(plan_phase8.5): 전화 요청은 `status = DRAFT`로 시작하고, 지사 콜백 후 사람이 `PENDING`으로 확정한다. 배차는 **그 확정 시점**에 시작한다 — DRAFT 단계에서는 `dispatch_status`를 `NULL`(미해당)로 두고, DRAFT→PENDING 전환 시 `OPEN`으로 세팅 + 후보 푸시.
- 즉 배차 로직의 **트리거는 "요청 생성"이 아니라 "수락 대기 상태로 들어가는 순간"**으로 정의한다. 앱 접수는 그 둘이 동시이고, 전화 접수는 분리되어 있을 뿐 — 동일한 배차 엔진을 양쪽이 공유한다.

---

## 4. 데이터 모델 영향

### 4.1 `ServiceRequest` 컬럼 추가

| 컬럼 | 타입 | 의미 |
| :-- | :-- | :-- |
| `dispatch_status` | `str` (nullable, index) | 배차 진행 상태 — §2.2 값. 전화 DRAFT는 NULL |
| `cancel_count` | `int` (default 0) | 담당 지사 취소 누적 횟수 — 재배포 한계 판단용 |
| `dispatch_deadline` | `datetime` (nullable) | 현재 수락 대기의 타임아웃 만료 시각. `OPEN`/`REASSIGNING` 진입 시 `now + 60분`으로 세팅, sweep이 이 값을 본다 |

- 기존 `status`·`assigned_branch_id`·`notified_at`·`accepted_at`·`assigned_at`·`completed_at`은 **건드리지 않는다**. `dispatch_status`는 독립 축(§2.1).
- 마이그레이션: plan_phase3.5·3.6과 동일하게 `init_db()`의 `ALTER TABLE ADD COLUMN IF NOT EXISTS` 패턴으로 추가하고, 정식 Alembic 리비전은 서버에서 후속 생성(현재 head `9ef3418df4f2` 다음).

### 4.2 신규 모델 — `DispatchEvent` (배차 이력)

취소 이력을 `cancel_count` 카운터 하나로만 두면 "누가·언제·왜 취소했는지", "몇 번째 재배포인지"를 알 수 없다. 배차 흐름은 한 요청에서 여러 번 일어나므로(수락→취소→재배포→수락...) **1:N 이력 테이블**이 필요하다.

> 검토: `AuditLog`로 충분하지 않은가? — `AuditLog`는 `service_requests` 테이블의 before/after를 통째로 남기는 범용 감사 로그라 "배차 이벤트만" 골라 보기·집계가 어렵다. 배차는 SLA·재배포율 등 **전용 지표 산출 대상**이므로 조회·집계가 쉬운 전용 테이블을 둔다. (plan_phase8.5가 통화 녹음을 `RequestMedia`에 안 섞고 `PhoneCall`을 신설한 것과 같은 판단.) `AuditLog`에도 기존대로 남는다 — 이중이 아니라 역할 분리.

제안 스키마 (DDL은 backend-db가 Alembic로 확정):

```
DispatchEvent
  id              UUID    PK
  request_id      UUID    FK service_requests.id  (index)
  branch_id       UUID    FK branches.id  nullable   # 이벤트 주체 지사 (BROADCAST는 NULL 가능)
  event_type      str     # BROADCAST | CLAIM | CLAIM_REJECTED | RELEASE
                          # | TIMEOUT | ESCALATE | HQ_ASSIGN | REBROADCAST
  reason          str     nullable                   # 취소 사유 (지사가 버튼식으로 선택 — 자유 텍스트 금지, 금기 ③)
  round_no        int     default 1                  # 몇 번째 배포 라운드인지 (재배포마다 +1)
  created_at      datetime
```

- `event_type = RELEASE`(취소) 이벤트가 곧 취소 이력이다. `reason`은 **버튼 선택형**("일정 불가"/"지역 밖"/"인력 부족"/"기타") — 무한 타이핑 폼 금지(금기 ③).
- 모든 배차 동작이 `DispatchEvent` 1행을 남긴다 → 재배포율·평균 라운드 수·지사별 취소 건수를 후속 phase에서 바로 집계 가능.
- Money 필드 없음 → Decimal 이슈 무관.

### 4.3 스키마 노출

- `RequestRead`에 `dispatch_status`, `cancel_count`, `dispatch_deadline` 추가 — 식당·지사·본사 화면이 배차 상태를 표시할 수 있게.
- `RequestCreate`는 변경 없음 — `dispatch_status`는 서버가 세팅하지 클라이언트가 보내지 않는다.

---

## 5. 동시 수락 경합 방지 — 기술 방안

이 기능의 **단 하나의 핵심 난점**이다. "담당은 반드시 한 명"을 DB가 보장해야 하며, 애플리케이션 코드의 `if`문으로는 경합을 막을 수 없다(읽고-판단하고-쓰는 사이에 다른 트랜잭션이 끼어든다).

### 5.1 채택 방안 — 조건부 원자적 UPDATE (compare-and-set)

수락은 "읽어서 비었으면 채운다"가 아니라 **"비어 있을 때만 채우는 단일 UPDATE 문"**으로 처리한다.

```sql
UPDATE service_requests
   SET assigned_branch_id = :branch_id,
       dispatch_status    = 'CLAIMED',
       accepted_at        = COALESCE(accepted_at, :now),  -- 최초값 유지
       updated_at         = :now
 WHERE id = :request_id
   AND assigned_branch_id IS NULL                          -- 아직 아무도 안 잡음
   AND dispatch_status IN ('OPEN', 'REASSIGNING', 'ESCALATED');
```

- 이 UPDATE의 `WHERE` 절이 곧 경합 방어선이다. PostgreSQL은 단일 UPDATE 문을 원자적으로 처리하므로, 두 지사가 동시에 같은 문을 날려도 **행 잠금에 의해 한 쪽만 조건을 만족**하고 나머지는 `WHERE`에 걸려 0건 갱신된다.
- 백엔드는 **갱신된 행 수(rowcount)**를 본다:
  - `rowcount == 1` → 수락 성공 → `DispatchEvent(CLAIM)` 기록 → 200 OK.
  - `rowcount == 0` → 이미 다른 지사가 잡았거나 대기 상태가 아님 → `DispatchEvent(CLAIM_REJECTED)` 기록 → 409 Conflict.
- 별도 비관적 락(`SELECT ... FOR UPDATE`)도 가능하나, 단일 조건부 UPDATE가 더 단순하고 잠금 구간이 짧다. → **조건부 UPDATE 채택.**

### 5.2 SQLite 환경 주의 (중요)

- 로컬 dev나 `tests/test_models.py`는 SQLite를 쓸 수 있다. SQLite도 단일 UPDATE는 원자적이라 위 방식이 동작하지만, `init_db()`처럼 **엔진별 동작 차이**(CLAUDE.md 경고)가 있으므로 테스트는 반드시 PostgreSQL에서 한다.
- 본 로직은 SQLModel/SQLAlchemy의 `update()` 구문으로 작성하고 `result.rowcount`로 성공 판정한다 — ORM 객체를 읽어 `setattr` 후 commit 하는 방식(현재 `update_request` 패턴)은 **경합에 취약하므로 claim/release 경로에는 쓰지 않는다.**

### 5.3 SLA(`accepted_at`)와의 정합

- `accepted_at`은 위 UPDATE에서 `COALESCE(accepted_at, :now)`로 처리 — 이미 값이 있으면 유지, 없으면 지금. plan_phase3.5의 "재배정 시 최초값 유지" 규칙과 정확히 일치한다.
- 따라서 SLA 지표 `accepted_at − notified_at`은 **"최초 수락까지 걸린 시간"**으로 일관되게 유지된다. 재배포·재수락이 끼어도 SLA 정의가 흔들리지 않는다.
- 단, "취소 후 재배포되어 다시 수락된 건"은 SLA상 빠르게 보이지만 실제로는 한 번 엎어진 건이므로, **재배차 발생 여부는 `cancel_count`/`DispatchEvent`로 별도 추적**한다. SLA 요약(`/requests/sla/summary`)에 "재배차 건수"를 후속 필드로 추가 권고(plan_phase3.5 확장).
- `release`(취소) 시 `accepted_at`을 지울지: **지우지 않는다.** SLA는 "지사가 처음 응답한 시각"의 사실을 측정하는 것이고, 취소는 그 후의 별개 사건이다. 재배차 영향은 위 별도 지표로 본다.

### 5.4 본사 강제 배정도 같은 보호 적용

- `HQ_ASSIGN`은 본사 권한이므로 `WHERE assigned_branch_id IS NULL` 조건은 빼되, **여전히 단일 UPDATE 문**으로 처리한다(자동 claim과 본사 PATCH가 같은 행에 동시 접근할 때의 경합 방지).
- 본사가 `CLAIMED` 상태를 다른 지사로 강제 변경하면 기존 담당 지사·신규 담당 지사 양쪽에 FCM 알림(`DispatchEvent(HQ_ASSIGN)` 기록).

---

## 6. 백엔드 엔드포인트 개요

> 코드는 미작성. 아래는 backend-db가 후속 구현할 범위 정의. 모두 `requests.py`에 추가.

| 엔드포인트 | 역할 | 인증 |
| :-- | :-- | :-- |
| `POST /requests/{id}/claim` | 지사 수락. body에 `branch_id`. §5.1 조건부 UPDATE. 성공 200 / 경합·마감 409 | 지사 (3.2b까지 잠정 개방 — §8 위험) |
| `POST /requests/{id}/release` | 담당 지사 취소. body에 `branch_id`, `reason`(버튼값). `REASSIGNING` 전이 + 재배포 푸시. `cancel_count` 한계 초과 시 `ESCALATED` | 지사 |
| `POST /requests/dispatch/sweep` | 타임아웃 점검 — 수락 대기 + `dispatch_deadline` 경과 건을 `ESCALATED`로 승격, 본사 알림. cron/부팅 태스크/본사 화면이 호출 | HQ_ADMIN 또는 내부 |
| `POST /requests/{id}/rebroadcast` | 본사가 `ESCALATED` 건의 후보를 확대해 다시 `OPEN`으로. `round_no` +1 | HQ_ADMIN |
| `PATCH /requests/{id}` (기존) | 본사 강제 배정 — `assigned_branch_id` 세팅 시 `dispatch_status=HQ_ASSIGNED` 분기 1개 추가. claim 경로와 같은 §5.4 보호 | HQ_ADMIN (3.2b 후) |
| `POST /requests/` (기존) | 생성 시 `dispatch_status=OPEN`, `dispatch_deadline=now+60분` 세팅. 후보 0곳이면 `ESCALATED` | 개방 (기존) |

추가로:
- 전화 접수 DRAFT→PENDING 확정 경로(plan_phase8.5)에서 `dispatch_status=OPEN` 세팅 + 후보 푸시 호출(공용 배차 함수로 분리해 앱·전화가 공유).
- 후보 푸시·재배포 푸시는 기존 `send_push_notification`(FCM) 재사용 — 신규 인프라 없음.
- `claim`/`release`/`sweep`/`rebroadcast` 모두 `DispatchEvent` 1행 + 기존 `AuditLog` 1행을 남긴다.

---

## 7. 단계별 작업 순서 (Steps)

### 7.1 MVP (Phase 3.7)

1. **[backend-db]** `domain.py` — `ServiceRequest`에 `dispatch_status`/`cancel_count`/`dispatch_deadline` 추가. `DispatchEvent` 모델 신설.
2. **[backend-db]** `init_db()`에 3개 컬럼 `ALTER TABLE ADD COLUMN IF NOT EXISTS`(3.5·3.6 패턴). `dispatch_events` 테이블 생성. 정식 Alembic 리비전은 서버에서 후속.
3. **[backend-db]** `schemas/domain.py` — `RequestRead`에 배차 3필드 노출.
4. **[backend-db]** 공용 배차 함수(`_broadcast_to_candidates`) 추출 — 후보 선정(기존 지역 매칭 재사용) + 푸시 + `dispatch_deadline` 세팅 + `DispatchEvent(BROADCAST)`.
5. **[backend-db]** `create_request` — 생성 시 `dispatch_status=OPEN` + 공용 배차 함수 호출. 후보 0곳 → `ESCALATED`.
6. **[backend-db]** `POST /requests/{id}/claim` — §5.1 조건부 UPDATE, rowcount 판정, 409 처리, 패자에게 마감 푸시.
7. **[backend-db]** `POST /requests/{id}/release` — `REASSIGNING` 전이, `cancel_count` 증가, 한계 초과 시 `ESCALATED`, 재배포 푸시, `DispatchEvent(RELEASE)`.
8. **[backend-db]** `POST /requests/dispatch/sweep` — 타임아웃 승격. + 서버 cron 또는 부팅 시 백그라운드 호출(devops-security 협업).
9. **[backend-db]** `POST /requests/{id}/rebroadcast` + `update_request`에 `HQ_ASSIGNED` 분기 추가.
10. **[backend-db]** 전화 접수(plan_phase8.5) DRAFT→PENDING 확정 시 공용 배차 함수 호출 — 단 8.5 착수 시 합류(본 phase에서는 함수만 공용화해 둠).
11. **[frontend-mobile]** 지사 앱(`manager.html`) — 요청 카드에 "수락"/"취소"(취소 사유 버튼) 추가, 409 응답 시 "이미 마감" 안내 + 카드 제거. 본사 앱(`admin.html`) — `ESCALATED` 목록·`cancel_count` 표시·재배포 버튼. 기존 필터·검색·탭 보존(harness_rules.md).
12. **[qa-analyst]** 동시 수락 경합 테스트(같은 요청에 2개 claim 동시 호출 → 정확히 1건 200, 1건 409 검증) — PostgreSQL에서. 취소→재배포→재수락, 타임아웃→ESCALATED, `cancel_count` 한계, 본사 강제배정 경합 시나리오.

### 7.2 고도화 (후속 — 별도 phase)

- 우선순위 배차(지사 평점·거리·현재 부하 기반으로 후보 순위화, 단계적 푸시).
- 지사별 취소율 지표·등급(실데이터 누적 후 — 금기 ①).
- 정식 스케줄러로 sweep·plan_phase3.6 방문 임박 알림 통합.
- SLA 요약에 "재배차 건수·평균 배차 라운드" 지표 추가.

---

## 8. 리스크

| 리스크 | 대응 |
| :-- | :-- |
| 동시 수락으로 담당이 2명이 됨 (치명) | §5.1 조건부 원자적 UPDATE + rowcount 판정. ORM read-modify-write 금지. PostgreSQL에서 동시성 테스트 필수(§7.1-12) |
| `dispatch_status` 추가가 기존 `status` 분기 코드를 깸 | 안 B 채택 — `status`는 한 줄도 안 건드림. 독립 컬럼 신설(§2.1) |
| `PATCH /requests` 무인증 개방(3.2 §6) — 아무 지사나 남의 요청 수락·취소 | **3.2b 인증 선행 권고**(§9). 그 전 잠정 배포 시 claim/release body의 `branch_id`를 토큰과 대조하는 임시 검증이라도 두고, harnes.md 잔여 위험에 등록 |
| 무한 재배포 루프(취소-재배포-취소...) | `cancel_count` 한계(기본 3) 초과 시 `ESCALATED` 강제 — 본사 개입(§3.6) |
| 타임아웃 sweep용 스케줄러가 과설계로 번질 위험 | MVP는 cron/부팅 태스크/화면 폴링의 경량 방식. 정식 워커는 plan_phase3.6 알림 스케줄러와 묶어 후속(§3.5) |
| 후보 0곳인 지역에서 요청이 영원히 `OPEN` 방치 | 생성 시 후보 0곳이면 즉시 `ESCALATED`(§3.1) |
| 본사 강제배정과 자동 claim이 같은 행에 동시 접근 | 본사 PATCH도 단일 UPDATE 문으로 처리(§5.4) |
| 재배차 건이 SLA상 빠르게 보여 품질 착시 | `accepted_at`은 최초값 유지, 재배차는 `cancel_count`/`DispatchEvent`로 별도 추적·집계(§5.3) |

---

## 9. 완료 조건 (AC)

- 요청 생성(앱) 시 `dispatch_status=OPEN`, 후보 지사 전원에게 FCM 푸시, `dispatch_deadline` 세팅된다.
- 후보 0곳이면 즉시 `ESCALATED` + 본사 알림.
- 지사가 "수락"하면 한 지사만 `CLAIMED`로 확정되고 `accepted_at`이 기록된다.
- 두 지사가 동시에 수락해도 **정확히 한 건만 200, 나머지는 409 "이미 마감"** — PostgreSQL 동시성 테스트로 검증.
- 담당 지사가 "취소"하면 `REASSIGNING`으로 바뀌고 후보들에게 재배포 푸시, `cancel_count`와 `DispatchEvent(RELEASE)`가 남는다.
- `cancel_count`가 한계(2)를 넘으면(3번째 취소부터) 재배포 대신 `ESCALATED`로 간다.
- `dispatch_deadline` 경과 시 `sweep`이 `ESCALATED`로 승격하고 본사에 알린다.
- 본사가 `ESCALATED` 건을 강제 배정(`HQ_ASSIGNED`)하거나 후보 확대 재배포(`OPEN`)할 수 있다.
- 모든 배차 동작이 `DispatchEvent` + `AuditLog`에 남는다.
- 기존 SLA 측정·정산·식당/지사/본사 기존 화면이 회귀 없이 동작한다(기존 `status` 값 불변).
- 전화 접수(8.5) DRAFT→PENDING 확정 시 동일한 배차 엔진이 동작한다(8.5 착수 시점에 검증).

---

## 10. 우선순위 권고 — 3.6·3.2b와의 선후 관계

**권고 순서: `3.2b 인증 정비` → `3.7 배차` → `3.6 스케줄링`.**

근거:

1. **3.2b(인증)가 반드시 선행해야 한다.** 배차의 모든 동작("이 지사가 수락한다", "이 지사가 취소한다")은 *행위 주체가 누구인지* 신뢰할 수 있어야 성립한다. 현재 `PATCH /requests`는 무인증 개방이고(3.2 §6 잔여 위험) 지사 로그인은 가짜 OTP다. 인증 없이 배차를 올리면 아무 지사나 남의 요청을 가로채거나 취소할 수 있어 기능 자체가 무의미해진다. → **3.2b 선행은 타협 불가.**

2. **3.7 배차는 3.6 스케줄링보다 먼저다.** plan_phase3.6 §2 흐름이 `[지사] 요청 수락(배정) → 일정 화면에서 슬롯 배치`로, **"수락"이 일정 배치의 전제**다. 3.6은 "이미 담당이 정해진 요청"을 날짜에 꽂는 기능이고, 3.7은 "담당을 어떻게 정하나"를 푼다. 담당 확정 메커니즘(3.7)이 먼저 서야 3.6이 의미가 있다. plan_phase3.6 자신도 §11에서 "일정 배치는 배정 이후의 별도 동작"이라 명시했다 — 3.7이 그 "배정"의 구현체다.

3. **3.5(SLA)와는 독립이며 이미 정합한다.** SLA는 구현 완료됐고, 본 배차 설계는 `notified_at`/`accepted_at`을 §5.3대로 그대로 채워 SLA 정의를 보존한다. 3.7이 3.5를 깨지 않는다.

4. **3.7과 3.6은 모순되지 않게 설계됨.** 3.6의 `SCHEDULED`는 기존 `status` 축, 3.7의 `dispatch_status`는 독립 축 — 두 컬럼이 직교하므로 충돌 없다. 3.6 흐름에 "수락 = `CLAIMED`/`HQ_ASSIGNED` 확정 시점"만 매핑하면 그대로 이어진다.

5. **비용·리스크는 중간.** 신규 테이블 1개(`DispatchEvent`) + 컬럼 3개 + 엔드포인트 4개. 정산 같은 비가역 영역은 안 건드린다. 다만 동시성이라는 까다로운 영역이라 PostgreSQL 동시성 테스트(§7.1-12)에 충분한 시간을 배정해야 한다.

요약: **`3.2b 인증` → `3.7 배차(본 문서)` → `3.6 스케줄링`.** 정산(4.x)과는 독립이라 병행 가능.

> **확인 질문 — 2026-05-16 대표 답변으로 모두 종결됨**
> 1. 수락 타임아웃 — **60분(1시간)으로 확정.** SLA 임계치도 60분으로 통일(plan_phase3.5 반영). → §3.5·§4.1·§6 반영.
> 2. 타임아웃 자동 점검(sweep) — **MVP는 방식 A(경량 — 본사 화면 열 때 점검 + 기동 시 백그라운드)로 확정.** 정식 cron 자동 실행(방식 B)은 plan_phase3.6 방문 임박 알림 스케줄러와 묶어 후속 통합. → §3.5 반영.
> 3. 재배포 한계 — **2회로 확정.** 2회까지 재배포, 3번째 취소부터 `ESCALATED`(본사 개입). → §3.6·§9 반영.
> 4. 반복 취소 지사 — **자동 제재 없음, 본사 화면에 "잦은 취소 지사" 누적 표시로 확정.** `DispatchEvent` 이력을 지사별 집계해 노출. → §3.6 반영.

## 11. 시행착오

*(착수 후 엔지니어가 기록)*

## 12. 참조

- harnes.md §5 (계획서 없는 개발 금지 — 본 문서가 그 이행) · 금기 ① (대시보드 선행 금지) · 금기 ③ (무한 타이핑 폼 금지 — 취소 사유 버튼식) · 금기 ④ (SLA 측정)
- harness_rules.md (동작하는 기능 보존 — 기존 `status`·필터·탭 불변)
- plan_phase3.2_auth.md §6 (`PATCH /requests` 무인증 잔여 위험 — 3.7 선행 조건)
- plan_phase3.5_sla_measurement.md (`notified_at`/`accepted_at` — §5.3 SLA 정합 근거)
- plan_phase3.6_scheduling.md §2·§11 ("수락=배정"이 일정 배치의 전제 — 선후관계 근거)
- plan_phase8.5_phone_intake.md §3·§7 (전화 접수 DRAFT→PENDING 확정 시 배차 합류)
- backend/app/api/v1/endpoints/requests.py (`create_request`, `update_request` — 지역 매칭·SLA 기록 재사용 대상)
- backend/app/models/domain.py (`ServiceRequest`, `Branch`, `AuditLog`, `DeviceToken`)
