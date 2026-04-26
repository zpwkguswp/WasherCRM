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

# 1. 앱 마운트 설정 (사장님용 모바일 웹 앱)
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")
if not os.path.exists(frontend_dir):
    os.makedirs(frontend_dir)
app.mount("/app", StaticFiles(directory=frontend_dir, html=True), name="app")

# 2. 업로드 사진 마운트 설정
upload_dir = os.path.join(os.path.dirname(__file__), "static", "uploads")
if not os.path.exists(upload_dir):
    os.makedirs(upload_dir)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")

# 3. 정적 자산(로고 등) 마운트 설정
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Admin UI 라우트
@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    static_path = os.path.join(os.path.dirname(__file__), "static", "admin.html")
    return FileResponse(static_path)

# Manager UI 라우트
@app.get("/manager", response_class=HTMLResponse)
async def manager_page():
    # frontend 폴더에 있는 manager.html을 반환
    manager_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "manager.html")
    return FileResponse(manager_path)

# 라우터 등록
app.include_router(api_router, prefix="/api/v1")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "WhiteOn API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
