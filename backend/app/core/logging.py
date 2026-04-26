import logging
import sys
from core.config import settings # 아직 설정 파일은 없지만 미리 구조화

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            # 향후 파일 로그 추가 가능: logging.FileHandler("app.log")
        ]
    )
    
    # 특정 라이브러리 로그 수준 조절
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
