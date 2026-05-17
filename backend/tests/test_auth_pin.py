"""Phase 3.2 §7 — 식당·지사 PIN 인증 + 소유권 검증 단독 테스트.

실행: backend/ 에서  python tests/test_auth_pin.py
(test_auth.py 와 동일하게 pytest 없이 직접 실행하는 스크립트)

DB·서버 연결이 필요 없다 — PIN 해시와 소유권 헬퍼 함수만 검증한다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException

from app.api import deps
from app.core import security

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


def denied(fn):
    """fn() 호출이 403 HTTPException을 던지면 True."""
    try:
        fn()
        return False
    except HTTPException as e:
        return e.status_code == 403
    except Exception:
        return False


print("\n[1] PIN 해시 (core/security.py)")

h = security.hash_pin("1234")
check("hash_pin 형식 pbkdf2_sha256$iter$salt$hash", h.startswith("pbkdf2_sha256$") and h.count("$") == 3)
check("올바른 PIN 검증 통과", security.verify_pin("1234", h))
check("틀린 PIN 검증 거부", not security.verify_pin("0000", h))
check("같은 PIN도 salt가 달라 해시가 매번 다름", security.hash_pin("1234") != security.hash_pin("1234"))
check("pin_hash가 None이면 기본 PIN 0000 통과", security.verify_pin("0000", None))
check("pin_hash가 None일 때 0000 외 PIN 거부", not security.verify_pin("9999", None))
check("깨진 해시 문자열 거부", not security.verify_pin("1234", "garbage"))


print("\n[2] 소유권 검증 헬퍼 (api/deps.py)")

HQ = {"role": "HQ_ADMIN", "sub": "admin"}
BR1 = {"role": "BRANCH", "sub": "branch-1"}
BR2 = {"role": "BRANCH", "sub": "branch-2"}
RES1 = {"role": "RESTAURANT", "sub": "rest-1"}
RES2 = {"role": "RESTAURANT", "sub": "rest-2"}


class FakeReq:
    def __init__(self, assigned_branch_id, restaurant_id):
        self.assigned_branch_id = assigned_branch_id
        self.restaurant_id = restaurant_id


req_b1 = FakeReq(assigned_branch_id="branch-1", restaurant_id="rest-1")
req_open = FakeReq(assigned_branch_id=None, restaurant_id="rest-1")

# assert_request_access — 수리요청 수정 권한
check("HQ는 어떤 요청이든 통과", deps.assert_request_access(HQ, req_b1) is None)
check("담당 지사는 자기 배정 요청 통과", deps.assert_request_access(BR1, req_b1) is None)
check("타 지사는 남의 배정 요청 거부(403)", denied(lambda: deps.assert_request_access(BR2, req_b1)))
check("미배정 요청은 어느 지사든 통과", deps.assert_request_access(BR2, req_open) is None)
check("식당은 자기 요청 통과", deps.assert_request_access(RES1, req_b1) is None)
check("식당은 남의 요청 거부(403)", denied(lambda: deps.assert_request_access(RES2, req_b1)))

# assert_self_or_hq — 본인 정보 수정 권한
check("HQ는 어떤 지사·식당 정보든 통과", deps.assert_self_or_hq(HQ, "branch-9") is None)
check("지사는 자기 지사 통과", deps.assert_self_or_hq(BR1, "branch-1") is None)
check("지사는 남의 지사 거부(403)", denied(lambda: deps.assert_self_or_hq(BR1, "branch-2")))
check("식당은 자기 식당 통과", deps.assert_self_or_hq(RES1, "rest-1") is None)
check("식당은 남의 식당 거부(403)", denied(lambda: deps.assert_self_or_hq(RES2, "rest-1")))

# assert_no_hq_only_fields — 본사 전용 필드 보호
check(
    "HQ는 본사 전용 필드 변경 통과",
    deps.assert_no_hq_only_fields(HQ, {"is_approved": True}, deps.HQ_ONLY_BRANCH_FIELDS) is None,
)
check(
    "지사는 일반 필드 변경 통과",
    deps.assert_no_hq_only_fields(BR1, {"address": "x"}, deps.HQ_ONLY_BRANCH_FIELDS) is None,
)
check(
    "지사가 승인·수수료·등급 변경 시 거부(403)",
    denied(lambda: deps.assert_no_hq_only_fields(BR1, {"commission_rate": 5}, deps.HQ_ONLY_BRANCH_FIELDS)),
)
check(
    "식당이 승인 필드 변경 시 거부(403)",
    denied(lambda: deps.assert_no_hq_only_fields(RES1, {"is_approved": True}, deps.HQ_ONLY_RESTAURANT_FIELDS)),
)


print(f"\n결과: {_passed} passed, {_failed} failed")
sys.exit(0 if _failed == 0 else 1)
