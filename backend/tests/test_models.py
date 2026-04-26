from sqlmodel import SQLModel, create_engine, Session, select
from app.models.domain import Branch, Restaurant, ServiceRequest, AuditLog
import uuid

# 테스트용 인메모리 SQLite DB
sqlite_url = "sqlite://"
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

def test_logic():
    print("🚀 DB 모델 및 로직 정합성 테스트 시작...")
    SQLModel.metadata.create_all(engine)
    
    with Session(engine) as session:
        # 1. 지사 생성
        branch = Branch(name="강남지사", region_code="SEOUL_GANGNAM", commission_rate=5.0)
        session.add(branch)
        session.commit()
        session.refresh(branch)
        assert branch.id is not None
        print("✅ 지사 생성 성공")

        # 2. 식당 생성
        restaurant = Restaurant(
            name="맛있는 식당", 
            phone="010-1234-5678", 
            address="서울시 강남구 역삼동"
        )
        session.add(restaurant)
        session.commit()
        session.refresh(restaurant)
        assert restaurant.id is not None
        print("✅ 식당 생성 성공")
        
        # 3. 서비스 요청 생성
        request = ServiceRequest(
            restaurant_id=restaurant.id,
            assigned_branch_id=branch.id,
            category="WATER_LEAK",
            description="싱크대 밑에서 물이 새요"
        )
        session.add(request)
        session.commit()
        session.refresh(request)
        
        assert request.status == "PENDING"
        assert request.restaurant.name == "맛있는 식당"
        assert request.branch.name == "강남지사"
        print("✅ 서비스 요청 및 관계(Relationship) 확인 성공")

        # 4. 감사 로그 생성
        log = AuditLog(
            table_name="restaurants",
            target_id=restaurant.id,
            action="INSERT",
            payload={"name": restaurant.name},
            changed_by="admin"
        )
        session.add(log)
        session.commit()
        print("✅ 감사 로그(AuditLog) 기록 성공")

    print("\n🎉 모든 테스트를 성공적으로 통과했습니다!")

if __name__ == "__main__":
    test_logic()
