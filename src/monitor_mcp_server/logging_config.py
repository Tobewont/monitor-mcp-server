#!/usr/bin/env python

import logging
import os
import sys

import structlog

from monitor_mcp_server import __version__

SERVICE_NAME = "monitor-mcp-server"

# 第三方库即使在本服务 LOG_LEVEL=DEBUG 时也保持安静的 logger 列表。
# 这些库 DEBUG 日志噪音极大（HTTP 报文体、连接复用细节、协议帧），
# 会淹没业务日志且容易泄漏敏感请求内容。
_NOISY_LIBS = ("httpx", "httpcore", "h11", "h2", "hpack",
               "asyncio", "urllib3", "fastmcp", "mcp")


def _inject_service_context(logger, method_name, event_dict):
    """structlog processor：为每条日志自动绑定 service / version 常量字段。"""
    event_dict.setdefault("service", SERVICE_NAME)
    event_dict.setdefault("version", __version__)
    return event_dict


def setup_logging() -> structlog.BoundLogger:
    """配置 MCP 服务器的结构化 JSON 日志。

    通过 LOG_LEVEL 环境变量控制日志级别（默认 INFO）。
    每条日志都会自动携带 service / version 字段便于聚合排查。

    Returns:
        配置好的 structlog 日志实例
    """
    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _inject_service_context,
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        context_class=dict,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=log_level,
    )

    # 把吵闹的第三方库提到 max(WARNING, 当前级别)，避免 DEBUG 时被淹没。
    quiet_level = max(log_level, logging.WARNING)
    for name in _NOISY_LIBS:
        logging.getLogger(name).setLevel(quiet_level)

    logger = structlog.get_logger(SERVICE_NAME)
    return logger


def get_logger() -> structlog.BoundLogger:
    """获取已配置的日志实例。

    Returns:
        配置好的 structlog 日志实例
    """
    return structlog.get_logger(SERVICE_NAME)
