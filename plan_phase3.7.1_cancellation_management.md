# plan_phase3.7.1 — 취소 내역 관리 (배차취소 가시화)

> 2026-05-16 작성. plan_phase3.7(배차)의 후속. 코드 미작성 — 본 문서 승인 후 착수.

## 1. 배경 / 목표

지사가 배차를 취소(`release`)할 때 사유(일정 불가 / 지역 밖 / 인력 부족 / 기타)를
이미 `DispatchEvent` 테이블에 기록하고 있다. 그러나 **본사가 이 취소 사유·이력을
볼 방법이 없다.** 두 가지 화면을 추가해 가시화한다.

1. **요청 단위** — 특정 수리 요청이 접수→배포→취소→재배포 되며 헤맨 이력을 본다.
2. **지사 단위** — 어느 지사가 얼마나 자주 취소하는지(잦은 취소 지사) 집계로 본다.

데이터는 이미 쌓이고 있으므로 **신규 테이블·마이그레이션 없음.** 조회 API와 화면만 추가.

## 2. 데이터 — 기존 `DispatchEvent` 재사용

`DispatchEvent`: `request_id`, `branch_id`, `event_type`(BROADCAST/CLAIM/RELEASE/
REASSIGN/ESCALATE/TIMEOUT/HQ_ASSIGN), `reason`, `round_no`, `created_at`.
취소는 `event_type='RELEASE'`, `reason`에 사유 문자열.

## 3. 백엔드 — 신규 엔드포인트 2개 (둘 다 HQ_ADMIN 전용)

| 엔드포인트 | 설명 |
| :-- | :-- |
| `GET /requests/{id}/dispatch-events` | 한 요청의 배차 이벤트 타임라인. 각 행: 이벤트종류·사유·지사명(branch_id→이름)·회차·시각. 시간순. |
| `GET /branches/metrics/cancellations` | 지사별 RELEASE(취소) 집계. 각 지사: 총 취소 건수 + 사유별 건수. 취소 많은 순 정렬. |

## 4. 프론트 — 본사앱(`admin.html`) 2곳

1. **관제 → 요청 클릭(openManageRequest 모달)**: "배차 이력" 섹션 추가.
   `dispatch-events`를 불러와 타임라인으로 표시 — 언제 누가 수락/취소했는지, 취소 사유.
2. **성과 분석 대시보드**: "지사별 취소 현황" 카드 추가.
   `metrics/cancellations` 표 — 지사명 / 취소 건수 / 사유별. 취소 건수 많은 지사는
   빨간색 강조("잦은 취소 지사").

## 5. 비범위 (이번에 안 함)

- 취소에 따른 패널티·점수 차감 — 안 함(대표 방침: 패널티 없음, 표시만).
- 기간 필터 — MVP는 전체 누적. 추후 필요 시 추가.

## 6. 착수 순서

1. 백엔드 엔드포인트 2개 → 로컬 검증
2. 본사앱 화면 2곳 → 로컬 검증
3. AWS 동기화 배포 + git 커밋
