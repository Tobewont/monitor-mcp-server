"""Tests for monitor-agent configuration management."""

from datetime import datetime, timedelta, timezone

import pytest
import httpx
from botocore.exceptions import ClientError
from fastmcp import Client, FastMCP

from monitor_mcp_server.config import MonitorAgentConfig, PrometheusConfig
from monitor_mcp_server.client import setup_environment
from monitor_mcp_server.monitor_agent import (
    MonitorAgentService,
    build_backup_key,
    build_s3_client,
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


def test_setup_environment_rejects_invalid_backup_timezone():
    cfg = PrometheusConfig(
        url="http://prometheus.example",
        monitor_agent=MonitorAgentConfig(
            enabled=True,
            s3_endpoint_url="https://s3.example.com",
            s3_bucket="bucket",
            s3_access_key_id="access",
            s3_secret_access_key="secret",
            backup_timezone="Asia/Shanghai",
        ),
    )

    assert setup_environment(cfg) is False


def test_setup_environment_rejects_overlapping_backup_prefix():
    cfg = PrometheusConfig(
        url="http://prometheus.example",
        monitor_agent=MonitorAgentConfig(
            enabled=True,
            s3_endpoint_url="https://s3.example.com",
            s3_bucket="bucket",
            s3_access_key_id="access",
            s3_secret_access_key="secret",
            config_prefix="monitor-agent/remote_configs",
            backup_prefix="monitor-agent",
        ),
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


@pytest.mark.asyncio
async def test_resolve_asset_id_rejects_invalid_ip():
    result = await resolve_asset_id('10.0.0.1"|.*', MonitorAgentConfig(enabled=True))

    assert result["status"] == "error"
    assert result["error_type"] == "client"
    assert "ip 参数必须是有效 IP 地址" in result["error"]


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
    def __init__(self, existing=None, fail_copy=False, last_modified=None, head_error=None):
        self.objects = dict(existing or {})
        self.last_modified = dict(last_modified or {})
        self.fail_copy = fail_copy
        self.head_error = head_error
        self.copied = []
        self.puts = []
        self.deletes = []

    def head_object(self, Bucket, Key):
        if self.head_error:
            raise self.head_error
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}

    def copy_object(self, Bucket, CopySource, Key):
        if self.fail_copy:
            raise Exception("copy failed")
        self.copied.append((CopySource["Key"], Key))
        self.objects[Key] = self.objects[CopySource["Key"]]
        self.last_modified[Key] = datetime.now(timezone.utc)

    def put_object(self, Bucket, Key, Body, ContentType, ContentLength=None):
        self.puts.append((Key, Body, ContentType, ContentLength))
        self.objects[Key] = Body
        self.last_modified[Key] = datetime.now(timezone.utc)

    def delete_object(self, Bucket, Key):
        self.deletes.append(Key)
        self.objects.pop(Key, None)
        self.last_modified.pop(Key, None)

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise Exception("not found")
        return {"Body": FakeBody(self.objects[Key])}

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):
        return {
            "Contents": [
                {
                    "Key": key,
                    "Size": len(value),
                    "LastModified": self.last_modified.get(key),
                }
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


def test_build_s3_client_disables_aws_chunked_checksum(monkeypatch):
    calls = []

    class FakeBoto3:
        @staticmethod
        def client(*args, **kwargs):
            calls.append((args, kwargs))
            return object()

    monkeypatch.setitem(__import__("sys").modules, "boto3", FakeBoto3)

    cfg = MonitorAgentConfig(
        enabled=True,
        s3_endpoint_url="https://s3.example.com",
        s3_access_key_id="access",
        s3_secret_access_key="secret",
        s3_addressing_style="path",
    )

    build_s3_client(cfg)

    client_kwargs = calls[0][1]
    botocore_config = client_kwargs["config"]
    assert botocore_config.request_checksum_calculation == "when_required"
    assert botocore_config.response_checksum_validation == "when_required"
    assert botocore_config.s3["payload_signing_enabled"] is False


def test_backup_key_uses_configured_timezone(monkeypatch):
    class FixedDatetime:
        @classmethod
        def now(cls, tz=None):
            from datetime import datetime

            return datetime(2026, 5, 25, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr("monitor_mcp_server.monitor_agent.datetime", FixedDatetime)

    backup_key = build_backup_key(
        MonitorAgentConfig(
            backup_prefix="monitor-agent/backups",
            backup_timezone="+08:00",
        ),
        "monitor-agent/configs/asset-001.yaml",
    )

    assert backup_key == "monitor-agent/backups/20260525T200000+0800-asset-001.yaml"


@pytest.mark.asyncio
async def test_cleanup_expired_backups_uses_last_modified():
    old_key = "monitor-agent/backups/old.yaml"
    fresh_key = "monitor-agent/backups/fresh.yaml"
    config_key = "monitor-agent/configs/current.yaml"
    now = datetime.now(timezone.utc)
    s3 = FakeS3Client(
        {
            old_key: "old",
            fresh_key: "fresh",
            config_key: "current",
        },
        last_modified={
            old_key: now - timedelta(days=181),
            fresh_key: now - timedelta(days=10),
            config_key: now - timedelta(days=300),
        },
    )
    service = MonitorAgentService(
        MonitorAgentConfig(
            enabled=True,
            s3_bucket="bucket",
            backup_prefix="monitor-agent/backups",
            backup_retention_days=180,
        ),
        s3_client=s3,
    )

    result = await service.cleanup_expired_backups()

    assert result["status"] == "success"
    assert result["expired_deleted"] == 1
    assert s3.deletes == [old_key]
    assert fresh_key in s3.objects
    assert config_key in s3.objects


@pytest.mark.asyncio
async def test_put_config_cleans_expired_backups_after_backup():
    old_backup = "monitor-agent/backups/old.yaml"
    now = datetime.now(timezone.utc)
    s3 = FakeS3Client(
        {
            "monitor-agent/configs/asset-001.yaml": "old: true\n",
            old_backup: "old backup",
        },
        last_modified={old_backup: now - timedelta(days=181)},
    )
    service = MonitorAgentService(
        MonitorAgentConfig(
            enabled=True,
            s3_bucket="bucket",
            config_prefix="monitor-agent/configs",
            backup_prefix="monitor-agent/backups",
            backup_retention_days=180,
        ),
        s3_client=s3,
    )

    result = await service.put_config(content="new: true\n", asset_id="asset-001")

    assert result["status"] == "success"
    assert old_backup in s3.deletes
    assert result["backup_retention"]["expired_deleted"] == 1


@pytest.mark.asyncio
async def test_put_config_backs_up_existing_object_before_write():
    s3 = FakeS3Client({"monitor-agent/configs/asset-001.yaml": "old: true\n"})
    service = make_service(s3)

    result = await service.put_config(content="new: true\n", asset_id="asset-001")

    assert result["status"] == "success"
    assert result["backed_up"] is True
    assert s3.copied[0][0] == "monitor-agent/configs/asset-001.yaml"
    assert s3.puts == [
        (
            "monitor-agent/configs/asset-001.yaml",
            b"new: true\n",
            "application/x-yaml",
            len(b"new: true\n"),
        )
    ]


@pytest.mark.asyncio
async def test_put_config_writes_backup_directly_under_backup_prefix():
    s3 = FakeS3Client({"monitor-agent/remote_configs/asset-001.yaml": "old: true\n"})
    service = MonitorAgentService(
        MonitorAgentConfig(
            enabled=True,
            s3_bucket="bucket",
            config_prefix="monitor-agent/remote_configs/",
            backup_prefix="monitor-agent/remote_configs_backups/",
        ),
        s3_client=s3,
    )

    result = await service.put_config(content="new: true\n", asset_id="asset-001")

    assert result["status"] == "success"
    backup_key = s3.copied[0][1]
    assert backup_key.startswith("monitor-agent/remote_configs_backups/")
    assert "/remote_configs/" not in backup_key


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
async def test_put_config_stops_when_head_object_fails():
    s3 = FakeS3Client(head_error=RuntimeError("network down"))
    service = make_service(s3)

    result = await service.put_config(content="new: true\n", asset_id="asset-001")

    assert result["status"] == "error"
    assert result["error_type"] == "upstream"
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
    server = FastMCP("Monitor Agent Disabled Test")

    async with Client(server) as client:
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
