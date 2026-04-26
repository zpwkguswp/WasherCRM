import sys
import os

# 라이브러리가 설치된 Roaming 폴더를 시스템 경로에 추가
roaming_path = os.path.expanduser(r"~\AppData\Roaming\Python\Python312\site-packages")
if roaming_path not in sys.path:
    sys.path.append(roaming_path)

try:
    from sqlmodel import Session, create_engine, text
    from dotenv import load_dotenv
except ImportError:
    # 혹시 다른 경로일 경우를 대비해 site 패키지 추가 시도
    import site
    sys.path.extend(site.getsitepackages())
    from sqlmodel import Session, create_engine, text
    from dotenv import load_dotenv

load_dotenv()

def patch_db():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not found in environment.")
        return
        
    engine = create_engine(db_url)
    with Session(engine) as session:
        try:
            print("Checking for is_approved column in restaurants table...")
            check_sql = text("SELECT column_name FROM information_schema.columns WHERE table_name='restaurants' AND column_name='is_approved';")
            result = session.execute(check_sql).fetchone()
            
            if not result:
                print("Adding is_approved column to restaurants table...")
                session.execute(text("ALTER TABLE restaurants ADD COLUMN is_approved BOOLEAN DEFAULT FALSE;"))
                session.execute(text("UPDATE restaurants SET is_approved = TRUE;"))
                session.commit()
                print("Column added successfully.")
            else:
                print("Column already exists.")
        except Exception as e:
            print(f"Error during patching: {e}")
            session.rollback()

if __name__ == "__main__":
    patch_db()
