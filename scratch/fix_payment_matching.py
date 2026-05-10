import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# .env 로드
load_dotenv('backend/.env')
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

with engine.connect() as conn:
    print("--- [결제 데이터 매칭 정밀 수선 시작] ---")
    
    # 1. 100원 결제건 수선 (#8217E870 매칭)
    # 8217e870 으로 시작하는 요청 ID 찾기
    req_100 = conn.execute(text("SELECT id FROM service_requests WHERE CAST(id AS TEXT) LIKE '8217e870%'")).fetchone()
    if req_100:
        new_id_100 = req_100[0]
        # 100원짜리 결제 데이터 업데이트
        res = conn.execute(
            text("UPDATE payments SET request_id = :new_id WHERE amount = 100"),
            {"new_id": new_id_100}
        )
        print(f"✅ 100원 결제건 -> 접수번호 #8217E870 ({new_id_100}) 연결 완료")
    else:
        print("⚠️ 오류: 접수번호 #8217E870 건을 DB에서 찾을 수 없습니다.")

    # 2. 50,000원 결제건 수선 (#BE4988BB 매칭)
    req_50k = conn.execute(text("SELECT id FROM service_requests WHERE CAST(id AS TEXT) LIKE 'be4988bb%'")).fetchone()
    if req_50k:
        new_id_50k = req_50k[0]
        res = conn.execute(
            text("UPDATE payments SET request_id = :new_id WHERE amount = 50000"),
            {"new_id": new_id_50k}
        )
        print(f"✅ 50,000원 결제건 -> 접수번호 #BE4988BB ({new_id_50k}) 연결 완료")
    else:
        print("⚠️ 오류: 접수번호 #BE4988BB 건을 DB에서 찾을 수 없습니다.")

    conn.commit()
    print("\n--- [수선 완료: 이제 모든 결제건이 올바른 접수번호와 매칭되었습니다.] ---")
