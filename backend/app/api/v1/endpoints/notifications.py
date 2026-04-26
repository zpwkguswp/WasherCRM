from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from uuid import UUID

router = APIRouter()

class NotificationRequest(BaseModel):
    target_id: UUID
    title: str
    body: str
    data: Optional[dict] = None

@router.post("/send-test")
async def send_test_notification(data: NotificationRequest):
    # 실제 Firebase 연동 전까지는 로그만 남깁니다.
    print(f"--- [MOCK NOTIFICATION] ---")
    print(f"Target: {data.target_id}")
    print(f"Title: {data.title}")
    print(f"Body: {data.body}")
    print(f"Data: {data.data}")
    print(f"---------------------------")
    
    return {"status": "success", "message": "Notification logged (Mock mode)"}
