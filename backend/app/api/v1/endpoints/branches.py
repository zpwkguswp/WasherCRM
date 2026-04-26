from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlmodel import Session, select, func
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from app.db.session import get_session
from app.models.domain import Branch, AuditLog, ServiceRequest, Settlement
from app.schemas.domain import BranchCreate, BranchUpdate, BranchRead

router = APIRouter()

@router.get("/metrics/performance")
def get_branch_performance(session: Session = Depends(get_session)):
    """
    본사 관리자용: 각 지사별 실적(완료 건수, 매출액)을 집계합니다.
    """
    # 1. 지사 목록 가져오기
    branches = session.exec(select(Branch)).all()
    metrics = []
    
    for b in branches:
        # 지사별 완료된 요청 수 계산
        completed_count = session.exec(
            select(func.count(ServiceRequest.id))
            .where(ServiceRequest.assigned_branch_id == b.id)
            .where(ServiceRequest.status == "COMPLETED")
        ).one()
        
        # 지사별 총 매출액 및 본사 수수료 계산 (Settlement 테이블 기준)
        revenue_data = session.exec(
            select(
                func.sum(Settlement.total_amount).label("total_revenue"),
                func.sum(Settlement.hq_commission).label("total_commission")
            )
            .where(Settlement.branch_id == b.id)
        ).first()
        
        metrics.append({
            "branch_id": b.id,
            "branch_name": b.name,
            "completed_requests": completed_count,
            "total_revenue": float(revenue_data[0] or 0),
            "total_hq_commission": float(revenue_data[1] or 0)
        })
        
    # 실적(완료 건수) 순으로 정렬해서 반환
    return sorted(metrics, key=lambda x: x["completed_requests"], reverse=True)

@router.post("/", response_model=BranchRead, status_code=status.HTTP_201_CREATED)
def create_branch(data: BranchCreate, session: Session = Depends(get_session)):
    # 이름 중복 체크
    existing = session.exec(select(Branch).where(Branch.name == data.name)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"'{data.name}'은(는) 이미 등록된 지사명입니다. 다른 이름을 사용해 주세요."
        )

    new_branch = Branch(**data.model_dump())
    session.add(new_branch)
    session.commit()
    session.refresh(new_branch)
    
    # 감사 로그
    log = AuditLog(
        table_name="branches",
        target_id=new_branch.id,
        action="INSERT",
        payload=jsonable_encoder(data),
        changed_by="system_admin"
    )
    session.add(log)
    session.commit()
    
    return new_branch

@router.get("/", response_model=List[BranchRead])
def list_branches(
    name: Optional[str] = None,
    phone: Optional[str] = None,
    session: Session = Depends(get_session)
):
    statement = select(Branch)
    if name:
        statement = statement.where(Branch.name.contains(name))
    if phone:
        statement = statement.where(Branch.manager_phone.contains(phone))
    
    return session.exec(statement).all()

@router.get("/{branch_id}", response_model=BranchRead)
def get_branch(branch_id: UUID, session: Session = Depends(get_session)):
    branch = session.get(Branch, branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    return branch

@router.patch("/{branch_id}", response_model=BranchRead)
def update_branch(branch_id: UUID, data: BranchUpdate, session: Session = Depends(get_session)):
    branch = session.get(Branch, branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
        
    # 이름 변경 시 중복 체크 (자신은 제외)
    if data.name and data.name != branch.name:
        existing = session.exec(select(Branch).where(Branch.name == data.name, Branch.id != branch_id)).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"'{data.name}'은(는) 이미 다른 지사에서 사용 중인 이름입니다."
            )

    old_data = branch.model_dump()
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(branch, key, value)
    
    branch.updated_at = datetime.utcnow()
    session.add(branch)
    
    # 감사 로그
    log = AuditLog(
        table_name="branches",
        target_id=branch.id,
        action="UPDATE",
        payload=jsonable_encoder({"before": old_data, "after": branch.model_dump()}),
        changed_by="system_admin"
    )
    session.add(log)
    
    session.commit()
    session.refresh(branch)
    return branch
@router.delete("/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_branch(
    branch_id: UUID, 
    confirmation_code: str, 
    session: Session = Depends(get_session)
):
    # 1. 안전 코드 확인
    if confirmation_code != "DELETE_CONFIRM":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="삭제 확인 코드가 일치하지 않습니다. ('DELETE_CONFIRM'을 입력하세요)"
        )

    branch = session.get(Branch, branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    # 2. 연관 데이터(A/S 요청)가 있는지 확인
    from app.models.domain import ServiceRequest
    linked_requests = session.exec(select(ServiceRequest).where(ServiceRequest.assigned_branch_id == branch_id)).first()
    if linked_requests:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="이 지사에 할당된 A/S 요청 내역이 존재하여 삭제할 수 없습니다. 먼저 내역을 정리해 주세요."
        )

    # 3. 삭제 및 감사 로그 기록
    log = AuditLog(
        table_name="branches",
        target_id=branch.id,
        action="DELETE",
        payload=jsonable_encoder(branch),
        changed_by="system_admin"
    )
    session.add(log)
    
    session.delete(branch)
    session.commit()
    return None
