# plan_phase3.5_sla_measurement — SLA(지사 응답시간) 측정

> 작성일: 2026-05-16 · 모델: Opus
> 근거: harnes.md 금기 ④ (SLA 대응시간 측정 누락 금지) · 2026-05-16 코드 감사 H5

## 0. 배경

현재 `ServiceRequest`에는 `created_at`, `assigned_at`(status가 IN_PROGRESS로 바뀔 때 기록), `completed_at`만 있다. **"지사가 요청을 수락하기까지 걸린 시간"을 측정할 수 없다** → 금기 ④ 위반.

## 1. 설계

- `ServiceRequest`에 컬럼 2개 추가:
  - `notified_at` — 요청이 생성되어 지사에 브로드캐스트된 시각 (**SLA 시작점**)
  - `accepted_at` — 어떤 지사가 처음 배정(수락)된 시각 (**SLA 종료점**)
- SLA 지표 = `accepted_at − notified_at` = "지사 수락까지 걸린 시간".

## 2. 단계별 작업

1. `domain.py` — `ServiceRequest`에 `notified_at`, `accepted_at` (nullable datetime) 추가.
2. `db/session.py` `init_db()` — `service_requests`에 두 컬럼 `ALTER TABLE ADD COLUMN IF NOT EXISTS` 추가. (로컬에 Alembic 미설치 — 기존 init_db 스키마 패치 방식을 답습. 정식 Alembic 리비전은 서버에서 후속 생성.)
3. `requests.py` `create_request` — 생성 시 `notified_at` 기록.
4. `requests.py` `update_request` — `assigned_branch_id`가 처음 None→값으로 바뀔 때 `accepted_at` 기록(재배정 시 최초값 유지).
5. `schemas/domain.py` `RequestRead` — `notified_at`, `accepted_at` 노출.
6. `GET /requests/sla/summary` (HQ_ADMIN 전용) — 수락 건수, 평균·최대 수락 소요시간(분), 임계치(기본 60분 = 1시간, 2026-05-16 대표 확정) 초과 건수, 미수락 대기 건수 반환.

## 3. 완료 조건 (AC)

- 새 요청 생성 시 `notified_at` 기록.
- 지사 최초 배정 시 `accepted_at` 기록, 재배정 시 최초값 유지.
- `/requests/sla/summary`가 본사 로그인 시 통계 반환, 비로그인 시 401.
- 기존 식당·지사·본사 화면 회귀 없음.

## 4. 참조

- harnes.md 금기 ④ · blueprint.md §2.3(SLA 관리) · 2026-05-16 코드 감사 보고
