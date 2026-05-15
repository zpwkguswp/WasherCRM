# 실행 계획서 2.1.5: 즉시 보안 강화 (Security Hardening)

**상태**: 🏗️ 진행 중
**담당**: Sonnet
**작업일**: 2026-05-12
**선행**: `scratch/aws_audit_20260512.md`에서 식별된 보안 이슈

---

## 1. 목표
2026-05-12 AWS 감사에서 발견된 보안 노출을 즉시 차단하고, 서버 재부팅 시 자동 복구 가능한 운영 구조를 갖춘다.

## 2. 해결 대상 이슈

| # | 이슈 | 위험 | 우선순위 |
| :--- | :--- | :--- | :--- |
| S1 | 백엔드 8000 포트가 `0.0.0.0`으로 바인딩되어 인터넷에 직접 노출 | Nginx 우회 가능, 스캐너 노출 | 🔴 최우선 |
| S2 | AWS Security Group의 8000 inbound 규칙 열려있음 | S1과 동일 (이중 차단 필요) | 🔴 최우선 |
| S3 | uvicorn이 nohup 단발 실행 — 재부팅 시 자동 기동 안 됨 | 가용성 | 🟡 |
| S4 | `serviceAccountKey.json` 권한 644 (그룹/other 읽기 가능) | 키 노출 위험 | 🟡 |
| S5 | `trading_bot.zip` (787MB) 불필요 디스크 점유 | 운영 부담 | 🟢 |
| S6 | `backend/venv_win/` Windows venv 잔재 | 운영 부담 | 🟢 |

## 3. 조치 내역

### S1: uvicorn을 127.0.0.1로 바인딩
- 기존 실행: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 변경 후: `uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Nginx는 동일 호스트에서 `proxy_pass http://127.0.0.1:8000`을 사용하므로 영향 없음.

### S2: AWS Security Group에서 8000 inbound 차단
- 대상 SG: `WhiteOn-SG`
- 제거할 규칙: TCP 8000 from 0.0.0.0/0
- 유지: 22 (SSH), 80 (HTTP), 443 (HTTPS) — 단 향후 22도 사용자 IP로 제한 권장

### S3: systemd 서비스 등록
- 파일: `/etc/systemd/system/washercrm-backend.service`
- 동작: 재부팅 자동 기동, 비정상 종료 시 자동 재시작(`Restart=on-failure`)
- ExecStart: `/home/ubuntu/backend/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- 기존 nohup 프로세스는 종료 후 systemd로 일원화

### S4: serviceAccountKey 권한 강화
- `chmod 600 /home/ubuntu/backend/serviceAccountKey.json`

### S5/S6: 디스크 정리
- `rm /home/ubuntu/trading_bot.zip`
- `rm -rf /home/ubuntu/backend/venv_win`
- `trading_bot/` 디렉토리는 사장님이 별도 운영 중이므로 보존

## 4. 완료 조건 (AC)
- [ ] `ss -tln | grep 8000` 결과가 `127.0.0.1:8000`만 표시 (0.0.0.0 안 보임)
- [ ] 외부에서 `curl http://13.124.100.75:8000/` → connection refused 또는 timeout
- [ ] 외부에서 `curl http://13.124.100.75/` → 200 OK (Nginx 정상)
- [ ] `systemctl status washercrm-backend` → active (running)
- [ ] 서버 재부팅 시뮬레이션 후 백엔드 자동 기동 확인 (선택)
- [ ] `ls -la /home/ubuntu/backend/serviceAccountKey.json` → `-rw-------` (600)
- [ ] `/home/ubuntu/trading_bot.zip` 삭제 확인

## 5. 롤백 계획
- systemd 서비스 비활성: `sudo systemctl disable --now washercrm-backend`
- 기존 nohup 실행 복원: `cd /home/ubuntu/backend && nohup ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > uvicorn.log 2>&1 &`
- SG에 8000 inbound 재추가 (AWS 콘솔)

## 6. 후속 작업
- §2.2 DB 통일 (다음 단계)
- §2.3 HTTPS 적용 (도메인 확보 후)
- 22번 SSH 포트도 본사 사무실/사장님 IP로 제한하는 작업 (Phase A 끝부분)
