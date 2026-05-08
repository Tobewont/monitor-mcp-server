"""支持 `python -m monitor_mcp_server` 启动方式。

与 `python main.py` 和 entry point `monitor-mcp-server` 等价，
便于已安装为 distribution 但项目根目录不可访问的场景（例如系统服务）。
"""

import sys

from monitor_mcp_server.tools import run_server


def main() -> None:
    try:
        run_server()
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001 - 顶层入口需吞所有异常
        print(f"启动失败: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
