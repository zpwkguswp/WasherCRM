from fastapi import APIRouter, Depends, status
from sqlmodel import Session, select
from typing import List
from app.db.session import get_session
from app.models.domain import DeviceToken
from app.schemas.domain import DeviceTokenCreate, DeviceTokenRead

router = APIRouter()

@router.post("/register", response_model=DeviceTokenRead)
def register_device(data: DeviceTokenCreate, session: Session = Depends(get_session)):
    # 1. 기존 동일 토큰이 있는지 확인
    statement = select(DeviceToken).where(DeviceToken.token == data.token)
    db_token = session.exec(statement).first()
    
    if db_token:
        # 이미 존재하면 정보 업데이트
        db_token.user_id = data.user_id
        db_token.user_type = data.user_type
        db_token.platform = data.platform
        db_token.is_active = True
    else:
        # 새로운 토큰 등록
        db_token = DeviceToken(**data.model_dump())
        session.add(db_token)
    
    session.commit()
    session.refresh(db_token)
    return db_token

@router.get("/tokens", response_model=List[DeviceTokenRead])
def list_tokens(session: Session = Depends(get_session)):
    return session.exec(select(DeviceToken)).all()
