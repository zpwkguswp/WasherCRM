import paramiko

SERVER_IP = '13.124.100.75'
KEY_PATH = 'AWS_accesskey/WhiteOn-Key.pem'
USERNAME = 'ubuntu'

def check_logs():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SERVER_IP, username=USERNAME, key_filename=KEY_PATH)

    print("--- Nginx Error Log ---")
    stdin, stdout, stderr = ssh.exec_command("sudo tail -n 20 /var/log/nginx/error.log")
    print(stdout.read().decode())

    print("\n--- Backend (Uvicorn) Log ---")
    stdin, stdout, stderr = ssh.exec_command("tail -n 20 /home/ubuntu/backend/uvicorn.log")
    print(stdout.read().decode())
    
    ssh.close()

if __name__ == "__main__":
    check_logs()
