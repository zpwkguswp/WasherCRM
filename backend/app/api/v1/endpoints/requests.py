from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from fastapi.encoders import jsonable_encoder
from sqlmodel import Session, select
from typing import List, Optional
from uuid import UUID
from datetime import datetime
import shutil
import os

from app.db.session import get_session
from app.models.domain import ServiceRequest, AuditLog, RequestMedia
from app.schemas.domain import RequestCreate, RequestUpdate, RequestRead

router = APIRouter()

@router.post("/", response_model=RequestRead, status_code=status.HTTP_201_CREATED)
def create_request(data: RequestCreate, session: Session = Depends(get_session)):
    # 1. 요청 생성
    new_request = ServiceRequest(**data.model_dump())
    session.add(new_request)
    session.commit()
    session.refresh(new_request)
    
    # 2. 감사 로그 기록
    log = AuditLog(
        table_name="service_requests",
        target_id=new_request.id,
        action="INSERT",
        payload=jsonable_encoder(data),
        changed_by="system_user" # 향후 인증 도입 시 실제 유저 ID로 변경
    )
    session.add(log)
    session.commit()
    
    return new_request

from sqlalchemy.orm import selectinload

from sqlalchemy import or_

@router.get("/", response_model=List[RequestRead])
def list_requests(
    status: Optional[str] = None, 
    restaurant_id: Optional[UUID] = None,
    assigned_branch_id: Optional[UUID] = None,
    unassigned_region: Optional[str] = None,
    session: Session = Depends(get_session)
):
    from app.models.domain import Restaurant
    statement = select(ServiceRequest).options(
        selectinload(ServiceRequest.media),
        selectinload(ServiceRequest.restaurant),
        selectinload(ServiceRequest.branch)
    )
    
    if unassigned_region and assigned_branch_id:
        # 지사 전용: 자신에게 배정된 건 OR (미배정 건 중 해당 지역 주소 포함 건)
        statement = statement.join(ServiceRequest.restaurant).where(
            or_(
                ServiceRequest.assigned_branch_id == assigned_branch_id,
                or_(
                    ServiceRequest.assigned_branch_id == None,
                    ServiceRequest.assigned_branch_id == None # Placeholder for OR logic
                ) & Restaurant.address.contains(unassigned_region)
            )
        )
    else:
        if status:
            statement = statement.where(ServiceRequest.status == status)
        if restaurant_id:
            statement = statement.where(ServiceRequest.restaurant_id == restaurant_id)
        if assigned_branch_id:
            statement = statement.where(ServiceRequest.assigned_branch_id == assigned_branch_id)
    
    results = session.exec(statement).all()
    return [RequestRead.from_db(r) for r in results]

@router.get("/{request_id}", response_model=RequestRead)
def get_request(request_id: UUID, session: Session = Depends(get_session)):
    db_request = session.get(ServiceRequest, request_id)
    if not db_request:
        raise HTTPException(status_code=404, detail="Request not found")
    return db_request

@router.patch("/{request_id}", response_model=RequestRead)
def update_request(request_id: UUID, data: RequestUpdate, session: Session = Depends(get_session)):
    db_request = session.get(ServiceRequest, request_id)
    if not db_request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    # 변경 사항 추적을 위한 이전 데이터 저장
    old_data = db_request.model_dump()
    
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key == "metadata":
            setattr(db_request, "metadata_json", value)
        else:
            setattr(db_request, key, value)
    
    # 상태 변경 시 관련 타임스탬프 업데이트 및 결제/정산 처리
    if "status" in update_data:
        if update_data["status"] == "IN_PROGRESS" and not db_request.assigned_at:
            db_request.assigned_at = datetime.utcnow()
        elif update_data["status"] == "COMPLETED" and not db_request.completed_at:
            db_request.completed_at = datetime.utcnow()
            # [추가] 완료 시 결제 및 정산 데이터 자동 생성 (대시보드 연동용)
            from app.models.domain import Payment, Settlement, Branch
            meta = db_request.metadata_json or {}
            amount = float(meta.get("requested_amount", 0))
            
            if amount > 0:
                # 1. 결제 기록 생성
                new_payment = Payment(
                    request_id=db_request.id,
                    amount=amount,
                    merchant_uid=f"auto_{db_request.id.hex[:8]}",
                    status="PAID"
                )
                session.add(new_payment)
                
                # 2. 지사 정산 데이터 생성
                if db_request.assigned_branch_id:
                    branch = session.get(Branch, db_request.assigned_branch_id)
                    rate = branch.commission_rate if branch else 0.0
                    hq_comm = amount * (rate / 100.0)
                    new_settlement = Settlement(
                        branch_id=db_request.assigned_branch_id,
                        request_id=db_request.id,
                        total_amount=amount,
                        hq_commission=hq_comm,
                        branch_settlement_amount=amount - hq_comm,
                        status="COMPLETED",
                        settled_at=datetime.utcnow()
                    )
                    session.add(new_settlement)
    
    db_request.updated_at = datetime.utcnow()
    session.add(db_request)
    
    # 감사 로그 기록
    log = AuditLog(
        table_name="service_requests",
        target_id=db_request.id,
        action="UPDATE",
        payload=jsonable_encoder({"before": old_data, "after": db_request.model_dump()}),
        changed_by="system_user"
    )
    session.add(log)
    
    session.commit()
    session.refresh(db_request)
    return db_request

@router.post("/{request_id}/media")
async def upload_media(
    request_id: UUID,
    file: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    # 1. 요청 존재 확인
    db_request = session.get(ServiceRequest, request_id)
    if not db_request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    # 2. 파일 저장 경로 설정
    upload_dir = os.path.join("app", "static", "uploads")
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
        
    file_extension = os.path.splitext(file.filename)[1]
    file_name = f"{request_id}_{datetime.now().timestamp()}{file_extension}"
    file_path = os.path.join(upload_dir, file_name)
    
    # 3. 실제 파일 저장
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # 4. DB 기록
    # 외부 접근용 URL 생성
    file_url = f"/uploads/{file_name}"
    
    new_media = RequestMedia(
        request_id=request_id,
        type="IMAGE",
        file_url=file_url
    )
    session.add(new_media)
    session.commit()
    
    return {"status": "success", "file_url": file_url}
