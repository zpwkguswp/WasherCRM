import boto3
import os
import time

# AWS 자격 증명 설정 (보안을 위해 하드코딩 금지)
# 로컬의 AWS_accesskey 폴더 내 CSV 파일을 참조하거나 환경변수를 설정하세요.
ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
SECRET_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
REGION = 'ap-northeast-2'

# 인증 정보가 환경변수에 없을 경우 경고
if not ACCESS_KEY or not SECRET_KEY:
    print("⚠️ 경고: AWS 인증 정보가 환경변수에 설정되지 않았습니다.")
    print("힌트: 'AWS_accesskey' 폴더의 CSV 파일을 확인하여 환경변수를 설정하거나 안전한 방식으로 로드하세요.")

ec2 = boto3.client(
    'ec2',
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    region_name=REGION
)

def deploy():
    print("--- AWS 인프라 구축 시작 ---")
    
    # 1. 키 페어 생성
    key_name = 'WhiteOn-Key'
    try:
        key_pair = ec2.create_key_pair(KeyName=key_name)
        with open(f"{key_name}.pem", "w") as f:
            f.write(key_pair['KeyMaterial'])
        print(f"1. 키 페어 생성 완료: {key_name}.pem")
    except Exception as e:
        if 'InvalidKeyPair.Duplicate' in str(e):
            print("1. 이미 존재하는 키 페어를 사용합니다.")
        else:
            print(f"1. 키 페어 오류: {e}")

    # 2. 보안 그룹 생성
    group_name = 'WhiteOn-SG'
    try:
        vpc_data = ec2.describe_vpcs()
        vpc_id = vpc_data['Vpcs'][0]['VpcId']
        
        sg = ec2.create_security_group(
            GroupName=group_name,
            Description='Security group for WhiteOn WasherCRM',
            VpcId=vpc_id
        )
        sg_id = sg['GroupId']
        
        # 보안 규칙 설정
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {'IpProtocol': 'tcp', 'FromPort': 22, 'ToPort': 22, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
                {'IpProtocol': 'tcp', 'FromPort': 80, 'ToPort': 80, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
                {'IpProtocol': 'tcp', 'FromPort': 443, 'ToPort': 443, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
                {'IpProtocol': 'tcp', 'FromPort': 8000, 'ToPort': 8000, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}
            ]
        )
        print(f"2. 보안 그룹 생성 완료: {sg_id}")
    except Exception as e:
        if 'InvalidGroup.Duplicate' in str(e):
            sg_data = ec2.describe_security_groups(GroupNames=[group_name])
            sg_id = sg_data['SecurityGroups'][0]['GroupId']
            print(f"2. 기존 보안 그룹 사용: {sg_id}")
        else:
            print(f"2. 보안 그룹 오류: {e}")
            return

    # 3. 최신 Ubuntu 22.04 AMI 찾기
    images = ec2.describe_images(
        Filters=[
            {'Name': 'name', 'Values': ['ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*']},
            {'Name': 'state', 'Values': ['available']}
        ],
        Owners=['099720109477'] # Canonical(Ubuntu) 공식 소유자 ID
    )
    # 최신 이미지 선택
    ami_id = sorted(images['Images'], key=lambda x: x['CreationDate'], reverse=True)[0]['ImageId']
    print(f"3. 최신 Ubuntu AMI 확인: {ami_id}")

    # 4. EC2 인스턴스 생성 (t3.micro)
    instance = ec2.run_instances(
        ImageId=ami_id,
        InstanceType='t3.micro',
        KeyName=key_name,
        SecurityGroupIds=[sg_id],
        MinCount=1,
        MaxCount=1,
        TagSpecifications=[{
            'ResourceType': 'instance',
            'Tags': [{'Key': 'Name', 'Value': 'WhiteOn-Server'}]
        }]
    )
    
    instance_id = instance['Instances'][0]['InstanceId']
    print(f"4. 인스턴스 생성 요청 완료: {instance_id}")

    # 5. 퍼블릭 IP 확인 (생성 대기)
    print("5. 서버 주소(IP) 할당 대기 중...")
    while True:
        desc = ec2.describe_instances(InstanceIds=[instance_id])
        state = desc['Reservations'][0]['Instances'][0]['State']['Name']
        if state == 'running':
            ip = desc['Reservations'][0]['Instances'][0].get('PublicIpAddress')
            if ip:
                print(f"--- 구축 완료! ---")
                print(f"서버 IP: {ip}")
                print(f"접속 명령어: ssh -i {key_name}.pem ubuntu@{ip}")
                break
        time.sleep(5)

if __name__ == "__main__":
    deploy()
