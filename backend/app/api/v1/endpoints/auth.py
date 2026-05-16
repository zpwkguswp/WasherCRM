"""인증 엔드포인트.

- 본사(HQ): id/비밀번호 로그인 (Phase 3.2a). 임시 계정은 환경변수
  HQ_ADMIN_ID / HQ_ADMIN_PASSWORD (기본값 admin / 0000).
- 식당·지사: 전화번호 + 4자리 PIN 임시 로그인 (Phase 3.2b-임시, plan_phase3.2 §7).
  PIN 기본값은 전원 "0000"이며 본인이 변경할 수 있다. 정식 PASS 휴대폰
  본인인증은 포트원 가입 후 §7.7 절차로 교체한다.
"""
import secrets
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import create_access_token, hash_pin, verify_pin
from app.db.session import get_session
from app.models.domain import Branch, Restaurant

router = APIRouter()

# PIN 무차별 대입 방어 (plan_phase3.2 §7.8)
_MAX_FAILED_LOGIN = 5
_LOCKOUT_MINUTES = 10


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    """본사 계정 로그인. 성공 시 HQ_ADMIN 역할의 JWT를 발급한다."""
    id_ok = secrets.compare_digest(body.username, settings.HQ_ADMIN_ID)
    pw_ok = secrets.compare_digest(body.password, settings.HQ_ADMIN_PASSWORD)
    if not (id_ok and pw_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )
    token = create_access_token(subject=body.username, role="HQ_ADMIN")
    return TokenResponse(access_token=token, role="HQ_ADMIN")


# --- 식당·지사 임시 로그인 (plan_phase3.2 §7) ---


class StaffLoginRequest(BaseModel):
    phone: str
    pin: str
    user_type: str  # BRANCH | RESTAURANT


class PinChangeRequest(BaseModel):
    new_pin: str


@router.post("/login/pin", response_model=TokenResponse)
def login_staff(body: StaffLoginRequest, session: Session = Depends(get_session)):
    """식당·지사 임시 로그인 — 전화번호 + 4자리 PIN.

    PIN 기본값은 "0000"(pin_hash IS NULL). 5회 연속 실패 시 10분 잠금.
    """
    user_type = body.user_type.upper()
    if user_type == "BRANCH":
        entity = session.exec(
            select(Branch).where(Branch.manager_phone == body.phone)
        ).first()
        role = "BRANCH"
    elif user_type == "RESTAURANT":
        entity = session.exec(
            select(Restaurant).where(Restaurant.phone == body.phone)
        ).first()
        role = "RESTAURANT"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_type은 BRANCH 또는 RESTAURANT여야 합니다.",
        )

    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="등록된 전화번호가 아닙니다.",
        )

    now = datetime.utcnow()

    # 잠금 상태 확인
    if entity.lockout_until and entity.lockout_until > now:
        remain = int((entity.lockout_until - now).total_seconds() // 60) + 1
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"로그인 시도가 많아 잠겼습니다. 약 {remain}분 후 다시 시도해 주세요.",
        )

    # PIN 검증
    if not verify_pin(body.pin, entity.pin_hash):
        entity.failed_login_count = (entity.failed_login_count or 0) + 1
        if entity.failed_login_count >= _MAX_FAILED_LOGIN:
            entity.lockout_until = now + timedelta(minutes=_LOCKOUT_MINUTES)
            entity.failed_login_count = 0
            session.add(entity)
            session.commit()
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"비밀번호를 {_MAX_FAILED_LOGIN}회 틀려 {_LOCKOUT_MINUTES}분간 잠겼습니다.",
            )
        session.add(entity)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="PIN이 올바르지 않습니다.",
        )

    # 성공 — 실패 카운터·잠금 해제
    entity.failed_login_count = 0
    entity.lockout_until = None
    session.add(entity)
    session.commit()

    token = create_access_token(subject=str(entity.id), role=role)
    return TokenResponse(access_token=token, role=role)


@router.post("/pin")
def change_pin(
    body: PinChangeRequest,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """본인 PIN을 4자리로 변경한다. 식당·지사 계정만 가능."""
    role = user.get("role")
    if role not in ("BRANCH", "RESTAURANT"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="식당·지사 계정만 PIN을 변경할 수 있습니다.",
        )

    pin = body.new_pin
    if not (pin.isdigit() and len(pin) == 4):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PIN은 숫자 4자리여야 합니다.",
        )

    model = Branch if role == "BRANCH" else Restaurant
    entity = session.get(model, UUID(user["sub"]))
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="계정을 찾을 수 없습니다.",
        )

    entity.pin_hash = hash_pin(pin)
    session.add(entity)
    session.commit()
    return {"status": "success", "message": "PIN이 변경되었습니다."}
