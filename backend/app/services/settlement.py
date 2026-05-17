"""정산 계산 엔진 (plan_phase4.2)

PAID 결제를 기간 × 지사별로 집계해 Settlement + SettlementItem 행을 생성한다.

설계 원칙:
- 모든 금액은 Decimal. float 금지 (CLAUDE.md).
- "바뀔 수 있는 정책"(수수료율·반올림·부가세율)은 이 파일 상단 상수에 모음.
  대표님이 정책을 바꿔도 여기 한 곳만 수정하면 된다.
- 정산 주기(주간/월간 등)는 이 엔진이 모른다. period_start/period_end만 받는다.
- 멱등: 같은 (지사, 기간)에 정산서가 이미 있으면 건너뛴다.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List

from fastapi.encoders import jsonable_encoder
from sqlmodel import Session, select

from app.models.domain import (
    Branch, ServiceRequest, Payment, Settlement, SettlementItem, AuditLog,
)

# ─── 변경 가능 정책 상수 ──────────────────────────────────────────
# 등급별 수수료율(%) — Branch.commission_rate가 0/없을 때의 기본값.
TIER_COMMISSION = {
    "BRONZE": Decimal("10"),
    "SILVER": Decimal("8"),
    "GOLD": Decimal("6"),
    "DIAMOND": Decimal("5"),
}
DEFAULT_COMMISSION = Decimal("10")  # 등급 미상 시

# 부가세 — 결제 금액은 VAT 포함. 공급가 = gross / (1 + VAT_RATE).
VAT_RATE = Decimal("0.1")

# 금액 반올림 단위 — 원 단위(소수점 없음). 규칙 변경 시 여기만 수정.
ROUND_UNIT = Decimal("1")
ROUND_MODE = ROUND_HALF_UP
# ─────────────────────────────────────────────────────────────────


def _won(value: Decimal) -> Decimal:
    """원 단위로 반올림한다."""
    return Decimal(value).quantize(ROUND_UNIT, rounding=ROUND_MODE)


def _commission_rate(branch: Branch) -> Decimal:
    """지사에 적용할 수수료율(%)을 결정한다.

    Branch.commission_rate가 양수면 그 값, 아니면 등급 매핑, 그것도 없으면 기본값.
    """
    rate = branch.commission_rate
    if rate and Decimal(str(rate)) > 0:
        return Decimal(str(rate))
    return TIER_COMMISSION.get((branch.tier or "").upper(), DEFAULT_COMMISSION)


def calculate_amounts(gross: Decimal, rate_percent: Decimal, refund_offset: Decimal = Decimal("0")) -> dict:
    """집계 총액(gross)으로부터 정산 금액 일체를 계산한다.

    공급가 = gross / (1 + VAT_RATE), 세액 = gross - 공급가 (합계 보존).
    본사 수수료 = gross × rate%, 지사액 = gross - 수수료.
    최종 지급액 = 지사액 - 환불차감.
    """
    gross = _won(gross)
    supply = _won(gross / (Decimal("1") + VAT_RATE))
    vat = gross - supply
    hq_commission = _won(gross * rate_percent / Decimal("100"))
    branch_amount = gross - hq_commission
    refund_offset = _won(refund_offset)
    net_amount = branch_amount - refund_offset
    return {
        "gross_amount": gross,
        "vat_amount": vat,
        "supply_amount": supply,
        "commission_rate": rate_percent,
        "hq_commission": hq_commission,
        "branch_amount": branch_amount,
        "refund_offset": refund_offset,
        "net_amount": net_amount,
    }


def generate_settlements(
    session: Session,
    period_start: date,
    period_end: date,
    period_type: str = "WEEKLY",
    changed_by: str = "system",
) -> List[Settlement]:
    """기간 내 PAID 결제를 지사별로 집계해 DRAFT 정산서를 생성한다.

    반환: 이번 호출에서 새로 생성된 Settlement 목록 (이미 있던 것은 제외).
    """
    if period_end < period_start:
        raise ValueError("period_end must not be before period_start")

    # 기간 경계 — period_end 당일 23:59:59까지 포함 (paid_at < 익일 0시)
    start_dt = datetime.combine(period_start, datetime.min.time())
    end_dt = datetime.combine(period_end + timedelta(days=1), datetime.min.time())

    created: List[Settlement] = []
    branches = session.exec(select(Branch).where(Branch.is_approved == True)).all()

    for branch in branches:
        # 멱등성 — 같은 (지사, 기간)에 정산서가 이미 있으면 건너뜀
        exists = session.exec(
            select(Settlement).where(
                Settlement.branch_id == branch.id,
                Settlement.period_start == period_start,
                Settlement.period_end == period_end,
            )
        ).first()
        if exists:
            continue

        # 해당 지사 배정 + 기간 내 PAID 결제 조회
        payments = session.exec(
            select(Payment)
            .join(ServiceRequest, Payment.request_id == ServiceRequest.id)
            .where(ServiceRequest.assigned_branch_id == branch.id)
            .where(Payment.status == "PAID")
            .where(Payment.paid_at >= start_dt)
            .where(Payment.paid_at < end_dt)
        ).all()

        # 활동 없으면 빈 정산서를 만들지 않는다 (환불도 현재 없음)
        if not payments:
            continue

        gross = sum((Decimal(str(p.amount)) for p in payments), Decimal("0"))
        rate = _commission_rate(branch)
        # 환불 차감 — 현재 환불 데이터 없음(plan_phase4.2 §2). PortOne 환불 도입 시 보강.
        amounts = calculate_amounts(gross, rate, refund_offset=Decimal("0"))

        status = "HOLD" if amounts["net_amount"] < 0 else "DRAFT"

        settlement = Settlement(
            branch_id=branch.id,
            period_start=period_start,
            period_end=period_end,
            period_type=period_type,
            gross_amount=amounts["gross_amount"],
            vat_amount=amounts["vat_amount"],
            commission_rate=amounts["commission_rate"],
            hq_commission=amounts["hq_commission"],
            branch_amount=amounts["branch_amount"],
            refund_offset=amounts["refund_offset"],
            net_amount=amounts["net_amount"],
            status=status,
        )
        session.add(settlement)
        session.flush()  # settlement.id 확보

        for p in payments:
            session.add(SettlementItem(
                settlement_id=settlement.id,
                payment_id=p.id,
                item_type="SERVICE",
                amount=Decimal(str(p.amount)),
                description=None,
            ))

        session.add(AuditLog(
            table_name="settlements",
            target_id=settlement.id,
            action="INSERT",
            payload=jsonable_encoder({
                "branch_id": str(branch.id),
                "period": f"{period_start}~{period_end}",
                "gross": str(amounts["gross_amount"]),
                "net": str(amounts["net_amount"]),
                "status": status,
                "item_count": len(payments),
            }),
            changed_by=changed_by,
        ))
        created.append(settlement)

    session.commit()
    for s in created:
        session.refresh(s)
    return created
