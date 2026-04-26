from sqlmodel import create_engine, Session, SQLModel
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, echo=True)

def get_session():
    with Session(engine) as session:
        yield session

def init_db():
    # 모델들을 임포트하여 metadata에 등록되도록 함
    from app.models.domain import Branch, Restaurant, ServiceRequest, RequestMedia, Payment, Settlement
    from sqlmodel import text, Session
    SQLModel.metadata.create_all(engine)
    
    # [임시 패치] restaurants 테이블에 region 컬럼 수동 추가
    with Session(engine) as session:
        try:
            session.execute(text("ALTER TABLE restaurants ADD COLUMN region VARCHAR;"))
            session.commit()
            print("Successfully added region to restaurants")
        except Exception:
            session.rollback()
