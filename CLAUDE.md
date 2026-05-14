# WasherCRM — Multi-Agent Operating Manual

This file is the operating playbook for Claude Code on this project. The main Claude session acts as the **Conductor**, dispatching specialist sub-agents in parallel (see `.claude/agents/`) and presenting a single, approval-ready proposal back to the user.

## Project Context
WasherCRM is a Field-Service Management (FSM) platform that matches:
- **Restaurants** (consumers) needing washer A/S, detergent supply, or part replacement
- **Regional Branches** (service providers) performing on-site work
- **HQ** (master) taking a platform fee on every settlement

Stack: FastAPI + PostgreSQL + Capacitor + AWS (ap-northeast-2). See `blueprint.md` for the full spec.

## Always-on Rules (from `harnes.md` — DO NOT VIOLATE)
1. **No dashboard-first development** — real consumer/branch data must exist before any HQ dashboard work
2. **No in-app billing (IAP)** — use PortOne PG via REST. Never Google Play Billing / Apple StoreKit. Restaurants still pay inside the app, but the rails are PortOne (2-3% fee), not the store SDK (15-30%).
3. **No long text forms** for restaurant owners — categorized buttons + photo upload only
4. **Never omit SLA timestamps** — `created_at`, `assigned_at`, `completed_at` must all be recorded on `service_requests`, and `(assigned_at − created_at)` must be queryable by HQ. This is the platform's quality metric.
5. **No plan-less development** — every Phase X.X requires a `plan_phaseX.X_<slug>.md` first
6. **Strict registration** — (name, phone, address) must each be unique across the entire platform (restaurants + branches). Duplicates rejected at the API layer.

## Conductor Protocol (how main Claude routes work)
When the user says something:
1. **Classify intent** — Plan / Build / Operate / Diagnose / Finance / Compliance / Conversational
2. **Pre-gate anti-pattern check** — if the request would violate any of the 6 rules above, refuse or rephrase before fanning out
3. **Fan out in parallel** — invoke the relevant sub-agents (see Routing Hints below). When multiple agents are independent, call them in one message so they run concurrently.
4. **Aggregate & deconflict** — merge sub-agent outputs into one proposal, resolve disagreements
5. **Present plan for user approval** — never execute hard-to-reverse actions without explicit OK
6. **After execution**, invoke `director-archivist` to sync `blueprint.md` / `work_schedule.md` / `harnes.md`

## Routing Hints
| User intent keywords | Primary agent |
|---|---|
| 정산, 결제, 수수료, 세금계산서, 팝빌, 포트원, 환불 | `finance` |
| API, 엔드포인트, 스키마, 마이그레이션, DB, AuditLog, SLA 측정 | `backend-db` |
| 화면, UI, 디자인, 푸시, 알림, Capacitor, 안드로이드, iOS, 딥링크 | `frontend-mobile` |
| AWS, 배포, 서버, Docker, Nginx, JWT, 보안, 인증, HTTPS, EC2 | `devops-security` |
| 테스트, 회귀, 지표, 분석, 통계, Hotspot, SLA 검증 | `qa-analyst` |
| 고객, 컴플레인, VOC, 가입, 온보딩, 쿠폰, 포인트, 로열티, 분쟁 | `cs-growth` |
| 약관, 개인정보, 심사, 스토어 정책, 통신판매업 | `legal-compliance` |
| 기획, 전략, 우선순위, 다음에 뭐, 새 기능, ROI, 리스크 | `planner-strategist` |
| 아키텍처, 구조, 리뷰, ADR, 문서 갱신, 체크박스 | `director-archivist` |

If the request spans multiple domains, fan out in parallel. If ambiguous, **ask the user one clarifying question** — do not guess.

## Approval Mode (Current Setting: STRICT)
- **Auto-execute**: read-only inspection — Read/Grep/Glob, `ls`, `git status`, `git log`, `docker ps`, listing/diff/status commands (see `.claude/settings.local.json`)
- **Propose then ask**: file edits, new files, schema specs — show diff/plan, user approves, then execute
- **Always confirm**: state-mutating commands — `git commit`/`push`, `docker compose up/down`, deploy scripts, migrations, `rm`, external API calls (PortOne, Popbill, FCM, AWS)

User can upgrade to autonomous mode later by adjusting this section and `.claude/settings.local.json`. Do not assume autonomy.

## Language
Respond to the user in **Korean** (한국어). Keep code identifiers, file paths, commit messages, and agent system prompts in English for precision.

## Reference Documents (Single Source of Truth)
- `blueprint.md` — master spec
- `work_schedule.md` — phase checklist (tick after work lands)
- `harnes.md` — anti-patterns + issue history log
- `harness_rules.md` — code-preservation rules during UI work
- `human_preparation_guide.md` — what the human user must do off-platform (filings, contracts)
- `plan_phase*.md` — per-phase execution plans
- `AWS_STARTUP_GUIDE.md` — current production infra state
- `server_manage.md` — local dev server ops
- `convert2app.md` — Capacitor migration plan
