"""Tests for the MCP tools functionality."""

import pytest
import json
from unittest.mock import patch, MagicMock
from fastmcp import Client
from monitor_mcp_server.tools import (
    mcp, execute_query, execute_range_query, list_metrics,
    get_metric_metadata, get_metric_labels, get_targets,
    get_label_values, get_alerts, get_rules, _get_ruler_url,
)
from monitor_mcp_server.config import config

@pytest.fixture
def mock_make_request():
    with patch("monitor_mcp_server.tools.make_prometheus_request") as mock:
        yield mock

@pytest.mark.asyncio
async def test_execute_query(mock_make_request):
    mock_make_request.return_value = {
        "resultType": "vector",
        "result": [{"metric": {"__name__": "up"}, "value": [1617898448.214, "1"]}]
    }

    async with Client(mcp) as client:
        result = await client.call_tool("execute_query", {"query":"up"})

        mock_make_request.assert_called_once_with("query", params={"query": "up"})
        assert result.data["resultType"] == "vector"
        assert len(result.data["result"]) == 1

@pytest.mark.asyncio
async def test_execute_query_with_time(mock_make_request):
    mock_make_request.return_value = {
        "resultType": "vector",
        "result": [{"metric": {"__name__": "up"}, "value": [1617898448.214, "1"]}]
    }

    async with Client(mcp) as client:
        result = await client.call_tool("execute_query", {"query":"up", "time":"2023-01-01T00:00:00Z"})

        mock_make_request.assert_called_once_with("query", params={"query": "up", "time": "2023-01-01T00:00:00Z"})
        assert result.data["resultType"] == "vector"

@pytest.mark.asyncio
async def test_execute_query_with_timeout(mock_make_request):
    mock_make_request.return_value = {
        "resultType": "vector",
        "result": []
    }

    async with Client(mcp) as client:
        result = await client.call_tool("execute_query", {"query":"up", "timeout": 60})

        mock_make_request.assert_called_once_with("query", params={"query": "up"}, timeout=60)
        assert result.data["resultType"] == "vector"

@pytest.mark.asyncio
async def test_execute_range_query(mock_make_request):
    mock_make_request.return_value = {
        "resultType": "matrix",
        "result": [{
            "metric": {"__name__": "up"},
            "values": [
                [1617898400, "1"],
                [1617898415, "1"]
            ]
        }]
    }

    async with Client(mcp) as client:
        result = await client.call_tool(
            "execute_range_query",{
            "query": "up",
            "start": "2023-01-01T00:00:00Z",
            "end": "2023-01-01T01:00:00Z",
            "step": "15s"
        })

        mock_make_request.assert_called_once_with("query_range", params={
            "query": "up",
            "start": "2023-01-01T00:00:00Z",
            "end": "2023-01-01T01:00:00Z",
            "step": "15s"
        })
        assert result.data["resultType"] == "matrix"
        assert len(result.data["result"]) == 1
        assert len(result.data["result"][0]["values"]) == 2

@pytest.mark.asyncio
async def test_list_metrics(mock_make_request):
    mock_make_request.return_value = ["up", "go_goroutines", "http_requests_total"]

    async with Client(mcp) as client:
        result = await client.call_tool("list_metrics", {})

        mock_make_request.assert_called_once_with("label/__name__/values")

        payload = result.content[0].text
        json_data = json.loads(payload)

        assert json_data["total"] == 3
        assert json_data["page"] == 1
        assert json_data["page_size"] == 50
        assert json_data["total_pages"] == 1
        assert len(json_data["metrics"]) == 3
        assert "up" in json_data["metrics"]

@pytest.mark.asyncio
async def test_list_metrics_pagination(mock_make_request):
    all_metrics = [f"metric_{i:03d}" for i in range(120)]
    mock_make_request.return_value = all_metrics

    async with Client(mcp) as client:
        result = await client.call_tool("list_metrics", {"page": 2, "page_size": 50})

        payload = result.content[0].text
        json_data = json.loads(payload)

        assert json_data["total"] == 120
        assert json_data["page"] == 2
        assert json_data["page_size"] == 50
        assert json_data["total_pages"] == 3
        assert len(json_data["metrics"]) == 50
        assert json_data["metrics"][0] == "metric_050"

@pytest.mark.asyncio
async def test_list_metrics_all(mock_make_request):
    all_metrics = [f"m{i}" for i in range(200)]
    mock_make_request.return_value = all_metrics

    async with Client(mcp) as client:
        result = await client.call_tool("list_metrics", {"page_size": 0})

        payload = result.content[0].text
        json_data = json.loads(payload)

        assert json_data["total"] == 200
        assert len(json_data["metrics"]) == 200
        assert json_data["total_pages"] == 1

@pytest.mark.asyncio
async def test_get_metric_metadata(mock_make_request):
    mock_make_request.return_value = {
        "up": [
            {"type": "gauge", "help": "Up indicates if the scrape was successful", "unit": ""}
        ]
    }

    async with Client(mcp) as client:
        result = await client.call_tool("get_metric_metadata", {"metric":"up"})

        payload = result.content[0].text
        json_data = json.loads(payload)

        mock_make_request.assert_called_once_with("metadata", params={"metric": "up"})
        assert isinstance(json_data, dict)
        assert json_data["metric"] == "up"
        assert "up" in json_data["metadata"]
        assert json_data["metadata"]["up"][0]["type"] == "gauge"

@pytest.mark.asyncio
async def test_get_metric_labels(mock_make_request):
    mock_make_request.return_value = [
        {"__name__": "http_requests_total", "job": "api", "method": "GET", "status": "200"}
    ]

    async with Client(mcp) as client:
        result = await client.call_tool("get_metric_labels", {"metric": "http_requests_total"})

        payload = result.content[0].text
        json_data = json.loads(payload)

        mock_make_request.assert_called_once_with(
            "series", params={"match[]": "http_requests_total", "limit": "10"}
        )
        assert json_data["metric"] == "http_requests_total"
        assert json_data["series_count"] == 1
        assert json_data["label_count"] == 3
        assert json_data["truncated"] is False
        assert json_data["sample_size"] == 10
        assert json_data["labels"]["job"] == ["api"]

@pytest.mark.asyncio
async def test_get_metric_labels_empty_response(mock_make_request):
    mock_make_request.return_value = []

    async with Client(mcp) as client:
        result = await client.call_tool("get_metric_labels", {"metric": "nonexistent_metric"})

        payload = result.content[0].text
        json_data = json.loads(payload)

        assert json_data["metric"] == "nonexistent_metric"
        assert json_data["series_count"] == 0
        assert json_data["labels"] == {}
        assert json_data["truncated"] is False
        assert "message" in json_data

@pytest.mark.asyncio
async def test_get_metric_labels_error_handling(mock_make_request):
    mock_make_request.side_effect = Exception("Connection error")

    async with Client(mcp) as client:
        result = await client.call_tool("get_metric_labels", {"metric": "test_metric"})

        payload = result.content[0].text
        json_data = json.loads(payload)

        assert "error" in json_data
        assert "Connection error" in json_data["error"]
        assert json_data["status"] == "error"

@pytest.mark.asyncio
async def test_get_metric_labels_with_limit(mock_make_request):
    mock_make_request.return_value = [{
        "__name__": "large_metric",
        "job": "api",
        "instance": "localhost:8080",
        "status": "200"
    }]

    async with Client(mcp) as client:
        result = await client.call_tool("get_metric_labels", {"metric": "large_metric"})

        payload = result.content[0].text
        json_data = json.loads(payload)

        assert json_data["series_count"] == 1
        assert json_data["truncated"] is False
        assert json_data["labels"]["job"] == ["api"]
        assert json_data["labels"]["instance"] == ["localhost:8080"]


@pytest.mark.asyncio
async def test_get_metric_labels_merges_sampled_values(mock_make_request):
    """sample_size>1 时应合并多条 series 的标签取值，而不是只看第一条。"""
    mock_make_request.return_value = [
        {"__name__": "m", "job": "api", "instance": "a:1"},
        {"__name__": "m", "job": "api", "instance": "b:1"},
        {"__name__": "m", "job": "web", "instance": "c:1"},
    ]

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_metric_labels", {"metric": "m", "sample_size": 5}
        )

        payload = result.content[0].text
        json_data = json.loads(payload)

        mock_make_request.assert_called_once_with(
            "series", params={"match[]": "m", "limit": "5"}
        )
        assert sorted(json_data["labels"]["job"]) == ["api", "web"]
        assert sorted(json_data["labels"]["instance"]) == ["a:1", "b:1", "c:1"]
        assert json_data["sample_size"] == 5

@pytest.mark.asyncio
async def test_get_label_values(mock_make_request):
    mock_make_request.return_value = ["prometheus", "node-exporter", "grafana"]

    async with Client(mcp) as client:
        result = await client.call_tool("get_label_values", {"label": "job"})

        payload = result.content[0].text
        json_data = json.loads(payload)

        mock_make_request.assert_called_once_with("label/job/values")
        assert json_data["label"] == "job"
        assert json_data["total"] == 3
        assert "prometheus" in json_data["values"]

@pytest.mark.asyncio
async def test_get_alerts(mock_make_request):
    mock_make_request.return_value = {
        "alerts": [
            {"state": "firing", "labels": {"alertname": "HighCPU"}, "value": "0.95"},
            {"state": "pending", "labels": {"alertname": "DiskFull"}, "value": "0.85"},
            {"state": "firing", "labels": {"alertname": "MemHigh"}, "value": "0.90"}
        ]
    }

    async with Client(mcp) as client:
        result = await client.call_tool("get_alerts", {})

        payload = result.content[0].text
        json_data = json.loads(payload)

        assert json_data["total"] == 3
        assert json_data["firing"] == 2
        assert json_data["pending"] == 1

@pytest.mark.asyncio
async def test_get_alerts_error_handling(mock_make_request):
    """Test get_alerts returns structured error on failure (B2 fix)."""
    mock_make_request.side_effect = Exception("Connection refused")

    async with Client(mcp) as client:
        result = await client.call_tool("get_alerts", {})
        payload = result.content[0].text
        json_data = json.loads(payload)

        assert "error" in json_data
        assert json_data["status"] == "error"

@pytest.mark.asyncio
async def test_get_rules(mock_make_request):
    mock_make_request.return_value = {
        "groups": [
            {
                "name": "test-group",
                "rules": [
                    {"name": "HighCPU", "type": "alerting"},
                    {"name": "cpu:rate5m", "type": "recording"}
                ]
            }
        ]
    }

    async with Client(mcp) as client:
        result = await client.call_tool("get_rules", {})

        payload = result.content[0].text
        json_data = json.loads(payload)

        assert json_data["total_groups"] == 1
        assert json_data["total_rules"] == 2

@pytest.mark.asyncio
async def test_get_rules_error_handling(mock_make_request):
    """Test get_rules returns structured error on failure (B2 fix)."""
    mock_make_request.side_effect = Exception("Connection refused")

    async with Client(mcp) as client:
        result = await client.call_tool("get_rules", {})
        payload = result.content[0].text
        json_data = json.loads(payload)

        assert "error" in json_data
        assert json_data["status"] == "error"

@pytest.mark.asyncio
async def test_get_targets(mock_make_request):
    mock_make_request.return_value = {
        "activeTargets": [
            {"discoveredLabels": {"__address__": "localhost:9090"}, "labels": {"job": "prometheus"}, "health": "up"}
        ],
        "droppedTargets": []
    }

    async with Client(mcp) as client:
        result = await client.call_tool("get_targets",{})

        payload = result.content[0].text
        json_data = json.loads(payload)

        mock_make_request.assert_called_once_with("targets")
        assert len(json_data["activeTargets"]) == 1
        assert json_data["activeTargets"][0]["health"] == "up"
        assert len(json_data["droppedTargets"]) == 0

@pytest.mark.asyncio
async def test_get_targets_error_handling(mock_make_request):
    """Test get_targets returns structured error on failure (B1/B2 fix)."""
    mock_make_request.side_effect = Exception("Connection refused")

    async with Client(mcp) as client:
        result = await client.call_tool("get_targets", {})
        payload = result.content[0].text
        json_data = json.loads(payload)

        assert "error" in json_data
        assert json_data["status"] == "error"


# ---------------------------------------------------------------------------
# Backend type routing
# ---------------------------------------------------------------------------

def test_get_ruler_url_prometheus_prefers_ruler_url():
    """prometheus 后端：RULER_URL 优先。"""
    original = (config.backend_type, config.url, config.ruler_url)
    try:
        config.backend_type = "prometheus"
        config.url = "http://query:9090"
        config.ruler_url = "http://ruler:9090"
        assert _get_ruler_url() == "http://ruler:9090"
    finally:
        config.backend_type, config.url, config.ruler_url = original


def test_get_ruler_url_prometheus_falls_back():
    """prometheus 后端：未配 RULER_URL 回退 PROMETHEUS_URL。"""
    original = (config.backend_type, config.url, config.ruler_url)
    try:
        config.backend_type = "prometheus"
        config.url = "http://query:9090"
        config.ruler_url = None
        assert _get_ruler_url() == "http://query:9090"
    finally:
        config.backend_type, config.url, config.ruler_url = original


def test_get_ruler_url_thanos_falls_back_to_query():
    """thanos 后端：未配 RULER_URL 时走 Thanos Query（推荐做法）。"""
    original = (config.backend_type, config.url, config.ruler_url)
    try:
        config.backend_type = "thanos"
        config.url = "http://thanos-query:9090"
        config.ruler_url = None
        assert _get_ruler_url() == "http://thanos-query:9090"
    finally:
        config.backend_type, config.url, config.ruler_url = original


def test_get_ruler_url_victoriametrics_requires_vmalert():
    """victoriametrics 后端：必须配 RULER_URL 指向 vmalert。"""
    original = (config.backend_type, config.url, config.ruler_url)
    try:
        config.backend_type = "victoriametrics"
        config.url = "http://vmselect:8481"
        config.ruler_url = "http://vmalert:8880"
        assert _get_ruler_url() == "http://vmalert:8880"
    finally:
        config.backend_type, config.url, config.ruler_url = original


@pytest.mark.asyncio
async def test_get_alerts_thanos_without_ruler_url_uses_query(mock_make_request):
    """Thanos 模式推荐做法：不配 RULER_URL，get_alerts 自动走 Thanos Query。"""
    mock_make_request.return_value = {"alerts": []}
    original = (config.backend_type, config.url, config.ruler_url)
    try:
        config.backend_type = "thanos"
        config.url = "http://thanos-query:9090"
        config.ruler_url = None
        async with Client(mcp) as client:
            await client.call_tool("get_alerts", {})
        mock_make_request.assert_called_once_with("alerts", base_url="http://thanos-query:9090")
    finally:
        config.backend_type, config.url, config.ruler_url = original


# ---------------------------------------------------------------------------
# 过滤 / 分页 / 摘要（C1、C3）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_alerts_state_filter(mock_make_request):
    mock_make_request.return_value = {
        "alerts": [
            {"state": "firing", "labels": {"alertname": "A", "severity": "warn"}},
            {"state": "firing", "labels": {"alertname": "B", "severity": "critical"}},
            {"state": "pending", "labels": {"alertname": "C", "severity": "warn"}},
        ]
    }
    async with Client(mcp) as client:
        result = await client.call_tool("get_alerts", {"state": "firing"})
    data = json.loads(result.content[0].text)
    assert data["total"] == 2
    assert data["source_total"] == 3
    assert all(a["state"] == "firing" for a in data["alerts"])


@pytest.mark.asyncio
async def test_get_alerts_severity_and_label_filter(mock_make_request):
    mock_make_request.return_value = {
        "alerts": [
            {"state": "firing", "labels": {"alertname": "A", "severity": "warn", "job": "x"}},
            {"state": "firing", "labels": {"alertname": "B", "severity": "critical", "job": "x"}},
            {"state": "firing", "labels": {"alertname": "C", "severity": "critical", "job": "y"}},
        ]
    }
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_alerts",
            {"severity": "critical", "label_filters": json.dumps({"job": "x"})},
        )
    data = json.loads(result.content[0].text)
    assert data["total"] == 1
    assert data["alerts"][0]["labels"]["alertname"] == "B"


@pytest.mark.asyncio
async def test_get_alerts_summary_only(mock_make_request):
    mock_make_request.return_value = {
        "alerts": [
            {"state": "firing", "labels": {"alertname": "X", "severity": "warn"}},
            {"state": "firing", "labels": {"alertname": "X", "severity": "warn"}},
            {"state": "pending", "labels": {"alertname": "X", "severity": "warn"}},
            {"state": "firing", "labels": {"alertname": "Y", "severity": "critical"}},
        ]
    }
    async with Client(mcp) as client:
        result = await client.call_tool("get_alerts", {"summary_only": True})
    data = json.loads(result.content[0].text)
    assert "summaries" in data and "alerts" not in data
    assert data["total_alertnames"] == 2
    assert data["total_instances"] == 4
    by_name = {s["alertname"]: s for s in data["summaries"]}
    assert by_name["X"]["count"] == 3
    assert by_name["X"]["states"] == {"firing": 2, "pending": 1}
    assert by_name["Y"]["count"] == 1


@pytest.mark.asyncio
async def test_get_alerts_invalid_state(mock_make_request):
    async with Client(mcp) as client:
        result = await client.call_tool("get_alerts", {"state": "nope"})
    data = json.loads(result.content[0].text)
    assert data["status"] == "error"
    assert data["error_type"] == "client"


@pytest.mark.asyncio
async def test_get_alerts_drop_annotations(mock_make_request):
    mock_make_request.return_value = {
        "alerts": [
            {
                "state": "firing",
                "labels": {"alertname": "A"},
                "annotations": {"summary": "xxx", "description": "yyy" * 100},
            }
        ]
    }
    async with Client(mcp) as client:
        result = await client.call_tool("get_alerts", {"include_annotations": False})
    data = json.loads(result.content[0].text)
    assert "annotations" not in data["alerts"][0]


@pytest.mark.asyncio
async def test_get_rules_type_and_name_filter(mock_make_request):
    mock_make_request.return_value = {
        "groups": [
            {
                "name": "g1",
                "file": "/etc/rules/file1.yml",
                "rules": [
                    {"name": "HighCPU", "type": "alerting"},
                    {"name": "cpu:rate5m", "type": "recording"},
                ],
            },
            {
                "name": "g2",
                "file": "/etc/rules/file2.yml",
                "rules": [{"name": "DiskFull", "type": "alerting"}],
            },
        ]
    }
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_rules", {"type_filter": "alerting", "rule_name_contains": "cpu"}
        )
    data = json.loads(result.content[0].text)
    assert data["total_groups"] == 1
    assert data["groups"][0]["name"] == "g1"
    assert len(data["groups"][0]["rules"]) == 1
    assert data["groups"][0]["rules"][0]["name"] == "HighCPU"


@pytest.mark.asyncio
async def test_get_rules_include_rules_false(mock_make_request):
    mock_make_request.return_value = {
        "groups": [
            {
                "name": "g1", "file": "/f.yml",
                "rules": [
                    {"name": "r1", "type": "alerting"},
                    {"name": "r2", "type": "recording"},
                ],
            },
        ]
    }
    async with Client(mcp) as client:
        result = await client.call_tool("get_rules", {"include_rules": False})
    data = json.loads(result.content[0].text)
    g = data["groups"][0]
    assert "rules" not in g
    assert g["rule_count"] == 2
    assert g["alerting_count"] == 1
    assert g["recording_count"] == 1


@pytest.mark.asyncio
async def test_get_targets_health_and_job_filter(mock_make_request):
    mock_make_request.return_value = {
        "activeTargets": [
            {"health": "up", "labels": {"job": "node-agent"}},
            {"health": "down", "labels": {"job": "node-agent"}},
            {"health": "down", "labels": {"job": "blackbox"}},
        ],
        "droppedTargets": [{"discoveredLabels": {"__address__": "x"}}],
    }
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_targets",
            {"health": "down", "job_contains": "node", "include_dropped": False},
        )
    data = json.loads(result.content[0].text)
    assert data["total"] == 1
    assert data["activeTargets"][0]["labels"]["job"] == "node-agent"
    assert data["health_counts"] == {"up": 1, "down": 2}
    assert data["droppedTargets"] == []
    assert data.get("dropped_omitted") is True
    assert data["dropped_total"] == 1


@pytest.mark.asyncio
async def test_list_metrics_contains_filter(mock_make_request):
    mock_make_request.return_value = [
        "node_cpu_seconds_total",
        "node_memory_MemFree_bytes",
        "http_requests_total",
        "go_goroutines",
    ]
    async with Client(mcp) as client:
        result = await client.call_tool("list_metrics", {"contains": "node"})
    data = json.loads(result.content[0].text)
    assert data["total_available"] == 4
    assert data["total"] == 2
    assert all("node" in m for m in data["metrics"])


@pytest.mark.asyncio
async def test_list_metrics_prefix_filter(mock_make_request):
    mock_make_request.return_value = ["up", "up_time", "node_cpu", "http"]
    async with Client(mcp) as client:
        result = await client.call_tool("list_metrics", {"prefix": "up"})
    data = json.loads(result.content[0].text)
    assert data["total"] == 2
    assert set(data["metrics"]) == {"up", "up_time"}


@pytest.mark.asyncio
async def test_execute_query_returns_structured_error_on_failure(mock_make_request):
    """execute_query 底层异常应返回结构化错误（A3/A4 修复）。"""
    mock_make_request.side_effect = ValueError("Prometheus API 错误: bad PromQL")
    async with Client(mcp) as client:
        result = await client.call_tool("execute_query", {"query": "up"})
    data = json.loads(result.content[0].text)
    assert data["status"] == "error"
    assert data["error_type"] == "upstream"
    assert data["query"] == "up"


@pytest.mark.asyncio
async def test_execute_query_rejects_control_chars(mock_make_request):
    """_validate_query 应拒绝包含 NUL 等控制字符的 PromQL（C6）。"""
    async with Client(mcp) as client:
        result = await client.call_tool("execute_query", {"query": "up\x00"})
    data = json.loads(result.content[0].text)
    assert data["status"] == "error"
    assert data["error_type"] == "client"
    mock_make_request.assert_not_called()
