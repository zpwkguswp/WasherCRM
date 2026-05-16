"""정산 API (plan_phase4.2)

HQ는 정산서를 생성·조회·상태전이하고, 지사는 자기 정산 명세서를 조회한다.
"""
from typing import List, Optional
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlmodel import Session, select, desc

from app.db.session import get_session
from app.models.domain import Branch, Settlement, SettlementItem, AuditLog
from app.schemas.domain import (
    SettlementRead, SettlementItemRead, SettlementGenerate, SettlementStatusUpdate,
)
from app.api.deps import require_role, get_current_user
from app.services.settlement import generate_settlements

router = APIRouter()

# 상태 전이 머신 (plan_phase4.2 §4) — 허용된 전이만 통과
ALLOWED_TRANSITIONS = {
    "DRAFT": {"REVIEW", "HOLD"},
    "REVIEW": {"APPROVED", "HOLD"},
    "APPROVED": {"PAID"},
    "PAID": {"INVOICED"},
    "INVOICED": set(),
    "HOLD": {"REVIEW"},
}


def _to_read(session: Session, s: Settlement, include_items: bool = False) -> SettlementRead:
    """Settlement → SettlementRead. 지사명·라인 수를 채운다."""
    data = SettlementRead.model_validate(s)
    branch = session.get(Branch, s.branch_id)
    if branch:
        data.branch_name = branch.name
    items = session.exec(
        select(SettlementItem).where(SettlementItem.settlement_id == s.id)
    ).all()
    data.item_count = len(items)
    if include_items:
        data.items = [SettlementItemRead.model_validate(it) for it in items]
    return data


@router.post("/generate", response_model=List[SettlementRead],
             dependencies=[Depends(require_role("HQ_ADMIN"))])
def generate(data: SettlementGenerate, user: dict = Depends(get_current_user),
             session: Session = Depends(get_session)):
    """기간 입력 → 활동 있는 전 지사의 DRAFT 정산서를 일괄 생성한다 (멱등).

    같은 기간을 두 번 호출해도 이미 만든 정산서는 중복 생성하지 않는다.
    """
    try:
        created = generate_settlements(
            session, data.period_start, data.period_end, data.period_type,
            changed_by=f"{user.get('role')}:{user.get('sub')}",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return [_to_read(session, s) for s in created]


@router.get("/", response_model=List[SettlementRead],
            dependencies=[Depends(require_role("HQ_ADMIN"))])
def list_settlements(branch_id: Optional[UUID] = None, status: Optional[str] = None,
                     period_start: Optional[date] = None, period_end: Optional[date] = None,
                     session: Session = Depends(get_session)):
    """전체 정산서 목록 (HQ). 지사·상태·기간으로 필터."""
    stmt = select(Settlement).order_by(desc(Settlement.period_start), desc(Settlement.created_at))
    if branch_id:
        stmt = stmt.where(Settlement.branch_id == branch_id)
    if status:
        stmt = stmt.where(Settlement.status == status)
    if period_start:
        stmt = stmt.where(Settlement.period_start >= period_start)
    if period_end:
        stmt = stmt.where(Settlement.period_end <= period_end)
    return [_to_read(session, s) for s in session.exec(stmt).all()]


@router.get("/my", response_model=List[SettlementRead],
            dependencies=[Depends(require_role("BRANCH"))])
def my_settlements(user: dict = Depends(get_current_user),
                   session: Session = Depends(get_session)):
    """본인 지사 정산 명세서 목록 (지사). 토큰 sub 기준 — 타 지사 조회 불가."""
    branch_id = UUID(user.get("sub"))
    stmt = (
        select(Settlement)
        .where(Settlement.branch_id == branch_id)
        .order_by(desc(Settlement.period_start))
    )
    return [_to_read(session, s) for s in session.exec(stmt).all()]


@router.get("/{settlement_id}", response_model=SettlementRead)
def get_settlement(settlement_id: UUID, user: dict = Depends(get_current_user),
                   session: Session = Depends(get_session)):
    """정산서 상세 + 라인 아이템. 지사는 본인 정산서만 조회 가능."""
    s = session.get(Settlement, settlement_id)
    if not s:
        raise HTTPException(status_code=404, detail="정산서를 찾을 수 없습니다.")
    role = user.get("role")
    if role == "BRANCH" and str(s.branch_id) != user.get("sub"):
        raise HTTPException(status_code=403, detail="본인 지사 정산서만 조회할 수 있습니다.")
    if role not in ("HQ_ADMIN", "BRANCH"):
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    return _to_read(session, s, include_items=True)


@router.patch("/{settlement_id}/status", response_model=SettlementRead,
              dependencies=[Depends(require_role("HQ_ADMIN"))])
def update_status(settlement_id: UUID, data: SettlementStatusUpdate,
                  user: dict = Depends(get_current_user),
                  session: Session = Depends(get_session)):
    """정산서 상태 전이 (HQ). 허용된 전이만 통과 — plan_phase4.2 §4."""
    from datetime import datetime

    s = session.get(Settlement, settlement_id)
    if not s:
        raise HTTPException(status_code=404, detail="정산서를 찾을 수 없습니다.")

    new_status = data.status
    if new_status not in ALLOWED_TRANSITIONS:
        raise HTTPException(status_code=400, detail=f"알 수 없는 상태: {new_status}")
    if new_status == s.status:
        raise HTTPException(status_code=400, detail="이미 해당 상태입니다.")
    if new_status not in ALLOWED_TRANSITIONS.get(s.status, set()):
        raise HTTPException(
            status_code=400,
            detail=f"'{s.status}' → '{new_status}' 전이는 허용되지 않습니다.",
        )

    old_status = s.status
    actor = f"{user.get('role')}:{user.get('sub')}"
    now = datetime.utcnow()
    s.status = new_status
    if new_status == "APPROVED":
        s.approved_at = now
        s.approved_by = actor
    elif new_status == "PAID":
        s.paid_at = now
    elif new_status == "INVOICED":
        s.invoiced_at = now
    if data.notes is not None:
        s.notes = data.notes

    session.add(s)
    session.add(AuditLog(
        table_name="settlements",
        target_id=s.id,
        action="UPDATE",
        payload=jsonable_encoder({"status": {"before": old_status, "after": new_status}}),
        changed_by=actor,
    ))
    session.commit()
    session.refresh(s)
    return _to_read(session, s, include_items=True)
