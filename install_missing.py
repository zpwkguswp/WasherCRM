import paramiko

SERVER_IP = '13.124.100.75'
KEY_PATH = 'AWS_accesskey/WhiteOn-Key.pem'
USERNAME = 'ubuntu'

def install_missing_pkg():
    print(f"서버({SERVER_IP})에 누락된 패키지 설치 중...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SERVER_IP, username=USERNAME, key_filename=KEY_PATH)

    commands = [
        "pip3 install firebase-admin",
        "pkill -f uvicorn || true",
        "cd /home/ubuntu/backend && nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > uvicorn.log 2>&1 &"
    ]

    for cmd in commands:
        print(f"실행: {cmd}")
        stdin, stdout, stderr = ssh.exec_command(cmd)
        stdout.channel.recv_exit_status()
    
    ssh.close()
    print("패키지 설치 및 백엔드 재가동 완료.")

if __name__ == "__main__":
    install_missing_pkg()
