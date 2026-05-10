import firebase_admin
from firebase_admin import credentials, messaging
import os
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

# Firebase 초기화
# backend 폴더에 있는 serviceAccountKey.json 파일을 사용합니다.
try:
    cred_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "serviceAccountKey.json")
    if not firebase_admin._apps:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize Firebase Admin SDK: {e}")

def send_push_notification(tokens: List[str], title: str, body: str, data: Optional[dict] = None):
    """
    여러 기기 토큰으로 푸시 알림을 발송합니다.
    """
    if not tokens:
        return
    
    # 500개 이상의 토큰일 경우 분할 발송이 필요하지만, 현재는 소규모이므로 한 번에 발송
    message = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data=data,
        tokens=tokens,
    )
    
    try:
        response = messaging.send_each_for_multicast(message)
        logger.info(f"Successfully sent {response.success_count} messages.")
        if response.failure_count > 0:
            logger.warning(f"Failed to send {response.failure_count} messages.")
        return response
    except Exception as e:
        logger.error(f"Error sending push notification: {e}")
        return None
