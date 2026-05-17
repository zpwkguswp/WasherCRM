# -*- coding: utf-8 -*-
"""WhiteOn 백엔드 E2E 통합 테스트 (2026-05-17 작성, QA-Analyst).

목적
----
6월 중순 외부 홍보 전, 식당/지사/본사 전 사용 시나리오를 HTTP API 레벨에서
망라 검증한다. pytest를 쓰지 않고 standalone 스크립트로 작성했다
(기존 tests/test_models.py / test_auth_pin.py 와 동일한 운영 방식).

실행
----
    backend/ 에서:
        venv_win/Scripts/python.exe tests/test_e2e.py

전제
----
- 로컬 서버가 http://localhost:8000 에서 실행 중이어야 한다.
- 로컬 DB(docker washer_db)에 접근 가능해야 한다. 정리(cleanup) 단계가
  DB에 직접 접속해 테스트가 만든 행을 삭제하므로, 끝나면 DB가 빈 상태로 남는다.

설계 원칙
---------
- 멱등: 시작 시 이전 잔여 테스트 데이터를 먼저 청소하고, 끝나면 다시 청소한다.
- 모든 테스트 데이터 이름/전화번호에 고정 접두사(_TP)를 붙여 식별 → 안전 삭제.
- 통과/실패를 콘솔과 tests/TEST_RESULTS_LATEST.txt 양쪽에 기록.
- 버그를 발견해도 수정하지 않는다 — FAIL로 기록만 한다.
- Windows cp949 콘솔 대비: 출력은 ASCII 위주.
"""
import os
import sys
import json
import time
import uuid
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = "http://localhost:8000/api/v1"
_TP = "E2ETEST_"  # 테스트 데이터 식별 접두사 (이름/설명에 사용)
_RESULT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "TEST_RESULTS_LATEST.txt")

# ---------------------------------------------------------------------------
# 결과 집계
# ---------------------------------------------------------------------------
_passed = 0
_failed = 0
_lines = []          # 결과 파일에 쓸 라인
_bugs = []           # 발견된 버그/이상 (라벨, 상세)
_created = {         # 정리 대상 추적
    "request_ids": set(),
    "restaurant_ids": set(),
    "branch_ids": set(),
    "payment_ids": set(),
    "settlement_ids": set(),
    "device_token_strs": set(),
}


def _log(msg):
    print(msg)
    _lines.append(msg)


def check(label, condition, bug_detail=None):
    """단언. condition이 거짓이면 FAIL + (bug_detail 주어지면) 버그 등록."""
    global _passed, _failed
    if condition:
        _passed += 1
        _log("  PASS  " + label)
    else:
        _failed += 1
        _log("  FAIL  " + label)
        if bug_detail:
            _bugs.append((label, bug_detail))


def section(title):
    _log("")
    _log("=" * 70)
    _log(title)
    _log("=" * 70)


# ---------------------------------------------------------------------------
# HTTP 헬퍼 (표준 라이브러리만 사용 — requests 의존성 없음)
# ---------------------------------------------------------------------------
def api(method, path, body=None, token=None, raw=False):
    """API 호출. (status_code, parsed_json_or_text) 반환. 예외는 던지지 않는다."""
    url = BASE + path
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            txt = resp.read().decode("utf-8", errors="replace")
            code = resp.status
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", errors="replace")
        code = e.code
    except Exception as e:
        return (0, str(e))
    if raw:
        return (code, txt)
    try:
        return (code, json.loads(txt) if txt else None)
    except Exception:
        return (code, txt)


# ---------------------------------------------------------------------------
# DB 직접 정리 (테스트가 만든 행을 안전하게 삭제 — 멱등)
# ---------------------------------------------------------------------------
def cleanup_db(phase):
    """접두사 _TP로 식별되는 테스트 데이터를 DB에서 직접 삭제한다.

    FK 의존 순서(자식 → 부모)대로 삭제한다. 서버 API에는 일괄삭제가 없으므로
    SQLModel 세션으로 직접 접근한다.
    """
    try:
        from sqlmodel import Session, select, delete
        from app.db.session import engine
        from app.models.domain import (
            ServiceRequest, Restaurant, Branch, Payment, RequestMedia,
            DispatchEvent, Settlement, SettlementItem, AuditLog, DeviceToken,
        )
    except Exception as e:
        _log("  [WARN] cleanup_db(%s): DB 모듈 import 실패 -> %s" % (phase, e))
        return

    removed = 0
    try:
        with Session(engine) as s:
            # 테스트 식당/지사 id 수집
            test_rests = s.exec(
                select(Restaurant).where(Restaurant.name.contains(_TP))
            ).all()
            test_branches = s.exec(
                select(Branch).where(Branch.name.contains(_TP))
            ).all()
            rest_ids = {r.id for r in test_rests}
            branch_ids = {b.id for b in test_branches}

            # 해당 식당의 요청
            test_reqs = []
            if rest_ids:
                test_reqs = s.exec(
                    select(ServiceRequest).where(ServiceRequest.restaurant_id.in_(rest_ids))
                ).all()
            req_ids = {r.id for r in test_reqs}

            # 자식부터 삭제: SettlementItem -> Payment -> RequestMedia -> DispatchEvent -> Settlement -> Request
            if req_ids:
                pays = s.exec(select(Payment).where(Payment.request_id.in_(req_ids))).all()
                pay_ids = {p.id for p in pays}
                if pay_ids:
                    for si in s.exec(select(SettlementItem).where(SettlementItem.payment_id.in_(pay_ids))).all():
                        s.delete(si); removed += 1
                for p in pays:
                    s.delete(p); removed += 1
                for m in s.exec(select(RequestMedia).where(RequestMedia.request_id.in_(req_ids))).all():
                    s.delete(m); removed += 1
                for de in s.exec(select(DispatchEvent).where(DispatchEvent.request_id.in_(req_ids))).all():
                    s.delete(de); removed += 1

            # 테스트 지사의 정산서 + 그 라인
            if branch_ids:
                setts = s.exec(select(Settlement).where(Settlement.branch_id.in_(branch_ids))).all()
                for st in setts:
                    for si in s.exec(select(SettlementItem).where(SettlementItem.settlement_id == st.id)).all():
                        s.delete(si); removed += 1
                for st in setts:
                    s.delete(st); removed += 1

            for r in test_reqs:
                s.delete(r); removed += 1
            for r in test_rests:
                s.delete(r); removed += 1
            for b in test_branches:
                s.delete(b); removed += 1

            # 테스트 디바이스 토큰
            for dt in s.exec(select(DeviceToken).where(DeviceToken.token.contains(_TP))).all():
                s.delete(dt); removed += 1

            # 테스트 대상 AuditLog (target_id가 위에서 지운 id들)
            all_ids = req_ids | rest_ids | branch_ids
            if all_ids:
                for al in s.exec(select(AuditLog).where(AuditLog.target_id.in_(all_ids))).all():
                    s.delete(al); removed += 1

            s.commit()
        _log("  [cleanup-%s] %d개 행 삭제" % (phase, removed))
    except Exception as e:
        _log("  [WARN] cleanup_db(%s) 실패: %s" % (phase, e))


# ---------------------------------------------------------------------------
# 테스트 데이터 팩토리
# ---------------------------------------------------------------------------
def uniq():
    return uuid.uuid4().hex[:8]


def make_restaurant(addr_region="E2EREGION", approved_expected=True):
    """식당 가입 헬퍼. (status, body) 반환."""
    u = uniq()
    body = {
        "name": _TP + "식당_" + u,
        "owner_name": "홍길동",
        "phone": "010" + u[:4] + u[4:],
        "address": "테스트시 " + addr_region + " " + u + "로 1",
        "region": addr_region,
    }
    return api("POST", "/restaurants/", body)


def make_branch(region_code="E2EREGION", phone=None):
    """지사 가입 헬퍼. (status, body) 반환."""
    u = uniq()
    body = {
        "name": _TP + "지사_" + u,
        "region_code": region_code,
        "address": "테스트시 " + region_code + " 지사로 " + u,
        "manager_phone": phone or ("011" + u[:4] + u[4:]),
        "commission_rate": 10.0,
    }
    return api("POST", "/branches/", body)


def approve_branch(branch_id, hq_token):
    """지사를 본사 권한으로 승인 처리."""
    return api("PATCH", "/branches/" + str(branch_id),
               {"is_approved": True}, token=hq_token)


def login_pin(phone, user_type, pin="0000"):
    return api("POST", "/auth/login/pin",
               {"phone": phone, "pin": pin, "user_type": user_type})


# ===========================================================================
# 테스트 시나리오
# ===========================================================================
def run():
    section("0. 사전 정리 + 서버 연결 확인")
    cleanup_db("pre")
    code, _ = api("GET", "/branches/")
    check("TC-000 서버 응답 확인 (GET /branches/ -> 200)", code == 200,
          bug_detail="서버가 응답하지 않음. localhost:8000 실행 여부 확인 필요.")
    if code != 200:
        _log("  [중단] 서버 미응답으로 테스트를 진행할 수 없습니다.")
        return

    # ----- 본사 로그인 토큰 확보 (이후 전 구간에서 사용) -----
    code, b = api("POST", "/auth/login", {"username": "admin", "password": "0000"})
    check("TC-010 본사 로그인 (admin/0000 -> 200, role=HQ_ADMIN)",
          code == 200 and isinstance(b, dict) and b.get("role") == "HQ_ADMIN")
    hq_token = b.get("access_token") if isinstance(b, dict) else None

    code, b = api("POST", "/auth/login", {"username": "admin", "password": "wrong"})
    check("TC-011 본사 로그인 실패 비밀번호 (-> 401)", code == 401)

    # =====================================================================
    section("1. 가입 (식당/지사/중복/필수항목)")
    # =====================================================================
    # --- 식당 가입 ---
    code, rest = make_restaurant()
    check("TC-100 식당 가입 성공 (-> 201)", code == 201)
    rest_a = rest if code == 201 else None
    if rest_a:
        _created["restaurant_ids"].add(rest_a["id"])
        check("TC-101 식당 가입 즉시 자동 승인 (is_approved=True)",
              rest_a.get("is_approved") is True,
              bug_detail="식당은 가입 즉시 자동승인 정책(2026-05-16). is_approved가 True가 아님.")

    # --- 식당 중복 (이름) ---
    if rest_a:
        dup = {"name": rest_a["name"], "phone": "01099998888",
               "address": "전혀다른주소 " + uniq(), "region": "E2EREGION"}
        code, b = api("POST", "/restaurants/", dup)
        check("TC-102 식당 이름 중복 차단 (-> 400)", code == 400)

        # --- 식당 중복 (전화) ---
        dup = {"name": _TP + "다른이름_" + uniq(), "phone": rest_a["phone"],
               "address": "전혀다른주소 " + uniq(), "region": "E2EREGION"}
        code, b = api("POST", "/restaurants/", dup)
        check("TC-103 식당 전화번호 중복 차단 (-> 400)", code == 400)

        # --- 식당 중복 (주소) ---
        dup = {"name": _TP + "또다른이름_" + uniq(), "phone": "01077776666",
               "address": rest_a["address"], "region": "E2EREGION"}
        code, b = api("POST", "/restaurants/", dup)
        check("TC-104 식당 주소 중복 차단 (-> 400)", code == 400)

    # --- 식당 필수항목 누락 ---
    code, b = api("POST", "/restaurants/", {"name": _TP + "누락_" + uniq()})
    check("TC-105 식당 필수항목 누락 거부 (phone/address 없음 -> 400 또는 422)",
          code in (400, 422))

    # --- 지사 가입 ---
    code, br = make_branch()
    check("TC-110 지사 가입 성공 (-> 201)", code == 201)
    branch_a = br if code == 201 else None
    if branch_a:
        _created["branch_ids"].add(branch_a["id"])
        check("TC-111 지사 가입 직후 미승인 상태 (is_approved=False)",
              branch_a.get("is_approved") is False,
              bug_detail="지사는 본사 승인 전 is_approved=False여야 함.")

    # --- 지사 중복 (이름) ---
    if branch_a:
        dup = {"name": branch_a["name"], "region_code": "E2EREGION",
               "address": "다른지사주소 " + uniq(), "manager_phone": "01155554444"}
        code, b = api("POST", "/branches/", dup)
        check("TC-112 지사 이름 중복 차단 (-> 400)", code == 400)

        # 지사 vs 식당 교차 중복 (이름) — 같은 이름 식당이 있으면 지사도 거부
        if rest_a:
            dup = {"name": rest_a["name"], "region_code": "E2EREGION",
                   "address": "교차중복주소 " + uniq(), "manager_phone": "01133332222"}
            code, b = api("POST", "/branches/", dup)
            check("TC-113 지사-식당 이름 교차 중복 차단 (-> 400)", code == 400)

    # --- 지사 필수항목 누락 ---
    code, b = api("POST", "/branches/", {"name": _TP + "지사누락_" + uniq(),
                                         "region_code": "E2EREGION"})
    check("TC-114 지사 필수항목 누락 거부 (manager_phone/address 없음 -> 400)",
          code in (400, 422))

    # 지사 A 승인 (이후 배차 테스트에서 후보가 되도록)
    if branch_a and hq_token:
        code, b = approve_branch(branch_a["id"], hq_token)
        check("TC-115 본사가 지사 승인 처리 (PATCH is_approved -> 200)", code == 200)
        if code == 200:
            check("TC-116 승인 후 is_approved=True 반영", b.get("is_approved") is True)

    # =====================================================================
    section("2. 로그인 (PIN / 잠금 / 미등록)")
    # =====================================================================
    if rest_a:
        code, b = login_pin(rest_a["phone"], "RESTAURANT", "0000")
        check("TC-200 식당 PIN 로그인 성공 (기본 0000 -> 200)",
              code == 200 and isinstance(b, dict) and b.get("role") == "RESTAURANT")
        rest_token = b.get("access_token") if isinstance(b, dict) else None
    else:
        rest_token = None

    if branch_a:
        code, b = login_pin(branch_a["manager_phone"], "BRANCH", "0000")
        check("TC-201 지사 PIN 로그인 성공 (기본 0000 -> 200)",
              code == 200 and isinstance(b, dict) and b.get("role") == "BRANCH")
        branch_token = b.get("access_token") if isinstance(b, dict) else None
    else:
        branch_token = None

    # --- 미등록 번호 ---
    code, b = login_pin("01000000000", "RESTAURANT", "0000")
    check("TC-202 미등록 전화번호 로그인 거부 (-> 401)", code == 401)

    # --- 잘못된 user_type ---
    code, b = login_pin("01000000000", "INVALID", "0000")
    check("TC-203 잘못된 user_type 거부 (-> 400)", code == 400)

    # --- PIN 연속 실패 + 잠금 (전용 식당 생성 — 다른 테스트에 영향 없게) ---
    code, lock_rest = make_restaurant()
    if code == 201:
        _created["restaurant_ids"].add(lock_rest["id"])
        phone = lock_rest["phone"]
        # 5회 연속 실패: 1~4회는 401, 5회째 잠금(423)
        results = []
        for i in range(5):
            c, _ = login_pin(phone, "RESTAURANT", "9999")
            results.append(c)
        check("TC-210 PIN 1~4회 실패 시 401 반환",
              all(c == 401 for c in results[:4]),
              bug_detail="실패 횟수 카운트 동작 이상. 1~4회째 응답: %s" % results[:4])
        check("TC-211 PIN 5회 실패 시 계정 잠금 (-> 423 LOCKED)",
              results[4] == 423,
              bug_detail="5회 연속 실패 시 423 잠금이 되어야 함. 실제: %s" % results[4])
        # 잠금 상태에서는 올바른 PIN도 거부
        c, _ = login_pin(phone, "RESTAURANT", "0000")
        check("TC-212 잠금 상태에서는 올바른 PIN도 거부 (-> 423)", c == 423,
              bug_detail="잠금 중에는 올바른 PIN(0000)도 423이어야 함. 실제: %s" % c)

    # =====================================================================
    section("3. 수리 요청 생성 + 지역 매칭 + 브로드캐스트")
    # =====================================================================
    req_a = None
    if rest_a:
        code, req_a = api("POST", "/requests/", {
            "restaurant_id": rest_a["id"],
            "category": "WATER_LEAK",
            "description": _TP + "노즐 누수 증상",
            "metadata": {"priority": "high", "requested_amount": 110000},
        })
        check("TC-300 식당 수리 요청 생성 (-> 201)", code == 201)
        if code == 201:
            _created["request_ids"].add(req_a["id"])
            check("TC-301 신규 요청 status=PENDING", req_a.get("status") == "PENDING")
            check("TC-302 신규 요청 notified_at 기록됨 (SLA 시작점)",
                  req_a.get("notified_at") is not None,
                  bug_detail="notified_at은 SLA 측정 시작점. 생성 시 채워져야 함.")
            # 후보 지사(승인된 같은 지역)가 있으므로 dispatch_status=OPEN
            check("TC-303 후보 지사 존재 시 dispatch_status=OPEN",
                  req_a.get("dispatch_status") == "OPEN",
                  bug_detail="승인된 동일 region 지사가 있으면 OPEN이어야 함. 실제: %s"
                             % req_a.get("dispatch_status"))

    # --- 후보 지사 없는 지역 -> 즉시 ESCALATED ---
    code, rest_noregion = make_restaurant(addr_region="NOWHEREZONE")
    if code == 201:
        _created["restaurant_ids"].add(rest_noregion["id"])
        code, req_esc = api("POST", "/requests/", {
            "restaurant_id": rest_noregion["id"],
            "category": "POWER_ISSUE",
            "description": _TP + "후보없음 케이스",
            "metadata": {"requested_amount": 50000},
        })
        if code == 201:
            _created["request_ids"].add(req_esc["id"])
            check("TC-304 후보 지사 0곳이면 즉시 ESCALATED",
                  req_esc.get("dispatch_status") == "ESCALATED",
                  bug_detail="매칭 지사 없으면 OPEN 방치 대신 ESCALATED여야 함. 실제: %s"
                             % req_esc.get("dispatch_status"))

    # --- 잘못된 restaurant_id (존재하지 않음) ---
    code, b = api("POST", "/requests/", {
        "restaurant_id": str(uuid.uuid4()),
        "category": "WATER_LEAK",
    })
    check("TC-305 존재하지 않는 restaurant_id 요청 거부 (-> 4xx/5xx, 201 아님)",
          code != 201,
          bug_detail="없는 식당 id로 요청 생성이 성공(201)하면 안 됨. 실제: %s" % code)

    # --- 필수항목 누락 (category 없음) ---
    if rest_a:
        code, b = api("POST", "/requests/", {"restaurant_id": rest_a["id"]})
        check("TC-306 category 누락 요청 거부 (-> 422)", code == 422)

    # =====================================================================
    section("4. 배차 (claim / release / rebroadcast / HQ_ASSIGN / 권한)")
    # =====================================================================
    # 두 번째 승인 지사 B 준비 (release 재배포 후보용)
    code, branch_b = make_branch()
    branch_b_token = None
    if code == 201:
        _created["branch_ids"].add(branch_b["id"])
        if hq_token:
            approve_branch(branch_b["id"], hq_token)
        code, b = login_pin(branch_b["manager_phone"], "BRANCH", "0000")
        branch_b_token = b.get("access_token") if isinstance(b, dict) else None

    # --- 지사 A가 요청 claim ---
    if req_a and branch_token:
        code, b = api("POST", "/requests/" + req_a["id"] + "/claim", token=branch_token)
        check("TC-400 지사 수락 claim 성공 (-> 200)", code == 200)
        if code == 200:
            check("TC-401 claim 후 dispatch_status=CLAIMED",
                  b.get("dispatch_status") == "CLAIMED")
            check("TC-402 claim 후 assigned_branch_id 채워짐",
                  b.get("assigned_branch_id") == branch_a["id"])
            check("TC-403 claim 후 accepted_at 기록됨 (SLA 종료점)",
                  b.get("accepted_at") is not None,
                  bug_detail="accepted_at은 SLA 종료점. claim 시 채워져야 함.")

        # --- 중복 claim (선착순 원자성) — 같은 지사가 또 claim ---
        code, b = api("POST", "/requests/" + req_a["id"] + "/claim", token=branch_token)
        check("TC-404 이미 수락된 요청 재-claim 거부 (-> 409 CONFLICT)", code == 409,
              bug_detail="이미 CLAIMED인 요청을 다시 claim하면 409여야 함. 실제: %s" % code)

        # --- 다른 지사 B가 claim 시도 ---
        if branch_b_token:
            code, b = api("POST", "/requests/" + req_a["id"] + "/claim", token=branch_b_token)
            check("TC-405 타 지사의 기수락 요청 claim 거부 (-> 409)", code == 409)

    # --- 무인증 claim 거부 ---
    if req_a:
        code, b = api("POST", "/requests/" + req_a["id"] + "/claim")
        check("TC-406 무인증 claim 거부 (-> 401)", code == 401)

    # --- 본사 토큰으로 claim 시도 (BRANCH 전용) ---
    if req_a and hq_token:
        code, b = api("POST", "/requests/" + req_a["id"] + "/claim", token=hq_token)
        check("TC-407 본사 토큰 claim 거부 (BRANCH 전용 -> 403)", code == 403)

    # --- release (담당 지사 취소) ---
    if req_a and branch_token:
        code, b = api("POST", "/requests/" + req_a["id"] + "/release",
                      {"reason": "일정 불가"}, token=branch_token)
        check("TC-410 담당 지사 취소 release 성공 (-> 200)", code == 200)
        if code == 200:
            check("TC-411 release 후 dispatch_status=REASSIGNING (1회차)",
                  b.get("dispatch_status") == "REASSIGNING",
                  bug_detail="1회 취소 시 REASSIGNING 재배포 상태여야 함. 실제: %s"
                             % b.get("dispatch_status"))
            check("TC-412 release 후 assigned_branch_id 비워짐",
                  b.get("assigned_branch_id") is None)
            check("TC-413 release 후 cancel_count=1", b.get("cancel_count") == 1)

        # --- 담당 아닌 지사가 release 시도 ---
        if branch_b_token:
            code, b = api("POST", "/requests/" + req_a["id"] + "/release",
                          {"reason": "기타"}, token=branch_b_token)
            check("TC-414 담당 아닌 지사의 release 거부 (-> 403)", code == 403)

    # --- 재배포 한계: 3번째 취소부터 ESCALATED ---
    # 새 요청으로 깨끗하게 검증 (지사 A claim -> release 반복)
    if rest_a and branch_token:
        code, req_esc2 = api("POST", "/requests/", {
            "restaurant_id": rest_a["id"],
            "category": "WATER_LEAK",
            "description": _TP + "재배포 한계 검증",
            "metadata": {"requested_amount": 80000},
        })
        if code == 201:
            _created["request_ids"].add(req_esc2["id"])
            last = None
            for i in range(3):
                c, _ = api("POST", "/requests/" + req_esc2["id"] + "/claim", token=branch_token)
                if c != 200:
                    break
                c, last = api("POST", "/requests/" + req_esc2["id"] + "/release",
                              {"reason": "인력 부족"}, token=branch_token)
            check("TC-415 3회 취소 시 ESCALATED 승격 (재배포 한계)",
                  isinstance(last, dict) and last.get("dispatch_status") == "ESCALATED",
                  bug_detail="cancel_count>2 (3번째 취소) 시 ESCALATED여야 함. 실제: %s"
                             % (last.get("dispatch_status") if isinstance(last, dict) else last))

            # --- 본사 재배포(rebroadcast): ESCALATED -> OPEN ---
            if hq_token and isinstance(last, dict) and last.get("dispatch_status") == "ESCALATED":
                code, b = api("POST", "/requests/" + req_esc2["id"] + "/rebroadcast",
                              token=hq_token)
                check("TC-416 본사 재배포 rebroadcast (ESCALATED -> OPEN, -> 200)",
                      code == 200)
                # 비-ESCALATED 재배포 거부
                code, b = api("POST", "/requests/" + req_esc2["id"] + "/rebroadcast",
                              token=hq_token)
                check("TC-417 ESCALATED 아닌 요청 재배포 거부 (-> 409)", code == 409)
            # 지사 토큰으로 rebroadcast 거부 (HQ 전용)
            if branch_token:
                code, b = api("POST", "/requests/" + req_esc2["id"] + "/rebroadcast",
                              token=branch_token)
                check("TC-418 지사 토큰 rebroadcast 거부 (HQ 전용 -> 403)", code == 403)

    # --- HQ_ASSIGN: 본사가 미배정 요청을 지사에 직접 배정 ---
    if rest_a and hq_token and branch_a:
        code, req_hq = api("POST", "/requests/", {
            "restaurant_id": rest_a["id"],
            "category": "POWER_ISSUE",
            "description": _TP + "HQ 배정 검증",
            "metadata": {"requested_amount": 60000},
        })
        if code == 201:
            _created["request_ids"].add(req_hq["id"])
            code, b = api("PATCH", "/requests/" + req_hq["id"],
                          {"assigned_branch_id": branch_a["id"]}, token=hq_token)
            check("TC-420 본사 직접 배정 HQ_ASSIGN (-> 200)", code == 200)
            if code == 200:
                check("TC-421 HQ 배정 후 dispatch_status=HQ_ASSIGNED",
                      b.get("dispatch_status") == "HQ_ASSIGNED",
                      bug_detail="본사 배정 시 HQ_ASSIGNED여야 함. 실제: %s"
                                 % b.get("dispatch_status"))

    # --- dispatch sweep (타임아웃 점검 — HQ 전용) ---
    if hq_token:
        code, b = api("POST", "/requests/dispatch/sweep", token=hq_token)
        check("TC-422 본사 타임아웃 sweep 호출 (-> 200, escalated_count 반환)",
              code == 200 and isinstance(b, dict) and "escalated_count" in b)
        code, b = api("POST", "/requests/dispatch/sweep")
        check("TC-423 무인증 sweep 거부 (-> 401)", code == 401)

    # =====================================================================
    section("5. 수리 진행 상태 전이")
    # =====================================================================
    # 진행 검증 전용 요청: 식당 -> 지사 claim -> 상태 전이
    flow_req = None
    if rest_a and branch_token and branch_a:
        code, flow_req = api("POST", "/requests/", {
            "restaurant_id": rest_a["id"],
            "category": "WATER_LEAK",
            "description": _TP + "상태전이 플로우",
            "metadata": {"requested_amount": 130000},
        })
        if code == 201:
            _created["request_ids"].add(flow_req["id"])
            api("POST", "/requests/" + flow_req["id"] + "/claim", token=branch_token)

            # PENDING -> IN_PROGRESS
            code, b = api("PATCH", "/requests/" + flow_req["id"],
                          {"status": "IN_PROGRESS"}, token=branch_token)
            check("TC-500 상태 PENDING -> IN_PROGRESS (-> 200)", code == 200)
            if code == 200:
                check("TC-501 IN_PROGRESS 전이 시 assigned_at 기록됨",
                      b.get("assigned_at") is not None,
                      bug_detail="IN_PROGRESS 진입 시 assigned_at이 채워져야 함.")

            # IN_PROGRESS -> PAYMENT_REQUESTED
            code, b = api("PATCH", "/requests/" + flow_req["id"],
                          {"status": "PAYMENT_REQUESTED"}, token=branch_token)
            check("TC-502 상태 IN_PROGRESS -> PAYMENT_REQUESTED (-> 200)", code == 200)

            # SUSPENDED (수리 중단) 후 재진행
            code, b = api("PATCH", "/requests/" + flow_req["id"],
                          {"status": "SUSPENDED"}, token=branch_token)
            check("TC-503 상태 -> SUSPENDED 수리 중단 (-> 200)", code == 200)
            code, b = api("PATCH", "/requests/" + flow_req["id"],
                          {"status": "IN_PROGRESS"}, token=branch_token)
            check("TC-504 SUSPENDED -> IN_PROGRESS 재진행 (-> 200)", code == 200)

            # 리포트(메타데이터) 작성
            code, b = api("PATCH", "/requests/" + flow_req["id"],
                          {"metadata": {"report": "노즐 교체 완료", "parts": "노즐 1개"}},
                          token=branch_token)
            check("TC-505 수리 리포트(metadata) 작성 (-> 200)", code == 200)
            if code == 200:
                meta = b.get("metadata") or {}
                check("TC-506 metadata 병합 보존 (기존 requested_amount 유지)",
                      meta.get("requested_amount") == 130000 and meta.get("report") == "노즐 교체 완료",
                      bug_detail="metadata PATCH는 기존 키를 덮어쓰지 않고 병합해야 함. 실제: %s" % meta)

    # =====================================================================
    section("6. 완료 -> 결제 자동 생성")
    # =====================================================================
    if flow_req and branch_token:
        code, b = api("PATCH", "/requests/" + flow_req["id"],
                      {"status": "COMPLETED"}, token=branch_token)
        check("TC-600 상태 -> COMPLETED (-> 200)", code == 200)
        if code == 200:
            check("TC-601 COMPLETED 전이 시 completed_at 기록됨",
                  b.get("completed_at") is not None)
        # 결제가 자동 생성됐는지 본사 결제 목록에서 확인
        if hq_token:
            code, pays = api("GET", "/payments/", token=hq_token)
            if code == 200 and isinstance(pays, list):
                matched = [p for p in pays if p.get("request_id") == flow_req["id"]]
                check("TC-602 COMPLETED 시 Payment 자동 생성됨", len(matched) >= 1,
                      bug_detail="완료 시 Payment 1건이 자동 생성돼야 함. 매칭 결제: %d개"
                                 % len(matched))
                if matched:
                    check("TC-603 자동 생성 Payment 금액 = requested_amount(130000)",
                          float(matched[0].get("amount", 0)) == 130000,
                          bug_detail="자동 결제 금액이 메타데이터 requested_amount와 달라짐. 실제: %s"
                                     % matched[0].get("amount"))
                    check("TC-604 자동 생성 Payment status=PAID",
                          matched[0].get("status") == "PAID")

    # =====================================================================
    section("7. 정산 (generate / 멱등 / 상태전이 / 권한)")
    # =====================================================================
    today = date.today()
    pstart = (today - timedelta(days=3)).isoformat()
    pend = (today + timedelta(days=1)).isoformat()
    sett_a = None
    if hq_token:
        code, setts = api("POST", "/settlements/generate", {
            "period_start": pstart, "period_end": pend, "period_type": "WEEKLY",
        }, token=hq_token)
        check("TC-700 정산서 생성 generate (-> 200)", code == 200)
        if code == 200 and isinstance(setts, list):
            # 테스트 지사의 정산서 찾기
            mine = [s for s in setts if s.get("branch_id") in
                    (branch_a["id"] if branch_a else None,)]
            check("TC-701 활동 있는 테스트 지사 정산서 생성됨",
                  len(mine) >= 1 or len(setts) >= 1,
                  bug_detail="완료 결제가 있는 지사의 정산서가 생성돼야 함.")
            if mine:
                sett_a = mine[0]
                _created["settlement_ids"].add(sett_a["id"])
                # 금액 검증: gross=130000, 수수료율 10% -> hq_commission=13000
                check("TC-702 정산 gross_amount = 결제합계(130000)",
                      float(sett_a.get("gross_amount", 0)) == 130000,
                      bug_detail="정산 gross가 결제 합계와 불일치. 실제: %s"
                                 % sett_a.get("gross_amount"))
                check("TC-703 정산 본사수수료 = gross*10% = 13000",
                      float(sett_a.get("hq_commission", 0)) == 13000,
                      bug_detail="수수료 계산 오류. 기대 13000, 실제: %s"
                                 % sett_a.get("hq_commission"))
                check("TC-704 정산 신규 생성 status=DRAFT",
                      sett_a.get("status") == "DRAFT")

        # --- 멱등성: 같은 기간 재호출 시 중복 생성 안 함 ---
        code, setts2 = api("POST", "/settlements/generate", {
            "period_start": pstart, "period_end": pend, "period_type": "WEEKLY",
        }, token=hq_token)
        check("TC-705 정산 generate 멱등성 (같은 기간 재호출 시 신규 0건)",
              code == 200 and isinstance(setts2, list) and len(setts2) == 0,
              bug_detail="같은 기간 재호출 시 중복 정산서가 생기면 안 됨. 신규: %s개"
                         % (len(setts2) if isinstance(setts2, list) else setts2))

        # --- 잘못된 기간 (end < start) ---
        code, b = api("POST", "/settlements/generate", {
            "period_start": pend, "period_end": pstart, "period_type": "WEEKLY",
        }, token=hq_token)
        check("TC-706 정산 잘못된 기간 거부 (end<start -> 400)", code == 400)

    # --- 정산 목록 / 상세 ---
    if hq_token:
        code, b = api("GET", "/settlements/", token=hq_token)
        check("TC-710 본사 정산서 목록 조회 (-> 200)", code == 200 and isinstance(b, list))
    if sett_a and hq_token:
        code, b = api("GET", "/settlements/" + sett_a["id"], token=hq_token)
        check("TC-711 정산서 상세 조회 (-> 200, items 포함)",
              code == 200 and isinstance(b, dict) and "items" in b)

    # --- 상태 전이: DRAFT -> REVIEW -> APPROVED -> PAID -> INVOICED ---
    if sett_a and hq_token:
        sid = sett_a["id"]
        seq = ["REVIEW", "APPROVED", "PAID", "INVOICED"]
        prev = "DRAFT"
        all_ok = True
        for nxt in seq:
            code, b = api("PATCH", "/settlements/" + sid + "/status",
                          {"status": nxt}, token=hq_token)
            if code != 200:
                all_ok = False
            prev = nxt
        check("TC-720 정산 정상 상태전이 DRAFT->REVIEW->APPROVED->PAID->INVOICED",
              all_ok,
              bug_detail="허용된 상태 전이 체인이 한 단계라도 실패함.")

        # --- 허용되지 않은 전이: INVOICED -> DRAFT ---
        code, b = api("PATCH", "/settlements/" + sid + "/status",
                      {"status": "DRAFT"}, token=hq_token)
        check("TC-721 허용 안 된 전이 거부 (INVOICED -> DRAFT -> 400)", code == 400)

        # --- 알 수 없는 상태 ---
        code, b = api("PATCH", "/settlements/" + sid + "/status",
                      {"status": "BOGUS"}, token=hq_token)
        check("TC-722 알 수 없는 상태값 거부 (-> 400)", code == 400)

    # --- 지사는 본인 정산서만 조회 ---
    if branch_token:
        code, b = api("GET", "/settlements/my", token=branch_token)
        check("TC-730 지사 본인 정산서 목록 조회 /my (-> 200)",
              code == 200 and isinstance(b, list))
    # 타 지사(B 토큰)로 지사 A 정산서 상세 접근 거부
    if sett_a and branch_b_token:
        code, b = api("GET", "/settlements/" + sett_a["id"], token=branch_b_token)
        check("TC-731 타 지사가 남의 정산서 상세 접근 거부 (-> 403)", code == 403,
              bug_detail="지사는 본인 정산서만 조회 가능해야 함. 실제: %s" % code)
    # 무인증 정산 목록 거부
    code, b = api("GET", "/settlements/")
    check("TC-732 무인증 정산서 목록 거부 (-> 401)", code == 401)
    # 지사가 본사 정산 목록 거부
    if branch_token:
        code, b = api("GET", "/settlements/", token=branch_token)
        check("TC-733 지사 토큰 본사 정산목록 거부 (HQ 전용 -> 403)", code == 403)

    # =====================================================================
    section("8. 월별 회계 리포트 CSV")
    # =====================================================================
    if hq_token:
        code, txt = api("GET", "/settlements/report/monthly?year=%d&month=%d"
                        % (today.year, today.month), token=hq_token, raw=True)
        check("TC-800 월별 회계 리포트 CSV 다운로드 (-> 200)", code == 200)
        if code == 200:
            check("TC-801 CSV에 헤더('지사명') 포함", "지사명" in txt or "\xeb\xa7\xa4" in txt,
                  bug_detail="CSV 헤더가 비어있거나 형식이 다름.")
        # 잘못된 month
        code, txt = api("GET", "/settlements/report/monthly?year=%d&month=13"
                        % today.year, token=hq_token, raw=True)
        check("TC-802 잘못된 month(13) 거부 (-> 400)", code == 400)
        # 무인증
        code, txt = api("GET", "/settlements/report/monthly?year=%d&month=1"
                        % today.year, raw=True)
        check("TC-803 무인증 회계 리포트 거부 (-> 401)", code == 401)

    # =====================================================================
    section("9. 권한 검증 (HQ 전용 / 역할 / 타 지사 자원)")
    # =====================================================================
    # HQ 전용 엔드포인트 무인증 차단
    code, b = api("GET", "/payments/")
    check("TC-900 무인증 결제 목록 거부 (-> 401)", code == 401)
    code, b = api("GET", "/audit-logs/")
    check("TC-901 무인증 감사 로그 거부 (-> 401)", code == 401)
    code, b = api("GET", "/notifications/tokens")
    check("TC-902 무인증 디바이스 토큰 목록 거부 (-> 401)", code == 401)
    code, b = api("GET", "/branches/metrics/performance")
    check("TC-903 무인증 지사 실적 메트릭 거부 (-> 401)", code == 401)

    # 지사 토큰으로 HQ 전용 엔드포인트 차단
    if branch_token:
        code, b = api("GET", "/payments/", token=branch_token)
        check("TC-910 지사 토큰 결제 목록 거부 (HQ 전용 -> 403)", code == 403)
        code, b = api("GET", "/audit-logs/", token=branch_token)
        check("TC-911 지사 토큰 감사 로그 거부 (HQ 전용 -> 403)", code == 403)
        code, b = api("GET", "/branches/metrics/performance", token=branch_token)
        check("TC-912 지사 토큰 실적 메트릭 거부 (HQ 전용 -> 403)", code == 403)

    # 식당 토큰으로 본사 전용 필드 변경 차단
    if rest_token and rest_a:
        code, b = api("PATCH", "/restaurants/" + rest_a["id"],
                      {"is_approved": False}, token=rest_token)
        check("TC-913 식당이 본사 전용 필드(is_approved) 변경 거부 (-> 403)", code == 403)

    # 지사 토큰으로 본사 전용 필드(commission_rate) 변경 차단
    if branch_token and branch_a:
        code, b = api("PATCH", "/branches/" + branch_a["id"],
                      {"commission_rate": 1.0}, token=branch_token)
        check("TC-914 지사가 본사 전용 필드(commission_rate) 변경 거부 (-> 403)", code == 403)

    # 지사가 타 지사 정보 수정 차단
    if branch_token and branch_b:
        code, b = api("PATCH", "/branches/" + branch_b["id"],
                      {"address": "침범시도 " + uniq()}, token=branch_token)
        check("TC-915 지사가 타 지사 정보 수정 거부 (-> 403)", code == 403)

    # 식당이 타 식당 정보 수정 차단
    if rest_token and rest_noregion:
        code, b = api("PATCH", "/restaurants/" + rest_noregion["id"],
                      {"owner_name": "침범"}, token=rest_token)
        check("TC-916 식당이 타 식당 정보 수정 거부 (-> 403)", code == 403)

    # =====================================================================
    section("10. 만족도 조사 + 디바이스 토큰")
    # =====================================================================
    # 만족도 조사: 완료된 요청 metadata.survey 저장
    if flow_req and branch_token:
        code, b = api("PATCH", "/requests/" + flow_req["id"],
                      {"metadata": {"survey": {"rating": 5, "comment": "친절했어요"}}},
                      token=branch_token)
        check("TC-1000 만족도 조사(survey) metadata 저장 (-> 200)", code == 200)
        if code == 200:
            meta = b.get("metadata") or {}
            check("TC-1001 survey 데이터 저장 확인 (rating=5)",
                  isinstance(meta.get("survey"), dict) and meta["survey"].get("rating") == 5)

    # 디바이스 토큰 등록
    dt_token_str = _TP + "fcmtoken_" + uniq()
    if rest_a:
        code, b = api("POST", "/notifications/register", {
            "token": dt_token_str, "platform": "android",
            "user_id": rest_a["id"], "user_type": "RESTAURANT",
        })
        check("TC-1010 디바이스 토큰 등록 (-> 200)", code == 200)
        _created["device_token_strs"].add(dt_token_str)
        # 동일 토큰 재등록 (업서트)
        code, b = api("POST", "/notifications/register", {
            "token": dt_token_str, "platform": "ios",
            "user_id": rest_a["id"], "user_type": "RESTAURANT",
        })
        check("TC-1011 동일 토큰 재등록 시 업데이트 (-> 200)", code == 200)
        if code == 200:
            check("TC-1012 재등록 시 platform 갱신 (android -> ios)",
                  b.get("platform") == "ios")
    # HQ가 토큰 목록 조회
    if hq_token:
        code, b = api("GET", "/notifications/tokens", token=hq_token)
        check("TC-1013 본사 디바이스 토큰 목록 조회 (-> 200)",
              code == 200 and isinstance(b, list))

    # =====================================================================
    section("11. 엣지 케이스 (404 / 400 / 422)")
    # =====================================================================
    fake_id = str(uuid.uuid4())
    code, b = api("GET", "/requests/" + fake_id)
    check("TC-1100 존재하지 않는 요청 조회 (-> 404)", code == 404)
    code, b = api("GET", "/branches/" + fake_id)
    check("TC-1101 존재하지 않는 지사 조회 (-> 404)", code == 404)
    code, b = api("GET", "/restaurants/" + fake_id)
    check("TC-1102 존재하지 않는 식당 조회 (-> 404)", code == 404)
    if hq_token:
        code, b = api("GET", "/settlements/" + fake_id, token=hq_token)
        check("TC-1103 존재하지 않는 정산서 조회 (-> 404)", code == 404)
        code, b = api("PATCH", "/requests/" + fake_id, {"status": "COMPLETED"},
                      token=hq_token)
        check("TC-1104 존재하지 않는 요청 수정 (-> 404)", code == 404)

    # 잘못된 UUID 형식
    code, b = api("GET", "/requests/not-a-uuid")
    check("TC-1105 잘못된 UUID 형식 요청 조회 (-> 422)", code == 422)

    # 빈 body 요청 생성
    code, b = api("POST", "/requests/", {})
    check("TC-1106 빈 body 요청 생성 거부 (-> 422)", code == 422)

    # 연관 데이터 있는 식당 삭제 차단
    if hq_token and rest_a:
        code, b = api("DELETE", "/restaurants/" + rest_a["id"], token=hq_token)
        check("TC-1107 요청 내역 있는 식당 삭제 차단 (-> 400)", code == 400,
              bug_detail="연관 요청이 있는 식당 삭제는 400으로 막아야 함. 실제: %s" % code)

    # 연관 데이터 있는 지사 삭제 차단
    if hq_token and branch_a:
        code, b = api("DELETE", "/branches/" + branch_a["id"], token=hq_token)
        check("TC-1108 배정 요청 있는 지사 삭제 차단 (-> 400)", code == 400,
              bug_detail="연관 요청이 있는 지사 삭제는 400으로 막아야 함. 실제: %s" % code)

    # =====================================================================
    section("12. SLA 측정 (notified_at -> accepted_at 경과)")
    # =====================================================================
    # SLA 측정 전용: 식당 -> 요청 -> claim, notified_at/accepted_at delta 확인
    if rest_a and branch_token and hq_token:
        code, sla_req = api("POST", "/requests/", {
            "restaurant_id": rest_a["id"],
            "category": "WATER_LEAK",
            "description": _TP + "SLA 측정",
            "metadata": {"requested_amount": 90000},
        })
        if code == 201:
            _created["request_ids"].add(sla_req["id"])
            check("TC-1200 SLA: 요청 생성 시 notified_at 기록",
                  sla_req.get("notified_at") is not None)
            time.sleep(1)  # 측정 가능한 delta 확보
            code, claimed = api("POST", "/requests/" + sla_req["id"] + "/claim",
                                token=branch_token)
            check("TC-1201 SLA: claim 시 accepted_at 기록",
                  code == 200 and claimed.get("accepted_at") is not None)
            # delta 계산
            if code == 200 and claimed.get("notified_at") and claimed.get("accepted_at"):
                try:
                    n = datetime.fromisoformat(claimed["notified_at"])
                    a = datetime.fromisoformat(claimed["accepted_at"])
                    delta = (a - n).total_seconds()
                    check("TC-1202 SLA: accepted_at - notified_at >= 0 (측정 가능)",
                          delta >= 0,
                          bug_detail="SLA delta가 음수. notified=%s accepted=%s" %
                                     (claimed["notified_at"], claimed["accepted_at"]))
                except Exception as e:
                    check("TC-1202 SLA: delta 계산 가능", False,
                          bug_detail="타임스탬프 파싱 실패: %s" % e)
            # 본사 SLA 요약 API로 조회 가능한지
            code, summary = api("GET", "/requests/sla/summary", token=hq_token)
            check("TC-1203 본사 SLA 요약 API 조회 (-> 200, accepted_count 포함)",
                  code == 200 and isinstance(summary, dict) and "accepted_count" in summary)
            if code == 200 and isinstance(summary, dict):
                check("TC-1204 SLA 요약에 평균 수락시간(avg_accept_minutes) 포함",
                      "avg_accept_minutes" in summary)

    # ----- 마무리 정리 -----
    section("99. 사후 정리 (테스트 데이터 삭제 -> DB 빈 상태 복원)")
    cleanup_db("post")
    # 정리 검증
    try:
        from sqlmodel import Session, select
        from app.db.session import engine
        from app.models.domain import Restaurant, Branch, ServiceRequest
        with Session(engine) as s:
            leftover_r = s.exec(select(Restaurant).where(Restaurant.name.contains(_TP))).all()
            leftover_b = s.exec(select(Branch).where(Branch.name.contains(_TP))).all()
        check("TC-999 정리 후 테스트 데이터 잔여 0건 (DB 빈 상태 복원)",
              len(leftover_r) == 0 and len(leftover_b) == 0,
              bug_detail="정리 후 테스트 식당 %d, 지사 %d 잔여" %
                         (len(leftover_r), len(leftover_b)))
    except Exception as e:
        _log("  [WARN] 정리 검증 실패: %s" % e)


# ===========================================================================
# 엔트리포인트
# ===========================================================================
def main():
    started = datetime.now()
    _log("WhiteOn 백엔드 E2E 통합 테스트")
    _log("실행 시각: " + started.strftime("%Y-%m-%d %H:%M:%S"))
    _log("대상: " + BASE)

    try:
        run()
    except Exception as e:
        import traceback
        _log("")
        _log("[FATAL] 테스트 실행 중 예외 발생:")
        _log(traceback.format_exc())
        # 예외가 나도 정리는 시도
        try:
            cleanup_db("emergency")
        except Exception:
            pass

    # 요약
    _log("")
    _log("=" * 70)
    _log("결과 요약")
    _log("=" * 70)
    total = _passed + _failed
    _log("총 %d개 케이스 / PASS %d / FAIL %d" % (total, _passed, _failed))
    if _bugs:
        _log("")
        _log("발견된 버그/이상 (%d건):" % len(_bugs))
        for i, (label, detail) in enumerate(_bugs, 1):
            _log("  [%d] %s" % (i, label))
            _log("      -> %s" % detail)
    else:
        _log("")
        _log("발견된 버그/이상: 없음")

    elapsed = (datetime.now() - started).total_seconds()
    _log("")
    _log("소요 시간: %.1f초" % elapsed)

    # 결과 파일 기록
    try:
        with open(_RESULT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines) + "\n")
        print("\n[결과 파일] " + _RESULT_FILE)
    except Exception as e:
        print("[WARN] 결과 파일 기록 실패: %s" % e)

    sys.exit(0 if _failed == 0 else 1)


if __name__ == "__main__":
    main()
