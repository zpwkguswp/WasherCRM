import paramiko

SERVER_IP = '13.124.100.75'
KEY_PATH = 'AWS_accesskey/WhiteOn-Key.pem'
USERNAME = 'ubuntu'

def fix_server():
    print(f"1. {SERVER_IP} 서버 접속 중...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SERVER_IP, username=USERNAME, key_filename=KEY_PATH)

    print("2. 권한 설정 및 백엔드 재가동 시작...")
    commands = [
        # Nginx 접근을 위한 홈 디렉토리 권한 개방
        "sudo chmod 755 /home/ubuntu",
        "sudo chmod -R 755 /home/ubuntu/www",
        
        # 백엔드 가동 (python3 -m uvicorn 방식 사용)
        "pkill -f uvicorn || true",
        "cd /home/ubuntu/backend && nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > uvicorn.log 2>&1 &",
        
        # Nginx 재시작
        "sudo systemctl restart nginx"
    ]

    for cmd in commands:
        print(f"실행 중: {cmd[:50]}...")
        stdin, stdout, stderr = ssh.exec_command(cmd)
        stdout.channel.recv_exit_status()

    print("\n--- 조치 완료! 10초 후 다시 접속해 보세요. ---")
    print(f"주소: http://{SERVER_IP}")
    ssh.close()

if __name__ == "__main__":
    fix_server()
