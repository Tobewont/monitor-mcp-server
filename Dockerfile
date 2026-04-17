# 使用官方Python 3.12-slim 镜像作为基础镜像
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 安装uv
RUN pip install --no-cache-dir uv

# 复制项目文件
COPY . /app

# 使用uv安装依赖
RUN uv pip install --system -e . && \
    adduser --disabled-password --no-create-home appuser

USER appuser

ENV PYTHONUNBUFFERED=1

# 暴露应用端口
EXPOSE 8000

# 默认启动命令
CMD ["python", "main.py"]
