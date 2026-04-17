#!/usr/bin/env python
"""Monitor MCP Server 启动入口。"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from monitor_mcp_server.tools import run_server

if __name__ == "__main__":
    try:
        run_server()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"启动失败: {e}", file=sys.stderr)
        sys.exit(1)
