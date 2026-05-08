"""Monitor MCP Server

基于 MCP（Model Context Protocol）协议的 Monitor MCP Server，
提供查询和分析 Prometheus / Thanos / Mimir / VictoriaMetrics 指标的能力。
"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("monitor_mcp_server")
except PackageNotFoundError:
    # 未安装为 distribution 时（如直接 git checkout 后裸跑），尝试从 pyproject.toml 解析。
    # 这样避免 fallback 字符串与 pyproject 中真实版本号漂移。
    __version__ = "0.0.0+unknown"
    try:
        import sys
        from pathlib import Path

        if sys.version_info >= (3, 11):
            import tomllib  # type: ignore[import-not-found]
        else:
            import tomli as tomllib  # type: ignore[no-redef]

        _pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        if _pyproject.is_file():
            with _pyproject.open("rb") as _fp:
                __version__ = tomllib.load(_fp).get("project", {}).get("version", __version__)
    except Exception:
        pass

del _pkg_version, PackageNotFoundError
