from pydantic import BaseModel, Field, model_validator
from typing import Optional, List
from uuid import UUID
from datetime import datetime

class RequestCreate(BaseModel):
    restaurant_id: UUID = Field(..., description="고장 접수를 신청하는 식당의 고유 ID (UUID)")
    category: str = Field(..., description="고장 유형 (예: 세척 불량, 전원 안 켜짐, 누수 등)", examples=["수압 저하"])
    description: Optional[str] = Field(None, description="구체적인 고장 증상 및 현장 상황 설명", examples=["세척기 내부 노즐에서 물이 약하게 나옵니다."])
    metadata: Optional[dict] = Field(default_factory=dict, description="기타 추가 정보 (모델명, 우선순위 등 자유로운 JSON 형식)", examples=[{"priority": "high", "model": "Washer-X1"}])

class RequestUpdate(BaseModel):
    assigned_branch_id: Optional[UUID] = None
    status: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[dict] = None

class MediaRead(BaseModel):
    id: UUID
    type: str
    file_url: str
    created_at: datetime
    class Config:
        from_attributes = True

class RequestRead(BaseModel):
    id: UUID
    restaurant_id: UUID
    assigned_branch_id: Optional[UUID]
    category: str
    description: Optional[str]
    status: str
    metadata: Optional[dict] = Field(None, validation_alias="metadata_json", serialization_alias="metadata")
    created_at: datetime
    assigned_at: Optional[datetime]
    completed_at: Optional[datetime]
    # 프론트엔드 편의를 위한 지점명 추가
    restaurant_name: Optional[str] = None
    branch_name: Optional[str] = None
    media: List[MediaRead] = []

    @model_validator(mode="after")
    def populate_names(self) -> "RequestRead":
        # relationship 객체가 로드되어 있는 경우 이름을 복사
        # self.restaurant, self.branch 필드가 스키마에 없으므로 context나 속성 확인 필요
        return self

    # SQLModel 모델에서 데이터를 변환할 때 이름을 직접 주입하기 위한 helper
    @classmethod
    def from_db(cls, obj):
        data = cls.model_validate(obj)
        if hasattr(obj, "restaurant") and obj.restaurant:
            data.restaurant_name = obj.restaurant.name
        if hasattr(obj, "branch") and obj.branch:
            data.branch_name = obj.branch.name
        return data

    class Config:
        from_attributes = True
        populate_by_name = True

class BranchCreate(BaseModel):
    name: str
    region_code: str
    address: Optional[str] = None
    manager_phone: Optional[str] = None
    commission_rate: float = 0.0

class BranchUpdate(BaseModel):
    name: Optional[str] = None
    region_code: Optional[str] = None
    address: Optional[str] = None
    manager_phone: Optional[str] = None
    commission_rate: Optional[float] = None
    is_approved: Optional[bool] = None

class BranchRead(BaseModel):
    id: UUID
    name: str
    region_code: str
    address: Optional[str] = None
    manager_phone: Optional[str]
    commission_rate: float
    is_approved: bool
    created_at: datetime

    class Config:
        from_attributes = True

class RestaurantCreate(BaseModel):
    name: str
    owner_name: Optional[str] = None
    phone: str
    address: str
    region: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class RestaurantUpdate(BaseModel):
    name: Optional[str] = None
    owner_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    region: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_approved: Optional[bool] = None

class RestaurantRead(BaseModel):
    id: UUID
    name: str
    owner_name: Optional[str]
    phone: str
    address: str
    region: Optional[str] = None
    latitude: Optional[float]
    longitude: Optional[float]
    is_approved: bool
    created_at: datetime
    # 식당 조회 시 해당 식당의 과거 요청 목록을 포함할 수 있도록 함
    requests: List["RequestRead"] = []

    class Config:
        from_attributes = True

class PaymentVerify(BaseModel):
    imp_uid: str
    merchant_uid: str
    request_id: UUID

class PaymentRead(BaseModel):
    id: UUID
    request_id: UUID
    merchant_uid: str
    amount: float
    status: str
    paid_at: datetime

    class Config:
        from_attributes = True

class DeviceTokenCreate(BaseModel):
    token: str
    platform: str
    user_id: Optional[UUID] = None
    user_type: Optional[str] = "MANAGER" # MANAGER, RESTAURANT

class DeviceTokenRead(BaseModel):
    id: UUID
    token: str
    platform: str
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True
