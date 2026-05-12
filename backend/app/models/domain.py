from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List
from uuid import UUID, uuid4
from sqlalchemy import Column, DateTime, Date, String, Text, DECIMAL, Float, JSON
from sqlmodel import SQLModel, Field, Relationship

class Branch(SQLModel, table=True):
    __tablename__ = "branches"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    region_code: str = Field(index=True)
    address: Optional[str] = None # 주소 필드 추가
    manager_phone: Optional[str] = None
    commission_rate: float = Field(default=0.0)
    is_approved: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    tier: str = Field(default="BRONZE") # BRONZE, SILVER, GOLD, DIAMOND
    settlement_cycle: str = Field(default="WEEKLY") # WEEKLY, BIWEEKLY, MONTHLY, CUSTOM

    requests: List["ServiceRequest"] = Relationship(back_populates="branch")
    settlements: List["Settlement"] = Relationship(back_populates="branch")

class Restaurant(SQLModel, table=True):
    __tablename__ = "restaurants"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    owner_name: Optional[str] = None
    phone: str = Field(index=True)
    address: str
    region: Optional[str] = None  # 지역 정보 추가
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_approved: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    requests: List["ServiceRequest"] = Relationship(back_populates="restaurant")

class ServiceRequest(SQLModel, table=True):
    __tablename__ = "service_requests"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    restaurant_id: UUID = Field(foreign_key="restaurants.id")
    assigned_branch_id: Optional[UUID] = Field(default=None, foreign_key="branches.id")
    category: str = Field(index=True)  # WATER_LEAK, POWER_ISSUE 등
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    status: str = Field(default="PENDING", index=True)
    metadata_json: Optional[dict] = Field(default_factory=dict, sa_column=Column("metadata", JSON))
    
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    assigned_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    branch: Optional[Branch] = Relationship(back_populates="requests")
    restaurant: Restaurant = Relationship(back_populates="requests")
    media: List["RequestMedia"] = Relationship(back_populates="request")
    payments: List["Payment"] = Relationship(back_populates="request")
    # NOTE: ServiceRequest → Settlement 직접 관계 제거 (§4.1 재설계)
    # 새 경로: ServiceRequest → Payment → SettlementItem → Settlement

class RequestMedia(SQLModel, table=True):
    __tablename__ = "request_media"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    request_id: UUID = Field(foreign_key="service_requests.id")
    type: str  # IMAGE, VIDEO
    file_url: str
    thumbnail_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    request: ServiceRequest = Relationship(back_populates="media")

class Payment(SQLModel, table=True):
    __tablename__ = "payments"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    request_id: UUID = Field(foreign_key="service_requests.id")
    imp_uid: Optional[str] = Field(default=None)
    merchant_uid: Optional[str] = Field(default=None)
    amount: Decimal = Field(sa_column=Column(DECIMAL(12, 2)))
    method: Optional[str] = None
    status: str = Field(default="PAID")
    paid_at: datetime = Field(default_factory=datetime.utcnow)
    
    request: ServiceRequest = Relationship(back_populates="payments")

class Settlement(SQLModel, table=True):
    """주기별 × 지사별 정산 헤더 (plan_phase4.1)

    period_start/period_end로 정의된 기간의 결제 집계.
    주기는 settlement_cycle 설정에 따라 결정되며, 과거 정산은 자기 기간을 그대로 유지.
    """
    __tablename__ = "settlements"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    branch_id: UUID = Field(foreign_key="branches.id", index=True)

    # 기간 정의 — 주기 무관
    period_start: date = Field(sa_column=Column(Date, index=True))  # 포함
    period_end: date = Field(sa_column=Column(Date, index=True))    # 포함
    period_type: str = Field(default="WEEKLY", index=True)  # WEEKLY|BIWEEKLY|MONTHLY|CUSTOM

    # 집계 금액 (VAT 포함 원화 기준)
    gross_amount: Decimal = Field(default=Decimal("0"), sa_column=Column(DECIMAL(14, 2)))
    vat_amount: Decimal = Field(default=Decimal("0"), sa_column=Column(DECIMAL(14, 2)))
    commission_rate: Decimal = Field(default=Decimal("0"), sa_column=Column(DECIMAL(5, 2)))
    hq_commission: Decimal = Field(default=Decimal("0"), sa_column=Column(DECIMAL(14, 2)))
    branch_amount: Decimal = Field(default=Decimal("0"), sa_column=Column(DECIMAL(14, 2)))
    refund_offset: Decimal = Field(default=Decimal("0"), sa_column=Column(DECIMAL(14, 2)))
    net_amount: Decimal = Field(default=Decimal("0"), sa_column=Column(DECIMAL(14, 2)))

    # 상태
    status: str = Fiel