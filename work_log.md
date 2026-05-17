# 📓 WasherCRM 작업 일지 (Work Log)

세션마다 한 일·결정·다음 할 일을 정리해 남기는 일지. **새 항목은 맨 아래에 append**한다(추가 전용).
`director-archivist` 에이전트가 세션 종료 시 기록한다. 원본 대화 트랜스크립트는
`~/.claude/projects/C--Users-zpwkg-Documents-WasherCRM/*.jsonl`에 Claude Code가 자동 보존하며, 이 문서는 그 요약본이다.

블록 형식: `세션 날짜 · 제목 / 대화 요약 / 한 일 / 결정 / 다음 할 일 / 미해결·주의`.

---

## 2026-05-15 — 세션 복구 + 연속 운영 체계 구축

**대화 요약**
- 이전 세션이 UTF-16 surrogate API 에러로 중단됨. 새 세션이 `git log` + `work_schedule.md`로 진행 상황을 파악하고 이어받음.
- 사용자가 "일을 늘 연속성 있게" 하고 싶어 함 → 작업 기록·정리 담당("친구")이 필요하다는 논의 → 기존 `director-archivist`를 확장하는 것으로 결정(신규 에이전트는 업무 중복).

**한 일**
- `human_preparation_guide.md` 인코딩 점검 — 이전 아카이브 커밋 `f9122de`가 이미 NUL 9바이트를 제거·정상화한 것 확인. 추가 조치 불필요.
- 워크트리 `claude/epic-feistel-a98d89` 폐기 — 구버전 스냅샷 확인 후 브랜치 삭제 + 워크트리 등록 해제. 권한 2줄은 메인의 `Bash(git *)`에 이미 포함되어 손실 없음.
- `CLAUDE.md` — `Continuous Operation Mode` 섹션 추가(세션 연속성·자율 실행 L0~L2·무중단 운영).
- `director-archivist.md` — Decision Log + Work journal 책임 추가.
- `decision_log.md` 신설 — ADR-001~005 (`workplan.md §9` 표 이전).
- `work_log.md` 신설(이 문서) + `SessionStart` 훅 설정.

**결정**
- ADR-005: Continuous Operation Mode 도입 (`decision_log.md` 참조).
- 작업 기록 담당은 신규 에이전트 대신 `director-archivist` 확장으로 통일.

**다음 할 일**
- **§3.2 JWT 인증 시스템** — `work_schedule.md` Phase B의 다음 작업. 착수 전 `plan_phase3.2_auth.md` 작성 필수(harnes.md §5). Opus 권장 작업.

**미해결·주의**
- 빈 디렉터리 `.claude/worktrees/epic-feistel-a98d89`가 프로세스 잠금으로 잔존. git은 인식하지 않으며 무해. 잠근 프로세스(터미널/에디터) 종료 후 수동 삭제 필요.

---

## 2026-05-15 (이어서) — 운영 분석(§6) + §3.2a 본사 로그인 구현

**대화 요약**
- 어제 끊긴 운영 분석(A)을 점검 → blueprint §6이 2026-05-11 기준이라 일부 stale함을 발견, 2026-05-15 기준으로 갱신.
- 이어서 인증(B)으로 진행. 사장님 결정: 본사는 id/비밀번호(`admin`/`0000` 임시), 식당·지사는 나중에 포트원 PASS로 정식 휴대폰 인증.
- 사장님이 비전문가용 쉬운 설명을 요청 → 용어(stale, JWT 등)는 처음 나올 때 풀어 설명하기로 함.

**한 일**
- `blueprint.md §6` 갱신 — "RDS 전환 필수" 등 stale 내용을 현재 상태(네이티브 PostgreSQL, 도메인 확보 등)로 정정.
- `plan_phase3.2_auth.md` 작성 (harnes.md §5).
- 백엔드: `core/security.py`(무의존성 표준 JWT HS256), `api/deps.py`(`require_role`), `endpoints/auth.py`(`POST /auth/login`), `core/config.py`에 JWT 설정 추가.
- `audit-logs`에 `require_role("HQ_ADMIN")` 적용, `api.py`에 auth 라우터 등록.
- `www/admin.html` + `backend/app/static/admin.html`(동일 파일)에 본사 로그인 화면 추가. `window.fetch` 래핑으로 기존 호출 수정 없이 토큰 자동 첨부.
- `tests/test_auth.py` 작성 — 14개 테스트 전부 통과.

**결정**
- ADR-006: 본사 id/pw + JWT, `admin`/`0000` 임시 계정.

**다음 할 일**
- 서버 기동 환경에서 `admin.html` 로그인 화면 브라우저 실동작 확인 (이번 세션은 자동 테스트까지만).
- §3.2b(식당·지사 PASS 인증)는 포트원 가입 후.

**미해결·주의**
- `admin`/`0000`은 임시 비밀번호 — 실서비스 오픈 전 반드시 교체 (harnes.md 2026-05-15 이슈로 등록됨).

---

## 2026-05-16 — 코드 감사 + 보안 개선 (H1·H2·H4·H7)

**대화 요약**
- 백엔드·프론트·보안·아키텍처 4개 도메인을 전문 에이전트로 병렬 감사 → 높음 7항목 발견. 사용자와 우선순위·진행 방식 합의.
- 사용자가 "삭제 기능 잠금"을 "데이터 삭제"로 오해해 우려 → 아무 데이터도 삭제하지 않았고 기능에 권한 잠금만 추가했음을 설명해 해소. (비전문가용 표현 주의 — [[user-non-technical-background]])

**한 일**
- 코드 감사 종합 보고서 작성.
- H2: `.gitignore`에 `.env.*` 추가, `.env.production` git 추적 제거 (placeholder뿐 — 실제 유출 없음 확인).
- H4: `init_db()`의 하드코딩 결제 재연결·가짜 후기 주입 SQL 제거, `payments.py` GET 부수효과 제거.
- H7: CORS `allow_origins` 와일드카드 제거 → 운영 도메인 화이트리스트.
- H1: 본사 전용 엔드포인트 6곳에 `require_role("HQ_ADMIN")` 적용 (실적 대시보드·삭제 3종·결제목록·기기토큰목록).
- 텔레그램 봇 토큰을 `backend/.env`(gitignore됨)에 저장, `@whiteon_claude_bot` 검증 완료.

**결정**
- ADR-007: API 잠금은 본사 전용 엔드포인트만, 식당·지사 사용 엔드포인트는 §3.2b까지 개방.

**다음 할 일**
- H5(SLA 측정) — DB 스키마 변경(컬럼 추가 + 마이그레이션) 필요. 동작 확인 단계와 함께 진행.
- 동작 확인 — 서버 기동 후 본사 로그인·잠금·식당·지사 화면 실동작 확인.
- 텔레그램 chat_id 확보 후 운영 알림 연동.

**미해결·주의**
- PATCH 엔드포인트(지사·식당·요청 수정/승인)는 아직 개방 — §3.2b 역할 분리 대기. harnes.md 2026-05-16 이슈 참조.

---

## 2026-05-17 — §4.2 정산 엔진 구현 (계산 알고리즘 + HQ·지사 운영 화면)

**대화 요약**
- §4.1 정산 스키마(2026-05-12) 위에 실제 계산 엔진과 운영 화면을 올리는 작업. 착수 전 `plan_phase4.2_settlement_engine.md` 선작성(harnes.md §5 준수).
- 외부 계정(PortOne 실결제·Popbill 실발행) 대기 항목은 이번 범위에서 제외하기로 합의 — 정산 엔진은 현재 결제 기록(매니저 입력액)을 그대로 집계하고, 추후 실결제가 붙어도 코드는 동일하게 동작.

**한 일**
- `backend/app/services/settlement.py` 신규 — 정산 계산 엔진. PAID 결제를 기간×지사별 집계 → Settlement+SettlementItem 생성. VAT 분리(공급가=gross/1.1), 등급별 수수료 매핑(BRONZE 10%·SILVER 8%·GOLD 6%·DIAMOND 5%), 멱등성((지사,기간) 중복 방지), 음수 net→HOLD. 변경 가능 정책(수수료율·VAT율·반올림)은 파일 상단 상수로 분리.
- `backend/app/api/v1/endpoints/settlements.py` 신규 — 정산 API 5종: POST /generate(HQ), GET /(HQ), GET /my(지사), GET /{id}(HQ·지사 본인), PATCH /{id}/status(HQ). 상태 전이 머신 DRAFT→REVIEW→APPROVED→PAID→INVOICED + HOLD 분기, 비허용 전이는 400.
- `backend/app/api/v1/api.py` — settlements 라우터 등록.
- `backend/app/schemas/domain.py` — SettlementRead/SettlementItemRead/SettlementGenerate/SettlementStatusUpdate 추가.
- `www/admin.html` — HQ "정산 관리" 탭 추가(기간 선택·생성, 정산서 목록·상세 모달, 상태 전이 버튼).
- `www/manager.html` — 지사 "정산" 탭 추가(본인 정산서 목록, 라인 펼쳐보기).
- `plan_phase4.2_settlement_engine.md` 신규 — 실행 계획서(코드보다 먼저 작성).
- 검증: 정산 산식 단위·통합 검산 통과(gross 880000→hq 70400(8%)→net 809600, 멱등성 OK), API 5종 동작 확인(상태 전이 정상·비정상 경로, BRANCH 본인만 조회·HQ전용 403), HTML JS 구문 검사 통과. AWS(13.124.100.75) 배포 완료, 백엔드 재기동 active, dev=AWS 6개 파일 md5 동일.
- 커밋 `0ed2802`(브랜치 1.0.0.7), GitHub 푸시 완료.

**결정**
- 외부 계정 대기(PortOne 실결제·Popbill 세금계산서 실발행)는 이번 범위에서 제외 — 정산 엔진은 현재 결제 기록을 집계, 추후 실결제 붙어도 코드 동일 동작.
- 환불 차감(refund_offset)은 현재 환불 데이터가 없어 0으로 고정, 로직 자리만 유지.
- 정산 주기·수수료율은 대표님이 반려·변경할 수 있는 정책 — 코드 상수/파라미터로 분리.

**다음 할 일**
- §4.5 Popbill 전자세금계산서 자동 발행 워커 — 사람 트랙(팝빌 가입·인증서 등록) 대기.
- §3.1 통합 로그인 페이지 UI — 보류 항목, 별도 착수 시점 협의 필요.
- §3.2b 식당·지사 PASS 휴대폰 본인인증 — 포트원 가입 후(사람 트랙 대기).
- §3.4 가입 검증 규칙 재설계.

**미해결·주의**
- AWS 배포 검증 중 `POST /generate`로 의정부1지사의 실제 테스트 결제(2026-05-11~17, 매출 11,000,110원) 정산서 1건이 DRAFT 상태로 생성됨. DRAFT라 비가역 아님 — 정식 정산 전 정리 또는 그대로 검토 진행 판단 필요.
- 정산 엔진은 현재 매니저 입력 결제액 기준 집계 — 실결제(PortOne) 연동 시 결제 데이터 출처만 바뀌고 엔진 로직은 불변.
