"""JWT 토큰 생성·검증 (Phase 3.2a — 본사 로그인).

표준 JWT(HS256)를 파이썬 기본 라이브러리만으로 구현한다. 별도 패키지 설치가
필요 없어 운영 서버 배포가 단순하다. Phase 3.2b에서 식당·지사 인증을 정식
도입할 때 필요하면 PyJWT 등으로 교체할 수 있다(토큰 형식은 표준이라 호환됨).
"""
import base64
import hashlib
import hmac
import json
import secrets
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


# --- PIN 해시 (plan_phase3.2 §7 — 식당·지사 임시 로그인) ---
# 4자리 PIN을 평문 저장하지 않고 pbkdf2-sha256으로 해시한다.
# 형식: "pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>"

_PIN_ITERATIONS = 100_000


def hash_pin(pin: str) -> str:
    """PIN을 임의 salt와 함께 해시한다."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), _PIN_ITERATIONS)
    return f"pbkdf2_sha256${_PIN_ITERATIONS}${salt}${dk.hex()}"


def verify_pin(pin: str, stored: str | None) -> bool:
    """입력 PIN을 검증한다. stored가 None이면 기본 PIN '0000'과 비교한다."""
    if stored is None:
        return hmac.compare_digest(pin, "0000")
    try:
        algo, iter_s, salt, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), int(iter_s))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False
