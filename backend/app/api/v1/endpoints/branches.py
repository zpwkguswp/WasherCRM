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
    # 1. 승인된 지사 목록만 가져오기
    branches = session.exec(select(Branch).where(Branch.is_approved == True)).all()
    metrics = []
    
    for b in branches:
        # 지사별 완료된 요청 수 계산
        completed_count = session.exec(
            select(func.count(ServiceRequest.id))
            .where(ServiceRequest.assigned_branch_id == b.id)
            .where(ServiceRequest.status == "COMPLETED")
        ).one()
        
        # 지사별 총 매출액 및 본사 수수료 계산 (Settlement 테이블 기준)
        # §4.1 재설계: Settlement.total_amount → Settlement.gross_amount
        revenue_data = session.exec(
            select(
                func.sum(Settlement.gross_amount).label("total_revenue"),
                func.sum(Settlement.hq_commission).label("total_commission")
            )
            .where(Settlement.branch_id == b.id)
        ).first()
        
        total_rev = float(revenue_data[0] or 0)
        
        # 등급 및 수수료 자동 계산 (새로운 정책 반영)
        tier = "BRONZE"
        new_rate = 10.0
        goal = 10000000
        if total_rev >= 30000000:
            tier = "DIAMOND"; new_rate = 5.0; goal = 30000000
        elif total_rev >= 20000000:
            tier = "GOLD"; new_rate = 6.0; goal = 30000000
        elif total_rev >= 10000000:
            tier = "SILVER"; new_rate = 8.0; goal = 20000000
            
        # 만족도 평균 계산 보정 (더 견고한 데이터 추출)
        all_completed = session.exec(
            select(ServiceRequest)
            .where(ServiceRequest.assigned_branch_id == b.id)
            .where(ServiceRequest.status == "COMPLETED")
        ).all()
        
        ratings = []
        for r in all_completed:
            meta = r.metadata_json
            if meta and isinstance(meta, dict) and "survey" in meta:
                s = meta["survey"]
                if isinstance(s, dict) and "rating" in s:
                    try:
                        val = float(s["rating"])
                        if val > 0: ratings.append(val)
                    except (ValueError, TypeError): continue
        
        avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0.0
        
        # 목표 달성률 계산
        progress = round((total_rev / goal) * 100, 1) if goal > 0 else 0.0

        metrics.append({
            "branch_id": b.id,
            "branch_name": b.name,
            "region_code": b.region_code,
            "tier": tier,
            "progress": progress,
            "completed_requests": len(all_completed),
            "total_revenue": total_rev,
            "total_hq_commission": float(revenue_data[1] or 0),
            "avg_satisfaction": avg_rating
        })
        
    # 실적(매출액) 순으로 정렬해서 반환
    return sorted(metrics, key=lambda x: x["total_revenue"], reverse=True)

@router.post("/", response_model=BranchRead, status_code=status.HTTP_201_CREATED)
def create_branch(data: BranchCreate, session: Session = Depends(get_session)):
    # 1. 필수 항목 기재 여부 확인
    if not data.manager_phone or not data.address or not data.name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이름, 핸드폰 번호, 상세 주소는 필수 입력 사항입니다."
        )

    # 2. 플랫폼 전체 중복 체크 (이름, 번호, 주소)
    from app.models.domain import Restaurant
    
    # 이름 중복 체크 (지사/식당 통합)
    dup_name_b = session.exec(select(Branch).where(Branch.name == data.name)).first()
    dup_name_r = session.exec(select(Restaurant).where(Restaurant.name == data.name)).first()
    if dup_name_b or dup_name_r:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{data.name}'은(는) 이미 등록된 이름입니다.")

    # 번호 중복 체크 (지사/식당 통합)
    dup_phone_b = session.exec(select(Branch).where(Branch.manager_phone == data.manager_phone)).first()
    dup_phone_r = session.exec(select(Restaurant).where(Restaurant.phone == data.manager_phone)).first()
    if dup_phone_b or dup_phone_r:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 시스템에 등록된 핸드폰 번호입니다.")

    # 주소 중복 체크 (지사/식당 통합)
    dup_addr_b = session.exec(select(Branch).where(Branch.address == data.address)).first()
    dup_addr_r = session.exec(select(Restaurant).where(Restaurant.address == data.address)).first()
    if dup_addr_b or dup_addr_r:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 등록된 상세 주소입니다. (중복 가입 방지)")

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
    
    branches = session.exec(statement).all()
    
    # 자동 승급 로직 적용
    for b in branches:
        if not b.is_approved:
            continue
            
        # 총 매출액 확인 (§4.1 재설계: total_amount → gross_amount)
        from app.models.domain import Settlement
        revenue_data = session.exec(
            select(func.sum(Settlement.gross_amount))
            .where(Settlement.branch_id == b.id)
        ).first()
        total_rev = float(revenue_data or 0)
        
        # 등급 및 수수료 자동 업데이트 (새로운 정책 반영)
        new_tier = "BRONZE"
        new_rate = 10.0
        if total_rev >= 30000000:
            new_tier = "DIAMOND"
            new_rate = 5.0
        elif total_rev >= 20000000:
            new_tier = "GOLD"
            new_rate = 6.0
        elif total_rev >= 10000000:
            new_tier = "SILVER"
            new_rate = 8.0
            
        if b.tier != new_tier:
            b.tier = new_tier
            b.commission_rate = new_rate
            session.add(b)
    
    session.commit()
    for b in branches:
        session.refresh(b)
        
    return branches

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
        
    # 이름 중복 체크 (자신은 제외)
    if data.name and data.name != branch.name:
        existing = session.exec(select(Branch).where(Branch.name == data.name, Branch.id != branch_id)).first()
        if existing: raise HTTPException(status_code=400, detail=f"'{data.name}'은(는) 이미 등록된 지사명입니다.")

    # 연락처 중복 체크
    if data.manager_phone and data.manager_phone != branch.manager_phone:
        existing = session.exec(select(Branch).where(Branch.manager_phone == data.manager_phone, Branch.id != branch_id)).first()
        if existing: raise HTTPException(status_code=400, detail="이미 시스템에 등록된 연락처입니다.")

    # 주소 중복 체크
    if data.address and data.address != branch.address:
        existing = session.exec(select(Branch).where(Branch.address == data.address, Branch.id != branch_id)).first()
        if existing: raise HTTPException(status_code=400, detail="이미 등록된 지사 주소입니다.")

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
def delete_branch(branch_id: UUID, session: Session = Depends(get_session)):
    # 관리자용이므로 확인 코드 없이 진행 (UI에서 컨펌 창 띄움)
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
