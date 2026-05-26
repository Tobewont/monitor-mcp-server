"""Prometheus HTTP 客户端，负责与 Prometheus / Thanos / Mimir / VictoriaMetrics API 通信。"""

import asyncio
import atexit
import json
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import dotenv
import httpx

from monitor_mcp_server.config import (
    config, PrometheusConfig, TransportType, BackendType, get_api_prefix,
    DEFAULT_REQUEST_TIMEOUT, MAX_QUERY_LENGTH,
    RETRY_MAX_ATTEMPTS, RETRY_BASE_DELAY, RETRY_STATUS_CODES,
    SENSITIVE_QUERY_KEYS,
)
from monitor_mcp_server.logging_config import get_logger

logger = get_logger()

# 共用 AsyncClient：复用连接池、HTTP/2（如安装了 h2 会自动启用）。
# 延迟创建以避免在无事件循环时初始化失败；所有工具共享同一个客户端。
_async_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()


async def _get_async_client() -> httpx.AsyncClient:
    """懒加载并返回全局 httpx.AsyncClient 实例。"""
    global _async_client
    if _async_client is None:
        async with _client_lock:
            if _async_client is None:
                _async_client = httpx.AsyncClient(
                    timeout=DEFAULT_REQUEST_TIMEOUT,
                    follow_redirects=True,
                    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
                )
    return _async_client


async def aclose_client() -> None:
    """显式关闭全局 AsyncClient（shutdown 或测试清理使用）。"""
    global _async_client
    if _async_client is not None:
        await _async_client.aclose()
        _async_client = None


def _sync_close_client() -> None:
    """atexit 回调：在解释器退出时尽力关闭客户端。

    如果已没有运行中的事件循环，调用 aclose 会抛异常，这时直接忽略——
    进程退出时底层 socket 会被 OS 回收。
    """
    global _async_client
    if _async_client is None:
        return
    try:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_async_client.aclose())
        finally:
            loop.close()
    except Exception:
        pass
    finally:
        _async_client = None


atexit.register(_sync_close_client)


def sanitize_url(url: str) -> str:
    """移除 URL 中的敏感信息，用于安全日志记录。

    清理范围：
    - netloc 里的 userinfo（`user:pass@host`）
    - query string 里落在 SENSITIVE_QUERY_KEYS 的键，值统一替换为 ***
    - fragment 里的 SENSITIVE_QUERY_KEYS（部分 OAuth 隐式流程将 token 放在 fragment）
    """
    def _mask_pairs(raw: str) -> str:
        items = parse_qsl(raw, keep_blank_values=True)
        sanitized = [
            (k, "***" if k.lower() in SENSITIVE_QUERY_KEYS else v)
            for k, v in items
        ]
        return urlencode(sanitized, safe="*")

    try:
        parsed = urlparse(url)
        netloc = parsed.netloc
        if parsed.username or parsed.password:
            host = parsed.hostname or ""
            if parsed.port:
                host = f"{host}:{parsed.port}"
            netloc = host

        query = _mask_pairs(parsed.query) if parsed.query else parsed.query
        fragment = parsed.fragment
        if fragment and "=" in fragment:
            fragment = _mask_pairs(fragment)

        if (netloc != parsed.netloc
                or query != parsed.query
                or fragment != parsed.fragment):
            return urlunparse(parsed._replace(
                netloc=netloc, query=query, fragment=fragment,
            ))
    except Exception:
        pass
    return url


def _parse_retry_after(value: Optional[str], cap_seconds: float = 60.0) -> Optional[float]:
    """解析 HTTP Retry-After 响应头，支持 delta-seconds 或 HTTP-date 两种格式。

    返回应等待的秒数（>=0），无法解析时返回 None。封顶 ``cap_seconds`` 防止
    上游返回过长（例如几小时）导致客户端长时间挂起。
    """
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        seconds = float(raw)
        if seconds < 0:
            return 0.0
        return min(seconds, cap_seconds)
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if target is None:
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    delta = (target - datetime.now(timezone.utc)).total_seconds()
    if delta <= 0:
        return 0.0
    return min(delta, cap_seconds)


def validate_query(query: str) -> None:
    """校验 PromQL 查询的基本合法性。

    拦截：空字符串、超长查询、包含控制字符（NUL/换行等易造成日志注入或上游异常）。
    """
    if not query or not query.strip():
        raise ValueError("查询语句不能为空")
    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError(f"查询语句过长（{len(query)} 字符），最大允许 {MAX_QUERY_LENGTH} 字符")
    for ch in query:
        code = ord(ch)
        if code < 0x20 and ch not in ("\t", "\n", "\r"):
            raise ValueError(f"查询语句包含不允许的控制字符: U+{code:04X}")
        if code == 0x7F:
            raise ValueError("查询语句包含不允许的 DEL 字符")


def build_error_response(
    message: str,
    *,
    error_type: str = "internal",
    **extra: Any,
) -> Dict[str, Any]:
    """构造结构化错误响应，所有工具共用同一形状。

    error_type 可选值建议：
    - upstream: 后端返回错误（API status!=success）
    - network: 网络异常、连接失败
    - timeout: 请求超时
    - auth: 认证相关错误
    - client: 客户端输入错误（例如非法参数）
    - internal: 未分类的内部异常
    """
    response = {"status": "error", "error": message, "error_type": error_type}
    response.update(extra)
    return response


def get_prometheus_auth() -> Tuple[Dict[str, str], Optional[Tuple[str, str]]]:
    """根据配置构建认证信息。

    优先级: Bearer Token > Basic Auth > 无认证

    Returns:
        (headers, auth) 元组：headers 为认证请求头，auth 为 Basic Auth 元组或 None
    """
    headers: Dict[str, str] = {}
    auth: Optional[Tuple[str, str]] = None
    if config.token:
        headers["Authorization"] = f"Bearer {config.token}"
    elif config.username and config.password:
        auth = (config.username, config.password)
    return headers, auth


async def make_prometheus_request(
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
    **_unused: Any,
) -> Any:
    """异步 API 请求（支持重试、连接池、多后端路由）。

    Args:
        endpoint: API 端点路径（如 'query'、'alerts'）
        params: 请求参数字典
        base_url: 目标服务地址，默认使用 config.url
        timeout: 请求超时秒数（默认使用 DEFAULT_REQUEST_TIMEOUT）

    Returns:
        API 响应中的 data 字段

    Raises:
        ValueError: URL 未配置、API 返回错误或 JSON 无法解析
        httpx.ConnectError / httpx.TimeoutException / httpx.HTTPStatusError:
            网络请求失败（各自对应连接/超时/HTTP 状态错误）
    """
    url_base = base_url or config.url
    if not url_base:
        logger.error("配置缺失", error="PROMETHEUS_URL 未设置")
        raise ValueError("Prometheus 配置缺失，请设置 PROMETHEUS_URL 环境变量。")

    effective_timeout = timeout if timeout is not None else DEFAULT_REQUEST_TIMEOUT
    api_prefix = get_api_prefix(config.backend_type)
    url = f"{url_base.rstrip('/')}{api_prefix}/{endpoint}"
    safe_url = sanitize_url(url)
    auth_headers, auth = get_prometheus_auth()
    headers = {**auth_headers}
    if config.org_id:
        headers["X-Scope-OrgID"] = config.org_id

    client = await _get_async_client()
    last_exception: Optional[BaseException] = None

    for attempt in range(RETRY_MAX_ATTEMPTS + 1):
        try:
            if attempt > 0:
                logger.debug("API 请求重试",
                             endpoint=endpoint, url=safe_url, attempt=attempt + 1)
            else:
                logger.debug("发送 API 请求",
                             endpoint=endpoint, url=safe_url, params=params)

            response = await client.get(
                url, params=params, auth=auth, headers=headers,
                timeout=effective_timeout,
            )

            if response.status_code in RETRY_STATUS_CODES and attempt < RETRY_MAX_ATTEMPTS:
                backoff = RETRY_BASE_DELAY * (2 ** attempt)
                # 优先使用上游 Retry-After（429/503 常见），与指数退避取较大值，
                # 既尊重上游限流策略，也保留指数退避的下限保护。
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                delay = max(backoff, retry_after) if retry_after is not None else backoff
                logger.warning("返回可重试状态码",
                               status_code=response.status_code,
                               attempt=attempt + 1, next_delay=delay,
                               retry_after=retry_after,
                               endpoint=endpoint)
                await asyncio.sleep(delay)
                continue

            response.raise_for_status()

            try:
                result = response.json()
            except json.JSONDecodeError as e:
                logger.error("无法解析响应 JSON",
                             endpoint=endpoint, url=safe_url, error=str(e))
                raise ValueError(f"Prometheus 返回了无效的 JSON 响应: {str(e)}")

            if not isinstance(result, dict) or result.get("status") != "success":
                error_msg = (result.get("error") if isinstance(result, dict) else None) or "未知错误"
                logger.error("API 返回错误", endpoint=endpoint, error=error_msg)
                raise ValueError(f"Prometheus API 错误: {error_msg}")

            data_field = result.get("data", {})
            if isinstance(data_field, dict):
                result_type = data_field.get("resultType")
            else:
                result_type = "list"
            logger.debug("API 请求成功",
                         endpoint=endpoint, result_type=result_type)
            return result["data"]

        except (httpx.ConnectError, httpx.TimeoutException) as e:
            last_exception = e
            if attempt < RETRY_MAX_ATTEMPTS:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning("连接失败，正在重试",
                               error=str(e), attempt=attempt + 1,
                               next_delay=delay, endpoint=endpoint)
                await asyncio.sleep(delay)
                continue
            logger.error("HTTP 请求失败（已用尽重试）",
                         endpoint=endpoint, url=safe_url, error=str(e))
            raise

        except httpx.HTTPStatusError as e:
            logger.error("HTTP 状态码异常",
                         endpoint=endpoint, url=safe_url,
                         status_code=e.response.status_code,
                         attempt=attempt + 1, error=str(e))
            raise

        except httpx.HTTPError as e:
            logger.error("HTTP 请求失败",
                         endpoint=endpoint, url=safe_url,
                         attempt=attempt + 1, error=str(e))
            raise

        except ValueError:
            raise

        except Exception as e:
            logger.error("请求发生异常",
                         endpoint=endpoint, url=safe_url,
                         attempt=attempt + 1, error=str(e))
            raise

    if last_exception:
        raise last_exception


def setup_environment(active_config: Optional[PrometheusConfig] = None) -> bool:
    """校验环境配置。

    Returns:
        配置有效返回 True，否则返回 False
    """
    cfg = active_config or config

    if dotenv.find_dotenv():
        logger.info("环境配置已加载", source=".env 文件")
    else:
        logger.info("环境配置已加载", source="环境变量", note="未找到 .env 文件")

    if not cfg.url:
        logger.error(
            "缺少必要配置",
            error="PROMETHEUS_URL 环境变量未设置",
            suggestion="请将其设置为你的 Prometheus 服务器地址",
            example="http://your-prometheus-server:9090"
        )
        return False

    if not cfg.url.startswith(("http://", "https://")):
        logger.error(
            "URL 格式无效",
            error="PROMETHEUS_URL 必须以 http:// 或 https:// 开头",
            current_value=sanitize_url(cfg.url)
        )
        return False

    if cfg.ruler_url and not cfg.ruler_url.startswith(("http://", "https://")):
        logger.error(
            "Ruler URL 格式无效",
            error="RULER_URL 必须以 http:// 或 https:// 开头",
            current_value=sanitize_url(cfg.ruler_url)
        )
        return False

    if cfg.backend_type not in BackendType.values():
        logger.error(
            "BACKEND_TYPE 无效",
            error=f"不支持的后端类型: {cfg.backend_type}",
            valid_values=BackendType.values(),
            example="prometheus"
        )
        return False

    if cfg.backend_type == BackendType.MIMIR.value and not cfg.org_id:
        logger.warning(
            "Mimir 后端强烈建议配置 ORG_ID",
            note="多租户场景下缺少 X-Scope-OrgID 可能导致 401/403"
        )

    if cfg.backend_type == BackendType.THANOS.value and cfg.ruler_url:
        logger.warning(
            "Thanos 模式下检测到 RULER_URL",
            note="建议删除 RULER_URL，改由 PROMETHEUS_URL（Thanos Query）聚合所有 Ruler 副本；"
                 "若 RULER_URL 指向单个 Ruler 实例，只能看到该副本负责分片的告警",
            ruler_url=sanitize_url(cfg.ruler_url)
        )

    if cfg.token and (cfg.username or cfg.password):
        logger.warning(
            "同时配置了 Bearer Token 与 Basic Auth",
            note="将优先使用 Bearer Token，Basic Auth (username/password) 会被忽略",
        )

    mcp_config = cfg.mcp_server_config
    if mcp_config:
        if str(mcp_config.mcp_server_transport).lower() not in TransportType.values():
            logger.error(
                "MCP 传输类型无效",
                error="PROMETHEUS_MCP_SERVER_TRANSPORT 环境变量值无效",
                suggestion="有效值：stdio、sse、streamable-http",
                example="stdio"
            )
            return False

        if not isinstance(mcp_config.mcp_bind_port, int):
            logger.error(
                "MCP 端口无效",
                error="PROMETHEUS_MCP_BIND_PORT 必须为整数",
                suggestion="请设置一个有效的端口号",
                example="8000"
            )
            return False

    monitor_agent = getattr(cfg, "monitor_agent", None)
    monitor_agent_enabled = getattr(monitor_agent, "enabled", False) is True
    if monitor_agent_enabled:
        required_fields = {
            "MONITOR_AGENT_S3_ENDPOINT_URL": monitor_agent.s3_endpoint_url,
            "MONITOR_AGENT_S3_BUCKET": monitor_agent.s3_bucket,
            "MONITOR_AGENT_S3_ACCESS_KEY_ID": monitor_agent.s3_access_key_id,
            "MONITOR_AGENT_S3_SECRET_ACCESS_KEY": monitor_agent.s3_secret_access_key,
        }
        missing = [name for name, value in required_fields.items() if not value]
        if missing:
            logger.error(
                "monitor-agent 配置管理缺少必要配置",
                missing=missing,
            )
            return False
        if "{ip}" not in monitor_agent.asset_query_template:
            logger.error(
                "MONITOR_AGENT_ASSET_QUERY_TEMPLATE 无效",
                error="模板必须包含 {ip} 占位符",
            )
            return False
        if "{ip}" not in monitor_agent.reload_url_template:
            logger.error(
                "MONITOR_AGENT_RELOAD_URL_TEMPLATE 无效",
                error="模板必须包含 {ip} 占位符",
            )
            return False
        backup_timezone = monitor_agent.backup_timezone.strip()
        if backup_timezone.upper() not in ("UTC", "Z") and not (
            len(backup_timezone) == 6
            and backup_timezone[0] in ("+", "-")
            and backup_timezone[3] == ":"
            and backup_timezone[1:3].isdigit()
            and backup_timezone[4:6].isdigit()
        ):
            logger.error(
                "MONITOR_AGENT_BACKUP_TIMEZONE 无效",
                error="必须是 UTC 或 +/-HH:MM 格式",
            )
            return False
        if monitor_agent.s3_addressing_style not in ("path", "virtual"):
            logger.error(
                "MONITOR_AGENT_S3_ADDRESSING_STYLE 无效",
                valid_values=["path", "virtual"],
            )
            return False
        if monitor_agent.reload_timeout <= 0:
            logger.error("MONITOR_AGENT_RELOAD_TIMEOUT 必须大于 0")
            return False
        if monitor_agent.backup_retention_days <= 0:
            logger.error("MONITOR_AGENT_BACKUP_RETENTION_DAYS 必须大于 0")
            return False

    auth_method = "none"
    if cfg.token:
        auth_method = "bearer_token"
    elif cfg.username and cfg.password:
        auth_method = "basic_auth"

    logger.info(
        "配置校验通过",
        backend_type=cfg.backend_type,
        query_url=sanitize_url(cfg.url),
        ruler_url=sanitize_url(cfg.ruler_url) if cfg.ruler_url else "(同 query_url)",
        api_prefix=get_api_prefix(cfg.backend_type),
        authentication=auth_method,
        org_id=cfg.org_id if cfg.org_id else None,
        monitor_agent_enabled=monitor_agent_enabled,
    )

    return True


# 公开 API 列表
__all__ = [
    "make_prometheus_request",
    "get_prometheus_auth",
    "setup_environment",
    "build_error_response",
    "sanitize_url",
    "validate_query",
    "aclose_client",
]

# 向后兼容别名（旧代码可能使用下划线前缀）
_sanitize_url = sanitize_url
_validate_query = validate_query
