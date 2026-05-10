import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "WasherCRM")
    VERSION: str = os.getenv("VERSION", "0.1.0")
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    
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
