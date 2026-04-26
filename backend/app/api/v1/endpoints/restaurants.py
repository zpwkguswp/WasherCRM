from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlmodel import Session, select
from typing import List
from uuid import UUID
from datetime import datetime

from app.db.session import get_session
from app.models.domain import Restaurant, AuditLog, ServiceRequest
from app.schemas.domain import RestaurantCreate, RestaurantUpdate, RestaurantRead

router = APIRouter()

@router.post("/", response_model=RestaurantRead, status_code=status.HTTP_201_CREATED)
def create_restaurant(data: RestaurantCreate, session: Session = Depends(get_session)):
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
def update_restaurant(restaurant_id: UUID, data: RestaurantUpdate, session: Session = Depends(get_session)):
    restaurant = session.get(Restaurant, restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    old_data = restaurant.model_dump()
    update_data = data.model_dump(exclude_unset=True)
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
        changed_by="system_admin"
    )
    session.add(log)
    
    session.commit()
    session.refresh(restaurant)
    return restaurant
