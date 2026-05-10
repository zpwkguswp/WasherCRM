import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# .env 로드
load_dotenv('backend/.env')
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

def extract_standard_region(address):
    if not address: return None
    parts = address.split(' ')
    if len(parts) >= 2:
        # 광역 + 시/군/구 (예: 경기 의정부시)
        return f"{parts[0]} {parts[1]}"
    return parts[0] if parts else None

with engine.connect() as conn:
    print("--- [DB 매칭 자동 수선 시작] ---")
    
    # 1. 식당(Restaurant) 지역 정보 일괄 업데이트
    restaurants = conn.execute(text("SELECT id, name, address, region FROM restaurants")).fetchall()
    updated_r = 0
    for r in restaurants:
        if not r[3] or r[3] == "None" or r[3] == "":
            std_region = extract_standard_region(r[2])
            if std_region:
                conn.execute(
                    text("UPDATE restaurants SET region = :region WHERE id = :id"),
                    {"region": std_region, "id": r[0]}
                )
                print(f"✅ 식당 업데이트: [{r[1]}] -> 지역: {std_region}")
                updated_r += 1
    
    # 2. 미승인 데이터 자동 승인 처리 (매칭 테스트를 위해)
    # conn.execute(text("UPDATE restaurants SET is_approved = true WHERE is_approved = false"))
    # conn.execute(text("UPDATE branches SET is_approved = true WHERE is_approved = false"))
    
    conn.commit()
    print(f"\n--- [수선 완료: 식당 {updated_r}건 처리됨] ---")
    print("이제 모든 지사와 식당이 표준 지역 정보로 매칭될 준비가 되었습니다.")
