# 📋 WasherCRM 의사결정 로그 (Decision Log)

이 문서는 프로젝트의 아키텍처·운영상 주요 결정을 시간순으로 기록하는 **단일 출처(single source of truth)**다. (Architecture Decision Record 간이판)

## 기록 규칙

- **추가 전용(append-only)** — 과거 결정 행은 수정·삭제하지 않는다. 결정이 번복되면 *새 행*을 추가하고 비고에 `ADR-xxx 대체`로 이전 결정을 참조한다.
- 날짜는 절대 표기(`2026-05-15`).
- 비자명한 결정 — 기술 스택, 스키마 형태, 인프라 선정, 정산 주기 규칙, Approval Mode 승급 등 — 이 확정되면 `director-archivist` 에이전트가 한 행을 추가한다.
- 아키텍처를 바꾸는 결정은 `blueprint.md`에도, 로드맵을 바꾸는 결정은 `workplan.md` / `work_schedule.md`에도 함께 반영한다.

## 결정 목록

| ID | 일자 | 결정 | 근거 | 결정자 |
| :--- | :--- | :--- | :--- | :--- |
| ADR-001 | 2026-05-11 | (이전) RDS PostgreSQL 검토 | SQLite는 결제 동시성 대응 불가 | — |
| ADR-002 | 2026-05-11 | 정산 주기는 주 단위, 마감 일요일, 지급 익주 화요일 | 사장님 요구사항(추정) | (확인 필요) |
| ADR-003 | 2026-05-12 | **EC2 네이티브 PostgreSQL 채택** (RDS 대신) — ADR-001 대체 | t3.micro 메모리 제약 + 운영 단순성. RDS는 결제 트래픽 시점에 재검토 | Sonnet+사용자 |
| ADR-004 | 2026-05-12 | trading_bot은 별도 인프라(Oracle Cloud Free 등) 이전 검토 | EC2 디스크 800MB 절약, 책임 분리 | 사용자 |
| ADR-005 | 2026-05-15 | **Continuous Operation Mode 도입** — 세션 연속성·자율 실행(L0/L1/L2)·무중단 운영 규정 | 2026-05-15 세션이 UTF-16 surrogate API 에러로 중단 → 연속성 보장 필요 | Opus+사용자 |
| ADR-006 | 2026-05-15 | **본사 로그인 = id/비밀번호 + JWT** (식당·지사는 PASS 휴대폰 인증으로 별도·나중에). 임시 계정 admin/0000, 환경변수로 분리. JWT는 무의존성 표준 HS256 자체 구현 | 본사 접근 통제가 시급(현재 무인증). 포트원 PASS는 사람 트랙 대기 중이라 식당·지사는 후순위 | 사용자+Opus |

---

## 관련 문서
- [CLAUDE.md](./CLAUDE.md) — Continuous Operation Mode 섹션
- [workplan.md](./workplan.md) — 작업 실행 계획서
- [blueprint.md](./blueprint.md) — 마스터 스펙
