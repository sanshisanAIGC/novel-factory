FROM python:3.11-slim

# 设置时区
RUN apt-get update && apt-get install -y tzdata && rm -rf /var/lib/apt/lists/*
ENV TZ=Asia/Shanghai

# 设置工作目录
WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 确保数据目录存在
RUN mkdir -p /app/data/chapters

# 默认启动定时发布调度器
CMD ["python", "scheduler.py"]
