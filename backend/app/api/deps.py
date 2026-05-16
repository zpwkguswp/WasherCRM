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


# --- 소유권 검증 (plan_phase3.2 §7) ---
# 토큰의 sub(엔티티 id)와 리소스 소유자를 대조한다. HQ_ADMIN은 항상 통과한다.

# 본사만 변경할 수 있는 필드 — 지사·식당이 직접 못 바꾼다.
HQ_ONLY_BRANCH_FIELDS = {"is_approved", "commission_rate", "tier"}
HQ_ONLY_RESTAURANT_FIELDS = {"is_approved"}


def _is_hq(user: dict) -> bool:
    return user.get("role") == "HQ_ADMIN"


def assert_request_access(user: dict, request) -> None:
    """수리요청 수정 권한 검증.

    HQ는 전체, 지사는 자기 배정분·미배정분, 식당은 자기 요청만 수정할 수 있다.
    """
    if _is_hq(user):
        return
    role, sub = user.get("role"), user.get("sub")
    if role == "BRANCH" and (
        request.assigned_branch_id is None
        or str(request.assigned_branch_id) == sub
    ):
        return
    if role == "RESTAURANT" and str(request.restaurant_id) == sub:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="이 요청에 대한 수정 권한이 없습니다.",
    )


def assert_self_or_hq(user: dict, entity_id) -> None:
    """지사·식당이 자기 자신의 정보만 수정하도록 검증한다. HQ는 전체 통과."""
    if _is_hq(user):
        return
    if user.get("role") in ("BRANCH", "RESTAURANT") and str(entity_id) == user.get("sub"):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="본인 정보만 수정할 수 있습니다.",
    )


def assert_no_hq_only_fields(user: dict, update_data: dict, hq_fields: set) -> None:
    """HQ가 아닌 사용자가 본사 전용 필드를 변경하려 하면 거부한다."""
    if _is_hq(user):
        return
    bad = hq_fields & set(update_data.keys())
    if bad:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"본사만 변경할 수 있는 항목입니다: {', '.join(sorted(bad))}",
        )
