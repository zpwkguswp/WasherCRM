# plan_phase3.2_auth — 인증 시스템 (JWT 로그인)

> 작성일: 2026-05-15 · 모델: Opus (blueprint §9 — 인증은 Opus 영역)
> 선행 규칙: harnes.md §5 (계획서 없는 개발 금지)
> **진행 현황 (2026-05-15)**: Phase 3.2a 구현·자동 테스트 완료(`tests/test_auth.py` 14/14). 브라우저 실동작 확인은 서버 기동 시. 3.2b는 포트원 PASS 가입 후.

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
