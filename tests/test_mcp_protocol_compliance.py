"""Tests for MCP protocol compliance — validates real tool implementations."""

import pytest
import json
from unittest.mock import patch, MagicMock
from fastmcp import Client
from monitor_mcp_server.client import get_prometheus_auth
from monitor_mcp_server.config import config, TransportType, MCPServerConfig, PrometheusConfig
from monitor_mcp_server.tools import (
    mcp, execute_query, execute_range_query, list_metrics,
    get_metric_metadata, get_metric_labels, get_targets, health_check,
    get_label_values, get_alerts, get_rules,
)


@pytest.fixture
def mock_make_request():
    with patch("monitor_mcp_server.tools.make_prometheus_request") as mock:
        yield mock


# ---------------------------------------------------------------------------
# Tool signature & return structure
# ---------------------------------------------------------------------------

class TestMCPToolCompliance:

    @pytest.mark.asyncio
    async def test_execute_query_returns_correct_structure(self, mock_make_request):
        mock_make_request.return_value = {
            "resultType": "vector",
            "result": [{"metric": {"__name__": "up"}, "value": [1609459200, "1"]}]
        }
        async with Client(mcp) as client:
            result = await client.call_tool("execute_query", {"query": "up"})
        assert result.data["resultType"] == "vector"
        assert len(result.data["result"]) == 1

    @pytest.mark.asyncio
    async def test_execute_query_with_time(self, mock_make_request):
        mock_make_request.return_value = {"resultType": "vector", "result": []}
        async with Client(mcp) as client:
            result = await client.call_tool("execute_query", {"query": "up", "time": "2023-01-01T00:00:00Z"})
        mock_make_request.assert_called_once_with("query", params={"query": "up", "time": "2023-01-01T00:00:00Z"})
        assert result.data["resultType"] == "vector"

    @pytest.mark.asyncio
    async def test_execute_range_query_returns_correct_structure(self, mock_make_request):
        mock_make_request.return_value = {"resultType": "matrix", "result": []}
        async with Client(mcp) as client:
            result = await client.call_tool("execute_range_query", {
                "query": "up", "start": "2023-01-01T00:00:00Z",
                "end": "2023-01-01T01:00:00Z", "step": "1m"
            })
        assert result.data["resultType"] == "matrix"

    @pytest.mark.asyncio
    async def test_list_metrics_returns_paginated(self, mock_make_request):
        mock_make_request.return_value = ["up", "go_goroutines", "http_requests_total"]
        async with Client(mcp) as client:
            result = await client.call_tool("list_metrics", {})
        data = json.loads(result.content[0].text)
        assert data["total"] == 3
        assert isinstance(data["metrics"], list)

    @pytest.mark.asyncio
    async def test_get_targets_returns_correct_structure(self, mock_make_request):
        mock_make_request.return_value = {
            "activeTargets": [{"health": "up", "labels": {"job": "prometheus"}}],
            "droppedTargets": []
        }
        async with Client(mcp) as client:
            result = await client.call_tool("get_targets", {})
        data = json.loads(result.content[0].text)
        assert "activeTargets" in data
        assert "droppedTargets" in data

    @pytest.mark.asyncio
    async def test_health_check_returns_correct_structure(self, mock_make_request):
        mock_make_request.return_value = {"resultType": "vector", "result": []}
        async with Client(mcp) as client:
            result = await client.call_tool("health_check", {})
        data = json.loads(result.content[0].text)
        assert "status" in data
        assert "timestamp" in data
        assert "prometheus" in data
        assert data["prometheus"]["connectivity"] == "healthy"
        for field in ("service", "version", "transport", "configuration"):
            assert field not in data

    @pytest.mark.asyncio
    async def test_health_check_target_ruler_with_dedicated_url(self, mock_make_request):
        mock_make_request.return_value = {"alerts": []}
        original_ruler = config.ruler_url
        config.ruler_url = "http://ruler:9090"
        try:
            async with Client(mcp) as client:
                result = await client.call_tool("health_check", {"target": "ruler"})
            data = json.loads(result.content[0].text)
            assert data["status"] == "healthy"
            assert "ruler" in data
            assert data["ruler"]["connectivity"] == "healthy"
            assert data["ruler"]["dedicated"] is True
            assert "prometheus" not in data
            # A5: Ruler 探活改用 /alerts（比 /rules 轻量很多）
            mock_make_request.assert_called_once_with("alerts", base_url="http://ruler:9090")
        finally:
            config.ruler_url = original_ruler

    @pytest.mark.asyncio
    async def test_health_check_target_prometheus_only(self, mock_make_request):
        mock_make_request.return_value = {"resultType": "vector", "result": []}
        async with Client(mcp) as client:
            result = await client.call_tool("health_check", {"target": "prometheus"})
        data = json.loads(result.content[0].text)
        assert data["status"] == "healthy"
        assert "prometheus" in data
        assert "ruler" not in data

    @pytest.mark.asyncio
    async def test_get_metric_metadata_returns_dict(self, mock_make_request):
        mock_make_request.return_value = {
            "up": [{"type": "gauge", "help": "Up status", "unit": ""}]
        }
        async with Client(mcp) as client:
            result = await client.call_tool("get_metric_metadata", {"metric": "up"})
        data = json.loads(result.content[0].text)
        assert isinstance(data, dict)
        assert "up" in data

    @pytest.mark.asyncio
    async def test_get_label_values_returns_correct_structure(self, mock_make_request):
        mock_make_request.return_value = ["prometheus", "node-exporter"]
        async with Client(mcp) as client:
            result = await client.call_tool("get_label_values", {"label": "job"})
        data = json.loads(result.content[0].text)
        assert data["label"] == "job"
        assert data["total"] == 2

    @pytest.mark.asyncio
    async def test_get_label_values_invalid_name(self, mock_make_request):
        async with Client(mcp) as client:
            result = await client.call_tool("get_label_values", {"label": "invalid-label!"})
        data = json.loads(result.content[0].text)
        assert "error" in data
        assert data["status"] == "error"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestMCPToolErrorHandling:

    @pytest.mark.asyncio
    async def test_health_check_degraded_on_prometheus_failure(self, mock_make_request):
        mock_make_request.side_effect = Exception("Connection timeout")
        async with Client(mcp) as client:
            result = await client.call_tool("health_check", {"target": "prometheus"})
        data = json.loads(result.content[0].text)
        assert data["status"] == "degraded"
        assert data["prometheus"]["connectivity"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_health_check_degraded_on_ruler_failure(self, mock_make_request):
        mock_make_request.side_effect = Exception("Ruler unreachable")
        original_ruler = config.ruler_url
        config.ruler_url = "http://ruler:9090"
        try:
            async with Client(mcp) as client:
                result = await client.call_tool("health_check", {"target": "ruler"})
            data = json.loads(result.content[0].text)
            assert data["status"] == "degraded"
            assert data["ruler"]["connectivity"] == "unhealthy"
            assert "Ruler unreachable" in data["ruler"]["error"]
        finally:
            config.ruler_url = original_ruler

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_without_url(self, mock_make_request):
        original_url = config.url
        config.url = ""
        try:
            async with Client(mcp) as client:
                result = await client.call_tool("health_check", {"target": "prometheus"})
            data = json.loads(result.content[0].text)
            assert data["status"] == "unhealthy"
            assert data["prometheus"]["connectivity"] == "unhealthy"
        finally:
            config.url = original_url

    @pytest.mark.asyncio
    async def test_health_check_invalid_target(self, mock_make_request):
        async with Client(mcp) as client:
            result = await client.call_tool("health_check", {"target": "invalid"})
        data = json.loads(result.content[0].text)
        assert data["status"] == "error"
        assert "error" in data

    @pytest.mark.asyncio
    async def test_get_metric_metadata_error_handling(self, mock_make_request):
        mock_make_request.side_effect = Exception("Connection refused")
        async with Client(mcp) as client:
            result = await client.call_tool("get_metric_metadata", {"metric": "up"})
        data = json.loads(result.content[0].text)
        assert "error" in data
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_get_metric_metadata_non_dict_response(self, mock_make_request):
        mock_make_request.return_value = "unexpected string"
        async with Client(mcp) as client:
            result = await client.call_tool("get_metric_metadata", {"metric": "up"})
        data = json.loads(result.content[0].text)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_get_metric_labels_non_list_response(self, mock_make_request):
        mock_make_request.return_value = "not a list"
        async with Client(mcp) as client:
            result = await client.call_tool("get_metric_labels", {"metric": "up"})
        data = json.loads(result.content[0].text)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_get_label_values_error_handling(self, mock_make_request):
        mock_make_request.side_effect = Exception("Connection refused")
        async with Client(mcp) as client:
            result = await client.call_tool("get_label_values", {"label": "job"})
        data = json.loads(result.content[0].text)
        assert "error" in data
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_get_alerts_with_ruler_url(self, mock_make_request):
        mock_make_request.return_value = {"alerts": [{"state": "firing", "labels": {"alertname": "Test"}}]}
        original_ruler = config.ruler_url
        config.ruler_url = "http://ruler:9090"
        try:
            async with Client(mcp) as client:
                result = await client.call_tool("get_alerts", {})
            mock_make_request.assert_called_once_with("alerts", base_url="http://ruler:9090")
            data = json.loads(result.content[0].text)
            assert data["firing"] == 1
        finally:
            config.ruler_url = original_ruler

    @pytest.mark.asyncio
    async def test_get_rules_with_ruler_url(self, mock_make_request):
        mock_make_request.return_value = {"groups": [{"name": "g1", "rules": [{"name": "r1"}]}]}
        original_ruler = config.ruler_url
        config.ruler_url = "http://ruler:9090"
        try:
            async with Client(mcp) as client:
                result = await client.call_tool("get_rules", {})
            mock_make_request.assert_called_once_with("rules", base_url="http://ruler:9090")
            data = json.loads(result.content[0].text)
            assert data["total_rules"] == 1
        finally:
            config.ruler_url = original_ruler


# ---------------------------------------------------------------------------
# Data format compliance
# ---------------------------------------------------------------------------

class TestMCPDataFormats:

    @pytest.mark.asyncio
    async def test_all_tools_return_json_serializable(self, mock_make_request):
        mock_make_request.side_effect = [
            {"resultType": "vector", "result": []},
            {"resultType": "matrix", "result": []},
            ["metric1", "metric2"],
            {"up": [{"type": "gauge", "help": "test"}]},
            [{"__name__": "m", "job": "test"}],
            ["prometheus"],
            {"alerts": []},
            {"groups": []},
            {"activeTargets": [], "droppedTargets": []},
        ]
        tool_calls = [
            ("execute_query", {"query": "up"}),
            ("execute_range_query", {"query": "up", "start": "now-1h", "end": "now", "step": "1m"}),
            ("list_metrics", {}),
            ("get_metric_metadata", {"metric": "up"}),
            ("get_metric_labels", {"metric": "m"}),
            ("get_label_values", {"label": "job"}),
            ("get_alerts", {}),
            ("get_rules", {}),
            ("get_targets", {}),
        ]
        async with Client(mcp) as client:
            for tool_name, args in tool_calls:
                result = await client.call_tool(tool_name, args)
                text = result.content[0].text
                try:
                    json.loads(text)
                except (TypeError, ValueError) as e:
                    pytest.fail(f"Tool {tool_name} returned non-JSON-serializable data: {e}")


# ---------------------------------------------------------------------------
# Server configuration
# ---------------------------------------------------------------------------

class TestMCPServerConfiguration:

    def test_transport_type_validation(self):
        valid = ["stdio", "sse", "streamable-http"]
        for t in valid:
            assert t in TransportType.values()
        for t in ["http", "tcp", "websocket"]:
            assert t not in TransportType.values()

    def test_server_config_validation(self):
        cfg = MCPServerConfig(mcp_server_transport="sse", mcp_bind_host="127.0.0.1", mcp_bind_port=8000)
        assert cfg.mcp_server_transport == "sse"

    def test_stdio_config_allows_empty_host_port(self):
        cfg = MCPServerConfig(mcp_server_transport="stdio", mcp_bind_host=None, mcp_bind_port=None)
        assert cfg.mcp_server_transport == "stdio"

    def test_authentication_configuration(self):
        orig = (config.username, config.password, config.token)
        try:
            config.username = config.password = config.token = None
            h, a = get_prometheus_auth()
            assert h == {} and a is None

            config.username, config.password = "u", "p"
            h, a = get_prometheus_auth()
            assert a == ("u", "p")

            config.token = "tok"
            h, a = get_prometheus_auth()
            assert h["Authorization"] == "Bearer tok" and a is None
        finally:
            config.username, config.password, config.token = orig

    def test_tool_descriptions_are_present(self):
        tools = [execute_query, execute_range_query, list_metrics,
                 get_metric_metadata, get_metric_labels, get_label_values,
                 get_targets, health_check, get_alerts, get_rules]
        for tool in tools:
            has_desc = (
                hasattr(tool, 'description') and tool.description
                or hasattr(tool, '__doc__') and tool.__doc__
            )
            assert has_desc, f"{tool.__name__} has no description or docstring"


# ---------------------------------------------------------------------------
# run_server stdio branch
# ---------------------------------------------------------------------------

class TestRunServerBranches:

    @patch("monitor_mcp_server.tools.setup_environment")
    @patch("monitor_mcp_server.tools.mcp.run")
    @patch("monitor_mcp_server.tools.config")
    def test_run_server_stdio(self, mock_config, mock_run, mock_setup):
        mock_setup.return_value = True
        mock_config.mcp_server_config = MCPServerConfig(
            mcp_server_transport="stdio", mcp_bind_host=None, mcp_bind_port=None
        )
        from monitor_mcp_server.tools import run_server
        run_server()
        mock_run.assert_called_once_with(transport="stdio")
