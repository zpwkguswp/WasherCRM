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
