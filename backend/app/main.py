from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from app.db.session import init_db
from app.api.v1.api import api_router
from contextlib import asynccontextmanager
import os

from fastapi.staticfiles import StaticFiles

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 어플리케이션 시작 시 DB 테이블 생성
    init_db()
    yield

app = FastAPI(
    title="WhiteOn API",
    description="화이트온 전국 세척기 통합 관리 플랫폼 API",
    version="0.1.0",
    lifespan=lifespan
)

# 1. 업로드 사진 마운트 설정
upload_dir = os.path.join(os.path.dirname(__file__), "static", "uploads")
if not os.path.exists(upload_dir):
    os.makedirs(upload_dir)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")

# 2. 정적 자산(로고 등) 마운트 설정
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")



# 루트 접속 시 런처(index.html) 표시
@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = os.path.join(www_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "WhiteOn API is running (www/index.html not found)"}

# Admin UI 라우트 — www/admin.html을 사용 (static/admin.html은 구버전 잔재)
@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    return FileResponse(os.path.join(www_dir, "admin.html"))

# 각 앱 전용 라우트
@app.get("/hq", response_class=HTMLResponse)
async def hq_page():
    return FileResponse(os.path.join(www_dir, "admin.html"))

@app.get("/manager", response_class=HTMLResponse)
async def manager_page():
    return FileResponse(os.path.join(www_dir, "manager.html"))

@app.get("/restaurant", response_class=HTMLResponse)
async def restaurant_page():
    return FileResponse(os.path.join(www_dir, "restaurant.html"))

# 라우터 등록
app.include_router(api_router, prefix="/api/v1")

# CORS 설정 — 허용 출처를 명시적으로 제한 (와일드카드 "*" 금지)
# 운영 도메인·로컬 개발·Capacitor 앱 출처만 허용. 필요 시 목록에 추가.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://whiteon.kr",
        "https://www.whiteon.kr",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "capacitor://localhost",
        "http://localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# UI 폴더(www) 루트 마운트 - 모든 파일 접근 가능 (다른 라우트들과 충돌하지 않도록 마지막에 배치)
www_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "www")
app.mount("/", StaticFiles(directory=www_dir, html=True), name="www")
