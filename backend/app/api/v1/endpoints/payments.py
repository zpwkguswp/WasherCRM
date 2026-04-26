import httpx
from typing import List, Optional
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlmodel import Session, select, desc

from app.db.session import get_session
from app.models.domain import Payment, ServiceRequest, AuditLog
from app.schemas.domain import PaymentVerify, PaymentRead
from app.core.config import settings

router = APIRouter()

@router.get("/", response_model=List[PaymentRead])
def list_payments(
    status: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    session: Session = Depends(get_session)
):
    """
    결제 내역을 필터링하여 조회합니다.
    """
    statement = select(Payment).order_by(desc(Payment.paid_at))
    
    if status:
        statement = statement.where(Payment.status == status)
    if start_date:
        statement = statement.where(Payment.paid_at >= start_date)
    if end_date:
        statement = statement.where(Payment.paid_at <= end_date)
        
    return session.exec(statement).all()

async def get_portone_token():
    url = "https://api.iamport.kr/users/getToken"
    payload = {
        "imp_key": settings.PORTONE_API_KEY,
        "imp_secret": settings.PORTONE_API_SECRET
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        if response.status_code == 200:
            return response.json()["response"]["access_token"]
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get PortOne access token"
            )

@router.post("/verify", response_model=PaymentRead)
async def verify_payment(
    data: PaymentVerify, 
    session: Session = Depends(get_session)
):
    # 1. 포트원 토큰 가져오기
    token = await get_portone_token()
    
    # 2. 포트원에서 결제 정보 조회
    url = f"https://api.iamport.kr/payments/{data.imp_uid}"
    headers = {"Authorization": token}
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="PortOne payment not found")
        
        payment_data = response.json()["response"]
        
    # 3. 결제 금액 및 상태 검증
    if payment_data["status"] != "paid":
        raise HTTPException(status_code=400, detail="Payment not completed")
        
    # 4. DB에 결제 정보 저장
    new_payment = Payment(
        request_id=data.request_id,
        imp_uid=data.imp_uid,
        merchant_uid=data.merchant_uid,
        amount=payment_data["amount"],
        method=payment_data["pay_method"],
        status="PAID"
    )
    session.add(new_payment)
    
    # 5. 자동 정산 데이터 생성
    # 요청 건을 통해 배정된 지사 정보를 가져옵니다.
    service_request = session.get(ServiceRequest, data.request_id)
    if service_request and service_request.assigned_branch_id:
        from app.models.domain import Branch, Settlement
        branch = session.get(Branch, service_request.assigned_branch_id)
        
        amount = float(payment_data["amount"])
        commission_rate = branch.commission_rate if branch else 0.0
        
        hq_comm = amount * (commission_rate / 100.0)
        branch_amount = amount - hq_comm
        
        new_settlement = Settlement(
            branch_id=service_request.assigned_branch_id,
            request_id=data.request_id,
            total_amount=amount,
            hq_commission=hq_comm,
            branch_settlement_amount=branch_amount,
            status="PENDING"
        )
        session.add(new_settlement)

    # 감사 로그 기록
    log = AuditLog(
        table_name="payments",
        target_id=new_payment.id,
        action="INSERT",
        payload=jsonable_encoder(new_payment),
        changed_by="system"
    )
    session.add(log)
    
    session.commit()
    session.refresh(new_payment)
    
    return new_payment
