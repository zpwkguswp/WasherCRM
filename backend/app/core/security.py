"""JWT 토큰 생성·검증 (Phase 3.2a — 본사 로그인).

표준 JWT(HS256)를 파이썬 기본 라이브러리만으로 구현한다. 별도 패키지 설치가
필요 없어 운영 서버 배포가 단순하다. Phase 3.2b에서 식당·지사 인증을 정식
도입할 때 필요하면 PyJWT 등으로 교체할 수 있다(토큰 형식은 표준이라 호환됨).
"""
import base64
import hashlib
import hmac
import json
import time

from app.core.config import settings


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def create_access_token(subject: str, role: str) -> str:
    """subject(계정 식별자)와 role을 담은 서명된 JWT를 만든다."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + settings.JWT_EXPIRE_HOURS * 3600,
    }
    signing_input = (
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    )
    signature = hmac.new(
        settings.JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    return signing_input + "." + _b64url_encode(signature)


def decode_access_token(token: str) -> dict | None:
    """토큰을 검증한다. 서명 불일치·만료·형식 오류면 None을 반환한다."""
    try:
        seg_header, seg_payload, seg_signature = token.split(".")
        signing_input = f"{seg_header}.{seg_payload}"
        expected = hmac.new(
            settings.JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_b64url_decode(seg_signature), expected):
            return None
        payload = json.loads(_b64url_decode(seg_payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload
