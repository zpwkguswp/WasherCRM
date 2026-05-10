import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# .env 로드
load_dotenv('backend/.env')
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

def extract_keyword(address):
    if not address: return ""
    parts = address.split(' ')
    for p in parts:
        if p.endswith('시') or p.endswith('군') or p.endswith('구'):
            return p.replace('시','').replace('군','').replace('구','')
    return ""

with engine.connect() as conn:
    print("--- [1. 지사 데이터 점검] ---")
    branches = conn.execute(text("SELECT id, name, address, region_code FROM branches")).fetchall()
    for b in branches:
        keyword = extract_keyword(b[2])
        print(f"지사명: {b[1]} | 주소: {b[2]} | 추출키워드: [{keyword}] | 지역코드: {b[3]}")
        if not keyword:
            print(f"  ⚠️ 경고: '{b[1]}' 지사의 주소에서 매칭 키워드를 추출할 수 없습니다.")

    print("\n--- [2. 식당 데이터 점검] ---")
    restaurants = conn.execute(text("SELECT id, name, address, region FROM restaurants")).fetchall()
    for r in restaurants:
        print(f"식당명: {r[1]} | 주소: {r[2]} | 지역필드: {r[3]}")
        if not r[3] or r[3] == "None":
            # 주소에서 지역 정보 추출 시도 (예: 경기 의정부시)
            parts = r[2].split(' ')
            if len(parts) >= 2:
                new_region = f"{parts[0]} {parts[1]}"
                print(f"  ➡️ 제안: '{r[1]}' 식당의 지역 필드를 [{new_region}]으로 업데이트 필요")
            else:
                print(f"  ⚠️ 경고: '{r[1]}' 식당의 주소 형식이 불완전합니다.")
