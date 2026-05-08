FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    UV_NO_CACHE=1

# 设置工作目录
WORKDIR /app

# 复制项目文件
COPY . /app

# 使用uv安装依赖
RUN pip install 'uv>=0.5,<1.0' \
 && uv pip install --system . \
 && pip uninstall -y uv \
 && groupadd --system --gid 1000 app \
 && useradd  --system --uid 1000 --gid 1000 --no-create-home --home /app app \
 && chown -R app:app /app

USER app:app

# 暴露应用端口
EXPOSE 8000

# 默认启动命令
CMD ["monitor-mcp-server"]
