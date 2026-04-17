"""MCP 工具定义与服务器启动。"""

import json
import sys
from collections import Counter
from typing import Any, Dict, Optional, List
from datetime import datetime, timezone

from fastmcp import FastMCP

from monitor_mcp_server.config import (
    config, TransportType,
    DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, LABEL_NAME_RE,
    DEFAULT_LABEL_SAMPLE_SIZE, MAX_LABEL_SAMPLE_SIZE,
)
from monitor_mcp_server.client import (
    make_prometheus_request, _sanitize_url, _validate_query,
    setup_environment, build_error_response,
)
from monitor_mcp_server.logging_config import setup_logging, get_logger

mcp = FastMCP("Monitor MCP")
logger = get_logger()


def _get_ruler_url() -> Optional[str]:
    """获取告警/规则查询地址。

    策略：优先使用 RULER_URL，未配置时回退到 PROMETHEUS_URL。

    部署建议：
    - Prometheus / Thanos Query / Mimir (via Gateway)：统一入口已覆盖
      /api/v1/alerts 和 /api/v1/rules，**无需**配置 RULER_URL。
    - VictoriaMetrics：vmselect 不提供 alerts/rules，**需要**把 RULER_URL
      指向 vmalert。
    - 若 Thanos 场景误把 RULER_URL 指向某个 Ruler 实例，只会看到该副本分片
      的告警；建议删除 RULER_URL 让流量走 Thanos Query 以聚合全量。
    """
    return config.ruler_url or config.url


def _paginate(items: List[Any], page: int, page_size: int) -> Dict[str, Any]:
    """对列表做分页，page_size<=0 表示返回全部。"""
    total = len(items)
    if page_size <= 0:
        return {
            "items": items,
            "total": total,
            "page": 1,
            "page_size": total,
            "total_pages": 1,
        }
    total_pages = max(1, (total + page_size - 1) // page_size)
    actual_page = max(1, min(page, total_pages))
    start = (actual_page - 1) * page_size
    return {
        "items": items[start:start + page_size],
        "total": total,
        "page": actual_page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def _classify_exception(exc: BaseException) -> str:
    """把常见异常归类为 error_type。"""
    name = exc.__class__.__name__
    if "Timeout" in name:
        return "timeout"
    if "Connection" in name or "RequestException" in name or "HTTPError" in name:
        return "network"
    if isinstance(exc, ValueError):
        # ValueError 可能来自上游 API 错误（build in client.py），也可能来自校验
        msg = str(exc)
        if "API 错误" in msg or "无效的 JSON" in msg:
            return "upstream"
        return "client"
    return "internal"


def run_server():
    """Monitor MCP Server 主入口。"""
    setup_logging()

    if not setup_environment():
        logger.error("环境配置失败，退出")
        sys.exit(1)

    mcp_config = config.mcp_server_config
    transport = mcp_config.mcp_server_transport

    http_transports = [TransportType.SSE.value, TransportType.STREAMABLE_HTTP.value]

    if transport in http_transports:
        logger.info("启动 Monitor MCP Server",
                    transport=transport,
                    host=mcp_config.mcp_bind_host,
                    port=mcp_config.mcp_bind_port)
        mcp.run(transport=transport, host=mcp_config.mcp_bind_host, port=mcp_config.mcp_bind_port)
    else:
        logger.info("启动 Monitor MCP Server", transport=transport)
        mcp.run(transport=transport)


# ---------------------------------------------------------------------------
# MCP 工具
# ---------------------------------------------------------------------------

@mcp.tool(description="健康检查端点，用于状态验证")
async def health_check(target: str = "all") -> Dict[str, Any]:
    """检查后端连接的健康状态。

    Args:
        target: 检查目标，可选值：
            - "all"（默认）：同时检查 Prometheus 和 Ruler（若已配置）
            - "prometheus"：仅检查 Prometheus
            - "ruler"：仅检查 Ruler
    """
    valid_targets = ("all", "prometheus", "ruler")
    if target not in valid_targets:
        return build_error_response(
            f"target 参数无效，可选值: {', '.join(valid_targets)}",
            error_type="client",
        )

    try:
        health_status: Dict[str, Any] = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        check_prometheus = target in ("all", "prometheus")
        check_ruler = target == "ruler" or (target == "all" and bool(config.ruler_url))

        if check_prometheus:
            if config.url:
                prom_info: Dict[str, Any] = {
                    "url": _sanitize_url(config.url),
                    "dedicated": True,
                }
                try:
                    await make_prometheus_request("query", params={"query": "1"})
                    prom_info["connectivity"] = "healthy"
                except Exception as e:
                    prom_info["connectivity"] = "unhealthy"
                    prom_info["error"] = str(e)
                    health_status["status"] = "degraded"
                health_status["prometheus"] = prom_info
            else:
                health_status["prometheus"] = {
                    "connectivity": "unhealthy",
                    "error": "PROMETHEUS_URL 未配置",
                    "dedicated": False,
                }
                health_status["status"] = "unhealthy"

        if check_ruler:
            ruler_url = _get_ruler_url()
            is_dedicated = bool(config.ruler_url)
            if ruler_url:
                ruler_info: Dict[str, Any] = {
                    "url": _sanitize_url(ruler_url),
                    "dedicated": is_dedicated,
                }
                try:
                    # 使用 /alerts 做探活：比 /rules 返回体小一个量级
                    await make_prometheus_request("alerts", base_url=ruler_url)
                    ruler_info["connectivity"] = "healthy"
                except Exception as e:
                    ruler_info["connectivity"] = "unhealthy"
                    ruler_info["error"] = str(e)
                    if health_status["status"] == "healthy":
                        health_status["status"] = "degraded"
                health_status["ruler"] = ruler_info
            elif target == "ruler":
                health_status["ruler"] = {
                    "connectivity": "unhealthy",
                    "error": "RULER_URL 和 PROMETHEUS_URL 均未配置",
                    "dedicated": False,
                }
                health_status["status"] = "unhealthy"

        logger.info("健康检查完成", status=health_status["status"], target=target)
        return health_status

    except Exception as e:
        logger.error("健康检查失败", error=str(e))
        return build_error_response(
            str(e),
            error_type=_classify_exception(e),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


@mcp.tool(description="执行 PromQL 即时查询")
async def execute_query(
    query: str,
    time: Optional[str] = None,
    timeout: Optional[int] = None
) -> Dict[str, Any]:
    """对 Prometheus 执行即时查询。

    Args:
        query: PromQL 查询字符串
        time: 可选的 RFC3339 或 Unix 时间戳（默认当前时间）
        timeout: 请求超时秒数（默认 30）

    Returns:
        包含结果类型（vector、matrix、scalar、string）和值的查询结果
    """
    try:
        _validate_query(query)
        params = {"query": query}
        if time:
            params["time"] = time

        kwargs = {}
        if timeout is not None:
            kwargs["timeout"] = timeout

        logger.info("执行即时查询", query=query, time=time)
        data = await make_prometheus_request("query", params=params, **kwargs)

        if not isinstance(data, dict):
            raise ValueError(f"查询返回了异常格式: {type(data).__name__}")
        result_type = data.get("resultType")
        result = data.get("result", [])
        result_count = len(result) if isinstance(result, list) else 1
        logger.info("即时查询完成",
                    query=query, result_type=result_type, result_count=result_count)
        return {"resultType": result_type, "result": result}

    except Exception as e:
        logger.error("即时查询失败", query=query, error=str(e))
        return build_error_response(
            str(e), error_type=_classify_exception(e), query=query,
        )


@mcp.tool(description="执行带起止时间和步长的 PromQL 范围查询")
async def execute_range_query(
    query: str,
    start: str,
    end: str,
    step: str,
    timeout: Optional[int] = None
) -> Dict[str, Any]:
    """对 Prometheus 执行范围查询。

    Args:
        query: PromQL 查询字符串
        start: 起始时间（RFC3339 或 Unix 时间戳）
        end: 结束时间（RFC3339 或 Unix 时间戳）
        step: 查询步长（如 '15s'、'1m'、'1h'）
        timeout: 请求超时秒数（默认 30）

    Returns:
        范围查询结果，通常为 matrix 类型
    """
    try:
        _validate_query(query)
        params = {"query": query, "start": start, "end": end, "step": step}

        kwargs = {}
        if timeout is not None:
            kwargs["timeout"] = timeout

        logger.info("执行范围查询", query=query, start=start, end=end, step=step)
        data = await make_prometheus_request("query_range", params=params, **kwargs)

        if not isinstance(data, dict):
            raise ValueError(f"范围查询返回了异常格式: {type(data).__name__}")
        result_type = data.get("resultType")
        result = data.get("result", [])
        result_count = len(result) if isinstance(result, list) else 1
        logger.info("范围查询完成",
                    query=query, result_type=result_type, result_count=result_count)
        return {"resultType": result_type, "result": result}

    except Exception as e:
        logger.error("范围查询失败", query=query, error=str(e))
        return build_error_response(
            str(e), error_type=_classify_exception(e), query=query,
        )


@mcp.tool(description="列出可用指标（支持分页和子串过滤）")
async def list_metrics(
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    contains: str = "",
    prefix: str = "",
) -> Dict[str, Any]:
    """获取可用的指标名称列表。

    Args:
        page: 页码，从 1 开始（默认 1）
        page_size: 每页条数（默认 50，上限 500，设为 0 返回全部）
        contains: 仅保留包含该子串的指标名（不区分大小写），空字符串不过滤
        prefix: 仅保留以该前缀开头的指标名（不区分大小写），空字符串不过滤

    Returns:
        包含指标列表和分页信息的字典
    """
    try:
        if page_size > MAX_PAGE_SIZE:
            page_size = MAX_PAGE_SIZE

        logger.info("获取可用指标列表",
                    page=page, page_size=page_size,
                    contains=contains, prefix=prefix)
        data = await make_prometheus_request("label/__name__/values")
        if not isinstance(data, list):
            raise ValueError(f"list_metrics 期望后端返回列表，实际为 {type(data).__name__}")

        total_available = len(data)
        filtered: List[str] = data
        if prefix:
            needle = prefix.lower()
            filtered = [m for m in filtered if isinstance(m, str) and m.lower().startswith(needle)]
        if contains:
            needle = contains.lower()
            filtered = [m for m in filtered if isinstance(m, str) and needle in m.lower()]

        paged = _paginate(filtered, page, page_size)

        logger.info("指标列表获取完成",
                    total_available=total_available,
                    filtered=paged["total"],
                    page=paged["page"],
                    returned=len(paged["items"]))
        return {
            "metrics": paged["items"],
            "total": paged["total"],
            "total_available": total_available,
            "page": paged["page"],
            "page_size": paged["page_size"],
            "total_pages": paged["total_pages"],
            "filters": {"contains": contains or None, "prefix": prefix or None},
        }

    except Exception as e:
        logger.error("获取指标列表失败", error=str(e))
        return build_error_response(str(e), error_type=_classify_exception(e))


@mcp.tool(description="获取指定指标的元数据")
async def get_metric_metadata(metric: str) -> Dict[str, Any]:
    """获取指定指标的元数据信息（类型、说明等）。

    Args:
        metric: 指标名称
    """
    logger.info("获取指标元数据", metric=metric)

    try:
        data = await make_prometheus_request("metadata", params={"metric": metric})

        if isinstance(data, dict):
            metadata = data
        else:
            logger.warning("元数据响应格式异常", data_type=type(data), metric=metric)
            return build_error_response(
                "响应格式异常", error_type="upstream",
                raw_data=data, metric=metric,
            )

        logger.info("指标元数据获取完成", metric=metric)
        return metadata

    except Exception as e:
        logger.error("获取指标元数据失败", metric=metric, error=str(e))
        return build_error_response(
            f"获取指标 '{metric}' 的元数据失败: {str(e)}",
            error_type=_classify_exception(e),
            metric=metric,
        )


@mcp.tool(description="获取指定指标的所有标签及其值示例")
async def get_metric_labels(
    metric: str,
    sample_size: int = DEFAULT_LABEL_SAMPLE_SIZE,
) -> Dict[str, Any]:
    """获取指定指标的标签结构。

    通过 series API 查询，取前 N 条时间序列并对每个标签合并出示例值列表，
    既能看到枚举型标签的多个取值，又能控制传输体积。

    Args:
        metric: 指标名称
        sample_size: 采样序列数（默认 10，上限 100，最小 1）。
            sample_size=1 等价旧版 "每个标签仅展示一个示例值" 的行为。

    注意：limit 参数需要 Prometheus 2.33+ 版本，旧版本会忽略该参数。
    """
    if sample_size < 1:
        sample_size = 1
    if sample_size > MAX_LABEL_SAMPLE_SIZE:
        sample_size = MAX_LABEL_SAMPLE_SIZE

    logger.info("获取指标标签", metric=metric, sample_size=sample_size)

    try:
        params = {"match[]": metric, "limit": str(sample_size)}
        data = await make_prometheus_request("series", params=params)

        if not isinstance(data, list):
            return build_error_response(
                "series API 返回了异常格式的响应",
                error_type="upstream",
                metric=metric, raw_data=data,
            )

        if not data:
            return {
                "metric": metric, "labels": {}, "series_count": 0,
                "label_count": 0, "sample_size": sample_size, "truncated": False,
                "message": f"未找到指标 '{metric}' 的时间序列，该指标可能不存在或没有数据。",
            }

        labels_result: Dict[str, List[str]] = {}
        for series in data:
            if not isinstance(series, dict):
                continue
            for label_name, label_value in series.items():
                if label_name == "__name__":
                    continue
                values = labels_result.setdefault(label_name, [])
                if label_value not in values:
                    values.append(label_value)

        logger.info("指标标签获取完成", metric=metric,
                    series_count=len(data), label_count=len(labels_result))
        return {
            "metric": metric,
            "labels": labels_result,
            "series_count": len(data),
            "label_count": len(labels_result),
            "sample_size": sample_size,
            "truncated": len(data) >= sample_size,
            "note": f"已基于前 {len(data)} 条时间序列去重合并标签值，限制采样可最小化 Token 消耗",
        }

    except Exception as e:
        logger.error("获取指标标签失败", metric=metric, error=str(e))
        return build_error_response(
            f"获取指标 '{metric}' 的标签失败: {str(e)}",
            error_type=_classify_exception(e),
            metric=metric,
        )


@mcp.tool(description="获取指定标签的所有值")
async def get_label_values(label: str) -> Dict[str, Any]:
    """获取指定标签名称的所有值。

    Args:
        label: 标签名称（如 'job'、'instance'、'namespace'）
    """
    if not LABEL_NAME_RE.match(label):
        return build_error_response(
            f"标签名 '{label}' 不合法，仅允许 [a-zA-Z_][a-zA-Z0-9_]*",
            error_type="client",
            label=label,
        )

    logger.info("获取标签值", label=label)

    try:
        data = await make_prometheus_request(f"label/{label}/values")

        logger.info("标签值获取完成", label=label, total_values=len(data))
        return {"label": label, "values": data, "total": len(data)}

    except Exception as e:
        logger.error("获取标签值失败", label=label, error=str(e))
        return build_error_response(
            f"获取标签 '{label}' 的值失败: {str(e)}",
            error_type=_classify_exception(e),
            label=label,
        )


def _parse_label_filters(raw: Optional[str]) -> Dict[str, str]:
    """把 JSON 字符串解析为 label 过滤器字典，解析失败抛 ValueError。"""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"label_filters 需要 JSON 对象字符串: {e}")
    if not isinstance(parsed, dict):
        raise ValueError("label_filters 必须是 JSON 对象")
    return {str(k): str(v) for k, v in parsed.items()}


def _match_labels(alert_labels: Dict[str, Any], filters: Dict[str, str]) -> bool:
    for key, expected in filters.items():
        actual = alert_labels.get(key)
        if actual is None or str(actual) != expected:
            return False
    return True


@mcp.tool(description="获取当前触发的告警列表（支持过滤、分页、聚合摘要）")
async def get_alerts(
    state: str = "all",
    severity: str = "",
    label_filters: Optional[str] = None,
    include_annotations: bool = True,
    summary_only: bool = False,
    page: int = 1,
    page_size: int = 0,
) -> Dict[str, Any]:
    """获取当前活跃告警。默认返回全部告警明细，可通过参数过滤或改为按名称聚合摘要。

    Args:
        state: 状态过滤，可选 "all"（默认）/ "firing" / "pending"
        severity: 仅保留匹配该 severity 标签的条目（空字符串表示不过滤）
        label_filters: JSON 对象字符串，按标签等值过滤。例如 '{"job":"node-agent","namespace":"prod"}'
        include_annotations: 是否在明细里保留 annotations 字段（关闭可显著减少 Token 消耗）
        summary_only: True 时按 alertname 聚合，返回每条告警规则的 state/severity 分布
        page: 页码（仅在 summary_only=False 且 page_size>0 时生效）
        page_size: 每页条数（默认 0 = 返回全部；上限 500）

    底层路由：若配置了 RULER_URL 则走 Ruler，否则走 PROMETHEUS_URL。
    """
    valid_states = ("all", "firing", "pending")
    if state not in valid_states:
        return build_error_response(
            f"state 参数无效，可选值: {', '.join(valid_states)}",
            error_type="client",
        )
    if page_size > MAX_PAGE_SIZE:
        page_size = MAX_PAGE_SIZE

    try:
        filters = _parse_label_filters(label_filters)
    except ValueError as e:
        return build_error_response(str(e), error_type="client")

    logger.info("获取告警列表",
                state=state, severity=severity or None,
                has_label_filters=bool(filters),
                summary_only=summary_only)

    try:
        data = await make_prometheus_request("alerts", base_url=_get_ruler_url())

        raw_alerts = data.get("alerts", []) if isinstance(data, dict) else []
        total_raw = len(raw_alerts)

        filtered: List[Dict[str, Any]] = []
        for a in raw_alerts:
            if not isinstance(a, dict):
                continue
            if state != "all" and a.get("state") != state:
                continue
            labels = a.get("labels") or {}
            if severity and str(labels.get("severity", "")) != severity:
                continue
            if filters and not _match_labels(labels, filters):
                continue
            filtered.append(a)

        firing = sum(1 for a in filtered if a.get("state") == "firing")
        pending = sum(1 for a in filtered if a.get("state") == "pending")

        if summary_only:
            groups: Dict[str, Dict[str, Any]] = {}
            for a in filtered:
                labels = a.get("labels") or {}
                name = str(labels.get("alertname") or "(unknown)")
                bucket = groups.setdefault(name, {
                    "alertname": name,
                    "count": 0,
                    "states": Counter(),
                    "severities": Counter(),
                    "sample_labels": labels,
                })
                bucket["count"] += 1
                bucket["states"][a.get("state", "unknown")] += 1
                sev = labels.get("severity")
                if sev:
                    bucket["severities"][str(sev)] += 1

            summaries = [
                {
                    "alertname": g["alertname"],
                    "count": g["count"],
                    "states": dict(g["states"]),
                    "severities": dict(g["severities"]),
                    "sample_labels": g["sample_labels"],
                }
                for g in sorted(groups.values(), key=lambda x: x["count"], reverse=True)
            ]

            logger.info("告警摘要获取完成",
                        total_raw=total_raw, filtered=len(filtered),
                        alertnames=len(summaries))
            return {
                "summaries": summaries,
                "total_alertnames": len(summaries),
                "total_instances": len(filtered),
                "firing": firing,
                "pending": pending,
                "source_total": total_raw,
                "filters": {
                    "state": state,
                    "severity": severity or None,
                    "label_filters": filters or None,
                },
            }

        # 明细列表（含分页）
        if not include_annotations:
            filtered = [{k: v for k, v in a.items() if k != "annotations"} for a in filtered]

        paged = _paginate(filtered, page, page_size)

        logger.info("告警列表获取完成",
                    total_raw=total_raw,
                    filtered=paged["total"],
                    firing=firing,
                    pending=pending,
                    returned=len(paged["items"]))
        return {
            "alerts": paged["items"],
            "total": paged["total"],
            "source_total": total_raw,
            "firing": firing,
            "pending": pending,
            "page": paged["page"],
            "page_size": paged["page_size"],
            "total_pages": paged["total_pages"],
            "filters": {
                "state": state,
                "severity": severity or None,
                "label_filters": filters or None,
                "include_annotations": include_annotations,
            },
        }

    except Exception as e:
        logger.error("获取告警列表失败", error=str(e))
        return build_error_response(
            f"获取告警列表失败: {str(e)}",
            error_type=_classify_exception(e),
        )


@mcp.tool(description="获取所有告警规则和记录规则（支持类型/名称过滤、分页、轻量模式）")
async def get_rules(
    type_filter: str = "all",
    group_contains: str = "",
    file_contains: str = "",
    rule_name_contains: str = "",
    include_rules: bool = True,
    page: int = 1,
    page_size: int = 0,
) -> Dict[str, Any]:
    """获取规则组列表。

    Args:
        type_filter: 规则类型过滤，"all"（默认）/ "alerting" / "recording"
        group_contains: 仅保留 group.name 包含该子串的组（不区分大小写）
        file_contains: 仅保留 group.file 包含该子串的组（不区分大小写）
        rule_name_contains: 仅保留组内 rule.name 包含该子串的规则；若组内无匹配规则则整组被过滤掉
        include_rules: False 时返回组级汇总（不含 rules 数组），用于大体量场景预览
        page: 页码（作用在组级）
        page_size: 每页组数（默认 0 = 全部；上限 500）

    底层路由：若配置了 RULER_URL 则走 Ruler，否则走 PROMETHEUS_URL。
    """
    valid_types = ("all", "alerting", "recording")
    if type_filter not in valid_types:
        return build_error_response(
            f"type_filter 参数无效，可选值: {', '.join(valid_types)}",
            error_type="client",
        )
    if page_size > MAX_PAGE_SIZE:
        page_size = MAX_PAGE_SIZE

    logger.info("获取规则列表",
                type_filter=type_filter,
                group_contains=group_contains or None,
                file_contains=file_contains or None,
                rule_name_contains=rule_name_contains or None,
                include_rules=include_rules)

    try:
        data = await make_prometheus_request("rules", base_url=_get_ruler_url())

        raw_groups = data.get("groups", []) if isinstance(data, dict) else []

        grp_needle = group_contains.lower() if group_contains else ""
        file_needle = file_contains.lower() if file_contains else ""
        rule_needle = rule_name_contains.lower() if rule_name_contains else ""

        filtered_groups: List[Dict[str, Any]] = []
        total_rules_all = 0
        total_alerting = 0
        total_recording = 0

        for g in raw_groups:
            if not isinstance(g, dict):
                continue
            if grp_needle and grp_needle not in str(g.get("name", "")).lower():
                continue
            if file_needle and file_needle not in str(g.get("file", "")).lower():
                continue

            rules = g.get("rules", []) or []
            kept_rules: List[Dict[str, Any]] = []
            g_alerting = 0
            g_recording = 0
            for r in rules:
                if not isinstance(r, dict):
                    continue
                rtype = r.get("type")
                if type_filter != "all" and rtype != type_filter:
                    continue
                if rule_needle and rule_needle not in str(r.get("name", "")).lower():
                    continue
                kept_rules.append(r)
                if rtype == "alerting":
                    g_alerting += 1
                elif rtype == "recording":
                    g_recording += 1

            if not kept_rules and (type_filter != "all" or rule_needle):
                continue

            group_out: Dict[str, Any] = {
                "name": g.get("name"),
                "file": g.get("file"),
                "interval": g.get("interval"),
                "rule_count": len(kept_rules),
                "alerting_count": g_alerting,
                "recording_count": g_recording,
            }
            if include_rules:
                group_out["rules"] = kept_rules
            filtered_groups.append(group_out)
            total_rules_all += len(kept_rules)
            total_alerting += g_alerting
            total_recording += g_recording

        paged = _paginate(filtered_groups, page, page_size)

        logger.info("规则列表获取完成",
                    total_groups=paged["total"],
                    total_rules=total_rules_all,
                    returned_groups=len(paged["items"]))
        return {
            "groups": paged["items"],
            "total_groups": paged["total"],
            "total_rules": total_rules_all,
            "total_alerting": total_alerting,
            "total_recording": total_recording,
            "page": paged["page"],
            "page_size": paged["page_size"],
            "total_pages": paged["total_pages"],
            "filters": {
                "type_filter": type_filter,
                "group_contains": group_contains or None,
                "file_contains": file_contains or None,
                "rule_name_contains": rule_name_contains or None,
                "include_rules": include_rules,
            },
        }

    except Exception as e:
        logger.error("获取规则列表失败", error=str(e))
        return build_error_response(
            f"获取规则列表失败: {str(e)}",
            error_type=_classify_exception(e),
        )


@mcp.tool(description="获取所有抓取目标的信息（支持健康状态/job 过滤、分页）")
async def get_targets(
    health: str = "all",
    job_contains: str = "",
    include_dropped: bool = True,
    page: int = 1,
    page_size: int = 0,
) -> Dict[str, Any]:
    """获取抓取目标。

    Args:
        health: 健康状态过滤，"all"（默认）/ "up" / "down" / "unknown"
        job_contains: 仅保留 labels.job 包含该子串的目标（不区分大小写）
        include_dropped: 是否返回 droppedTargets（默认 True；关闭可减小响应体积）
        page: 页码（作用在 activeTargets）
        page_size: 每页条数（默认 0 = 全部；上限 500）
    """
    valid_health = ("all", "up", "down", "unknown")
    if health not in valid_health:
        return build_error_response(
            f"health 参数无效，可选值: {', '.join(valid_health)}",
            error_type="client",
        )
    if page_size > MAX_PAGE_SIZE:
        page_size = MAX_PAGE_SIZE

    logger.info("获取抓取目标信息",
                health=health, job_contains=job_contains or None,
                include_dropped=include_dropped)

    try:
        data = await make_prometheus_request("targets")

        active_raw = data.get("activeTargets", []) if isinstance(data, dict) else []
        dropped_raw = data.get("droppedTargets", []) if isinstance(data, dict) else []

        job_needle = job_contains.lower() if job_contains else ""

        active_filtered: List[Dict[str, Any]] = []
        for t in active_raw:
            if not isinstance(t, dict):
                continue
            if health != "all" and t.get("health") != health:
                continue
            if job_needle:
                job = str((t.get("labels") or {}).get("job", "")).lower()
                if job_needle not in job:
                    continue
            active_filtered.append(t)

        health_counts = Counter(
            t.get("health", "unknown") for t in active_raw if isinstance(t, dict)
        )

        paged = _paginate(active_filtered, page, page_size)

        result: Dict[str, Any] = {
            "activeTargets": paged["items"],
            "total": paged["total"],
            "source_total_active": len(active_raw),
            "health_counts": dict(health_counts),
            "page": paged["page"],
            "page_size": paged["page_size"],
            "total_pages": paged["total_pages"],
            "filters": {
                "health": health,
                "job_contains": job_contains or None,
                "include_dropped": include_dropped,
            },
        }
        if include_dropped:
            result["droppedTargets"] = dropped_raw
            result["dropped_total"] = len(dropped_raw)
        else:
            result["dropped_total"] = len(dropped_raw)

        logger.info("抓取目标获取完成",
                    active_targets=len(active_raw),
                    filtered_active=paged["total"],
                    dropped_targets=len(dropped_raw))
        return result

    except Exception as e:
        logger.error("获取抓取目标失败", error=str(e))
        return build_error_response(
            f"获取抓取目标失败: {str(e)}",
            error_type=_classify_exception(e),
        )
