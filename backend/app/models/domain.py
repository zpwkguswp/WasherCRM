from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4
from sqlalchemy import Column, DateTime, String, Text, DECIMAL, Float, JSON
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
    
    requests: List["ServiceRequest"] = Relationship(back_populates="branch")

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
    settlements: List["Settlement"] = Relationship(back_populates="request")

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
    amount: float = Field(sa_column=Column(DECIMAL(12, 2)))
    method: Optional[str] = None
    status: str = Field(default="PAID")
    paid_at: datetime = Field(default_factory=datetime.utcnow)
    
    request: ServiceRequest = Relationship(back_populates="payments")

class Settlement(SQLModel, table=True):
    __tablename__ = "settlements"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    branch_id: UUID = Field(foreign_key="branches.id")
    request_id: UUID = Field(foreign_key="service_requests.id")
    total_amount: float = Field(sa_column=Column(DECIMAL(12, 2)))
    hq_commission: float = Field(sa_column=Column(DECIMAL(12, 2)))
    branch_settlement_amount: float = Field(sa_column=Column(DECIMAL(12, 2)))
    status: str = Field(default="PENDING")
    settled_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    request: ServiceRequest = Relationship(back_populates="settlements")

class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    table_name: str = Field(index=True)
    target_id: UUID = Field(index=True)
    action: str = Field(index=True) # INSERT, UPDATE, DELETE
    payload: Optional[dict] = Field(default_factory=dict, sa_column=Column(JSON))
    changed_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

class DeviceToken(SQLModel, table=True):
    __tablename__ = "device_tokens"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: Optional[UUID] = Field(default=None, index=True) # 지사 ID 또는 식당 ID
    user_type: str = Field(default="MANAGER", index=True) # MANAGER, RESTAURANT
    token: str = Field(index=True, unique=True)
    platform: str # android, ios, web
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
