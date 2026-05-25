"""Tests for monitor-agent configuration management."""

import pytest
import httpx
from fastmcp import Client, FastMCP

from monitor_mcp_server.config import MonitorAgentConfig, PrometheusConfig
from monitor_mcp_server.client import setup_environment
from monitor_mcp_server.monitor_agent import (
    MonitorAgentService,
    register_monitor_agent_tools,
    resolve_asset_id,
    validate_monitor_agent_yaml,
)


def test_setup_environment_requires_s3_settings_when_monitor_agent_enabled():
    cfg = PrometheusConfig(
        url="http://prometheus.example",
        monitor_agent=MonitorAgentConfig(enabled=True),
    )

    assert setup_environment(cfg) is False


@pytest.mark.asyncio
async def test_resolve_asset_id_reads_first_configured_label(monkeypatch):
    async def fake_request(endpoint, params=None, **kwargs):
        assert endpoint == "query"
        assert params == {"query": 'up{instance=~"10.0.0.1(:.*)?"}'}
        return {
            "resultType": "vector",
            "result": [
                {
                    "metric": {
                        "instance": "10.0.0.1:9100",
                        "asset_id": "asset-001",
                    },
                    "value": [1710000000, "1"],
                }
            ],
        }

    monkeypatch.setattr("monitor_mcp_server.monitor_agent.make_prometheus_request", fake_request)

    result = await resolve_asset_id(
        "10.0.0.1",
        MonitorAgentConfig(
            enabled=True,
            asset_query_template='up{instance=~"{ip}(:.*)?"}',
            asset_id_labels=("asset_id", "hostname"),
        ),
    )

    assert result["status"] == "success"
    assert result["asset_id"] == "asset-001"
    assert result["asset_label"] == "asset_id"
    assert result["matches"] == 1


@pytest.mark.asyncio
async def test_resolve_asset_id_rejects_conflicting_assets(monkeypatch):
    async def fake_request(endpoint, params=None, **kwargs):
        return {
            "resultType": "vector",
            "result": [
                {"metric": {"asset_id": "asset-001"}, "value": [1, "1"]},
                {"metric": {"asset_id": "asset-002"}, "value": [1, "1"]},
            ],
        }

    monkeypatch.setattr("monitor_mcp_server.monitor_agent.make_prometheus_request", fake_request)

    result = await resolve_asset_id("10.0.0.1", MonitorAgentConfig(enabled=True))

    assert result["status"] == "error"
    assert result["error_type"] == "client"
    assert "多个资产编号" in result["error"]


def test_validate_monitor_agent_yaml_rejects_invalid_yaml():
    result = validate_monitor_agent_yaml("scrape_configs: [")

    assert result["status"] == "error"
    assert result["error_type"] == "client"


class FakeBody:
    def __init__(self, text):
        self.text = text

    def read(self):
        return self.text.encode("utf-8")


class FakeS3Client:
    def __init__(self, existing=None, fail_copy=False):
        self.objects = dict(existing or {})
        self.fail_copy = fail_copy
        self.copied = []
        self.puts = []
        self.deletes = []

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise Exception("not found")
        return {}

    def copy_object(self, Bucket, CopySource, Key):
        if self.fail_copy:
            raise Exception("copy failed")
        self.copied.append((CopySource["Key"], Key))
        self.objects[Key] = self.objects[CopySource["Key"]]

    def put_object(self, Bucket, Key, Body, ContentType):
        self.puts.append((Key, Body, ContentType))
        self.objects[Key] = Body

    def delete_object(self, Bucket, Key):
        self.deletes.append(Key)
        self.objects.pop(Key, None)

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise Exception("not found")
        return {"Body": FakeBody(self.objects[Key])}

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):
        return {
            "Contents": [
                {"Key": key, "Size": len(value)}
                for key, value in sorted(self.objects.items())
                if key.startswith(Prefix)
            ],
            "IsTruncated": False,
        }


def make_service(s3_client):
    return MonitorAgentService(
        MonitorAgentConfig(
            enabled=True,
            s3_bucket="bucket",
            config_prefix="monitor-agent/configs",
            backup_prefix="monitor-agent/backups",
        ),
        s3_client=s3_client,
    )


@pytest.mark.asyncio
async def test_put_config_backs_up_existing_object_before_write():
    s3 = FakeS3Client({"monitor-agent/configs/asset-001.yaml": "old: true\n"})
    service = make_service(s3)

    result = await service.put_config(content="new: true\n", asset_id="asset-001")

    assert result["status"] == "success"
    assert result["backed_up"] is True
    assert s3.copied[0][0] == "monitor-agent/configs/asset-001.yaml"
    assert s3.puts == [
        ("monitor-agent/configs/asset-001.yaml", "new: true\n", "application/x-yaml")
    ]


@pytest.mark.asyncio
async def test_put_config_stops_when_backup_fails():
    s3 = FakeS3Client(
        {"monitor-agent/configs/asset-001.yaml": "old: true\n"},
        fail_copy=True,
    )
    service = make_service(s3)

    result = await service.put_config(content="new: true\n", asset_id="asset-001")

    assert result["status"] == "error"
    assert not s3.puts


@pytest.mark.asyncio
async def test_delete_config_backs_up_before_delete():
    s3 = FakeS3Client({"monitor-agent/configs/asset-001.yaml": "old: true\n"})
    service = make_service(s3)

    result = await service.delete_config(asset_id="asset-001")

    assert result["status"] == "success"
    assert result["backed_up"] is True
    assert s3.copied[0][0] == "monitor-agent/configs/asset-001.yaml"
    assert s3.deletes == ["monitor-agent/configs/asset-001.yaml"]


@pytest.mark.asyncio
async def test_reload_calls_monitor_agent_url(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.client = real_async_client(transport=transport)

        async def __aenter__(self):
            return self.client

        async def __aexit__(self, exc_type, exc, tb):
            await self.client.aclose()

    monkeypatch.setattr("monitor_mcp_server.monitor_agent.httpx.AsyncClient", FakeAsyncClient)

    service = MonitorAgentService(
        MonitorAgentConfig(
            enabled=True,
            reload_url_template="http://{ip}:12345/reload",
            reload_timeout=3,
        )
    )

    result = await service.reload("10.0.0.1")

    assert result["status"] == "success"
    assert str(requests[0].url) == "http://10.0.0.1:12345/reload"


@pytest.mark.asyncio
async def test_monitor_agent_tools_are_not_registered_by_default():
    from monitor_mcp_server.tools import mcp

    async with Client(mcp) as client:
        tools = await client.list_tools()

    tool_names = {tool.name for tool in tools}
    assert "monitor_agent_reload" not in tool_names


@pytest.mark.asyncio
async def test_register_monitor_agent_tools_exposes_reload(monkeypatch):
    async def fake_reload(self, ip):
        return {"status": "success", "ip": ip}

    monkeypatch.setattr(MonitorAgentService, "reload", fake_reload)

    server = FastMCP("Monitor Agent Test")
    register_monitor_agent_tools(server)

    async with Client(server) as client:
        tools = await client.list_tools()
        result = await client.call_tool("monitor_agent_reload", {"ip": "10.0.0.1"})

    tool_names = {tool.name for tool in tools}
    assert {
        "monitor_agent_resolve_asset",
        "monitor_agent_list_configs",
        "monitor_agent_get_config",
        "monitor_agent_put_config",
        "monitor_agent_delete_config",
        "monitor_agent_reload",
    }.issubset(tool_names)
    assert result.data == {"status": "success", "ip": "10.0.0.1"}
