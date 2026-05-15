from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select, desc
from typing import List, Optional
from uuid import UUID

from app.db.session import get_session
from app.models.domain import AuditLog
from app.api.deps import require_role

router = APIRouter()

@router.get("/", dependencies=[Depends(require_role("HQ_ADMIN"))])
def list_audit_logs(
    table_name: Optional[str] = None,
    target_id: Optional[UUID] = None,
    limit: int = Query(default=100, le=500),
    session: Session = Depends(get_session)
):
    """
    시스템의 모든 변경 이력(로그)을 조회합니다.
    최신순으로 정렬되어 반환됩니다.
    """
    statement = select(AuditLog).order_by(desc(AuditLog.created_at))
    
    if table_name:
        statement = statement.where(AuditLog.table_name == table_name)
    if target_id:
        statement = statement.where(AuditLog.target_id == target_id)
        
    statement = statement.limit(limit)
    
    results = session.exec(statement).all()
    return results
