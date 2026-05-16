from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlmodel import Session, select
from typing import List
from uuid import UUID
from datetime import datetime

from app.db.session import get_session
from app.models.domain import Restaurant, AuditLog, ServiceRequest
from app.schemas.domain import RestaurantCreate, RestaurantUpdate, RestaurantRead
from app.api.deps import (
    require_role,
    get_current_user,
    assert_self_or_hq,
    assert_no_hq_only_fields,
    HQ_ONLY_RESTAURANT_FIELDS,
)

router = APIRouter()

@router.post("/", response_model=RestaurantRead, status_code=status.HTTP_201_CREATED)
def create_restaurant(data: RestaurantCreate, session: Session = Depends(get_session)):
    # 1. 필수 항목 기재 여부 확인
    if not data.phone or not data.address or not data.name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이름, 핸드폰 번호, 상세 주소는 필수 입력 사항입니다."
        )

    # 2. 플랫폼 전체 중복 체크 (이름, 번호, 주소)
    from app.models.domain import Branch
    
    # 이름 중복 체크 (지사/식당 통합)
    dup_name_r = session.exec(select(Restaurant).where(Restaurant.name == data.name)).first()
    dup_name_b = session.exec(select(Branch).where(Branch.name == data.name)).first()
    if dup_name_r or dup_name_b:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{data.name}'은(는) 이미 등록된 이름입니다.")

    # 번호 중복 체크 (지사/식당 통합)
    dup_phone_r = session.exec(select(Restaurant).where(Restaurant.phone == data.phone)).first()
    dup_phone_b = session.exec(select(Branch).where(Branch.manager_phone == data.phone)).first()
    if dup_phone_r or dup_phone_b:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 시스템에 등록된 핸드폰 번호입니다.")

    # 주소 중복 체크 (지사/식당 통합)
    dup_addr_r = session.exec(select(Restaurant).where(Restaurant.address == data.address)).first()
    dup_addr_b = session.exec(select(Branch).where(Branch.address == data.address)).first()
    if dup_addr_r or dup_addr_b:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 등록된 상세 주소입니다. (중복 가입 방지)")

    new_restaurant = Restaurant(**data.model_dump())
    session.add(new_restaurant)
    session.commit()
    session.refresh(new_restaurant)
    
    # 감사 로그
    log = AuditLog(
        table_name="restaurants",
        target_id=new_restaurant.id,
        action="INSERT",
        payload=jsonable_encoder(data),
        changed_by="system_admin"
    )
    session.add(log)
    session.commit()
    
    return new_restaurant

@router.get("/", response_model=List[RestaurantRead])
def list_restaurants(session: Session = Depends(get_session)):
    return session.exec(select(Restaurant)).all()

@router.get("/{restaurant_id}", response_model=RestaurantRead)
def get_restaurant(restaurant_id: UUID, session: Session = Depends(get_session)):
    restaurant = session.get(Restaurant, restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return restaurant

@router.patch("/{restaurant_id}", response_model=RestaurantRead)
def update_restaurant(
    restaurant_id: UUID,
    data: RestaurantUpdate,
    session: Session = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    restaurant = session.get(Restaurant, restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    # 소유권 검증 (plan_phase3.2 §7) — 본인 식당만, HQ는 전체 허용
    assert_self_or_hq(user, restaurant_id)

    old_data = restaurant.model_dump()
    update_data = data.model_dump(exclude_unset=True)
    # 본사 전용 필드(승인)는 식당이 직접 못 바꾼다
    assert_no_hq_only_fields(user, update_data, HQ_ONLY_RESTAURANT_FIELDS)
    for key, value in update_data.items():
        setattr(restaurant, key, value)
    
    restaurant.updated_at = datetime.utcnow()
    session.add(restaurant)
    
    # 감사 로그
    log = AuditLog(
        table_name="restaurants",
        target_id=restaurant.id,
        action="UPDATE",
        payload=jsonable_encoder({"before": old_data, "after": restaurant.model_dump()}),
        changed_by=f"{user.get('role')}:{user.get('sub')}"
    )
    session.add(log)
    
    session.commit()
    session.refresh(restaurant)
    return restaurant

@router.delete("/{restaurant_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_role("HQ_ADMIN"))])
def delete_restaurant(restaurant_id: UUID, session: Session = Depends(get_session)):
    restaurant = session.get(Restaurant, restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    # 연관된 수리 요청이 있는지 확인
    linked_requests = session.exec(select(ServiceRequest).where(ServiceRequest.restaurant_id == restaurant_id)).first()
    if linked_requests:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="이 식당의 수리 요청 내역이 존재하여 삭제할 수 없습니다. 먼저 내역을 정리해 주세요."
        )

    # 감사 로그
    log = AuditLog(
        table_name="restaurants",
        target_id=restaurant.id,
        action="DELETE",
        payload=jsonable_encoder(restaurant),
        changed_by="system_admin"
    )
    session.add(log)
    
    session.delete(restaurant)
    session.commit()
    return None
