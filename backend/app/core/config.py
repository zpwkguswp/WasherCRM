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

settings = Settings()
