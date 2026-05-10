import paramiko
from scp import SCPClient
import os
import time
import zipfile

# 설정 정보
SERVER_IP = '13.124.100.75'
KEY_PATH = 'AWS_accesskey/WhiteOn-Key.pem'
USERNAME = 'ubuntu'

def zip_project():
    print("1. 프로젝트 파일 압축 중...")
    with zipfile.ZipFile('project.zip', 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk('backend'):
            for file in files:
                if '__pycache__' not in root and '.venv' not in root and '.db' not in file:
                    zipf.write(os.path.join(root, file))
        for root, dirs, files in os.walk('www'):
            for file in files:
                zipf.write(os.path.join(root, file))

def setup_remote():
    print(f"2. {SERVER_IP} 서버 접속 중...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    # 키 파일 권한 문제 방지 (Windows용 처리)
    ssh.connect(SERVER_IP, username=USERNAME, key_filename=KEY_PATH)
    
    with SCPClient(ssh.get_transport()) as scp:
        print("3. 파일 전송 중...")
        scp.put('project.zip', 'project.zip')

    print("4. 서버 환경 설정 및 패키지 설치 시작 (시간이 다소 소요될 수 있습니다)...")
    commands = [
        "sudo apt-get update",
        "sudo apt-get install -y python3-pip nginx unzip",
        "unzip -o project.zip",
        "cd backend && pip3 install -r requirements.txt",
        
        # Nginx 설정 작성
        """
sudo bash -c 'cat > /etc/nginx/sites-available/washercrm <<EOF
server {
    listen 80;
    server_name _;

    location / {
        root /home/ubuntu/www;
        index index.html;
        try_files \$uri \$uri/ /index.html;
    }

    location /api/v1 {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /static/ {
        alias /home/ubuntu/backend/app/static/;
    }
}
EOF'
        """,
        "sudo ln -sf /etc/nginx/sites-available/washercrm /etc/nginx/sites-enabled/",
        "sudo rm -f /etc/nginx/sites-enabled/default",
        "sudo chmod 755 /home/ubuntu",
        "sudo chmod -R 755 /home/ubuntu/www",
        "sudo chmod -R 755 /home/ubuntu/backend/app/static",
        "sudo systemctl restart nginx",
        
        # 백엔드 가동 (이미 실행 중이면 종료 후 재시작)
        "pkill -f uvicorn || true",
        "cd /home/ubuntu/backend && nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > uvicorn.log 2>&1 &"
    ]

    for cmd in commands:
        print(f"실행 중: {cmd[:50]}...")
        stdin, stdout, stderr = ssh.exec_command(cmd)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            print(f"오류 발생: {stderr.read().decode()}")

    print("\n--- 모든 설정 및 가동 완료! ---")
    print(f"웹 접속 주소: http://{SERVER_IP}")
    ssh.close()

if __name__ == "__main__":
    zip_project()
    setup_remote()
