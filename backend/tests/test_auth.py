"""Phase 3.2a 인증 시스템 단독 테스트 스크립트.

실행: backend/ 에서  python tests/test_auth.py
(test_models.py 와 동일하게 pytest 없이 직접 실행하는 스크립트)

DB 연결이 필요 없다 — JWT 유틸과 로그인 엔드포인트만 검증한다.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.deps import require_role
from app.api.v1.endpoints import auth as auth_module
from app.core import security
from app.core.config import settings

_passed = 0
_failed = 0


def check(label, condition):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS  {label}")
    else:
        _failed += 1
        print(f"  FAIL  {label}")


print("\n[1] JWT 유틸 (core/security.py)")

token = security.create_access_token(subject="admin", role="HQ_ADMIN")
decoded = security.decode_access_token(token)
check("정상 토큰 생성·검증 round-trip", decoded is not None)
check("payload의 sub 보존", decoded and decoded.get("sub") == "admin")
check("payload의 role 보존", decoded and decoded.get("role") == "HQ_ADMIN")

check("위변조 토큰 거부", security.decode_access_token(token[:-4] + "AAAA") is None)
check("형식 깨진 토큰 거부", security.decode_access_token("not-a-jwt") is None)

# 만료 토큰: 만료시간을 과거로 잡아 발급 후 검증
_orig_hours = settings.JWT_EXPIRE_HOURS
settings.JWT_EXPIRE_HOURS = -1
expired = security.create_access_token(subject="admin", role="HQ_ADMIN")
settings.JWT_EXPIRE_HOURS = _orig_hours
check("만료된 토큰 거부", security.decode_access_token(expired) is None)


print("\n[2] 로그인 엔드포인트 + 권한 의존성 (TestClient)")

test_app = FastAPI()
test_app.include_router(auth_module.router, prefix="/api/v1/auth")


@test_app.get("/api/v1/protected")
def _protected(user: dict = Depends(require_role("HQ_ADMIN"))):
    return {"ok": True, "role": user["role"]}


client = TestClient(test_app)

ok = client.post("/api/v1/auth/login", json={"username": "admin", "password": "0000"})
check("admin/0000 로그인 성공 (200)", ok.status_code == 200)
issued = ok.json().get("access_token") if ok.status_code == 200 else None
check("로그인 응답에 access_token 포함", bool(issued))
check("로그인 응답 role=HQ_ADMIN", ok.status_code == 200 and ok.json().get("role") == "HQ_ADMIN")

bad_pw = client.post("/api/v1/auth/login", json={"username": "admin", "password": "9999"})
check("틀린 비밀번호 거부 (401)", bad_pw.status_code == 401)

bad_id = client.post("/api/v1/auth/login", json={"username": "hacker", "password": "0000"})
check("틀린 아이디 거부 (401)", bad_id.status_code == 401)

no_token = client.get("/api/v1/protected")
check("토큰 없이 보호 API 호출 차단 (401)", no_token.status_code == 401)

bad_token = client.get("/api/v1/protected", headers={"Authorization": "Bearer garbage.token.here"})
check("위조 토큰으로 보호 API 호출 차단 (401)", bad_token.status_code == 401)

good = client.get("/api/v1/protected", headers={"Authorization": f"Bearer {issued}"})
check("정상 토큰으로 보호 API 통과 (200)", good.status_code == 200)


print(f"\n결과: {_passed} passed, {_failed} failed")
sys.exit(0 if _failed == 0 else 1)
