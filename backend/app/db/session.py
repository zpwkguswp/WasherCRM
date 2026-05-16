from sqlmodel import create_engine, Session, SQLModel
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, echo=True)

def get_session():
    with Session(engine) as session:
        yield session

def init_db():
    # 모델들을 임포트하여 metadata에 등록되도록 함
    from app.models.domain import Branch, Restaurant, ServiceRequest, RequestMedia, Payment, Settlement, DispatchEvent
    from sqlmodel import text, Session
    SQLModel.metadata.create_all(engine)
    
    # [임시 패치] 수동 컬럼 추가 (SQLModel은 기존 테이블 변경 미지원)
    with Session(engine) as session:
        # 1. restaurants 테이블
        try:
            session.execute(text("ALTER TABLE restaurants ADD COLUMN region VARCHAR;"))
            session.commit()
            print("Successfully added region to restaurants")
        except Exception: session.rollback()
        
        # 2. branches 테이블
        try:
            session.execute(text("ALTER TABLE branches ADD COLUMN address VARCHAR;"))
            session.commit()
            print("Successfully added address to branches")
        except Exception: session.rollback()

        # 3. service_requests SLA 측정 컬럼 (plan_phase3.5 H5)
        try:
            session.execute(text("ALTER TABLE service_requests ADD COLUMN IF NOT EXISTS notified_at TIMESTAMP;"))
            session.execute(text("ALTER TABLE service_requests ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMP;"))
            session.commit()
            print("Successfully added SLA columns to service_requests")
        except Exception: session.rollback()

        # 4. [매칭 자동 수선] 식당 지역 정보 표준화 및 전체 승인 처리
        try:
            # 주소의 앞 두 단어(예: 경기 의정부시)를 region 필드에 삽입
            session.execute(text("""
                UPDATE restaurants 
                SET region = split_part(address, ' ', 1) || ' ' || split_part(address, ' ', 2)
                WHERE region IS NULL OR region = '' OR region = 'None';
            """))
            # 지사/식당 전체 승인 처리 (매칭 활성화)
            session.execute(text("UPDATE restaurants SET is_approved = true WHERE is_approved = false;"))
            session.execute(text("UPDATE branches SET is_approved = true WHERE is_approved = false;"))

            session.commit()
            print("Successfully normalized restaurant regions and approvals")
        except Exception as e:
            session.rollback()
            print(f"DB Normalize Error: {e}")

        # 5. [임시 로그인 plan_phase3.2 §7] 식당·지사 PIN 인증 컬럼
        try:
            for tbl in ("branches", "restaurants"):
                session.execute(text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS pin_hash VARCHAR;"))
                session.execute(text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS failed_login_count INTEGER DEFAULT 0;"))
                session.execute(text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS lockout_until TIMESTAMP;"))
            session.commit()
            print("Successfully added PIN auth columns to branches/restaurants")
        except Exception as e:
            session.rollback()
            print(f"PIN column add error: {e}")

        # 6. [배차 plan_phase3.7] service_requests 배차 컬럼
        #    (dispatch_events 테이블은 SQLModel.metadata.create_all이 생성)
        try:
            session.execute(text("ALTER TABLE service_requests ADD COLUMN IF NOT EXISTS dispatch_status VARCHAR;"))
            session.execute(text("ALTER TABLE service_requests ADD COLUMN IF NOT EXISTS cancel_count INTEGER DEFAULT 0;"))
            session.execute(text("ALTER TABLE service_requests ADD COLUMN IF NOT EXISTS dispatch_deadline TIMESTAMP;"))
            session.commit()
            print("Successfully added dispatch columns to service_requests")
        except Exception as e:
            session.rollback()
            print(f"Dispatch column add error: {e}")
