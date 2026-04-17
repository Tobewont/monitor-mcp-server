"""Monitor MCP Server

基于 MCP（Model Context Protocol）协议的监控服务器，
为 AI 助手提供查询和分析 Prometheus / Thanos 指标的能力。
"""

try:
    from importlib.metadata import version
    __version__ = version("monitor_mcp_server")
except Exception:
    __version__ = "1.0.0"
