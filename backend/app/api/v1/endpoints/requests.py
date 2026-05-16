from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from fastapi.encoders import jsonable_encoder
from sqlmodel import Session, select
from typing import List, Optional
from uuid import UUID
from datetime import datetime
import shutil
import os

from app.db.session import get_session
from app.models.domain import ServiceRequest, AuditLog, RequestMedia, DeviceToken, Branch, Restaurant, Payment, Settlement
from app.schemas.domain import RequestCreate, RequestUpdate, RequestRead
from app.utils.notifications import send_push_notification
from app.services.storage import storage
from app.api.deps import require_role

router = APIRouter()

@router.post("/", response_model=RequestRead, status_code=status.HTTP_201_CREATED)
def create_request(data: RequestCreate, session: Session = Depends(get_session)):
    # 1. 요청 생성 (notified_at = 지사 브로드캐스트 시각, SLA 시작점)
    new_request = ServiceRequest(**data.model_dump())
    new_request.notified_at = datetime.utcnow()
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

@router.get("/sla/summary", dependencies=[Depends(require_role("HQ_ADMIN"))])
def sla_summary(threshold_minutes: int = 60, session: Session = Depends(get_session)):
    """본사용: 지사 수락 SLA 요약 — notified_at→accepted_at 경과시간 통계."""
    accepted = session.exec(
        select(ServiceRequest).where(
            ServiceRequest.notified_at.is_not(None),
            ServiceRequest.accepted_at.is_not(None),
        )
    ).all()
    elapsed = [
        (r.accepted_at - r.notified_at).total_seconds() / 60.0 for r in accepted
    ]
    count = len(elapsed)
    pending = session.exec(
        select(func.count(ServiceRequest.id)).where(
            ServiceRequest.notified_at.is_not(None),
            ServiceRequest.accepted_at.is_(None),
        )
    ).one()
    return {
        "accepted_count": count,
        "avg_accept_minutes": round(sum(elapsed) / count, 1) if count else 0.0,
        "max_accept_minutes": round(max(elapsed), 1) if count else 0.0,
        "threshold_minutes": threshold_minutes,
        "over_threshold_count": sum(1 for e in elapsed if e > threshold_minutes),
        "pending_unaccepted_count": pending,
    }

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
    was_unassigned = db_request.assigned_branch_id is None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key == "metadata":
            # [중요] 기존 객체를 직접 update하면 DB 변경 감지가 안 될 수 있음
            # 반드시 새로운 dict 객체를 생성하여 할당해야 함
            current_meta = dict(db_request.metadata_json or {})
            if isinstance(value, dict):
                current_meta.update(value)
            db_request.metadata_json = current_meta
        else:
            setattr(db_request, key, value)
    
    # 지사가 처음 배정(수락)된 시각 기록 — SLA 종료점
    if was_unassigned and db_request.assigned_branch_id is not None and db_request.accepted_at is None:
        db_request.accepted_at = datetime.utcnow()

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
            # 메타데이터에서 요청 금액 가져오기
            amount = db_request.metadata_json.get("requested_amount", 0) if db_request.metadata_json else 0
            
            # 1. 결제 기록 생성
            new_payment = Payment(
                request_id=db_request.id,
                amount=amount,
                merchant_uid=f"auto_{db_request.id.hex[:8]}",
                status="PAID"
            )
            session.add(new_payment)
            
            # 2. (DEPRECATED §4.1) 요청 완료 시 Settlement를 즉시 생성하던 로직 제거.
            # 새 설계는 주기 단위 배치로 Settlement를 생성. §4.2에서 구현 예정.
    
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

@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_role("HQ_ADMIN"))])
def delete_request(request_id: UUID, session: Session = Depends(get_session)):
    db_request = session.get(ServiceRequest, request_id)
    if not db_request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    # 관련 미디어 파일이 있다면 함께 삭제 로직을 넣을 수 있으나, 
    # 여기서는 간단히 DB 레코드만 삭제합니다.
    session.delete(db_request)
    session.commit()
    return None
