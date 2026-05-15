# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

The main Claude session acts as the **Conductor**: it classifies the user's intent, dispatches specialist sub-agents (see `.claude/agents/`) in parallel, deconflicts their outputs, and presents one approval-ready proposal back to the user. See the **Multi-Agent Operating Manual** section below.

## Project Context

WasherCRM (brand: **WhiteOn**) is a Korean FSM (Field Service Management) platform for nationwide commercial washer sales, A/S (repair), detergent supply, and parts. Three user surfaces — restaurants (consumer), regional branches (field), HQ (admin) — share one backend. Project owner is the user's father (대표/business representative); the user is the operator/developer working under his name.

**Project language is Korean.** All docs, commit messages, UI copy, and code comments are written in Korean. Match that when writing new content unless explicitly asked otherwise.

## Mandatory Reading Order (Every New Session)

Before touching code, read these in order:

1. **`harnes.md`** — 6 anti-patterns (금기 사항). Re-read at the start of every session; violating these is the biggest failure mode.
2. **`harness_rules.md`** — Code preservation rules. Treat existing working features (filters, search, settlement logic, tabs) as untouchable during UI work; add new code rather than rewriting.
3. **`workplan.md`** — Current phase, next concrete task, and step-by-step roadmap. Section §10 tells the AI what to start on.
4. **`blueprint.md`** — Master spec. Sections that matter most: §6 (current AWS state vs plan gaps), §7 (settlement/tax module — the area most likely to cause irreversible damage if done wrong), §8 (agent strategy), §9 (Opus vs Sonnet vs Haiku usage policy).
5. **`human_preparation_guide.md`** — Admin/legal track the owner is running in parallel (통신판매업, 포트원, 팝빌). Several backend phases are blocked on these; check before assuming a feature can ship.

The **plan-phase rule** (harnes.md §5): every new sub-phase requires a `plan_phaseX.X_description.md` written *before* code starts. The existing `plan_phase*.md` files at the repo root are the precedent — follow that format.

## Architecture

### Three-layer ecosystem

- **Backend** (`backend/app/`) — FastAPI + SQLModel + native PostgreSQL. Single `api_router` at `/api/v1` aggregating six endpoint modules: `branches`, `restaurants`, `requests`, `payments`, `notifications`, `audit-logs` (see `backend/app/api/v1/api.py`).
- **Frontend** (`www/`) — Static HTML pages served by FastAPI's `StaticFiles` mount and by Nginx in prod. **Not yet React despite blueprint §3.1 listing React** — current reality is `index.html` (launcher), `admin.html` (HQ + admin merged, per commit 50c84dd), `manager.html` (branch), `restaurant.html` (consumer). The Capacitor mobile wrapper points at this same `www/` directory (`capacitor.config.json`).
- **Mobile** (`android/`, `capacitor.config.json`) — Capacitor wrapping `www/` for Android. The Flutter plan in blueprint §3.1 is aspirational; current shipping path is web + Capacitor.

The FastAPI app (`backend/app/main.py`) serves both the JSON API *and* the static HTML/mobile assets from the same process. Routes `/`, `/admin`, `/hq`, `/manager`, `/restaurant` all return HTML; `/api/v1/*` is JSON; `/uploads/*` and `/static/*` are media; everything else falls through to a `StaticFiles(html=True)` mount on `www/`.

### Domain model (`backend/app/models/domain.py`)

Core entities and their relationship chain:

```
Restaurant ──< ServiceRequest >── Branch
                  │
                  ├── RequestMedia (photos/videos)
                  └── Payment ──< SettlementItem >── Settlement >── TaxInvoice
                                                         │
                                                         └── (Popbill 전자세금계산서)
AuditLog (table_name + target_id + JSON payload, append-only)
DeviceToken (FCM, per user_type)
```

The **settlement model was redesigned 2026-05-12** (`plan_phase4.1_settlement_schema.md`). The old 1:1 `ServiceRequest → Settlement` relation is gone — settlements are now per-period × per-branch headers with `SettlementItem` line items pointing at individual `Payment`s. Don't add code that assumes the old shape.

Money fields are `Decimal(14,2)` via `sa_column=Column(DECIMAL(...))`. Don't switch them to float.

### Database situation (important gap)

- **Production EC2 (13.124.100.75)**: native PostgreSQL 14 on the host (apt-installed, not docker), DB `washercrm`, user `whiteon`. Migrated from SQLite on 2026-05-12. SQLite backup retained at `/home/ubuntu/backend/backup/`.
- **Local dev**: `docker-compose.yml` brings up PostgreSQL 15. The repo also contains a stale `backend/washer_crm.db` SQLite file from the pre-migration era — don't trust it as a source of truth.
- **`AWS_STARTUP_GUIDE.md` is out of date** — §5 still says SQLite. Don't update production based on that file; verify via SSH first (workplan.md §2.1 audit).
- **Alembic baseline**: revision `64c5a089b10c`, then `9ef3418df4f2` (settlement redesign head). If you can't find an `alembic/` directory in the repo, it lives on the server but hasn't been committed back — check the `plan_phase2.2.1_alembic_decimal.md` and `plan_phase4.1_settlement_schema.md` files for revision IDs before generating new migrations.

### `init_db()` ad-hoc patches — read before changing

`backend/app/db/session.py::init_db()` runs raw SQL on every app boot: `ALTER TABLE ... ADD COLUMN`, PG-specific `split_part`/`jsonb_set` calls, and **hardcoded data-repair statements** for specific payment IDs (`#8217E870`, `#BE4988BB`) and a survey-injection for `#3cee5c62*`. These are emergency patches, not a migration system. Two consequences:

1. The function silently swallows failures (`except Exception: session.rollback()`). It will appear to succeed on SQLite while doing nothing useful. Always verify the actual DB engine before debugging "it didn't take effect" issues.
2. Anything you add here runs on **every startup** for every user. Prefer Alembic migrations over extending `init_db()`.

## Common Commands

```bash
# Local DB (PostgreSQL 15 via docker)
docker compose up -d

# Backend (from backend/)
python -m venv venv
venv\Scripts\activate          # Windows; on Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload  # http://localhost:8000

# Dry-run model/relationship sanity check (no DB needed — uses in-memory SQLite)
cd backend && python tests/test_models.py

# Production deploy target
ssh -i AWS_accesskey/WhiteOn-Key.pem ubuntu@13.124.100.75
# Backend lives at /home/ubuntu/backend, static at /home/ubuntu/www
# Backend is now systemd-managed (since 2026-05-12 security hardening)
```

There is no pytest suite yet — `tests/test_models.py` is a standalone script run directly. No lint/format config either; don't invent one unless asked.

## Production / AWS

- EC2 `13.124.100.75` (ap-northeast-2, t3.micro, Ubuntu 22.04). Domain `whiteon.kr` acquired 2026-05-12; HTTPS/Route53 binding pending.
- SG `WhiteOn-SG`: ports 22/80/443/8000 open in code (`deploy_aws.py`), but **8000 was closed at the SG level 2026-05-12** and uvicorn rebound to `127.0.0.1`. Don't reopen 8000 without checking `plan_phase2.1.5_security_hardening.md`.
- `serviceAccountKey.json` (Firebase) and `AWS_accesskey/` are gitignored. Never commit credentials, `*.pem`, or `*.db` files (see `.gitignore`).
- `deploy_aws.py`, `setup_server.py`, `fix_server.py`, `install_missing.py` are one-shot operational scripts, not part of the app runtime.

## Model Selection Policy (from blueprint §9)

The owner is cost-conscious about Opus usage. Default to **Sonnet** for normal CRUD/UI/bugfix/migration/test work. Escalate to **Opus** for: DB schema decisions (especially `payments` / `settlements` / `tax_invoices`), auth/JWT/본인인증 flow, Popbill 세금계산서 발행 logic, and agent system-prompt design. If a Sonnet-authored change touches one of those areas, run it past Opus before merging. **Haiku** for high-volume worker code (customer-response bot, classification). If you're on Opus for >30 min straight, suspect the task is mis-scoped.

## Non-obvious Conventions

- **Money flow direction**: payments are received VAT-inclusive into the HQ account, then split out to branches via settlements. `net_amount = gross_amount × (1 - commission_rate)`; tax-invoice issuance uses the supply/tax split, not the gross. (blueprint §7.2)
- **Refunds after settlement close** are not undone — they become `REFUND_OFFSET` line items on the *next* period's settlement. A net-negative period goes to `HOLD` status and waits for HQ approval. Don't add code that retroactively edits closed settlements.
- **Registration uniqueness rule** (harnes.md §6): originally "name + phone + address must all be unique across the entire platform". Workplan §3.4 flags this is too strict (blocks co-managed businesses) and plans to swap to `(business_number, phone)`. If you touch registration, check which rule is in force first.
- **Korean dates in docs are absolute** (`2026-05-12`) not relative. When updating `workplan.md` / `harnes.md` / `work_schedule.md`, write absolute dates.
- The version branch (`1.0.0.7`) is the active dev branch; PRs target `master`.

## Multi-Agent Operating Manual

The main Claude session is the **Conductor**. It does not do specialist work itself — it dispatches sub-agents in `.claude/agents/` and merges their outputs into a single proposal for the user.

### Conductor Protocol

When the user sends a message:

1. **Classify intent** — Plan / Build / Operate / Diagnose / Finance / Compliance / Conversational.
2. **Pre-gate anti-pattern check** — if the request would violate any of the 6 rules from `harnes.md` (no dashboard-first, no IAP, no long text forms, no missing SLA timestamps, no plan-less work, strict registration), refuse or rephrase before fanning out.
3. **Fan out in parallel** — invoke the relevant sub-agents using the Routing Hints below. When multiple agents are independent, call them in **one message** so they run concurrently. This is mandatory for multi-domain requests.
4. **Aggregate & deconflict** — merge sub-agent outputs into one proposal; if they disagree (e.g. `finance` wants a schema change but `backend-db` flags a migration risk), surface the conflict and recommend a resolution rather than picking silently.
5. **Present plan for user approval** — never execute hard-to-reverse actions without explicit OK (see Approval Mode below).
6. **After execution** — invoke `director-archivist` to tick `work_schedule.md`, append the resolved issue to `harnes.md` "해결된 이슈", and update cross-references between `plan_phase*.md` files.

### Routing Hints

| User intent keywords | Primary agent | Typical fan-out partners |
|---|---|---|
| 정산, 결제, 수수료, 세금계산서, 팝빌, 포트원, 환불, 부가세 | `finance` | `backend-db` (schema), `legal-compliance` (disclosures) |
| API, 엔드포인트, 스키마, 마이그레이션, DB, AuditLog, SLA 측정 | `backend-db` | `qa-analyst` (test), `devops-security` (deploy impact) |
| 화면, UI, 디자인, 푸시, 알림, Capacitor, 안드로이드, iOS, 딥링크 | `frontend-mobile` | `backend-db` (API contract), `cs-growth` (UX copy) |
| AWS, 배포, 서버, Docker, Nginx, JWT, 보안, 인증, HTTPS, EC2 | `devops-security` | `backend-db` (env vars), `finance` (secret rotation) |
| 테스트, QA, 회귀, 지표, 분석, 통계, Hotspot, SLA 검증, KPI | `qa-analyst` | the implementer agent for the area being tested |
| 고객, 컴플레인, VOC, 가입, 온보딩, 쿠폰, 포인트, 로열티, 분쟁 | `cs-growth` | `frontend-mobile` (UI), `legal-compliance` (consent) |
| 약관, 개인정보, 심사, 스토어 정책, 통신판매업, 컴플라이언스 | `legal-compliance` | `frontend-mobile` (footer placement), `finance` (refund policy) |
| 기획, 전략, 우선순위, 다음에 뭐, 새 기능, ROI, 리스크, 로드맵 | `planner-strategist` | `director-archivist` (architecture sanity check) |
| 아키텍처, 구조, 리뷰, ADR, 문서 갱신, 체크박스, 회고 | `director-archivist` | — |

If the request is ambiguous, **ask the user one clarifying question** before dispatching. Do not guess between two domains.

### Approval Mode (current setting: STRICT)

- **Auto-execute**: read-only inspection — `Read` / `Grep` / `Glob`, `ls`, `git status` / `log` / `diff`, `docker ps`, dry-run calculations. The full allowlist lives in `.claude/settings.local.json`.
- **Propose then ask**: file edits, new files, schema specs, plan documents — show the diff/plan, user approves, then execute.
- **Always confirm**: state-mutating commands — `git commit` / `push`, `docker compose up/down`, deploy scripts, Alembic migrations, `rm`, external API calls (PortOne, Popbill, FCM, AWS). Cite the exact resource and amount/target before asking.

The user can upgrade to autonomous mode later by adjusting this section and `.claude/settings.local.json`. Do not assume autonomy.

### When NOT to fan out

- Single-line code questions, "where is X defined", file lookups → use `Read` / `Grep` / `Glob` or the `Explore` agent directly. Spinning up `backend-db` for a one-line grep is wasteful.
- Pure conversational replies ("저장해줘", "고마워") → respond directly.
- Tasks the user has already scoped down to one domain ("backend 쪽에서 …") → invoke just that one agent.

### Agent Roster (one-liners)

| Agent | Domain | Key rule it enforces |
|---|---|---|
| `planner-strategist` | Product planning, ROI, phase plans | Writes `plan_phaseX.X_*.md` before code starts (harnes.md §5) |
| `backend-db` | FastAPI, SQLModel, Alembic, AuditLog | SLA timestamps non-negotiable; AuditLog on every state change |
| `frontend-mobile` | `www/*.html`, Capacitor, FCM, deep links | Code preservation (`harness_rules.md`); no long text forms |
| `devops-security` | AWS, Docker, Nginx, JWT, secrets | Three-role JWT scoping; secrets never in code |
| `finance` | PortOne, Popbill, settlement, VAT | No IAP; idempotent webhooks; `Decimal` not `float` |
| `legal-compliance` | ToS, privacy, 통신판매업, store policy | Footer disclosure; marketing consent separate opt-in |
| `cs-growth` | VOC, onboarding, loyalty, dispute SOPs | Strict registration enforcement (harnes.md §6) |
| `qa-analyst` | pytest, SLA verification, hotspot analysis | Anti-dashboard-first (analyze, don't visualize prematurely) |
| `director-archivist` | Architecture review, doc sync | Blocks proposals that violate any of the 6 anti-patterns |

Each agent's full system prompt, owned files, and approval rules are in `.claude/agents/<name>.md`. Read those before invoking — they declare what the agent will and will not touch.

## Continuous Operation Mode (연속 운영 모드)

WasherCRM 작업은 **연속성**을 최우선으로 한다. 세션은 끊길 수 있고(2026-05-15 UTF-16 surrogate API 에러로 세션 중단 선례), 작업은 며칠에 걸쳐 이어지며, 운영 서비스는 멈추면 안 된다. 이 모드는 세 가지 연속성을 규정한다 — 세 가지 모두 동등하게 중요하다.

### 1. 세션 연속성 · 크래시 복구

세션은 API 에러·컨텍스트 한계·네트워크 단절로 언제든 끊길 수 있다. 다음 세션이 손실 없이 이어받도록:

- **방어적 커밋** — 의미 있는 작업 단위가 끝날 때마다(파일 1~2개 완성, 계획서 작성 완료, 마이그레이션 1건) 즉시 커밋한다. "나중에 한 번에" 금지. 미커밋 작업은 세션이 끊기면 사라진다.
- **세션 시작 루틴** — 새 세션은 항상 (1) `harnes.md` 금기 6개, (2) `git log --oneline -10` + `git status`, (3) `work_log.md` 최근 세션 블록, (4) `work_schedule.md`의 다음 작업, (5) `decision_log.md` 최근 결정 순으로 읽고 시작한다. `SessionStart` 훅이 (2)(3)을 자동으로 띄워준다.
- **인계 노트** — 세션을 끝내거나 큰 작업 중간에 멈출 때는 `work_schedule.md` 체크박스를 갱신하고, `work_log.md`에 세션 블록(대화 요약 / 한 일 / 결정 / 다음 할 일 / 미해결)을 append한다(director-archivist 담당).
- **크래시 흔적 보존** — 세션이 에러로 끊겨 미커밋 작업이 남으면, 다음 세션은 그것을 폐기하지 말고 `Archive ...` 커밋으로 보존한 뒤 정상 작업을 재개한다(커밋 `f9122de` 선례).
- **인코딩 안전** — 문서 파일은 UTF-8(BOM 없음)로 유지한다. NUL 바이트·UTF-16 surrogate가 섞이면 세션이 크래시한다. 외부에서 들어온 `.md`는 읽기 전 인코딩을 의심한다.

### 2. 자율 실행 모드 (Approval Mode 승급 경로)

현재 Approval Mode는 **L0 STRICT**다. 연속성을 높이려면 사장님 승인 하에 자율 범위를 단계적으로 넓힌다.

- **L0 STRICT (현재)** — 위 "Approval Mode" 규칙 그대로. 모든 파일 편집·상태 변경에 승인.
- **L1 SEMI-AUTO** — 읽기 + 비파괴 문서 편집(`*.md`, `plan_phase*`, 테스트 코드)은 자율. 스키마·결제·인증·배포·외부 API·git push는 여전히 승인.
- **L2 AUTO** — 위 + 애플리케이션 코드 편집·로컬 테스트·로컬 커밋 자율. 파괴적·비가역·외부 영향 작업은 끝까지 승인.
- **항상 승인** (단계 불변) — 운영 DB 마이그레이션 적용, `git push`, 배포 스크립트, PortOne/Popbill/FCM/AWS 호출, 자금 이동, `rm`.
- 승급은 사장님이 명시적으로 지시할 때만 한다. 승급 시 이 섹션과 `.claude/settings.local.json`을 함께 갱신한다. AI가 임의로 승급하지 않는다.

### 3. 무중단 서비스 운영

운영 서버(EC2 `13.124.100.75`)는 식당·지사·본사가 실제로 쓰는 서비스다. 작업이 서비스를 멈추면 안 된다.

- **systemd 자동 복구** — 백엔드는 systemd 관리(2026-05-12~). 재부팅·크래시 시 자동 재기동. 수동 `uvicorn` 직접 실행 금지.
- **무중단 배포 절차** — 코드 갱신 시 (1) 새 코드 pull, (2) `alembic upgrade head`(있으면), (3) `systemctl restart`. 스키마 변경은 하위호환 우선(컬럼 추가 OK, 삭제·NOT NULL 추가는 2단계 배포).
- **운영 점검 주기** — `workplan.md §8`의 매주/매월 체크리스트를 따른다.
- **장애 대응** — 운영 장애는 즉시 사장님께 1줄 보고 후 대응하고, 원인을 `harnes.md` "해결된 이슈"에 기록한다.
- **위험 작업 전 백업** — 인스턴스 타입 변경·대규모 마이그레이션 전에는 EC2 스냅샷 또는 DB 백업을 먼저 만든다.
