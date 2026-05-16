# 실행 계획서 4.2: 정산 엔진 (계산 알고리즘 + 운영 화면)

**상태**: 🏗️ 구현 완료 — 백엔드·HQ화면·지사화면, 로컬 검증 통과. AWS 배포 진행 중
**담당**: Sonnet 작성 → Opus 사후 리뷰 (blueprint §9.2 — 정산은 비가역 위험 영역)
**작업일**: 2026-05-16
**선행**: §4.1 (정산 DB 스키마 — 완료, 테이블 3종 존재)
**참조**: blueprint §7.2, plan_phase4.1 §8

---

## 1. 목표

정산 DB 스키마(§4.1)는 완성됐으나 **데이터를 채우는 로직이 없다.** 이번 단계는:

1. PAID 결제들을 **주차별 × 지사별로 모아** 정산서(`settlements` + `settlement_items`)를 생성하는 계산 엔진.
2. 본사(HQ)가 정산서를 검토·승인·지급 처리하는 운영 화면.
3. 지사가 자기 정산 명세서를 조회하는 화면.

**이번 단계에 포함하지 않는 것** (외부 계정 대기 — 사람 트랙):
- ① 실결제(PortOne) — 지금은 수리 완료 시 매니저 입력액으로 가짜 결제 기록. 정산은 이 기록을 그대로 집계한다.
- ③ 세금계산서(Popbill) 실발행 — `tax_invoices` 행 생성까지만, 국세청 전송은 §4.5.

## 2. 비즈니스 규칙 (확정 — blueprint §7.2 + plan_phase4.1 §2)

| 항목 | 규칙 |
| :--- | :--- |
| 정산 주기 | 주차별 (월~일 마감), 익주 화요일 지급 |
| 결제 금액 성격 | VAT 포함 (VAT-inclusive) |
| 공급가/세액 분리 | 공급가 = gross ÷ 1.1, 세액 = gross − 공급가 (원 단위 반올림 ROUND_HALF_UP) |
| 본사 수수료 | hq_commission = gross × 수수료율 |
| 수수료율 출처 | `Branch.commission_rate`. 0이면 등급 매핑(BRONZE 10%·SILVER 8%·GOLD 6%·DIAMOND 5%) |
| 지사 지급액 | branch_amount = gross − hq_commission |
| 환불 차감 | 마감 후 환불은 다음 주기 `REFUND_OFFSET` 라인으로 차감. **현재 환불 데이터 없음 → refund_offset = 0** (컬럼·로직 자리만 유지) |
| 최종 지급액 | net_amount = branch_amount − refund_offset |
| 음수 정산 | net_amount < 0 → status `HOLD` (본사 승인 대기), 그 외 `DRAFT` |
| 마감 후 수정 | 확정(APPROVED 이상)된 정산은 재계산·수정 금지. 환불은 다음 주기로만 반영 |

## 3. 계산 엔진 — `app/services/settlement.py` (신규)

핵심 함수 `generate_settlements(session, period_start, period_end, period_type)`:

```
1. 승인된 지사 전체 조회
2. 지사별로:
   a. 해당 지사 배정 + 기간 내 paid_at + status=PAID 결제 조회
   b. 활동 없으면(결제 0건, 환불 0) → 건너뜀 (빈 정산서 안 만듦)
   c. gross_amount   = Σ payment.amount
   d. supply_amount  = round(gross / 1.1)
      vat_amount     = gross − supply_amount
   e. rate           = commission_rate (없으면 등급 매핑)
      hq_commission  = round(gross × rate)
      branch_amount  = gross − hq_commission
   f. refund_offset  = 0 (현재), net_amount = branch_amount − refund_offset
   g. status         = "HOLD" if net_amount < 0 else "DRAFT"
   h. Settlement 1행 + 결제 1건당 SettlementItem 1행(item_type=SERVICE) 생성
   i. AuditLog 기록 (table=settlements, action=INSERT)
3. 멱등성: (branch_id, period_start, period_end)에 이미 정산서가 있으면 건너뜀
   (중복 생성 방지 — 같은 주를 두 번 눌러도 안전)
```

- 모든 금액 계산은 `Decimal`. float 금지 (CLAUDE.md).
- 반올림은 `Decimal.quantize(Decimal("1"), ROUND_HALF_UP)` — 원 단위. 반올림 규칙은 한 곳(상수)에서 관리해 추후 변경 가능.

## 4. 상태 전이 (state machine)

```
DRAFT ──→ REVIEW ──→ APPROVED ──→ PAID ──→ INVOICED
  │         │
  └─────────┴──→ HOLD ──→ REVIEW   (음수 정산 본사 처리 후 복귀)
```

- 허용 전이만 dict로 정의, 그 외 요청은 400 거부.
- APPROVED 진입 시 `approved_at`·`approved_by` 기록. PAID 시 `paid_at`. INVOICED 시 `invoiced_at`.
- 모든 전이는 AuditLog 기록.

## 5. API — `app/api/v1/endpoints/settlements.py` (신규, `/api/v1/settlements`)

| 메서드 | 경로 | 권한 | 설명 |
| :--- | :--- | :--- | :--- |
| POST | `/generate` | HQ_ADMIN | 기간 입력 → 해당 주 전 지사 정산서 일괄 생성 (멱등) |
| GET | `/` | HQ_ADMIN | 전체 정산서 목록 (branch_id·status·기간 필터) |
| GET | `/my` | BRANCH | 본인 지사 정산서 목록 (토큰 sub 기준) |
| GET | `/{id}` | HQ_ADMIN·BRANCH | 정산서 상세 + 라인 아이템. 지사는 본인 것만 |
| PATCH | `/{id}/status` | HQ_ADMIN | 상태 전이 (§4 state machine) |

- 스키마: `app/schemas/domain.py`에 `SettlementRead`, `SettlementItemRead`, `SettlementGenerate`, `SettlementStatusUpdate` 추가.
- `api.py`에 settlements 라우터 등록.

## 6. 프론트엔드

### 6.1 HQ — `www/admin.html` 정산 탭 (신규 또는 기존 정산 영역 확장)
- 상단: 주차 선택 + **[정산서 생성]** 버튼 → `POST /settlements/generate`
- 정산서 목록 테이블: 지사명 · 기간 · gross · 본사수수료 · 지급액 · 상태 배지
- 행 클릭 → 상세 모달: 라인 아이템 목록 + 상태 전이 버튼 (검토→승인→지급 처리)
- HOLD 건은 붉은 배지로 강조
- **harness_rules.md 준수**: 기존 결제 내역·필터 영역 건드리지 않고 정산 영역만 추가

### 6.2 지사 — `www/manager.html` 정산 명세서
- "정산" 탭(또는 내역 탭 내 섹션): `GET /settlements/my`
- 주차별 카드: 기간 · 매출 합계 · 본사 수수료 · **내 지급액(net)** · 상태
- 카드 클릭 → 명세서 상세 (어떤 수리 건들이 합산됐는지 라인 목록)

## 7. 작업 순서

1. `app/services/settlement.py` 계산 엔진 작성
2. `app/schemas/domain.py` 정산 스키마 4종 추가
3. `app/api/v1/endpoints/settlements.py` 작성 + `api.py` 등록
4. 로컬 검증 — 테스트 결제 데이터로 `POST /generate` → 정산서·라인 생성 확인, 금액 산식 수동 검산
5. `www/admin.html` 정산 탭
6. `www/manager.html` 정산 명세서
7. 로컬 브라우저 실동작 확인 (HQ 생성→승인, 지사 조회)
8. AWS 배포 + dev=AWS md5 동일성 검증
9. 커밋 + push

## 8. 완료 조건 (AC)

- [x] `POST /settlements/generate` → 활동 있는 지사마다 DRAFT 정산서 1건 + 결제당 라인 1건 생성
- [x] 같은 기간 재요청 시 중복 생성 안 됨 (멱등)
- [x] gross = Σ결제, 공급가+세액 = gross, branch_amount = gross−hq_commission 수동 검산 일치
- [x] 음수 net → status HOLD (코드 경로 검증)
- [x] 상태 전이: 허용 경로만 통과, 비허용 경로 400
- [x] 지사는 `/my`·`/{id}`에서 **본인 정산서만** 조회 (타 지사 차단)
- [x] HQ 화면 — 마크업·JS 구문 검증, 페이지 정상 서빙 (브라우저 실클릭은 사장님 확인 필요)
- [x] 지사 화면 — 마크업·JS 구문 검증, 페이지 정상 서빙 (브라우저 실클릭은 사장님 확인 필요)
- [x] 모든 정산서 생성·상태 전이가 AuditLog에 기록
- [ ] dev=AWS md5 동일

## 9. 위험·제약

| 위험 | 대응 |
| :--- | :--- |
| 잘못된 산식이 운영 정산서에 박히면 되돌리기 어려움 | DRAFT 상태에서만 재계산 허용, APPROVED 이상 잠금. 로컬 수동 검산을 AC에 포함 |
| 같은 주를 두 번 눌러 중복 정산서 | (branch, period) 멱등 키로 차단 |
| 반올림 오차 (공급가/세액, 수수료) | 반올림 규칙 상수 1곳 관리, 세액 = gross − 공급가로 합계 보존 |
| 가짜 결제(매니저 입력액) 기반 — 실결제 아님 | 정산 로직은 결제 출처를 모름. PortOne 연동 후에도 같은 코드 동작 |
| 환불 미구현 | refund_offset = 0 고정, 로직 자리만 유지. PortOne 환불 도입 시 §4.2 보강 |

## 10. 후속

- §4.5 Popbill 세금계산서 실발행 워커 (사람 트랙 — Popbill 계정 대기)
- 환불 → REFUND_OFFSET 실로직 (PortOne 환불 도입 후)
- 정산 주기 자동화 (스케줄러로 매주 화요일 자동 generate)
