# 실행 계획서 4.1: 정산 DB 스키마 재설계

**상태**: 🏗️ 진행 중
**담당**: Sonnet (Opus 사후 리뷰 권장 — blueprint §9.2)
**작업일**: 2026-05-12
**선행**: §2.2.1 (Alembic 베이스라인 + Decimal)
**참조**: blueprint §7.1, §7.2

---

## 1. 목표
- 현재 1:1 (Settlement ↔ ServiceRequest) 구조를 **주차/월/격주 무관 × 지사별 기간 집계** 구조로 전환.
- 환불·수정세금계산서·음수 정산까지 처음부터 수용하는 모델.
- **정산 주기는 향후 변경 가능**하도록 설계 (DB 변경 없이 정책 코드만 수정).

## 2. 비즈니스 결정 (사용자 합의)
| 항목 | 결정 |
| :--- | :--- |
| 기본 정산 주기 | 주차별 (월~일 마감, 익주 화요일 지급) |
| 향후 변경 가능성 | **있음** — 월별/격주별로 변경될 수 있음 |
| 변경 대응 방식 | DB 스키마는 주기를 모름. period_start/period_end만 저장. 정책 코드/설정 한 줄 변경으로 신규 정산 주기 바꿈. 과거 정산은 자기 기간 그대로 보존. |
| 지사별 다른 주기 가능성 | **장기 가능성 있음** — `Branch.settlement_cycle` 컬럼 사전 추가, 현재는 모두 `WEEKLY` 기본값 |
| 부가세 처리 | 결제 금액 = VAT 포함(VAT-inclusive). 정산 시 공급가/세액 분리. (blueprint §7.2) |
| 환불 처리 | 정산 확정 후 환불은 다음 주기에 `REFUND_OFFSET` 라인으로 차감. 누적 음수 시 `HOLD` 상태로 본사 승인 대기. |

## 3. 새 스키마 (요약)

### 3.1 `settlements` — 기간별 × 지사별 정산 헤더
```
id (UUID, PK)
branch_id (UUID, FK→branches, index)
period_start (DATE, index)        # 포함
period_end (DATE, index)          # 포함
period_type (str, index)          # WEEKLY|BIWEEKLY|MONTHLY|CUSTOM

gross_amount (DECIMAL 14,2)       # VAT 포함 결제 총액
vat_amount (DECIMAL 14,2)         # 부가세 (gross / 11, 반올림 규칙은 §4.2에서)
commission_rate (DECIMAL 5,2)     # 적용된 수수료율 % 스냅샷
hq_commission (DECIMAL 14,2)      # 본사 수수료액
branch_amount (DECIMAL 14,2)      # 지사 정산액 (gross - hq_commission)
refund_offset (DECIMAL 14,2)      # 환불 차감 (이전 기간에서 발생)
net_amount (DECIMAL 14,2)         # 실제 지급액 (branch_amount - refund_offset)

status (str, index)               # DRAFT|REVIEW|APPROVED|PAID|INVOICED|HOLD
created_at, approved_at, paid_at, invoiced_at (TIMESTAMP)
approved_by (str)
notes (TEXT)
```

### 3.2 `settlement_items` — 라인 아이템 (1:N)
```
id (UUID, PK)
settlement_id (UUID, FK→settlements, index)
payment_id (UUID, FK→payments, nullable, index)  # REFUND_OFFSET은 nullable
item_type (str, index)            # SERVICE|PARTS|DETERGENT|REFUND_OFFSET
amount (DECIMAL 14,2)             # 음수 허용 (환불)
description (TEXT)
created_at (TIMESTAMP)
```

### 3.3 `tax_invoices` — 세금계산서 발행 이력
```
id (UUID, PK)
settlement_id (UUID, FK→settlements, index)
popbill_mgt_key (str, unique, index)   # 우리가 발급한 관리번호
popbill_ntsconfirm_num (str, nullable) # 국세청 승인번호
invoice_type (str)                # NORMAL|MODIFY (수정세금계산서)
original_invoice_id (UUID, FK→tax_invoices, nullable)
supply_amount (DECIMAL 14,2)      # 공급가액
tax_amount (DECIMAL 14,2)         # 세액
total_amount (DECIMAL 14,2)       # 합계
status (str)                      # PENDING|ISSUED|FAILED|CANCELLED
issued_at (TIMESTAMP, nullable)
error_message (TEXT)
retry_count (int)
created_at, updated_at (TIMESTAMP)
```

### 3.4 `branches` 변경
- 신규 컬럼 `settlement_cycle (str, default='WEEKLY')` 추가
- 기존 `commission_rate (float)`는 유지 (정산 계산 시 Decimal 변환)

### 3.5 `service_requests` 변경
- ServiceRequest → Settlement 직접 관계 제거. (이제 ServiceRequest → Payment → SettlementItem → Settlement 경로)
- DB 컬럼 영향 없음, Python relationship만 제거.

## 4. 기존 데이터 처리
- 현재 `settlements` 테이블에 3건의 테스트 데이터 존재 (1:1 구조)
- 새 스키마와 의미 불일치 → **CSV로 스냅샷 후 테이블 드롭**
- 위치: `/home/ubuntu/backend/backup/settlements_legacy_20260512.csv`
- 원본 SQLite 백업(`washer_crm_20260512_134047.db`)에도 남아있음

## 5. 작업 순서
1. 로컬 `domain.py` 갱신:
   - Settlement 재정의 (request_id 제거, 새 컬럼 다수)
   - SettlementItem 추가
   - TaxInvoice 추가
   - Branch에 settlement_cycle + settlements 관계 추가
   - ServiceRequest.settlements 관계 제거
2. 서버 작업:
   a. `settlements` 테이블 → CSV 스냅샷
   b. `DROP TABLE settlements`
   c. 신규 `domain.py` 업로드
   d. `alembic revision --autogenerate -m "settlement redesign"`
   e. 생성된 마이그레이션 검토
   f. `alembic upgrade head`
   g. 백엔드 재기동
3. 검증

## 6. 완료 조건 (AC)
- [ ] `alembic history` → 베이스라인 + settlement_redesign 2건
- [ ] PG에 `settlements`, `settlement_items`, `tax_invoices` 3개 테이블 존재
- [ ] `branches.settlement_cycle` 컬럼 존재, 기본값 `WEEKLY`
- [ ] `settlements_legacy_20260512.csv` 백업 파일 존재
- [ ] 백엔드 정상 응답 (`curl /api/v1/branches/` HTTP 200)
- [ ] 백엔드 로그에 신규 모델 import 에러 없음

## 7. 롤백 계획
- `alembic downgrade -1` → 베이스라인으로 복귀
- `domain.py`를 백업 버전으로 복원
- 백엔드 재기동

## 8. 후속 작업
- [x] §4.2 정산 계산 알고리즘 — 부가세 분리 공식, 환불 오프셋 처리, 음수 정산 HOLD 전이. **완료 2026-05-17** (`plan_phase4.2_settlement_engine.md`). §4.3 HQ 정산 관리 화면·§4.4 지사 정산 명세서 페이지도 §4.2 범위에 통합 구현됨.
- [x] §4.3 HQ 정산 관리 화면 — DRAFT→REVIEW→APPROVED→PAID→INVOICED 상태 전이. **완료 2026-05-17** (§4.2에 통합, `www/admin.html` "정산 관리" 탭).
- [x] §4.4 지사용 정산 명세서 페이지. **완료 2026-05-17** (§4.2에 통합, `www/manager.html` "정산" 탭).
- [ ] §4.5 Popbill 세금계산서 발행 워커 (사람 트랙 대기 — 팝빌 가입·인증서 등록 필요).

## 9. 알려진 위험·제약
| 위험 | 대응 |
| :--- | :--- |
| ServiceRequest.settlements 관계 제거로 인한 기존 API 영향 | 백엔드 코드 grep — 이 관계를 참조하는 곳 사전 확인 |
| Alembic autogenerate가 ENUM/제약조건을 누락할 가능성 | 생성된 마이그레이션 직접 검토 후 적용 |
| `tax_invoices.original_invoice_id` self-referential FK 처리 | 마이그레이션에서 FK는 `op.create_foreign_key` 별도 추가 가능성 |
