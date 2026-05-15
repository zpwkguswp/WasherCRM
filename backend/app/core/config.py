import os
import secrets
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "WasherCRM")
    VERSION: str = os.getenv("VERSION", "0.1.0")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL")

    # Auth / JWT (Phase 3.2a — 본사 로그인)
    # JWT_SECRET 미설정 시 프로세스마다 임의 생성됨 → 서버 재시작하면 재로그인 필요.
    # 운영 서버는 .env에 고정값을 둘 것 (재시작해도 로그인 유지).
    JWT_SECRET: str = os.getenv("JWT_SECRET") or secrets.token_hex(32)
    JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "12"))
    # 본사 임시 계정 — 실서비스 오픈 전 반드시 강한 비밀번호로 교체 (harnes.md 참조)
    HQ_ADMIN_ID: str = os.getenv("HQ_ADMIN_ID", "admin")
    HQ_ADMIN_PASSWORD: str = os.getenv("HQ_ADMIN_PASSWORD", "0000")
    
    # PortOne (Payment)
    PORTONE_API_KEY: str = os.getenv("PORTONE_API_KEY")
    PORTONE_API_SECRET: str = os.getenv("PORTONE_API_SECRET")
    
    # Firebase (FCM)
    FIREBASE_SERVICE_ACCOUNT_JSON: str = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")

    # Storage Settings (local or s3)
    STORAGE_TYPE: str = os.getenv("STORAGE_TYPE", "local")
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "whiteon-media")
    S3_REGION: str = os.getenv("S3_REGION", "ap-northeast-2")
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")

settings = Settings()
