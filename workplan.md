# 🗂️ WasherCRM 작업 실행 계획서 (Workplan)

> **이 문서의 목적**: Sonnet(또는 다른 세션의 AI)이 이 문서를 보고 즉시 다음 작업을 이어갈 수 있도록, 모든 작업을 (1) **착수 전 확인사항**, (2) **단계별 작업 항목**, (3) **완료 조건(AC)**, (4) **참조 문서**의 4단 구조로 정리한다.
>
> **선행 문서**:
> - [blueprint.md](./blueprint.md) — 전체 청사진 (특히 §6 운영 상태, §7 정산 모듈, §8 에이전트, §9 모델 정책)
> - [harnes.md](./harnes.md) — **금기 사항 6개 — 모든 작업 전 필독**
> - [human_preparation_guide.md](./human_preparation_guide.md) — 사람 트랙 행정 작업 (진행 중)
> - [work_schedule.md](./work_schedule.md) — 단순 체크리스트(이 문서가 상위)
> - [AWS_STARTUP_GUIDE.md](./AWS_STARTUP_GUIDE.md) — 서버 운영
>
> **현재 마지막 업데이트**: 2026-05-11

---

## 0. 작업 착수 전 공통 체크리스트 (매번 확인)

새 세션을 시작할 때마다 AI는 다음을 순서대로 수행한다.

1. **harnes.md 금기 사항 6개 재확인** — 특히 "계획서 없는 개발 금지". 새로운 세부 단계 진입 시 `plan_phaseX.X_description.md`부터 작성.
2. **이 workplan.md의 현재 진행 상태 섹션(§1) 확인** — 어디까지 완료됐는지.
3. **EC2 실제 상태 1회 점검**: `ssh -i AWS_accesskey/WhiteOn-Key.pem ubuntu@13.124.100.75` 접속 후 백엔드/DB/Nginx 프로세스 살아있는지 확인.
4. **변경 작업 시작 전 `git status` 확인** — 미커밋 변경 사항 있으면 먼저 사장님께 확인.
5. **모델 정책(blueprint §9) 확인** — 지금 하는 작업이 Sonnet 일감인지 Opus 일감인지.

---

## 1. 현재 진행 상태 (Status Snapshot)

### 1.1 완료 (Done)
- [x] Phase 0: PostgreSQL 마이그레이션 (로컬), Docker DB 환경, HQ 대시보드 포맷팅, 용량 정리
- [x] Phase 1.1: DB 스키마 설계 — `plan_phase1.1_schema.md`
- [x] Phase 1.2.1: AuditLog / 로그 시스템 (※ Alembic은 계획만 있고 미적용 — §2.2에서 함께 처리)
- [x] Phase 1.2.2: 코어 API
- [x] Phase 1.2.3: 지사·식당 관리 API + Admin UI 검색 기능
- [x] AWS EC2 초기 배포 (2026-05-10) — `13.124.100.75`
- [x] **§2.1 EC2 상태 점검 (2026-05-12)** — `scratch/aws_audit_20260512.md`
- [x] **§2.1.5 보안 강화 (2026-05-12)** — `plan_phase2.1.5_security_hardening.md`
  - uvicorn 127.0.0.1 바인딩, AWS SG에서 8000 차단
  - systemd 서비스 등록 (재부팅 자동 복구)
  - serviceAccountKey 권한 600, trading_bot.zip + venv_win 정리
- [x] **§2.2 DB를 PostgreSQL로 통일 (2026-05-12)** — `plan_phase2.2_db_postgres.md`
  - 네이티브 PostgreSQL 14 설치, DB `washercrm` + 사용자 `whiteon` 생성
  - 백업 SQLite에서 실데이터 19건 전부 PostgreSQL로 이관
  - 백엔드 재기동 후 API 200 OK 확인
  - SQLite 백업: `/home/ubuntu/backend/backup/washer_crm_20260512_134047.db`
  - .env 백업: `/home/ubuntu/backend/.env.sqlite.bak`
  - **남은 항목 (별도 처리)**: Alembic 셋업, `Payment.amount` 등 Decimal 타입 보정
- [x] **§2.2.1 Alembic 베이스라인 + Decimal 타입 보정 (2026-05-12)** — `plan_phase2.2.1_alembic_decimal.md`
  - Alembic 정식 도입, 베이스라인 리비전 `64c5a089b10c` 고정
  - `Payment.amount` + `Settlement.*` 3개 필드 Decimal 적용
  - Pydantic 경고 제거 확인
- [x] **§4.1 정산 DB 스키마 재설계 (2026-05-12)** — `plan_phase4.1_settlement_schema.md`
  - 1:1 Settlement(ServiceRequest 의존) → 주기별×지사별 집계 + SettlementItem + TaxInvoice 구조
  - 정산 주기 변경 가능성 대응(period_start/end 기반, Branch.settlement_cycle 컬럼 사전 추가)
  - 환불·수정세금계산서·음수정산 대응 가능한 status 흐름
  - Alembic 리비전: `9ef3418df4f2` (head)
  - 기존 3건 테스트 데이터 CSV 백업 (`backup/settlements_legacy_20260512_140626.csv`)
  - 도메인: **whiteon.kr** 확보 (2026-05-12)

### 1.2 진행 중 (In Progress)
- [ ] **사람 트랙**: 통신판매업 신고, 도메인 구매, 포트원·팝빌 가입, 전자세금계산서 인증서 발급 (human_preparation_guide.md 참조)
- [ ] AWS 인프라 정상화 (DB·HTTPS·인스턴스 사이즈) — **§2가 다음 작업**

### 1.3 격차 / 미해결 이슈
- ⚠️ AWS_STARTUP_GUIDE.md상 DB가 SQLite로 명시되어 있음 → 실제 어떤 상태인지 §2.1에서 확인 후 PostgreSQL로 통일 필요.
- ⚠️ HTTPS 미적용 → 포트원 결제 심사 통과 불가.
- ⚠️ harnes.md §6 (이름/번호/주소 중복 금지) 규칙은 부부 공동운영 케이스를 막을 수 있음. §6에서 재검토.

---

## 2. Phase A: AWS 인프라 정상화 (최우선, 1~2주)

> **착수 전제**: 사람 트랙(도메인 구매)이 진행 중이어야 함. 도메인 미확보 시에도 2.1, 2.3은 진행 가능.

### 2.1 [AI / Sonnet] EC2 실제 상태 점검
- SSH로 접속하여 다음을 확인하고 결과를 `scratch/aws_audit_YYYYMMDD.md`에 기록.
  - `ps aux | grep uvicorn` — 백엔드 프로세스 살아있는지
  - `ls -la /home/ubuntu/backend/` — DB 파일 종류 (`washer_crm.db` SQLite인지, 또는 RDS 연결인지)
  - `cat /home/ubuntu/backend/.env` (있다면) — DB URL 확인
  - `docker ps` — 컨테이너 사용 여부
  - `df -h`, `free -m` — 디스크/메모리 상태
- **AC**: `scratch/aws_audit_*.md` 작성 완료 + 사장님께 1줄 요약 보고.

### 2.2 [AI / Sonnet+Opus 리뷰] DB를 PostgreSQL로 통일
- 사전 작업: `plan_phase2.2_db_postgres.md` 작성.
- **결정 (2026-05-12)**: t3.micro의 914MB RAM 제약을 고려해 **EC2 내 네이티브 PostgreSQL(apt 설치)** 선택. Docker 오버헤드 회피. RDS는 결제 트래픽 시점에 재검토.
- Alembic 셋업 포함 (기존 plan에서 완료로 잘못 기록됨).
- 데이터: 현재 SQLite는 172KB 테스트 데이터 → 백업만 보존하고 PostgreSQL은 fresh 시작.
- **AC**: 백엔드가 PostgreSQL 바라보며 정상 동작 + systemd 서비스 정상 + Alembic `upgrade head` 성공 + 기존 SQLite 파일 백업 보관.

### 2.3 [AI / Sonnet] HTTPS·도메인·푸터 적용
- Route 53에 도메인 등록(사람 트랙 완료 후).
- ACM에서 SSL 인증서 발급 또는 Nginx + certbot.
- Nginx 설정: 80→443 강제 리다이렉트, Backend는 8000 → 외부 차단, ALB/Nginx만 외부 노출.
- 프론트 푸터에 다음 노출: 상호(WhiteOn), 대표자(사장님 성함), 사업자등록번호, 통신판매업 신고번호, 주소, 대표 전화, 이용약관/개인정보처리방침 링크.
- **AC**: `https://whiteon.kr` 접속 시 정상 페이지 + 푸터 필수정보 노출 + 80→443 리다이렉트.

### 2.4 [AI / Sonnet] EC2 인스턴스 업그레이드
- 현재 t3.micro → t3.small (최소) 또는 t3.medium (권장)로 변경.
- 스냅샷 백업 → 인스턴스 중지 → 타입 변경 → 재시작 → 헬스체크.
- **AC**: 새 사이즈에서 백엔드/Nginx 정상 동작 + 응답시간 측정 기록.

---

## 3. Phase B: 통합 인증·본인확인 (PASS) — 2~3주

> **선행 조건**: 사람 트랙 — 포트원 가입 및 본인인증 부가서비스 심사 통과 필요.
> **참조**: blueprint §2.2(Auth), §7.3(외부 연동 흐름)

### 3.1 [AI / Sonnet] 통합 로그인 페이지
- `/login.html` UI — 식당/지사/본사 3가지 역할 분기.
- **AC**: 디자인 통일 + 반응형(모바일 우선).

### 3.2 [AI / Opus 권장] JWT 인증 시스템
- 사전 작업: `plan_phase3.2_auth.md` 작성.
- 역할: `ROLE_RESTAURANT`, `ROLE_BRANCH`, `ROLE_HQ_ADMIN`.
- 토큰: access(15분) + refresh(14일), refresh rotate.
- 미들웨어로 권한 데코레이터 구현 (`@require_role("BRANCH")`).
- **AC**: 3가지 역할 모두 로그인 + 권한별 API 차단 확인 + 단위 테스트.

### 3.3 [AI / Sonnet] 포트원 본인확인(PASS) 연동
- 가입 플로우에 PASS 본인인증 삽입.
- 휴대폰/생년월일이 입력값과 일치하는지 검증.
- `users.is_verified` 플래그 처리.
- harnes.md §6 재검토 결과 반영(아래 3.4 참조).
- **AC**: 테스트 계정으로 본인확인 성공 → 회원가입 완료 → DB에 인증정보 저장.

### 3.4 [AI / Sonnet] 가입 검증 규칙 재설계
- 기존 "이름·번호·주소 중복 금지"를 "사업자번호 + 휴대폰 조합 유니크"로 변경 제안.
- harnes.md §6 업데이트 + 본사 승인.
- **AC**: 부부 공동운영 케이스에서 정상 가입 가능.

---

## 4. Phase C: 정산 시스템 (회계·세금계산서 포함) — 3~4주

> **이 모듈은 잘못 짜면 회계상 후유증이 큼. blueprint §7 필독.**
> **선행 조건**: Phase A 완료(PostgreSQL 정착). 사람 트랙 — 팝빌 가입 및 인증서 등록.

### 4.1 [AI / Opus 필수] 정산 DB 스키마
- 사전 작업: `plan_phase4.1_settlement_schema.md` 작성.
- 테이블: `settlements`, `settlement_items`, `tax_invoices` (blueprint §7.1 참조).
- Alembic 마이그레이션 작성.
- **AC**: 마이그레이션 정상 적용 + 모델 단위 테스트 통과.

### 4.2 [AI / Opus 필수] 정산 계산 알고리즘
- 사전 작업: `plan_phase4.2_settlement_logic.md` 작성.
- 케이스 매트릭스 작성 후 구현:
  - 정상 정산(수수료 + VAT 분리)
  - 부분환불 → 다음 주기 차감
  - 전액환불 → 다음 주기 차감 또는 회수
  - 음수 정산 → `HOLD` + 본사 승인
- **AC**: 케이스별 단위 테스트 모두 통과 + 사장님 1회 데모.

### 4.3 [AI / Sonnet] HQ 정산 관리 대시보드
- 화면: 미정산/검토중/승인/지급완료/세금계산서발행 5단계 칸반.
- 액션: 검토 → 승인 → 지급실행 → 세금계산서 발행.
- **AC**: 클릭 한 번에 상태 전이 + AuditLog 자동 기록.

### 4.4 [AI / Sonnet] 지사용 정산 명세서 페이지
- 주차별 정산 내역, 수수료 차감 내역, 지급 예정일 표시.
- PDF 다운로드 버튼.
- **AC**: 지사 로그인 후 본인 지사 명세서만 조회 가능.

### 4.5 [AI / Opus 권장] 팝빌 세금계산서 발행 연동
- 사전 작업: `plan_phase4.5_popbill.md` 작성.
- 정산 `APPROVED` → 비동기 워커(Celery 또는 FastAPI BackgroundTask) → Popbill API.
- 수정세금계산서 흐름(환불 발생 시) 별도 구현.
- 실패 3회 재시도 → 본사 알림.
- **AC**: 테스트 계정으로 세금계산서 발행 성공 + 수정세금계산서 발행 성공.

### 4.6 [AI / Sonnet] 월말 회계 리포트
- CSV/Excel 자동 생성: 매출, 수수료, VAT, 지사별 정산 집계.
- 사장님 이메일로 매월 1일 자동 발송(스케줄러).
- **AC**: 샘플 1개월 리포트가 정상 생성 + 사장님이 외부 회계SW에 import 가능한 형식.

---

## 5. Phase D: 실거래 결제 — 2주

> **선행 조건**: 포트원 실거래 심사 통과(사람 트랙), Phase A·B 완료.

### 5.1 [AI / Sonnet] PG 결제 모듈 연동
- 식당 앱 결제 화면 → 포트원 SDK → 결제 → webhook 검증.
- 결제 성공 시 `payments` insert + `service_requests.status = COMPLETED` 전제 검사.
- **AC**: 신용카드·카카오페이·계좌이체 각 1건 이상 실거래 성공.

### 5.2 [AI / Sonnet] 결제 webhook 검증
- 클라이언트가 보낸 amount와 webhook의 amount 일치 검증(변조 방지).
- 위변조 의심 시 자동 환불 + 본사 알림.
- **AC**: 위변조 시뮬레이션 테스트 통과.

### 5.3 [AI / Sonnet] 환불·부분환불 API
- HQ 대시보드에서 환불 처리 가능.
- 환불 발생 시 4.2의 음수 정산 로직 자동 연계.
- **AC**: 환불 1건 처리 → 다음 정산 주기에 차감 확인.

---

## 6. Phase E: 에이전트 도입 (단계적) — 우선 (1)번부터

> **참조**: blueprint §8. **(1)번 정산 검토 에이전트 외에는 운영 안정화 후 진행.**

### 6.1 [AI / Opus 필수] 정산 검토 에이전트
- 사전 작업: `plan_phase6.1_settlement_agent.md` 작성.
- 도구: `read_settlement(period)`, `read_payments(period)`, `detect_anomaly(data)`, `send_summary(to, text)`.
- DB 쓰기 권한 없음. 초안만 생성.
- 매주 정산 마감일 오전 9시 자동 실행 → 본사에 요약 발송.
- **AC**: 모의 정산 데이터로 이상치 1건 이상 검출 + 정상 요약 전송.

### 6.2~6.5: 운영 6개월 후 재검토
- A/S 분류, Hotspot 분석, 세금계산서 검증, 고객 응대 봇 — 각각 별도 plan_phase로 작성 후 진행.

---

## 7. Phase F: 모바일 앱 (Flutter/Capacitor) — 별도 트랙

> 현재 `android/`, `frontend/`, `capacitor.config.json` 존재. 웹앱 안정화 후 진행.
> blueprint §5 (Phase 5) 참조.

- [ ] Capacitor 빌드 파이프라인 정비
- [ ] FCM 푸시 연동
- [ ] 카메라/GPS 네이티브 권한
- [ ] 구글 플레이 콘솔 — 20인 테스터 14일 정책 대응
- [ ] 앱스토어 심사

---

## 8. 정기 운영 체크리스트 (매주 / 매월)

### 매주 (월요일)
- [ ] EC2 디스크/메모리 사용량 확인
- [ ] 백엔드 로그 에러 점검 (`/home/ubuntu/backend/uvicorn.log`)
- [ ] 정산 검토 에이전트 결과 확인
- [ ] git push (코드/문서)

### 매월 (1일)
- [ ] 월말 회계 리포트 정상 발송 확인
- [ ] 사용자 가입 통계 확인 (식당/지사 수)
- [ ] AWS 비용 확인
- [ ] harnes.md 신규 이슈 정리

---

## 9. 의사결정 로그 (Decision Log)

> 의사결정 로그는 별도 문서로 분리되었다 → **[decision_log.md](./decision_log.md)**
> 새 결정은 그 문서에 추가한다(추가 전용). `director-archivist` 에이전트가 관리한다.

---

## 10. 다음 작업 (Sonnet이 이 문서를 처음 봤을 때 무엇부터 할지)

> **다음 세션에 들어온 AI는 이 순서를 따른다.**

1. `harnes.md`의 금기 사항 6개를 다시 읽는다.
2. `git log --oneline -20`으로 최근 변경 사항을 본다.
3. **§2.1 (EC2 실제 상태 점검)** 부터 시작한다. SSH로 접속해서 DB가 SQLite인지 PostgreSQL인지 먼저 확인하고 `scratch/aws_audit_YYYYMMDD.md`에 기록한 뒤 사장님께 1줄 보고.
4. 그 결과에 따라 §2.2 또는 §2.3으로 분기한다.

새 단계 진입 전에는 반드시 `plan_phaseX.X_description.md`를 먼저 작성한다. (harnes.md §5)
