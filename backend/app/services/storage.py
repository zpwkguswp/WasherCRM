import os
import boto3
from abc import ABC, abstractmethod
from fastapi import UploadFile
from app.core.config import settings
from pathlib import Path
import uuid

class StorageService(ABC):
    @abstractmethod
    async def upload_file(self, file: UploadFile, folder: str = "uploads") -> str:
        pass

class LocalStorageService(StorageService):
    def __init__(self):
        self.base_path = Path("app/static")
        if not self.base_path.exists():
            self.base_path.mkdir(parents=True, exist_ok=True)

    async def upload_file(self, file: UploadFile, folder: str = "uploads") -> str:
        folder_path = self.base_path / folder
        if not folder_path.exists():
            folder_path.mkdir(parents=True, exist_ok=True)

        file_extension = Path(file.filename).suffix
        file_name = f"{uuid.uuid4()}{file_extension}"
        file_path = folder_path / file_name
        
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
            
        return f"/static/{folder}/{file_name}"

class S3StorageService(StorageService):
    def __init__(self):
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.S3_REGION
        )
        self.bucket_name = settings.S3_BUCKET_NAME

    async def upload_file(self, file: UploadFile, folder: str = "uploads") -> str:
        file_extension = Path(file.filename).suffix
        file_name = f"{folder}/{uuid.uuid4()}{file_extension}"
        
        content = await file.read()
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=file_name,
            Body=content,
            ContentType=file.content_type
        )
        
        return f"https://{self.bucket_name}.s3.{settings.S3_REGION}.amazonaws.com/{file_name}"

def get_storage() -> StorageService:
    if settings.STORAGE_TYPE == "s3":
        return S3StorageService()
    return LocalStorageService()

storage = get_storage()
