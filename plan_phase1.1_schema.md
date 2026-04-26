# 실행 계획서 1.1: DB 스키마 설계 (PostgreSQL)

**상태**: 🏗️ 진행 중  
**담당**: Antigravity  
**작업 내용**: 서비스 플랫폼의 근간이 되는 데이터베이스 스키마 정의 및 ORM 모델 작성

---

## 1. 설계 목표
- 식당의 A/S 요청 데이터를 정형(카테고리)/비정형(줄글, 미디어) 모두 효율적으로 수용.
- 지사별 SLA(대응 시간) 및 지역별 고장 빈도(Hotspot) 분석이 가능한 구조 구축.
- 결제 및 부품 사용 이력의 무결성 보장.

## 2. 데이터베이스 스키마 (DDL)

```sql
-- 확장 기능 활성화 (UUID 생성용)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. 지사 테이블
CREATE TABLE branches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    region_code VARCHAR(20) NOT NULL, -- 예: 'SEOUL_GANGNAM'
    manager_phone VARCHAR(20),
    commission_rate DECIMAL(5, 2) DEFAULT 0.00, -- 수수료율 (%)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. 식당(소비자) 테이블
CREATE TABLE restaurants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(200) NOT NULL,
    owner_name VARCHAR(100),
    phone VARCHAR(20) NOT NULL,
    address TEXT NOT NULL,
    latitude DOUBLE PRECISION, -- Hotspot 분석용
    longitude DOUBLE PRECISION, -- Hotspot 분석용
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. 서비스 요청(A/S) 테이블
CREATE TYPE request_status AS ENUM ('PENDING', 'ASSIGNED', 'VISITING', 'COMPLETED', 'CANCELLED');

CREATE TABLE service_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id),
    assigned_branch_id UUID REFERENCES branches(id),
    category VARCHAR(50) NOT NULL, -- 예: 'WATER_LEAK', 'POWER_ISSUE'
    description TEXT, -- 점주의 상세 설명 (줄글)
    status request_status DEFAULT 'PENDING',
    metadata JSONB, -- 기타 기기 정보 등 확장 데이터
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, -- 접수 시간
    assigned_at TIMESTAMP WITH TIME ZONE, -- 지사 배정 시간
    completed_at TIMESTAMP WITH TIME ZONE, -- 수리 완료 시간
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. 요청 미디어 테이블 (사진/동영상)
CREATE TYPE media_type AS ENUM ('IMAGE', 'VIDEO');

CREATE TABLE request_media (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID NOT NULL REFERENCES service_requests(id) ON DELETE CASCADE,
    type media_type NOT NULL,
    file_url TEXT NOT NULL,
    thumbnail_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. 결제 정보 테이블
CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID NOT NULL REFERENCES service_requests(id),
    amount DECIMAL(12, 2) NOT NULL,
    method VARCHAR(50), -- 'CARD', 'KAKAOPAY' 등
    pg_transaction_id VARCHAR(100),
    status VARCHAR(20), -- 'PAID', 'CANCELLED'
    paid_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

## 3. 백엔드 엔티티 클래스 (Python / SQLModel 예시)

```python
from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4
from sqlalchemy import Column, DateTime, String, Text, DECIMAL, Float
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB, ENUM
from sqlmodel import SQLModel, Field, Relationship

class Branch(SQLModel, table=True):
    __tablename__ = "branches"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    region_code: str
    manager_phone: Optional[str] = None
    commission_rate: float = Field(default=0.0)
    
    requests: List["ServiceRequest"] = Relationship(back_populates="branch")

class Restaurant(SQLModel, table=True):
    __tablename__ = "restaurants"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    owner_name: str
    phone: str
    address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class ServiceRequest(SQLModel, table=True):
    __tablename__ = "service_requests"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    restaurant_id: UUID = Field(foreign_key="restaurants.id")
    assigned_branch_id: Optional[UUID] = Field(default=None, foreign_key="branches.id")
    category: str
    description: Optional[str] = None
    status: str = Field(default="PENDING")
    metadata: Optional[dict] = Field(default_factory=dict, sa_column=Column(JSONB))
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    assigned_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    branch: Optional[Branch] = Relationship(back_populates="requests")
```

## 4. 특이사항 및 향후 고려 사항
- **Full-Text Search**: `description` 필드에 대해 한글 형태소 분석기(n-gram 등)를 적용하여 추후 고장 증상 검색 기능을 강화할 수 있음.
- **Indexing**: `status`, `created_at`, `assigned_branch_id` 필드에 인덱스를 생성하여 대쉬보드 조회 성능 최적화 예정.
