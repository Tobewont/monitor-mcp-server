"""Tests for setup_environment and run_server."""

import pytest
from unittest.mock import patch, MagicMock
from monitor_mcp_server.config import MCPServerConfig
from monitor_mcp_server.client import setup_environment
from monitor_mcp_server.tools import run_server

def _default_mock(mock_config, **overrides):
    """为 MagicMock config 设置默认属性，避免 backend_type 等字段变成 MagicMock 对象。"""
    defaults = {
        "url": "http://test:9090",
        "ruler_url": None,
        "backend_type": "prometheus",
        "username": None,
        "password": None,
        "token": None,
        "org_id": None,
        "mcp_server_config": None,
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock_config, k, v)


@patch("monitor_mcp_server.client.config")
def test_setup_environment_success(mock_config):
    _default_mock(mock_config)

    assert setup_environment() is True

@patch("monitor_mcp_server.client.config")
def test_setup_environment_missing_url(mock_config):
    _default_mock(mock_config, url="")

    assert setup_environment() is False

@patch("monitor_mcp_server.client.config")
def test_setup_environment_with_auth(mock_config):
    _default_mock(mock_config, username="user", password="pass")

    assert setup_environment() is True

@patch("monitor_mcp_server.client.config")
def test_setup_environment_with_custom_mcp_config(mock_config):
    _default_mock(
        mock_config,
        username="user", password="pass",
        mcp_server_config=MCPServerConfig(
            mcp_server_transport="sse",
            mcp_bind_host="localhost",
            mcp_bind_port=5000,
        ),
    )

    assert setup_environment() is True

@patch("monitor_mcp_server.client.config")
def test_setup_environment_with_custom_mcp_config_caps(mock_config):
    _default_mock(
        mock_config,
        username="user", password="pass",
        mcp_server_config=MCPServerConfig(
            mcp_server_transport="SSE",
            mcp_bind_host="localhost",
            mcp_bind_port=5000,
        ),
    )

    assert setup_environment() is True

@patch("monitor_mcp_server.client.config")
def test_setup_environment_with_undefined_mcp_server_transports(mock_config):
    with pytest.raises(ValueError, match="PROMETHEUS_MCP_SERVER_TRANSPORT 为必填项"):
        mock_config.mcp_server_config = MCPServerConfig(
            mcp_server_transport=None,
            mcp_bind_host="localhost",
            mcp_bind_port=5000
        )

@patch("monitor_mcp_server.client.config")
def test_setup_environment_with_undefined_mcp_bind_host(mock_config):
    with pytest.raises(ValueError, match="PROMETHEUS_MCP_BIND_HOST 为必填项"):
        mock_config.mcp_server_config = MCPServerConfig(
            mcp_server_transport="sse",
            mcp_bind_host=None,
            mcp_bind_port=5000
        )

@patch("monitor_mcp_server.client.config")
def test_setup_environment_with_undefined_mcp_bind_port(mock_config):
    with pytest.raises(ValueError, match="PROMETHEUS_MCP_BIND_PORT 为必填项"):
        mock_config.mcp_server_config = MCPServerConfig(
            mcp_server_transport="sse",
            mcp_bind_host="localhost",
            mcp_bind_port=None
        )

@patch("monitor_mcp_server.client.config")
def test_setup_environment_with_bad_mcp_config_transport(mock_config):
    _default_mock(
        mock_config,
        username="user", password="pass",
        mcp_server_config=MCPServerConfig(
            mcp_server_transport="wrong_transport",
            mcp_bind_host="localhost",
            mcp_bind_port=5000,
        ),
    )

    assert setup_environment() is False

@patch("monitor_mcp_server.client.config")
def test_setup_environment_with_bad_mcp_config_port(mock_config):
    _default_mock(
        mock_config,
        username="user", password="pass",
        mcp_server_config=MCPServerConfig(
            mcp_server_transport="sse",
            mcp_bind_host="localhost",
            mcp_bind_port="some_string",
        ),
    )

    assert setup_environment() is False

@patch("monitor_mcp_server.tools.setup_environment")
@patch("monitor_mcp_server.tools.mcp.run")
@patch("monitor_mcp_server.tools.sys.exit")
def test_run_server_success(mock_exit, mock_run, mock_setup):
    mock_setup.return_value = True
    run_server()

    mock_setup.assert_called_once()
    mock_exit.assert_not_called()

@patch("monitor_mcp_server.tools.setup_environment")
@patch("monitor_mcp_server.tools.mcp.run")
@patch("monitor_mcp_server.tools.sys.exit")
def test_run_server_setup_failure(mock_exit, mock_run, mock_setup):
    mock_setup.return_value = False
    mock_exit.side_effect = SystemExit(1)

    with pytest.raises(SystemExit):
        run_server()

    mock_setup.assert_called_once()
    mock_run.assert_not_called()

@patch("monitor_mcp_server.client.config")
def test_setup_environment_bearer_token_auth(mock_config):
    _default_mock(mock_config, username="", password="", token="bearer_token_123")

    assert setup_environment() is True

@patch("monitor_mcp_server.tools.setup_environment")
@patch("monitor_mcp_server.tools.mcp.run")
@patch("monitor_mcp_server.tools.config")
def test_run_server_streamable_http_transport(mock_config, mock_run, mock_setup):
    mock_setup.return_value = True
    mock_config.mcp_server_config = MCPServerConfig(
        mcp_server_transport="streamable-http",
        mcp_bind_host="localhost",
        mcp_bind_port=8000
    )

    run_server()

    mock_run.assert_called_once_with(transport="streamable-http", host="localhost", port=8000)

@patch("monitor_mcp_server.tools.setup_environment")
@patch("monitor_mcp_server.tools.mcp.run")
@patch("monitor_mcp_server.tools.config")
def test_run_server_sse_transport(mock_config, mock_run, mock_setup):
    mock_setup.return_value = True
    mock_config.mcp_server_config = MCPServerConfig(
        mcp_server_transport="sse",
        mcp_bind_host="0.0.0.0",
        mcp_bind_port=9090
    )

    run_server()

    mock_run.assert_called_once_with(transport="sse", host="0.0.0.0", port=9090)

@patch("monitor_mcp_server.client.config")
def test_setup_environment_invalid_url_scheme(mock_config):
    """Test setup_environment rejects URL without http(s) scheme."""
    _default_mock(mock_config, url="ftp://test:9090")

    assert setup_environment() is False

@patch("monitor_mcp_server.client.config")
def test_setup_environment_invalid_ruler_url(mock_config):
    """Test setup_environment rejects invalid RULER_URL."""
    _default_mock(mock_config, ruler_url="ftp://ruler:9090")

    assert setup_environment() is False

@patch("monitor_mcp_server.client.config")
def test_setup_environment_with_ruler_url(mock_config):
    """Test setup_environment accepts valid RULER_URL."""
    _default_mock(mock_config, url="http://query:9090", ruler_url="http://ruler:9090")

    assert setup_environment() is True


@patch("monitor_mcp_server.client.config")
def test_setup_environment_invalid_backend_type(mock_config):
    """Test setup_environment rejects unknown BACKEND_TYPE."""
    _default_mock(mock_config, backend_type="invalid")

    assert setup_environment() is False


@patch("monitor_mcp_server.client.config")
def test_setup_environment_backend_thanos(mock_config):
    """Thanos 模式合法配置通过校验。"""
    _default_mock(mock_config, backend_type="thanos", ruler_url="http://ruler:9090")

    assert setup_environment() is True


@patch("monitor_mcp_server.client.config")
def test_setup_environment_backend_mimir(mock_config):
    """Mimir 模式合法配置通过校验。"""
    _default_mock(mock_config, backend_type="mimir", org_id="tenant-1")

    assert setup_environment() is True
