import paramiko

SERVER_IP = '13.124.100.75'
KEY_PATH = 'AWS_accesskey/WhiteOn-Key.pem'
USERNAME = 'ubuntu'

def init_db_on_server():
    print(f"서버({SERVER_IP}) DB 초기화 중...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SERVER_IP, username=USERNAME, key_filename=KEY_PATH)

    # SQLModel을 사용한 테이블 생성
    cmd = "cd /home/ubuntu/backend && python3 -c 'from sqlmodel import SQLModel; from app.db.session import engine; from app.models.domain import Branch, Restaurant, ServiceRequest; SQLModel.metadata.create_all(bind=engine); print(\"DB 초기화 완료\")'"
    stdin, stdout, stderr = ssh.exec_command(cmd)
    print(stdout.read().decode())
    print(stderr.read().decode())
    
    ssh.close()

if __name__ == "__main__":
    init_db_on_server()
