#!/usr/bin/env python3
"""
部署脚本：将项目上传到服务器并启动
"""
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

HOST = os.getenv("DEPLOY_HOST", "121.199.15.69")
USER = os.getenv("DEPLOY_USER", "root")
PASSWORD = os.getenv("DEPLOY_PASSWORD", "")
PROJECT_DIR = Path(__file__).parent
REMOTE_DIR = "/root/novel-factory"

try:
    import paramiko
except ImportError:
    print("安装 paramiko...")
    os.system(f"{sys.executable} -m pip install paramiko -q")
    import paramiko


def ssh_connect():
    """建立 SSH 连接"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD)
    return client


def run_ssh(ssh, cmd, desc=""):
    """执行远程命令"""
    if desc:
        print(f"  {desc}...")
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if err:
        print(f"  [stderr] {err[:200]}")
    return out


def upload_file(sftp, local_path, remote_path):
    """上传单个文件"""
    try:
        sftp.put(str(local_path), remote_path)
        return True
    except Exception as e:
        print(f"  上传失败 {local_path}: {e}")
        return False


def main():
    print(f"部署 AI 小说工厂到 {HOST}...")
    print(f"本地目录: {PROJECT_DIR}")
    print(f"远程目录: {REMOTE_DIR}")

    ssh = ssh_connect()
    sftp = ssh.open_sftp()

    try:
        # Step 1: 创建远程目录
        print("\n[1/5] 创建远程目录...")
        run_ssh(ssh, f"mkdir -p {REMOTE_DIR}/src/ai {REMOTE_DIR}/src/feishu {REMOTE_DIR}/src/novel {REMOTE_DIR}/data/chapters")

        # Step 2: 上传文件
        print("\n[2/5] 上传项目文件...")

        # 需要上传的文件列表（排除敏感和临时文件）
        files_to_upload = [
            # 根目录
            "requirements.txt", "Dockerfile", "docker-compose.yml",
            "config.py", "main.py", "scheduler.py",
            # src/
            "src/__init__.py",
            "src/ai/__init__.py", "src/ai/client.py", "src/ai/editor.py",
            "src/ai/writer.py", "src/ai/prompts.py",
            "src/feishu/__init__.py", "src/feishu/auth.py",
            "src/feishu/wiki_reader.py", "src/feishu/wiki_writer.py",
            "src/novel/__init__.py", "src/novel/state.py",
            "src/novel/style.py", "src/novel/context.py",
            "src/pipeline.py",
            # 数据文件
            "data/style_profile.json", "data/original_novel.txt",
            "data/state.json",
        ]

        # 添加所有章节文件
        chapters_dir = PROJECT_DIR / "data" / "chapters"
        if chapters_dir.exists():
            for ch_file in chapters_dir.glob("chapter_*.txt"):
                rel_path = str(ch_file.relative_to(PROJECT_DIR)).replace("\\", "/")
                files_to_upload.append(rel_path)

        uploaded = 0
        for f in files_to_upload:
            local = PROJECT_DIR / f
            remote = f"{REMOTE_DIR}/{f.replace(chr(92), '/')}"
            if local.exists():
                if upload_file(sftp, local, remote):
                    uploaded += 1
            else:
                print(f"  跳过（不存在）: {f}")

        print(f"  上传完成: {uploaded}/{len(files_to_upload)} 个文件")

        # 上传 .env
        env_file = PROJECT_DIR / ".env"
        if env_file.exists():
            upload_file(sftp, env_file, f"{REMOTE_DIR}/.env")

        # Step 3: 构建 Docker 镜像
        print("\n[3/5] 构建 Docker 镜像...")
        run_ssh(ssh,
            f"cd {REMOTE_DIR} && docker-compose down 2>/dev/null; docker-compose build --no-cache 2>&1 | tail -20",
            "构建中"
        )

        # Step 4: 启动服务
        print("\n[4/5] 启动服务...")
        run_ssh(ssh, f"cd {REMOTE_DIR} && docker-compose up -d")

        # Step 5: 等待并验证
        print("\n[5/5] 验证服务...")
        time.sleep(3)
        logs = run_ssh(ssh, f"cd {REMOTE_DIR} && docker-compose logs --tail=20")
        print(f"  容器日志:\n{logs}")

        # 检查容器状态
        status = run_ssh(ssh, "docker ps --filter name=novel-factory --format '{{.Status}}'")
        print(f"  容器状态: {status.strip()}")

        # 运行状态检查
        print("\n检查小说项目状态...")
        status_out = run_ssh(ssh,
            f"cd {REMOTE_DIR} && docker exec novel-factory python main.py status 2>&1"
        )
        print(status_out[:1000])

        print("\n部署完成！")

    finally:
        sftp.close()
        ssh.close()


if __name__ == "__main__":
    main()
