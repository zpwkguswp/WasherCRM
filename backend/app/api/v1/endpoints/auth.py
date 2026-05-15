"""인증 엔드포인트 (Phase 3.2a — 본사 로그인).

본사(HQ)는 id/비밀번호로 로그인한다. 임시 계정은 환경변수
HQ_ADMIN_ID / HQ_ADMIN_PASSWORD (기본값 admin / 0000)로 정의된다.
식당·지사 인증은 Phase 3.2b에서 휴대폰 본인인증(PASS)으로 별도 도입한다.
"""
import secrets

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.config import settings
from app.core.security import create_access_token

router = APIRouter()


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
