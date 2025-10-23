"""Tests for the MCP tools functionality."""

import pytest
import json
from unittest.mock import patch, MagicMock
from fastmcp import Client
from prometheus_mcp_server.server import mcp, execute_query, execute_range_query, list_metrics, get_metric_metadata, get_metric_labels, get_targets

@pytest.fixture
def mock_make_request():
    """Mock the make_prometheus_request function."""
    with patch("prometheus_mcp_server.server.make_prometheus_request") as mock:
        yield mock

@pytest.mark.asyncio
async def test_execute_query(mock_make_request):
    """Test the execute_query tool."""
    # Setup
    mock_make_request.return_value = {
        "resultType": "vector",
        "result": [{"metric": {"__name__": "up"}, "value": [1617898448.214, "1"]}]
    }

    async with Client(mcp) as client:
        # Execute
        result = await client.call_tool("execute_query", {"query":"up"})

        # Verify
        mock_make_request.assert_called_once_with("query", params={"query": "up"})
        assert result.data["resultType"] == "vector"
        assert len(result.data["result"]) == 1

@pytest.mark.asyncio
async def test_execute_query_with_time(mock_make_request):
    """Test the execute_query tool with a specified time."""
    # Setup
    mock_make_request.return_value = {
        "resultType": "vector",
        "result": [{"metric": {"__name__": "up"}, "value": [1617898448.214, "1"]}]
    }

    async with Client(mcp) as client:
        # Execute
        result = await client.call_tool("execute_query", {"query":"up", "time":"2023-01-01T00:00:00Z"})
        
        # Verify
        mock_make_request.assert_called_once_with("query", params={"query": "up", "time": "2023-01-01T00:00:00Z"})
        assert result.data["resultType"] == "vector"

@pytest.mark.asyncio
async def test_execute_range_query(mock_make_request):
    """Test the execute_range_query tool."""
    # Setup
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
        # Execute
        result = await client.call_tool(
            "execute_range_query",{
            "query": "up", 
            "start": "2023-01-01T00:00:00Z", 
            "end": "2023-01-01T01:00:00Z", 
            "step": "15s"
        })

        # Verify
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
    """Test the list_metrics tool."""
    # Setup
    mock_make_request.return_value = ["up", "go_goroutines", "http_requests_total"]

    async with Client(mcp) as client:
        # Execute
        result = await client.call_tool("list_metrics", {})

        # Verify
        mock_make_request.assert_called_once_with("label/__name__/values")
        assert result.data == ["up", "go_goroutines", "http_requests_total"]

@pytest.mark.asyncio
async def test_get_metric_metadata(mock_make_request):
    """Test the get_metric_metadata tool."""
    # Setup
    mock_make_request.return_value = {
        "up": [
            {"type": "gauge", "help": "Up indicates if the scrape was successful", "unit": ""}
        ]
    }

    async with Client(mcp) as client:
        # Execute
        result = await client.call_tool("get_metric_metadata", {"metric":"up"})

        payload = result.content[0].text
        json_data = json.loads(payload)

        # Verify
        mock_make_request.assert_called_once_with("metadata", params={"metric": "up"})
        assert isinstance(json_data, dict)
        assert "up" in json_data
        assert json_data["up"][0]["type"] == "gauge"

@pytest.mark.asyncio
async def test_get_metric_labels(mock_make_request):
    """Test the get_metric_labels tool."""
    # Setup
    mock_make_request.return_value = [
        {"__name__": "http_requests_total", "job": "api", "method": "GET", "status": "200"},
        {"__name__": "http_requests_total", "job": "api", "method": "POST", "status": "200"},
        {"__name__": "http_requests_total", "job": "web", "method": "GET", "status": "404"},
        {"__name__": "http_requests_total", "job": "web", "method": "GET", "status": "200"}
    ]

    async with Client(mcp) as client:
        # Execute
        result = await client.call_tool("get_metric_labels", {"metric": "http_requests_total"})

        payload = result.content[0].text
        json_data = json.loads(payload)

        # Verify
        mock_make_request.assert_called_once_with("series", params={"match[]": "http_requests_total", "limit": "1"})
        assert isinstance(json_data, dict)
        assert json_data["metric"] == "http_requests_total"
        assert json_data["series_count"] == 4
        assert json_data["label_count"] == 3
        assert "limited" in json_data
        assert json_data["limited"] == True  # Any data means limited is True
        
        # Check labels
        labels = json_data["labels"]
        assert "job" in labels
        assert "method" in labels
        assert "status" in labels
        assert set(labels["job"]) == {"api", "web"}
        assert set(labels["method"]) == {"GET", "POST"}
        assert set(labels["status"]) == {"200", "404"}

@pytest.mark.asyncio
async def test_get_metric_labels_empty_response(mock_make_request):
    """Test the get_metric_labels tool with empty response."""
    # Setup
    mock_make_request.return_value = []

    async with Client(mcp) as client:
        # Execute
        result = await client.call_tool("get_metric_labels", {"metric": "nonexistent_metric"})

        payload = result.content[0].text
        json_data = json.loads(payload)

        # Verify
        mock_make_request.assert_called_once_with("series", params={"match[]": "nonexistent_metric", "limit": "1"})
        assert isinstance(json_data, dict)
        assert json_data["metric"] == "nonexistent_metric"
        assert json_data["series_count"] == 0
        assert json_data["labels"] == {}
        assert "No time series found" in json_data["message"]

@pytest.mark.asyncio
async def test_get_metric_labels_error_handling(mock_make_request):
    """Test the get_metric_labels tool error handling."""
    # Setup
    mock_make_request.side_effect = Exception("Connection error")

    async with Client(mcp) as client:
        # Execute
        result = await client.call_tool("get_metric_labels", {"metric": "test_metric"})

        payload = result.content[0].text
        json_data = json.loads(payload)

        # Verify
        assert isinstance(json_data, dict)
        assert "error" in json_data
        assert "Connection error" in json_data["error"]
        assert json_data["metric"] == "test_metric"
        assert json_data["status"] == "error"

@pytest.mark.asyncio
async def test_get_metric_labels_with_limit(mock_make_request):
    """Test the get_metric_labels tool with limit applied."""
    # Setup - simulate 1 series (minimal data for label discovery)
    mock_series = [{
        "__name__": "large_metric", 
        "job": "api", 
        "instance": "localhost:8080", 
        "status": "200"
    }]
    
    mock_make_request.return_value = mock_series

    async with Client(mcp) as client:
        # Execute
        result = await client.call_tool("get_metric_labels", {"metric": "large_metric"})

        payload = result.content[0].text
        json_data = json.loads(payload)

        # Verify
        mock_make_request.assert_called_once_with("series", params={"match[]": "large_metric", "limit": "1"})
        assert isinstance(json_data, dict)
        assert json_data["metric"] == "large_metric"
        assert json_data["series_count"] == 1
        assert json_data["limited"] == True  # 1 series >= 1 limit, so limited is True
        
        # Check that we get all label keys from the single series
        labels = json_data["labels"]
        assert "job" in labels
        assert "instance" in labels
        assert "status" in labels
        # With limit=1, we only get one value per label
        assert labels["job"] == ["api"]
        assert labels["instance"] == ["localhost:8080"]
        assert labels["status"] == ["200"]

@pytest.mark.asyncio
async def test_get_targets(mock_make_request):
    """Test the get_targets tool."""
    # Setup
    mock_make_request.return_value = {
        "activeTargets": [
            {"discoveredLabels": {"__address__": "localhost:9090"}, "labels": {"job": "prometheus"}, "health": "up"}
        ],
        "droppedTargets": []
    }

    async with Client(mcp) as client:
        # Execute
        result = await client.call_tool("get_targets",{})

        payload = result.content[0].text
        json_data = json.loads(payload)

        # Verify
        mock_make_request.assert_called_once_with("targets")
        assert len(json_data["activeTargets"]) == 1
        assert json_data["activeTargets"][0]["health"] == "up"
        assert len(json_data["droppedTargets"]) == 0
