"""monitor-agent 采集配置管理能力。"""

import asyncio
import posixpath
from datetime import datetime, timezone
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, Optional

import httpx

from monitor_mcp_server.client import build_error_response, make_prometheus_request
from monitor_mcp_server.config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, MonitorAgentConfig, config
from monitor_mcp_server.logging_config import get_logger

logger = get_logger()


def _classify_error(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response is not None and exc.response.status_code in (401, 403):
            return "auth"
        return "upstream"
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError, httpx.HTTPError)):
        return "network"
    return "internal"


def _strip_slashes(value: str) -> str:
    return value.strip().strip("/")


def _safe_filename(filename: str) -> str:
    raw = filename.strip()
    if not raw:
        raise ValueError("filename 不能为空")
    if "\\" in raw:
        raise ValueError("filename 必须使用相对 POSIX 路径，不能包含反斜杠")
    posix_path = PurePosixPath(raw)
    windows_path = PureWindowsPath(raw)
    if posix_path.is_absolute() or windows_path.is_absolute():
        raise ValueError("filename 不能是绝对路径")
    if any(part in ("", ".", "..") for part in posix_path.parts):
        raise ValueError("filename 不能包含空路径、'.' 或 '..'")
    return posix_path.as_posix()


def _object_key(prefix: str, filename: str) -> str:
    clean_prefix = _strip_slashes(prefix)
    clean_filename = _safe_filename(filename)
    return posixpath.join(clean_prefix, clean_filename) if clean_prefix else clean_filename


def _filename_from_asset(asset_id: str, extension: str) -> str:
    asset = _safe_filename(asset_id)
    suffix = extension if extension.startswith(".") else f".{extension}"
    if asset.endswith(suffix):
        return asset
    return f"{asset}{suffix}"


def _backup_key(agent_config: MonitorAgentConfig, key: str) -> str:
    filename = posixpath.basename(key)
    parent = posixpath.basename(posixpath.dirname(key)) or "root"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return _object_key(agent_config.backup_prefix, f"{parent}/{timestamp}-{filename}")


def validate_monitor_agent_yaml(content: str) -> Dict[str, Any]:
    """校验 monitor-agent YAML 配置内容。"""
    if not isinstance(content, str):
        return build_error_response("content 必须是字符串", error_type="client")
    try:
        import yaml

        yaml.safe_load(content)
    except Exception as exc:
        return build_error_response(f"YAML 配置无效: {exc}", error_type="client")
    return {"status": "success"}


async def resolve_asset_id(
    ip: str,
    agent_config: Optional[MonitorAgentConfig] = None,
) -> Dict[str, Any]:
    """根据机器 IP 查询 Prometheus 指标标签中的资产编号。"""
    cfg = agent_config or config.monitor_agent or MonitorAgentConfig()
    if not ip or not ip.strip():
        return build_error_response("ip 不能为空", error_type="client")

    query = cfg.asset_query_template.replace("{ip}", ip.strip())

    try:
        data = await make_prometheus_request("query", params={"query": query})
        results = data.get("result", []) if isinstance(data, dict) else []
        found: Dict[str, Dict[str, Any]] = {}
        for item in results:
            metric = item.get("metric", {}) if isinstance(item, dict) else {}
            if not isinstance(metric, dict):
                continue
            for label in cfg.asset_id_labels:
                value = metric.get(label)
                if value:
                    found[str(value)] = {"asset_label": label, "metric": metric}
                    break

        if not found:
            return build_error_response(
                "未从指标标签中找到资产编号，请检查查询模板或资产标签配置",
                error_type="client",
                query=query,
            )
        if len(found) > 1:
            return build_error_response(
                f"根据 IP 查询到多个资产编号: {', '.join(sorted(found))}",
                error_type="client",
                query=query,
            )

        asset_id, match = next(iter(found.items()))
        return {
            "status": "success",
            "ip": ip.strip(),
            "asset_id": asset_id,
            "asset_label": match["asset_label"],
            "query": query,
            "matches": len(results),
            "metric": match["metric"],
        }
    except Exception as exc:
        logger.error("monitor-agent 资产编号解析失败", ip=ip, error=str(exc))
        return build_error_response(str(exc), error_type=_classify_error(exc))


def build_s3_client(agent_config: MonitorAgentConfig):
    """创建 S3 兼容客户端，延迟导入以避免未启用功能时引入额外开销。"""
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise RuntimeError("monitor-agent 配置管理需要安装 boto3 依赖") from exc

    return boto3.client(
        "s3",
        endpoint_url=agent_config.s3_endpoint_url,
        aws_access_key_id=agent_config.s3_access_key_id,
        aws_secret_access_key=agent_config.s3_secret_access_key,
        region_name=agent_config.s3_region,
        config=Config(s3={"addressing_style": agent_config.s3_addressing_style}),
    )


class MonitorAgentService:
    """封装 monitor-agent 配置对象存储、资产解析和 reload。"""

    def __init__(
        self,
        agent_config: Optional[MonitorAgentConfig] = None,
        *,
        s3_client: Optional[Any] = None,
    ) -> None:
        self.config = agent_config or config.monitor_agent or MonitorAgentConfig()
        self._s3_client = s3_client

    @property
    def s3_client(self) -> Any:
        if self._s3_client is None:
            self._s3_client = build_s3_client(self.config)
        return self._s3_client

    async def _resolve_filename(
        self,
        *,
        ip: Optional[str] = None,
        asset_id: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        if filename:
            safe_name = _safe_filename(filename)
            return {
                "status": "success",
                "filename": safe_name,
                "key": _object_key(self.config.config_prefix, safe_name),
            }
        if asset_id:
            safe_name = _filename_from_asset(asset_id, self.config.config_extension)
            return {
                "status": "success",
                "asset_id": asset_id,
                "filename": safe_name,
                "key": _object_key(self.config.config_prefix, safe_name),
            }
        if ip:
            resolved = await resolve_asset_id(ip, self.config)
            if resolved.get("status") == "error":
                return resolved
            safe_name = _filename_from_asset(resolved["asset_id"], self.config.config_extension)
            resolved.update({
                "filename": safe_name,
                "key": _object_key(self.config.config_prefix, safe_name),
            })
            return resolved
        return build_error_response("必须提供 filename、asset_id 或 ip", error_type="client")

    async def _object_exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(
                self.s3_client.head_object,
                Bucket=self.config.s3_bucket,
                Key=key,
            )
            return True
        except Exception:
            return False

    async def _backup_existing(self, key: str) -> Dict[str, Any]:
        backup_key = _backup_key(self.config, key)
        try:
            await asyncio.to_thread(
                self.s3_client.copy_object,
                Bucket=self.config.s3_bucket,
                CopySource={"Bucket": self.config.s3_bucket, "Key": key},
                Key=backup_key,
            )
            return {"status": "success", "backup_key": backup_key}
        except Exception as exc:
            return build_error_response(f"备份原配置失败: {exc}", error_type="upstream")

    async def list_configs(
        self,
        *,
        prefix: Optional[str] = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Dict[str, Any]:
        list_prefix = _object_key(self.config.config_prefix, prefix) if prefix else _strip_slashes(self.config.config_prefix)
        try:
            objects = []
            token = None
            while True:
                kwargs = {"Bucket": self.config.s3_bucket, "Prefix": list_prefix}
                if token:
                    kwargs["ContinuationToken"] = token
                response = await asyncio.to_thread(self.s3_client.list_objects_v2, **kwargs)
                objects.extend(response.get("Contents", []))
                if not response.get("IsTruncated"):
                    break
                token = response.get("NextContinuationToken")
                if not token:
                    break

            page_size = min(page_size, MAX_PAGE_SIZE) if page_size > 0 else 0
            total = len(objects)
            if page_size <= 0:
                items = objects
                actual_page = 1
                total_pages = 1
            else:
                total_pages = max(1, (total + page_size - 1) // page_size)
                actual_page = max(1, min(page, total_pages))
                start = (actual_page - 1) * page_size
                items = objects[start:start + page_size]
            return {
                "status": "success",
                "configs": items,
                "total": total,
                "page": actual_page,
                "page_size": len(items) if page_size <= 0 else page_size,
                "total_pages": total_pages,
            }
        except Exception as exc:
            return build_error_response(str(exc), error_type="upstream")

    async def get_config(
        self,
        *,
        ip: Optional[str] = None,
        asset_id: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        target = await self._resolve_filename(ip=ip, asset_id=asset_id, filename=filename)
        if target.get("status") == "error":
            return target
        try:
            response = await asyncio.to_thread(
                self.s3_client.get_object,
                Bucket=self.config.s3_bucket,
                Key=target["key"],
            )
            content = response["Body"].read().decode("utf-8")
            return {"status": "success", **target, "content": content}
        except Exception as exc:
            return build_error_response(str(exc), error_type="upstream", key=target["key"])

    async def put_config(
        self,
        *,
        content: str,
        ip: Optional[str] = None,
        asset_id: Optional[str] = None,
        filename: Optional[str] = None,
        reload: bool = False,
    ) -> Dict[str, Any]:
        if reload and not ip:
            return build_error_response("reload=true 时必须提供 ip", error_type="client")
        validation = validate_monitor_agent_yaml(content)
        if validation.get("status") == "error":
            return validation
        target = await self._resolve_filename(ip=ip, asset_id=asset_id, filename=filename)
        if target.get("status") == "error":
            return target

        backed_up = False
        backup_key = None
        if await self._object_exists(target["key"]):
            backup = await self._backup_existing(target["key"])
            if backup.get("status") == "error":
                return backup
            backed_up = True
            backup_key = backup["backup_key"]
        try:
            await asyncio.to_thread(
                self.s3_client.put_object,
                Bucket=self.config.s3_bucket,
                Key=target["key"],
                Body=content,
                ContentType="application/x-yaml",
            )
        except Exception as exc:
            return build_error_response(str(exc), error_type="upstream", key=target["key"])

        response = {
            "status": "success",
            **target,
            "backed_up": backed_up,
            "backup_key": backup_key,
        }
        if reload:
            response["reload"] = await self.reload(ip)
        return response

    async def delete_config(
        self,
        *,
        ip: Optional[str] = None,
        asset_id: Optional[str] = None,
        filename: Optional[str] = None,
        reload: bool = False,
    ) -> Dict[str, Any]:
        if reload and not ip:
            return build_error_response("reload=true 时必须提供 ip", error_type="client")
        target = await self._resolve_filename(ip=ip, asset_id=asset_id, filename=filename)
        if target.get("status") == "error":
            return target
        if not await self._object_exists(target["key"]):
            return build_error_response("配置文件不存在", error_type="client", key=target["key"])

        backup = await self._backup_existing(target["key"])
        if backup.get("status") == "error":
            return backup
        try:
            await asyncio.to_thread(
                self.s3_client.delete_object,
                Bucket=self.config.s3_bucket,
                Key=target["key"],
            )
        except Exception as exc:
            return build_error_response(str(exc), error_type="upstream", key=target["key"])

        response = {
            "status": "success",
            **target,
            "backed_up": True,
            "backup_key": backup["backup_key"],
        }
        if reload:
            response["reload"] = await self.reload(ip)
        return response

    async def reload(self, ip: str) -> Dict[str, Any]:
        if not ip or not ip.strip():
            return build_error_response("ip 不能为空", error_type="client")
        url = self.config.reload_url_template.replace("{ip}", ip.strip())

        try:
            async with httpx.AsyncClient(timeout=self.config.reload_timeout) as client:
                response = await client.post(url)
                response.raise_for_status()
            return {
                "status": "success",
                "ip": ip.strip(),
                "url": url,
                "status_code": response.status_code,
            }
        except Exception as exc:
            return build_error_response(str(exc), error_type=_classify_error(exc), url=url)


def register_monitor_agent_tools(mcp: Any) -> None:
    """向 FastMCP 实例注册 monitor-agent 工具。"""

    @mcp.tool(description="根据机器 IP 从指标标签解析 monitor-agent 资产编号")
    async def monitor_agent_resolve_asset(ip: str) -> Dict[str, Any]:
        return await resolve_asset_id(ip)

    @mcp.tool(description="列出 S3 上的 monitor-agent 配置文件")
    async def monitor_agent_list_configs(
        prefix: Optional[str] = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Dict[str, Any]:
        return await MonitorAgentService().list_configs(
            prefix=prefix,
            page=page,
            page_size=page_size,
        )

    @mcp.tool(description="读取 S3 上的 monitor-agent YAML 配置")
    async def monitor_agent_get_config(
        ip: Optional[str] = None,
        asset_id: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await MonitorAgentService().get_config(
            ip=ip,
            asset_id=asset_id,
            filename=filename,
        )

    @mcp.tool(description="创建或更新 S3 上的 monitor-agent YAML 配置，更新前自动备份")
    async def monitor_agent_put_config(
        content: str,
        ip: Optional[str] = None,
        asset_id: Optional[str] = None,
        filename: Optional[str] = None,
        reload: bool = False,
    ) -> Dict[str, Any]:
        return await MonitorAgentService().put_config(
            content=content,
            ip=ip,
            asset_id=asset_id,
            filename=filename,
            reload=reload,
        )

    @mcp.tool(description="删除 S3 上的 monitor-agent YAML 配置，删除前自动备份")
    async def monitor_agent_delete_config(
        ip: Optional[str] = None,
        asset_id: Optional[str] = None,
        filename: Optional[str] = None,
        reload: bool = False,
    ) -> Dict[str, Any]:
        return await MonitorAgentService().delete_config(
            ip=ip,
            asset_id=asset_id,
            filename=filename,
            reload=reload,
        )

    @mcp.tool(description="调用 monitor-agent /reload 接口重载配置")
    async def monitor_agent_reload(ip: str) -> Dict[str, Any]:
        return await MonitorAgentService().reload(ip)


__all__ = [
    "MonitorAgentService",
    "build_s3_client",
    "register_monitor_agent_tools",
    "resolve_asset_id",
    "validate_monitor_agent_yaml",
]
