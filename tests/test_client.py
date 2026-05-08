"""Tests for the HTTP client functionality (httpx.AsyncClient 版本)。"""

import json as _json
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from monitor_mcp_server.client import (
    make_prometheus_request,
    get_prometheus_auth,
    sanitize_url,
)
from monitor_mcp_server.config import config


pytestmark = pytest.mark.asyncio


def _make_response(*, status_code: int = 200, json_payload=None, raise_status: BaseException = None,
                   json_side_effect: BaseException = None) -> MagicMock:
    """构造一个行为像 httpx.Response 的 mock 对象。"""
    resp = MagicMock()
    resp.status_code = status_code
    if raise_status is not None:
        resp.raise_for_status = MagicMock(side_effect=raise_status)
    else:
        resp.raise_for_status = MagicMock()
    if json_side_effect is not None:
        resp.json = MagicMock(side_effect=json_side_effect)
    else:
        resp.json = MagicMock(return_value=json_payload or {
            "status": "success",
            "data": {"resultType": "vector", "result": []},
        })
    return resp


@pytest.fixture
def mock_client():
    """把全局 AsyncClient 替换成 AsyncMock，避免真实网络调用。"""
    with patch("monitor_mcp_server.client._get_async_client") as mock_get:
        fake = MagicMock()
        fake.get = AsyncMock()
        mock_get.return_value = fake
        yield fake


@pytest.fixture(autouse=True)
def _stub_async_sleep():
    """把 asyncio.sleep 打桩，避免重试用例真的等待。"""
    with patch("monitor_mcp_server.client.asyncio.sleep", new=AsyncMock()):
        yield


# ---------------------------------------------------------------------------
# 基础请求
# ---------------------------------------------------------------------------

async def test_make_prometheus_request_no_auth(mock_client):
    mock_client.get.return_value = _make_response()
    config.url = "http://test:9090"
    config.username = None
    config.password = None
    config.token = None

    result = await make_prometheus_request("query", {"query": "up"})

    mock_client.get.assert_awaited_once()
    assert result == {"resultType": "vector", "result": []}


async def test_make_prometheus_request_with_basic_auth(mock_client):
    mock_client.get.return_value = _make_response()
    config.url = "http://test:9090"
    config.username = "user"
    config.password = "pass"
    config.token = None

    await make_prometheus_request("query", {"query": "up"})

    kwargs = mock_client.get.call_args.kwargs
    assert kwargs["auth"] == ("user", "pass")


async def test_make_prometheus_request_with_token_auth(mock_client):
    mock_client.get.return_value = _make_response()
    config.url = "http://test:9090"
    config.username = None
    config.password = None
    config.token = "token123"

    await make_prometheus_request("query", {"query": "up"})

    kwargs = mock_client.get.call_args.kwargs
    assert kwargs["headers"]["Authorization"] == "Bearer token123"


async def test_make_prometheus_request_error(mock_client):
    mock_client.get.return_value = _make_response(
        json_payload={"status": "error", "error": "Test error"},
    )
    config.url = "http://test:9090"

    with pytest.raises(ValueError, match="Prometheus API 错误: Test error"):
        await make_prometheus_request("query", {"query": "up"})


# ---------------------------------------------------------------------------
# 网络异常 & 重试
# ---------------------------------------------------------------------------

async def test_make_prometheus_request_connection_error(mock_client):
    mock_client.get.side_effect = httpx.ConnectError("Connection failed")
    config.url = "http://test:9090"

    with pytest.raises(httpx.ConnectError):
        await make_prometheus_request("query", {"query": "up"})


async def test_make_prometheus_request_timeout(mock_client):
    mock_client.get.side_effect = httpx.ReadTimeout("Request timeout")
    config.url = "http://test:9090"

    with pytest.raises(httpx.ReadTimeout):
        await make_prometheus_request("query", {"query": "up"})


async def test_make_prometheus_request_http_error(mock_client):
    error = httpx.HTTPStatusError(
        "500 Server Error",
        request=httpx.Request("GET", "http://test/x"),
        response=httpx.Response(500),
    )
    mock_client.get.return_value = _make_response(status_code=500, raise_status=error)
    config.url = "http://test:9090"

    with pytest.raises(httpx.HTTPStatusError):
        await make_prometheus_request("query", {"query": "up"})


async def test_make_prometheus_request_retry_on_503(mock_client):
    fail_resp = MagicMock()
    fail_resp.status_code = 503

    ok_resp = _make_response()
    mock_client.get.side_effect = [fail_resp, ok_resp]
    config.url = "http://test:9090"

    result = await make_prometheus_request("query", {"query": "up"})

    assert result == {"resultType": "vector", "result": []}
    assert mock_client.get.await_count == 2


async def test_make_prometheus_request_retry_connection_then_succeed(mock_client):
    ok_resp = _make_response()
    mock_client.get.side_effect = [httpx.ConnectError("boom"), ok_resp]
    config.url = "http://test:9090"

    result = await make_prometheus_request("query", {"query": "up"})

    assert result == {"resultType": "vector", "result": []}
    assert mock_client.get.await_count == 2


async def test_make_prometheus_request_request_exception(mock_client):
    mock_client.get.side_effect = httpx.RequestError("Generic request error")
    config.url = "http://test:9090"

    with pytest.raises(httpx.HTTPError):
        await make_prometheus_request("query", {"query": "up"})


async def test_make_prometheus_request_generic_exception(mock_client):
    mock_client.get.side_effect = RuntimeError("Unexpected error")
    config.url = "http://test:9090"

    with pytest.raises(RuntimeError, match="Unexpected error"):
        await make_prometheus_request("query", {"query": "up"})


# ---------------------------------------------------------------------------
# JSON 解析
# ---------------------------------------------------------------------------

async def test_make_prometheus_request_json_decode_error(mock_client):
    mock_client.get.return_value = _make_response(
        json_side_effect=_json.JSONDecodeError("Invalid JSON", "", 0),
    )
    config.url = "http://test:9090"

    with pytest.raises(ValueError, match="Prometheus 返回了无效的 JSON 响应"):
        await make_prometheus_request("query", {"query": "up"})


async def test_make_prometheus_request_list_data_format(mock_client):
    mock_client.get.return_value = _make_response(
        json_payload={
            "status": "success",
            "data": [{"metric": {}, "value": [1609459200, "1"]}],
        },
    )
    config.url = "http://test:9090"

    result = await make_prometheus_request("query", {"query": "up"})

    assert result == [{"metric": {}, "value": [1609459200, "1"]}]


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

async def test_make_prometheus_request_missing_url(mock_client):
    original_url = config.url
    config.url = None
    try:
        with pytest.raises(ValueError, match="Prometheus 配置缺失"):
            await make_prometheus_request("query", {"query": "up"})
    finally:
        config.url = original_url


async def test_make_prometheus_request_with_org_id(mock_client):
    mock_client.get.return_value = _make_response()
    config.url = "http://test:9090"
    original = config.org_id
    config.org_id = "test-org"
    try:
        await make_prometheus_request("query", {"query": "up"})
        kwargs = mock_client.get.call_args.kwargs
        assert kwargs["headers"]["X-Scope-OrgID"] == "test-org"
    finally:
        config.org_id = original


async def test_make_prometheus_request_with_base_url(mock_client):
    mock_client.get.return_value = _make_response()
    config.url = "http://query:9090"
    config.token = None
    config.username = None
    config.password = None

    await make_prometheus_request("alerts", base_url="http://ruler:9090")

    args = mock_client.get.call_args.args
    assert args[0] == "http://ruler:9090/api/v1/alerts"


# ---------------------------------------------------------------------------
# 后端前缀
# ---------------------------------------------------------------------------

async def test_mimir_backend_uses_prometheus_prefix(mock_client):
    mock_client.get.return_value = _make_response()
    original = config.backend_type
    config.backend_type = "mimir"
    config.url = "http://mimir:9090"
    config.token = None
    config.username = None
    config.password = None
    try:
        await make_prometheus_request("query", {"query": "up"})
        url = mock_client.get.call_args.args[0]
        assert url == "http://mimir:9090/prometheus/api/v1/query"
    finally:
        config.backend_type = original


async def test_prometheus_backend_uses_default_prefix(mock_client):
    mock_client.get.return_value = _make_response()
    original = config.backend_type
    config.backend_type = "thanos"
    config.url = "http://thanos:9090"
    config.token = None
    config.username = None
    config.password = None
    try:
        await make_prometheus_request("query", {"query": "up"})
        url = mock_client.get.call_args.args[0]
        assert url == "http://thanos:9090/api/v1/query"
    finally:
        config.backend_type = original


# ---------------------------------------------------------------------------
# URL 脱敏（同步函数，保持非 async）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio(loop_scope=None)
async def test_sanitize_url_removes_credentials():
    assert sanitize_url("http://user:pass@host:9090/path") == "http://host:9090/path"
    assert sanitize_url("http://host:9090/path") == "http://host:9090/path"
    assert sanitize_url("http://user@host/path") == "http://host/path"


async def test_sanitize_url_masks_sensitive_query_params():
    url = "https://h/x?token=abc&foo=1&Api_Key=xxx&Password=yyy"
    sanitized = sanitize_url(url)
    assert "abc" not in sanitized
    assert "xxx" not in sanitized
    assert "yyy" not in sanitized
    assert "token=***" in sanitized
    assert "Api_Key=***" in sanitized
    assert "Password=***" in sanitized
    assert "foo=1" in sanitized


async def test_sanitize_url_keeps_non_sensitive_query():
    assert sanitize_url("https://h/x?start=0&end=1") == "https://h/x?start=0&end=1"


async def test_get_prometheus_auth_token_wins_over_basic():
    original = (config.token, config.username, config.password)
    try:
        config.token = "tok"
        config.username = "u"
        config.password = "p"
        headers, auth = get_prometheus_auth()
        assert headers["Authorization"] == "Bearer tok"
        assert auth is None
    finally:
        config.token, config.username, config.password = original
