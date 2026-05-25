FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_NO_CACHE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"

# 设置工作目录
WORKDIR /app

# 复制项目文件
COPY . /app

RUN uv sync --locked --no-dev \
 && groupadd --system --gid 1000 app \
 && useradd  --system --uid 1000 --gid 1000 --no-create-home --home /app app \
 && chown -R app:app /app

USER app:app

# 暴露应用端口
EXPOSE 8000

# 默认启动命令
CMD ["monitor-mcp-server"]
