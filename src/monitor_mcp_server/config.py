"""配置定义与加载。"""

import os
import re
import logging
from typing import Optional
from dataclasses import dataclass
from enum import Enum

import dotenv

dotenv.load_dotenv()

DEFAULT_REQUEST_TIMEOUT = 30
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500
MAX_QUERY_LENGTH = 10000
DEFAULT_LABEL_SAMPLE_SIZE = 10
MAX_LABEL_SAMPLE_SIZE = 100

RETRY_MAX_ATTEMPTS = 3  # 最大重试次数（不含首次请求），总请求次数 = 1 + RETRY_MAX_ATTEMPTS
RETRY_BASE_DELAY = 0.5
RETRY_STATUS_CODES = {429, 502, 503, 504}

LABEL_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

SENSITIVE_QUERY_KEYS = frozenset({
    "token", "access_token", "api_key", "apikey", "apitoken",
    "password", "passwd", "secret", "authorization",
})


class TransportType(str, Enum):
    """支持的 MCP 服务器传输类型。

    - stdio: 标准输入输出，适用于 Claude Desktop / Cursor 等客户端直接调用
    - sse: Server-Sent Events，HTTP 长连接单向推送（MCP 早期协议）
    - streamable-http: 基于 HTTP 的双向流式传输（MCP 推荐协议)
    """
    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable-http"

    @classmethod
    def values(cls) -> list[str]:
        return [transport.value for transport in cls]


class BackendType(str, Enum):
    """支持的后端类型，用于路径前缀与 alerts/rules 路由适配。

    - prometheus: 原生 Prometheus，API 前缀 /api/v1；alerts/rules 走 RULER_URL or PROMETHEUS_URL
    - thanos: Thanos Query，API 前缀 /api/v1；alerts/rules 默认走 PROMETHEUS_URL 以获得聚合结果
              （RULER_URL 仅用于调试单一 Ruler 副本，默认被忽略）
    - mimir: Grafana Mimir，API 前缀 /prometheus/api/v1；强烈建议配 ORG_ID
    - victoriametrics: VictoriaMetrics，API 前缀 /api/v1；alerts/rules 建议通过 RULER_URL 指向 vmalert
    """
    PROMETHEUS = "prometheus"
    THANOS = "thanos"
    MIMIR = "mimir"
    VICTORIAMETRICS = "victoriametrics"

    @classmethod
    def values(cls) -> list[str]:
        return [backend.value for backend in cls]


def get_api_prefix(backend: str) -> str:
    """根据后端类型返回 API 路径前缀（不带尾部斜杠）。"""
    if backend == BackendType.MIMIR.value:
        return "/prometheus/api/v1"
    return "/api/v1"


@dataclass
class MCPServerConfig:
    """MCP 服务器传输配置。"""
    mcp_server_transport: Optional[str] = None
    mcp_bind_host: Optional[str] = None
    mcp_bind_port: Optional[int] = None

    def __post_init__(self):
        if not self.mcp_server_transport:
            raise ValueError("PROMETHEUS_MCP_SERVER_TRANSPORT 为必填项")
        if self.mcp_server_transport != TransportType.STDIO.value:
            if not self.mcp_bind_host:
                raise ValueError("PROMETHEUS_MCP_BIND_HOST 为必填项（非 stdio 模式）")
            if self.mcp_bind_port is None:
                raise ValueError("PROMETHEUS_MCP_BIND_PORT 为必填项（非 stdio 模式）")


@dataclass
class PrometheusConfig:
    """后端连接配置。

    支持 Prometheus / Thanos / Mimir / VictoriaMetrics。
    ruler_url 用于将 alerts/rules 请求路由到独立的 Ruler 组件。
    """
    url: Optional[str] = None
    ruler_url: Optional[str] = None
    backend_type: str = BackendType.PROMETHEUS.value
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    org_id: Optional[str] = None
    mcp_server_config: Optional[MCPServerConfig] = None


def _safe_parse_port(value: str, default: int = 8000) -> int:
    """安全解析端口号，非法值回退到默认端口并记录警告。"""
    try:
        port = int(value)
        if not (1 <= port <= 65535):
            logging.warning("PROMETHEUS_MCP_BIND_PORT 超出范围 (%s)，使用默认端口 %d", value, default)
            return default
        return port
    except (ValueError, TypeError):
        logging.warning("PROMETHEUS_MCP_BIND_PORT 不是有效整数 (%s)，使用默认端口 %d", value, default)
        return default


config = PrometheusConfig(
    url=os.environ.get("PROMETHEUS_URL"),
    ruler_url=os.environ.get("RULER_URL"),
    backend_type=os.environ.get("BACKEND_TYPE", BackendType.PROMETHEUS.value).lower(),
    username=os.environ.get("PROMETHEUS_USERNAME"),
    password=os.environ.get("PROMETHEUS_PASSWORD"),
    token=os.environ.get("PROMETHEUS_TOKEN"),
    org_id=os.environ.get("ORG_ID"),
    mcp_server_config=MCPServerConfig(
        mcp_server_transport=os.environ.get("PROMETHEUS_MCP_SERVER_TRANSPORT", "stdio").lower(),
        mcp_bind_host=os.environ.get("PROMETHEUS_MCP_BIND_HOST", "127.0.0.1"),
        mcp_bind_port=_safe_parse_port(os.environ.get("PROMETHEUS_MCP_BIND_PORT", "8000"))
    )
)
