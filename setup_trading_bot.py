import paramiko
from scp import SCPClient
import os
import zipfile

# 설정 정보
SERVER_IP = '13.124.100.75'
KEY_PATH = 'AWS_accesskey/WhiteOn-Key.pem'
USERNAME = 'ubuntu'
BOT_LOCAL_DIR = r'C:\Users\zpwkg\Documents\TradingBot'
BOT_REMOTE_DIR = '/home/ubuntu/trading_bot'

def zip_bot():
    print("1. 트레이딩 봇 파일 압축 중 (용량 최적화)...")
    exclude_exts = ['.zip', '.csv', '.db', '.log', '.pkl', '.exe', '.bat']
    exclude_dirs = [
        '__pycache__', '.git', 'venv311', 'NVIDIA Corporation', 'data_storage',
        'v29_logs', 'v30_logs', 'v32_logs', 'v33_2_logs', 'v33_3_logs', 'v34_logs', 'v35_logs',
        'old', 'scratch', 'tests'
    ]
    
    with zipfile.ZipFile('trading_bot.zip', 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(BOT_LOCAL_DIR):
            # 제외 폴더 필터링
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for file in files:
                # 제외 확장자 필터링 (단, config.py나 중요 코드는 포함)
                if any(file.endswith(ext) for ext in exclude_exts) and 'weights' not in root:
                    continue
                
                rel_path = os.path.relpath(os.path.join(root, file), BOT_LOCAL_DIR)
                zipf.write(os.path.join(root, file), rel_path)

def setup_bot():
    print(f"2. {SERVER_IP} 서버 접속 중...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SERVER_IP, username=USERNAME, key_filename=KEY_PATH)
    
    with SCPClient(ssh.get_transport()) as scp:
        print("3. 봇 패키지 전송 중...")
        scp.put('trading_bot.zip', 'trading_bot.zip')

    print("4. 봇 환경 설정 및 실행 시작...")
    commands = [
        f"mkdir -p {BOT_REMOTE_DIR}",
        f"unzip -o trading_bot.zip -d {BOT_REMOTE_DIR}",
        "sudo apt-get update && sudo apt-get install -y python3-venv",
        f"cd {BOT_REMOTE_DIR} && python3 -m venv venv",
        f"cd {BOT_REMOTE_DIR} && ./venv/bin/pip install --upgrade pip",
        f"cd {BOT_REMOTE_DIR} && ./venv/bin/pip install -r requirements.txt",
        
        # 이전 실행 중인 봇 종료 (v35_live.py 기준)
        "pkill -f v35_live.py || true",
        
        # 봇 백그라운드 실행 (로그는 bot_live.log에 기록)
        f"cd {BOT_REMOTE_DIR} && nohup ./venv/bin/python v35_live.py > bot_live.log 2>&1 &"
    ]

    for cmd in commands:
        print(f"실행 중: {cmd[:60]}...")
        stdin, stdout, stderr = ssh.exec_command(cmd)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            print(f"알림/오류: {stderr.read().decode()}")

    print("\n--- 트레이딩 봇 배포 및 가동 완료! ---")
    print(f"로그 확인: ssh 접속 후 'tail -f {BOT_REMOTE_DIR}/bot_live.log' 실행")
    ssh.close()

if __name__ == "__main__":
    zip_bot()
    setup_bot()
