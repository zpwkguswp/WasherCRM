"""인증·권한 FastAPI 의존성 (Phase 3.2a).

엔드포인트에 `Depends(require_role("HQ_ADMIN"))`를 붙이면 해당 역할의
유효한 JWT가 있어야만 접근할 수 있다.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_access_token

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    """Authorization: Bearer <token> 헤더를 검증하고 토큰 payload를 반환한다."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다.",
        )
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않거나 만료된 토큰입니다. 다시 로그인해 주세요.",
        )
    return payload


def require_role(*allowed_roles: str):
    """지정한 역할만 통과시키는 의존성을 만든다."""

    def checker(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="접근 권한이 없습니다.",
            )
        return user

    return checker
