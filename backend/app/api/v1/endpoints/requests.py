from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from fastapi.encoders import jsonable_encoder
from sqlmodel import Session, select
from typing import List, Optional
from uuid import UUID
from datetime import datetime
import shutil
import os

from app.db.session import get_session
from app.models.domain import ServiceRequest, AuditLog, RequestMedia, DeviceToken, Branch, Restaurant
from app.schemas.domain import RequestCreate, RequestUpdate, RequestRead
from app.utils.notifications import send_push_notification
from app.services.storage import storage

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
    
    # 3. 푸시 알림 발송 (해당 지역 매니저에게만)
    try:
        # 1. 요청을 올린 식당 정보 조회
        restaurant = session.get(Restaurant, new_request.restaurant_id)
        
        # 2. 모든 매니저 토큰과 담당 지역 정보 조회
        token_statement = select(DeviceToken.token, Branch.region_code).join(
            Branch, Branch.id == DeviceToken.user_id
        ).where(
            DeviceToken.user_type == "MANAGER",
            DeviceToken.is_active == True
        )
        results = session.exec(token_statement).all()
        
        token_list = []
        for token, region_code in results:
            # 지역이 정확히 일치하거나, 식당 주소에 지사 지역 코드가 포함된 경우 (예: "수원" in "경기 수원시...")
            if region_code == restaurant.region or (region_code and region_code in restaurant.address):
                token_list.append(token)
        
        print(f"--- Notification Debug ---")
        print(f"Restaurant Region: {restaurant.region}")
        print(f"Restaurant Address: {restaurant.address}")
        print(f"Found {len(token_list)} manager(s) to notify.")
        print(f"--------------------------")

        if token_list:
            send_push_notification(
                tokens=token_list,
                title="🔔 신규 수리 요청 접수",
                body=f"[{data.category}] 새로운 수리 요청이 등록되었습니다.",
                data={"request_id": str(new_request.id)}
            )
            print(f"Successfully triggered notification for {len(token_list)} tokens.")
    except Exception as e:
        print(f"Notification error: {e}")
    
    return new_request

from sqlalchemy.orm import selectinload

from sqlalchemy import or_, String, func

@router.get("/", response_model=List[RequestRead])
def list_requests(
    status: Optional[str] = None, 
    restaurant_id: Optional[UUID] = None,
    assigned_branch_id: Optional[UUID] = None,
    unassigned_region: Optional[str] = None,
    search_query: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    session: Session = Depends(get_session)
):
    from app.models.domain import Restaurant, Branch
    statement = select(ServiceRequest).join(Restaurant, isouter=True).join(Branch, isouter=True).options(
        selectinload(ServiceRequest.media),
        selectinload(ServiceRequest.restaurant),
        selectinload(ServiceRequest.branch)
    )
    
    if assigned_branch_id:
        # 지사의 정보를 가져와서 지역 코드를 확인 (unassigned_region이 우선, 없으면 DB의 region_code 사용)
        from app.models.domain import Branch
        branch = session.get(Branch, assigned_branch_id)
        region = unassigned_region or (branch.region_code if branch else None)
        
        # 1. 이미 이 지사에 배정된 요청 OR 
        # 2. 아직 배정되지 않았고(PENDING) 식당 주소에 해당 지역명이 포함된 요청
        statement = statement.where(
            or_(
                ServiceRequest.assigned_branch_id == assigned_branch_id,
                (
                    (ServiceRequest.assigned_branch_id == None) & 
                    (Restaurant.address.contains(region) if region else False)
                )
            )
        )
    else:
        if status:
            statement = statement.where(ServiceRequest.status == status)
        if restaurant_id:
            statement = statement.where(ServiceRequest.restaurant_id == restaurant_id)

    # 통합 검색어 처리 (접수번호, 식당명, 지사명)
    if search_query:
        # UUID 형식인 경우 ID와 매칭, 아니면 이름들과 매칭
        statement = statement.where(
            or_(
                func.cast(ServiceRequest.id, String).contains(search_query),
                Restaurant.name.contains(search_query),
                Branch.name.contains(search_query)
            )
        )

    # 기간 필터링 처리
    if start_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        statement = statement.where(ServiceRequest.created_at >= start_dt)
    if end_date:
        # 종료일은 해당 날짜의 23:59:59까지 포함
        end_dt = datetime.strptime(f"{end_date} 23:59:59", "%Y-%m-%d %H:%M:%S")
        statement = statement.where(ServiceRequest.created_at <= end_dt)
    
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
    
    # 상태 변경 시 관련 타임스탬프 업데이트 및 알람 발송
    if "status" in update_data:
        status = update_data["status"]
        if status == "IN_PROGRESS" and not db_request.assigned_at:
            db_request.assigned_at = datetime.utcnow()
        elif status == "COMPLETED" and not db_request.completed_at:
            db_request.completed_at = datetime.utcnow()
            
        # [추가] 식당 사장님께 상태 변경 알림 발송
        try:
            from app.models.domain import DeviceToken
            from app.utils.notifications import send_push_notification
            
            # 식당 사장님의 토큰 조회
            token_statement = select(DeviceToken.token).where(
                DeviceToken.user_id == db_request.restaurant_id,
                DeviceToken.user_type == "RESTAURANT",
                DeviceToken.is_active == True
            )
            tokens = session.exec(token_statement).all()
            
            if tokens:
                status_msg = {
                    "IN_PROGRESS": "🛠️ 수리 매니저가 현장에 도착하여 수리를 시작했습니다.",
                    "PAYMENT_REQUESTED": "💳 수리가 완료되어 결제 요청이 도착했습니다.",
                    "COMPLETED": "✅ 모든 수리 및 결제가 완료되었습니다. 감사합니다!"
                }
                msg = status_msg.get(status, f"수리 상태가 [{status}] (으)로 변경되었습니다.")
                
                send_push_notification(
                    tokens=tokens,
                    title="📣 수리 진행 알림",
                    body=msg,
                    data={"request_id": str(db_request.id), "status": status}
                )
                print(f"Sent status update notification to restaurant: {db_request.restaurant_id}")
        except Exception as e:
            print(f"Failed to send status update notification: {e}")

        # [추가] 완료 시 결제 및 정산 데이터 자동 생성
        if status == "COMPLETED":
            # ... (기존 정산 로직 유지)
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
    
    # 2. 공통 저장소 서비스를 이용해 파일 업로드 (Local 또는 S3 자동 전환)
    file_url = await storage.upload_file(file, folder="uploads")
        
    # 3. DB 기록
    new_media = RequestMedia(
        request_id=request_id,
        type="IMAGE",
        file_url=file_url
    )
    session.add(new_media)
    session.commit()
    
    return {"status": "success", "file_url": file_url}

@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_request(request_id: UUID, session: Session = Depends(get_session)):
    db_request = session.get(ServiceRequest, request_id)
    if not db_request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    # 관련 미디어 파일이 있다면 함께 삭제 로직을 넣을 수 있으나, 
    # 여기서는 간단히 DB 레코드만 삭제합니다.
    session.delete(db_request)
    session.commit()
    return None
