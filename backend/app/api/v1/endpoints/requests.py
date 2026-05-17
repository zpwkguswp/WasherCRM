from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Body
from fastapi.encoders import jsonable_encoder
from sqlmodel import Session, select
from sqlalchemy import update as sa_update, or_, String, func
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta
import shutil
import os

from app.db.session import get_session
from app.models.domain import (
    ServiceRequest, AuditLog, RequestMedia, DeviceToken, Branch, Restaurant,
    Payment, Settlement, DispatchEvent,
)
from app.schemas.domain import RequestCreate, RequestUpdate, RequestRead
from app.utils.notifications import send_push_notification
from app.services.storage import storage
from app.api.deps import require_role, get_current_user, assert_request_access

router = APIRouter()

# 배차 (plan_phase3.7) — 수락 대기 상태 / 타임아웃 / 재배포 한계
DISPATCH_OPEN_STATES = ("OPEN", "REASSIGNING", "ESCALATED")  # 지사가 수락 가능한 상태
DISPATCH_TIMEOUT_MINUTES = 60   # 수락 대기 타임아웃 (대표 확정 2026-05-16)
DISPATCH_REBROADCAST_LIMIT = 2  # 재배포 한계 — 3번째 취소부터 ESCALATED


def _hq_device_tokens(session: Session) -> List[str]:
    """본사(HQ) 알림용 FCM 토큰 목록. HQ 토큰이 없으면 빈 리스트(무해)."""
    try:
        rows = session.exec(
            select(DeviceToken.token).where(
                DeviceToken.user_type.in_(("HQ", "HQ_ADMIN")),
                DeviceToken.is_active == True,
            )
        ).all()
        return list(rows)
    except Exception as e:
        print(f"HQ token lookup error: {e}")
        return []


def _notify_hq(session: Session, title: str, body: str, request_id: UUID):
    """본사에 FCM 알림 — 베스트에포트(실패해도 배차 흐름은 진행)."""
    try:
        tokens = _hq_device_tokens(session)
        if tokens:
            send_push_notification(
                tokens=tokens,
                title=title,
                body=body,
                data={"request_id": str(request_id)},
            )
    except Exception as e:
        print(f"HQ notification error: {e}")


def _find_candidate_branches(session: Session, restaurant: Restaurant) -> List[Branch]:
    """후보 지사 선정 — create_request의 지역 매칭 로직 재사용.

    식당 region이 지사 region_code와 일치하거나, 식당 address에 region_code가
    포함된 지사를 후보로 반환한다.
    """
    branches = session.exec(select(Branch)).all()
    candidates: List[Branch] = []
    for b in branches:
        rc = b.region_code
        if not rc:
            continue
        if rc == restaurant.region or (restaurant.address and rc in restaurant.address):
            candidates.append(b)
    return candidates


def _broadcast_to_candidates(session: Session, request: ServiceRequest, round_no: int = 1) -> int:
    """공용 배차 함수 — 후보 지사 선정 + FCM 푸시 + 마감시각 세팅 + BROADCAST 이벤트.

    앱 접수(create_request)와 재배포(release/rebroadcast)가 공유한다.
    반환값: 후보 지사 수. 호출자는 0이면 ESCALATED 처리를 해야 한다.
    """
    restaurant = session.get(Restaurant, request.restaurant_id)
    candidates = _find_candidate_branches(session, restaurant) if restaurant else []

    # 한 번이라도 이 요청을 취소(RELEASE)한 지사는 후보에서 제외 — 같은 건이 다시 가지 않게.
    released_branch_ids = set(session.exec(
        select(DispatchEvent.branch_id)
        .where(DispatchEvent.request_id == request.id)
        .where(DispatchEvent.event_type == "RELEASE")
    ).all())
    candidates = [b for b in candidates if b.id not in released_branch_ids]

    # 후보 지사 매니저 토큰 조회 후 FCM 푸시
    if candidates:
        branch_ids = [b.id for b in candidates]
        try:
            token_rows = session.exec(
                select(DeviceToken.token).where(
                    DeviceToken.user_id.in_(branch_ids),
                    DeviceToken.user_type == "MANAGER",
                    DeviceToken.is_active == True,
                )
            ).all()
            tokens = list(token_rows)
            if tokens:
                body = "재배정 요청 — 이전 담당 지사가 처리를 취소했습니다." if round_no > 1 \
                    else f"[{request.category}] 새로운 수리 요청이 등록되었습니다."
                send_push_notification(
                    tokens=tokens,
                    title="신규 수리 요청 접수" if round_no == 1 else "수리 요청 재배정",
                    body=body,
                    data={"request_id": str(request.id), "round_no": str(round_no)},
                )
        except Exception as e:
            print(f"Broadcast push error: {e}")

    # 수락 대기 타임아웃 만료 시각 세팅
    request.dispatch_deadline = datetime.utcnow() + timedelta(minutes=DISPATCH_TIMEOUT_MINUTES)

    # 배차 이벤트 기록 (BROADCAST는 주체 지사가 없으므로 branch_id=NULL)
    session.add(DispatchEvent(
        request_id=request.id,
        branch_id=None,
        event_type="BROADCAST",
        round_no=round_no,
    ))
    return len(candidates)


def _dispatch_audit(session: Session, request_id: UUID, action: str, payload: dict, changed_by: str):
    """배차 동작에 대한 AuditLog 1행 기록."""
    session.add(AuditLog(
        table_name="service_requests",
        target_id=request_id,
        action=action,
        payload=jsonable_encoder(payload),
        changed_by=changed_by,
    ))

@router.post("/", response_model=RequestRead, status_code=status.HTTP_201_CREATED)
def create_request(data: RequestCreate, session: Session = Depends(get_session)):
    # 1. 요청 생성 (notified_at = 지사 브로드캐스트 시각, SLA 시작점)
    # RequestCreate.metadata → ServiceRequest.metadata_json 으로 명시 매핑.
    # (model_dump() 전개 시 필드명이 달라 metadata가 유실되던 버그 수정)
    new_request = ServiceRequest(
        restaurant_id=data.restaurant_id,
        category=data.category,
        description=data.description,
        metadata_json=data.metadata or {},
    )
    new_request.notified_at = datetime.utcnow()
    new_request.dispatch_status = "OPEN"  # 배차 시작 (plan_phase3.7 §3.1)
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

    # 3. 배차 — 후보 지사에게 푸시 + dispatch_deadline 세팅 + BROADCAST 이벤트
    candidate_count = _broadcast_to_candidates(session, new_request, round_no=1)
    if candidate_count == 0:
        # 후보 0곳 — OPEN에 방치하지 않고 즉시 ESCALATED + 본사 알림 (plan_phase3.7 §3.1)
        new_request.dispatch_status = "ESCALATED"
        session.add(DispatchEvent(
            request_id=new_request.id,
            branch_id=None,
            event_type="ESCALATE",
            reason="NO_CANDIDATE",
            round_no=1,
        ))
        _dispatch_audit(
            session, new_request.id, "DISPATCH",
            {"event": "ESCALATE", "reason": "NO_CANDIDATE", "dispatch_status": "ESCALATED"},
            "system_user",
        )
        session.add(new_request)
        session.commit()
        session.refresh(new_request)
        _notify_hq(
            session,
            title="배차 불가 — 본사 확인 필요",
            body=f"[{new_request.category}] 매칭되는 후보 지사가 없어 본사 배정이 필요합니다.",
            request_id=new_request.id,
        )
    else:
        session.add(new_request)
        session.commit()
        session.refresh(new_request)

    return new_request

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
        # 이 지사가 한 번이라도 취소(RELEASE)한 요청은 목록에서 제외 — 다시 보이지 않게.
        released_ids = list(session.exec(
            select(DispatchEvent.request_id)
            .where(DispatchEvent.branch_id == assigned_branch_id)
            .where(DispatchEvent.event_type == "RELEASE")
        ).all())
        if released_ids:
            statement = statement.where(ServiceRequest.id.not_in(released_ids))
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

@router.get("/{request_id}/dispatch-events", dependencies=[Depends(require_role("HQ_ADMIN"))])
def get_dispatch_events(request_id: UUID, session: Session = Depends(get_session)):
    """본사용: 한 요청의 배차 이벤트 타임라인 (plan_phase3.7.1).

    접수(BROADCAST)→수락(CLAIM)→취소(RELEASE+사유)→재배포→본사확인(ESCALATE) 등을
    시간순으로 반환한다. 지사 이름은 branch_id로 매핑해 함께 내려준다.
    """
    events = session.exec(
        select(DispatchEvent)
        .where(DispatchEvent.request_id == request_id)
        .order_by(DispatchEvent.created_at)
    ).all()
    branch_ids = {e.branch_id for e in events if e.branch_id}
    names = {}
    if branch_ids:
        for b in session.exec(select(Branch).where(Branch.id.in_(branch_ids))).all():
            names[b.id] = b.name
    return [
        {
            "event_type": e.event_type,
            "reason": e.reason,
            "branch_id": str(e.branch_id) if e.branch_id else None,
            "branch_name": names.get(e.branch_id),
            "round_no": e.round_no,
            "created_at": e.created_at,
        }
        for e in events
    ]

@router.get("/{request_id}", response_model=RequestRead)
def get_request(request_id: UUID, session: Session = Depends(get_session)):
    db_request = session.get(ServiceRequest, request_id)
    if not db_request:
        raise HTTPException(status_code=404, detail="Request not found")
    return db_request

@router.patch("/{request_id}", response_model=RequestRead)
def update_request(
    request_id: UUID,
    data: RequestUpdate,
    session: Session = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    db_request = session.get(ServiceRequest, request_id)
    if not db_request:
        raise HTTPException(status_code=404, detail="Request not found")

    # 소유권 검증 (plan_phase3.2 §7) — 본인 요청만, HQ는 전체 허용
    assert_request_access(user, db_request)

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

    # 배정 — assigned_branch_id가 처음 None→값으로 채워질 때만 dispatch_status 갱신.
    # 본사가 배정하면 HQ_ASSIGNED, 지사가 스스로 배정(수락)하면 CLAIMED.
    # (was_unassigned 조건으로, 이미 배정된 건의 단순 status 수정 PATCH에서
    #  dispatch_status가 잘못 덮어써지는 것을 막는다.)
    if (
        was_unassigned
        and "assigned_branch_id" in update_data
        and db_request.assigned_branch_id is not None
    ):
        is_hq = user.get("role") == "HQ_ADMIN"
        db_request.dispatch_status = "HQ_ASSIGNED" if is_hq else "CLAIMED"
        event_type = "HQ_ASSIGN" if is_hq else "CLAIM"
        session.add(DispatchEvent(
            request_id=db_request.id,
            branch_id=db_request.assigned_branch_id,
            event_type=event_type,
            round_no=1,
        ))
        _dispatch_audit(
            session, db_request.id, "DISPATCH",
            {"event": event_type, "assigned_branch_id": str(db_request.assigned_branch_id),
             "dispatch_status": db_request.dispatch_status},
            f"{user.get('role')}:{user.get('sub')}",
        )

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
        changed_by=f"{user.get('role')}:{user.get('sub')}"
    )
    session.add(log)
    
    session.commit()
    session.refresh(db_request)
    return db_request

# ============================================================
# 배차 엔드포인트 (plan_phase3.7)
# ============================================================

@router.post("/{request_id}/claim", response_model=RequestRead)
def claim_request(
    request_id: UUID,
    session: Session = Depends(get_session),
    user: dict = Depends(require_role("BRANCH")),
):
    """지사 수락 (선착순) — plan_phase3.7 §5.1 조건부 원자적 UPDATE.

    수락 지사는 토큰의 sub(branch id)에서 가져온다. body로 branch_id를 받지
    않는다(사칭 방지). 동시 수락 경합은 단일 UPDATE 문의 WHERE 절이 막는다.
    """
    branch_id = UUID(user.get("sub"))
    now = datetime.utcnow()

    db_request = session.get(ServiceRequest, request_id)
    if not db_request:
        raise HTTPException(status_code=404, detail="Request not found")

    # 핵심: 조건부 원자적 UPDATE — "비어 있을 때만 채운다"를 단일 SQL 문으로.
    # PostgreSQL이 행 잠금으로 동시 수락 중 한 쪽만 조건을 만족시킨다.
    stmt = (
        sa_update(ServiceRequest)
        .where(
            ServiceRequest.id == request_id,
            ServiceRequest.assigned_branch_id.is_(None),
            ServiceRequest.dispatch_status.in_(DISPATCH_OPEN_STATES),
        )
        .values(
            assigned_branch_id=branch_id,
            dispatch_status="CLAIMED",
            # accepted_at 최초값 유지 (plan_phase3.5 / §5.3)
            accepted_at=func.coalesce(ServiceRequest.accepted_at, now),
            updated_at=now,
        )
    )
    result = session.exec(stmt)

    if result.rowcount == 1:
        # 수락 성공
        session.add(DispatchEvent(
            request_id=request_id,
            branch_id=branch_id,
            event_type="CLAIM",
            round_no=1,
        ))
        _dispatch_audit(
            session, request_id, "DISPATCH",
            {"event": "CLAIM", "branch_id": str(branch_id), "dispatch_status": "CLAIMED"},
            f"BRANCH:{branch_id}",
        )
        session.commit()
        session.refresh(db_request)
        return db_request

    # rowcount == 0 — 이미 다른 지사가 잡았거나 수락 대기 상태가 아님
    session.add(DispatchEvent(
        request_id=request_id,
        branch_id=branch_id,
        event_type="CLAIM_REJECTED",
        round_no=1,
    ))
    _dispatch_audit(
        session, request_id, "DISPATCH",
        {"event": "CLAIM_REJECTED", "branch_id": str(branch_id)},
        f"BRANCH:{branch_id}",
    )
    session.commit()
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="이미 다른 지사가 수락했거나 수락할 수 없는 요청입니다.",
    )


@router.post("/{request_id}/release", response_model=RequestRead)
def release_request(
    request_id: UUID,
    reason: str = Body(..., embed=True),
    session: Session = Depends(get_session),
    user: dict = Depends(require_role("BRANCH")),
):
    """담당 지사 취소 — plan_phase3.7 §3.4.

    취소 지사는 토큰 sub에서 가져온다. 현재 담당 지사가 아니면 403.
    reason은 버튼 선택형 문자열("일정 불가"/"지역 밖"/"인력 부족"/"기타").
    cancel_count > 2(3번째 취소부터)면 재배포하지 않고 ESCALATED.
    """
    branch_id = UUID(user.get("sub"))

    db_request = session.get(ServiceRequest, request_id)
    if not db_request:
        raise HTTPException(status_code=404, detail="Request not found")

    # 현재 담당 지사만 취소 가능
    if db_request.assigned_branch_id is None or db_request.assigned_branch_id != branch_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="현재 담당 지사만 취소할 수 있습니다.",
        )

    # 담당 해제 — assigned_branch_id NULL, cancel_count +1. accepted_at은 유지(§5.3)
    db_request.assigned_branch_id = None
    db_request.cancel_count = (db_request.cancel_count or 0) + 1
    db_request.updated_at = datetime.utcnow()

    # 취소 이벤트 기록
    session.add(DispatchEvent(
        request_id=request_id,
        branch_id=branch_id,
        event_type="RELEASE",
        reason=reason,
        round_no=db_request.cancel_count,
    ))

    if db_request.cancel_count > DISPATCH_REBROADCAST_LIMIT:
        # 재배포 한계 초과(3번째 취소부터) — 재배포하지 않고 ESCALATED
        db_request.dispatch_status = "ESCALATED"
        session.add(DispatchEvent(
            request_id=request_id,
            branch_id=None,
            event_type="ESCALATE",
            reason="REBROADCAST_LIMIT",
            round_no=db_request.cancel_count,
        ))
        _dispatch_audit(
            session, request_id, "DISPATCH",
            {"event": "RELEASE", "branch_id": str(branch_id), "reason": reason,
             "cancel_count": db_request.cancel_count, "dispatch_status": "ESCALATED"},
            f"BRANCH:{branch_id}",
        )
        session.add(db_request)
        session.commit()
        session.refresh(db_request)
        _notify_hq(
            session,
            title="반복 취소 — 본사 확인 필요",
            body=f"[{db_request.category}] 재배포 한계를 초과해 본사 배정이 필요합니다.",
            request_id=request_id,
        )
        return db_request

    # 재배포 — REASSIGNING 전이 후 후보 지사에 재푸시
    db_request.dispatch_status = "REASSIGNING"
    _broadcast_to_candidates(session, db_request, round_no=db_request.cancel_count + 1)
    _dispatch_audit(
        session, request_id, "DISPATCH",
        {"event": "RELEASE", "branch_id": str(branch_id), "reason": reason,
         "cancel_count": db_request.cancel_count, "dispatch_status": "REASSIGNING"},
        f"BRANCH:{branch_id}",
    )
    session.add(db_request)
    session.commit()
    session.refresh(db_request)
    return db_request


@router.post("/dispatch/sweep", dependencies=[Depends(require_role("HQ_ADMIN"))])
def sweep_dispatch_timeouts(session: Session = Depends(get_session)):
    """타임아웃 점검 — plan_phase3.7 §3.5 방식 A.

    수락 대기(OPEN/REASSIGNING) 중 dispatch_deadline이 지난 요청을
    ESCALATED로 승격하고 본사에 알린다. 승격 건수를 반환한다.
    """
    now = datetime.utcnow()
    expired = session.exec(
        select(ServiceRequest).where(
            ServiceRequest.dispatch_status.in_(("OPEN", "REASSIGNING")),
            ServiceRequest.dispatch_deadline.is_not(None),
            ServiceRequest.dispatch_deadline < now,
        )
    ).all()

    for req in expired:
        req.dispatch_status = "ESCALATED"
        req.updated_at = now
        session.add(req)
        session.add(DispatchEvent(
            request_id=req.id,
            branch_id=None,
            event_type="TIMEOUT",
            reason="DEADLINE_EXCEEDED",
            round_no=(req.cancel_count or 0) + 1,
        ))
        _dispatch_audit(
            session, req.id, "DISPATCH",
            {"event": "TIMEOUT", "dispatch_status": "ESCALATED"},
            "system_sweep",
        )

    session.commit()

    for req in expired:
        _notify_hq(
            session,
            title="배차 타임아웃 — 본사 확인 필요",
            body=f"[{req.category}] 수락 대기 시간이 초과되어 본사 배정이 필요합니다.",
            request_id=req.id,
        )

    return {"escalated_count": len(expired)}


@router.post("/{request_id}/rebroadcast", response_model=RequestRead)
def rebroadcast_request(
    request_id: UUID,
    session: Session = Depends(get_session),
    user: dict = Depends(require_role("HQ_ADMIN")),
):
    """본사 재배포 — plan_phase3.7 §3.5.

    ESCALATED 건을 OPEN으로 되돌리고 후보 지사에 다시 푸시한다.
    round_no는 직전 BROADCAST 라운드 +1.
    """
    db_request = session.get(ServiceRequest, request_id)
    if not db_request:
        raise HTTPException(status_code=404, detail="Request not found")

    if db_request.dispatch_status != "ESCALATED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ESCALATED 상태의 요청만 재배포할 수 있습니다.",
        )

    # 직전 최대 round_no 조회 후 +1
    last_round = session.exec(
        select(func.max(DispatchEvent.round_no)).where(
            DispatchEvent.request_id == request_id
        )
    ).one()
    next_round = (last_round or 1) + 1

    db_request.dispatch_status = "OPEN"
    db_request.updated_at = datetime.utcnow()
    candidate_count = _broadcast_to_candidates(session, db_request, round_no=next_round)

    session.add(DispatchEvent(
        request_id=request_id,
        branch_id=None,
        event_type="REBROADCAST",
        round_no=next_round,
    ))

    if candidate_count == 0:
        # 여전히 후보 0곳 — 다시 ESCALATED로 되돌리고 본사 알림
        db_request.dispatch_status = "ESCALATED"
        session.add(DispatchEvent(
            request_id=request_id,
            branch_id=None,
            event_type="ESCALATE",
            reason="NO_CANDIDATE",
            round_no=next_round,
        ))

    _dispatch_audit(
        session, request_id, "DISPATCH",
        {"event": "REBROADCAST", "round_no": next_round,
         "candidate_count": candidate_count, "dispatch_status": db_request.dispatch_status},
        f"{user.get('role')}:{user.get('sub')}",
    )
    session.add(db_request)
    session.commit()
    session.refresh(db_request)

    if candidate_count == 0:
        _notify_hq(
            session,
            title="재배포 실패 — 후보 지사 없음",
            body=f"[{db_request.category}] 재배포했으나 매칭 지사가 없습니다.",
            request_id=request_id,
        )

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
