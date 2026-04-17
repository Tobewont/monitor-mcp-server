# Monitor MCP Server

[English](README_EN.md)

基于 [MCP（Model Context Protocol）](https://modelcontextprotocol.io) 协议的监控查询服务器，为 AI 助手提供 **Prometheus**、**Thanos**、**Mimir**、**VictoriaMetrics** 的指标查询与分析能力。

> 通过 `BACKEND_TYPE` 声明后端类型，服务器会自动选择合适的 API 路径前缀（Mimir 使用 `/prometheus/api/v1`）。绝大多数部署下只需要配 `PROMETHEUS_URL` 一个地址；只有 VictoriaMetrics 需要额外配置 `RULER_URL` 指向 vmalert。

---

## 功能概览

| 工具 | 说明 |
|------|------|
| `execute_query` | 执行 PromQL 即时查询（支持自定义超时） |
| `execute_range_query` | 执行带时间范围和步长的 PromQL 范围查询（支持自定义超时） |
| `list_metrics` | 列出可用指标名称（支持分页，默认每页 50 条） |
| `get_metric_metadata` | 获取指定指标的类型、说明等元数据 |
| `get_metric_labels` | 获取指定指标的标签结构（限制 1 条序列，最小化传输） |
| `get_label_values` | 获取指定标签的所有值 |
| `get_alerts` | 获取当前触发的告警列表（支持 RULER_URL 路由） |
| `get_rules` | 获取所有告警规则和记录规则（支持 RULER_URL 路由） |
| `get_targets` | 获取所有抓取目标的健康状态 |
| `health_check` | 服务自身健康检查（含后端连通性检测） |

---

## 快速开始

### 环境变量

| 变量 | 说明 | 必填 | 默认值 |
|------|------|:----:|--------|
| `PROMETHEUS_URL` | 查询地址（Prometheus / Thanos Query / Mimir Gateway / VM vmselect） | ✅ | — |
| `BACKEND_TYPE` | 后端类型：`prometheus` / `thanos` / `mimir` / `victoriametrics` | | `prometheus` |
| `RULER_URL` | 告警/规则独立地址，仅 VM 必需（指向 vmalert），其它后端留空即可 | | — |
| `PROMETHEUS_USERNAME` | Basic Auth 用户名 | | — |
| `PROMETHEUS_PASSWORD` | Basic Auth 密码 | | — |
| `PROMETHEUS_TOKEN` | Bearer Token（优先级高于 Basic Auth） | | — |
| `ORG_ID` | 多租户 OrgID（Thanos / Mimir 等） | | — |
| `PROMETHEUS_MCP_SERVER_TRANSPORT` | 传输协议：`stdio` / `sse` / `streamable-http` | | `stdio` |
| `PROMETHEUS_MCP_BIND_HOST` | SSE / streamable-http 模式绑定地址 | | `127.0.0.1` |
| `PROMETHEUS_MCP_BIND_PORT` | SSE / streamable-http 模式绑定端口 | | `8000` |
| `LOG_LEVEL` | 日志级别：`DEBUG` / `INFO` / `WARNING` / `ERROR` | | `INFO` |

### 后端适配速查

| 后端 | `BACKEND_TYPE` | `PROMETHEUS_URL` | `RULER_URL` | 其他 |
|---|---|---|---|---|
| Prometheus 原生 | `prometheus`（默认） | Prometheus 地址 | **留空** | 单进程，所有 API 在同一 URL |
| Thanos | `thanos` | **Thanos Query** 地址 | **留空** | Thanos Query (v0.13+) 聚合所有 Ruler 副本的 alerts/rules |
| Grafana Mimir | `mimir` | Mimir Gateway 地址 | **留空** | Gateway 做路径路由；自动加 `/prometheus/api/v1` 前缀；建议配 `ORG_ID` |
| VictoriaMetrics | `victoriametrics` | vmselect 地址 | **指向 vmalert** | vmselect 不提供 alerts/rules，必须单独访问 vmalert |

> **常见坑**：Thanos 多副本 Ruler 场景下，若把 `RULER_URL` 指向某一个 Ruler 实例，`get_alerts` / `get_rules` 只会看到该副本评估的分片。**正确做法是留空 `RULER_URL`**，让请求走 Thanos Query 拿到聚合全量。

> **Mimir 微服务模式**：如果你的部署绕过 Gateway 直连 query-frontend，query-frontend 不会转发 alerts/rules 到 Ruler，此时需要把 `RULER_URL` 指向 Mimir Ruler。推荐做法仍是通过 Gateway 提供统一入口。

### 本地运行

```bash
# 克隆项目
git clone <repo-url> && cd monitor-mcp-server

# 安装依赖（推荐 uv）
pip install uv
uv pip install --system .

# 配置
cp env.example .env
# 编辑 .env，填入 PROMETHEUS_URL

# 启动
python main.py
```

所有配置通过 `.env` 文件或环境变量传入，详见上方环境变量表格。

### Docker 运行

```bash
# stdio 模式（默认）
docker run -i --rm -e PROMETHEUS_URL=http://your-prometheus:9090 monitor-mcp-server

# streamable-http 模式
docker run --rm -p 8000:8000 \
  -e PROMETHEUS_URL=http://your-prometheus:9090 \
  -e PROMETHEUS_MCP_SERVER_TRANSPORT=streamable-http \
  -e PROMETHEUS_MCP_BIND_HOST=0.0.0.0 \
  monitor-mcp-server

# 带认证 + 调试日志
docker run -i --rm \
  -e PROMETHEUS_URL=http://your-prometheus:9090 \
  -e PROMETHEUS_TOKEN=your-token \
  -e LOG_LEVEL=DEBUG \
  monitor-mcp-server
```

### Docker 构建

```bash
docker build -t monitor-mcp-server .
```

---

## MCP 客户端接入

<details>
<summary><b>Claude Desktop / VS Code / Cursor</b></summary>

```json
{
  "mcpServers": {
    "monitor": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-e", "PROMETHEUS_URL", "monitor-mcp-server"],
      "env": {
        "PROMETHEUS_URL": "http://your-prometheus:9090"
      }
    }
  }
}
```

也可以直接使用本地 Python 启动：

```json
{
  "mcpServers": {
    "monitor": {
      "command": "python",
      "args": ["main.py"],
      "cwd": "/path/to/monitor-mcp-server",
      "env": {
        "PROMETHEUS_URL": "http://your-prometheus:9090"
      }
    }
  }
}
```
</details>

<details>
<summary><b>Docker Compose</b></summary>

```yaml
version: '3.8'
services:
  monitor-mcp:
    build: .
    ports:
      - "8000:8000"
    environment:
      - PROMETHEUS_URL=http://prometheus:9090
      - PROMETHEUS_MCP_SERVER_TRANSPORT=streamable-http
      - PROMETHEUS_MCP_BIND_HOST=0.0.0.0
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/')"]
      interval: 30s
      timeout: 10s
      retries: 3
```
</details>

<details>
<summary><b>Kubernetes</b></summary>

项目提供了基础的 K8s 部署方案（Deployment、Service、Secret），其他资源（Namespace、ConfigMap、Ingress、HPA）以内联示例形式在 k8s/README.md 中提供。

详细部署文档请参考：**[k8s/README.md](k8s/README.md)**

快速预览：

```bash
# 部署（先修改 k8s/ 下的配置文件）
kubectl apply -f k8s/

# 验证
kubectl get pods -l app.kubernetes.io/name=monitor-mcp-server
```

</details>

---

## API 参考

### `execute_query`

执行 PromQL 即时查询。

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `query` | string | ✅ | PromQL 表达式 |
| `time` | string | | 评估时间戳（RFC3339 或 Unix） |
| `timeout` | int | | 请求超时秒数（默认 30） |

```json
{ "resultType": "vector", "result": [{ "metric": {"__name__": "up"}, "value": [1617898448, "1"] }] }
```

### `execute_range_query`

执行 PromQL 范围查询。

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `query` | string | ✅ | PromQL 表达式 |
| `start` | string | ✅ | 起始时间 |
| `end` | string | ✅ | 结束时间 |
| `step` | string | ✅ | 步长（如 `15s`、`1m`、`1h`） |
| `timeout` | int | | 请求超时秒数（默认 30） |

### `list_metrics`

列出可用指标名称，支持分页。

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `page` | int | | 页码，从 1 开始（默认 1） |
| `page_size` | int | | 每页条数（默认 50，上限 500，设为 0 返回全部） |

```json
{ "metrics": ["up", "go_goroutines", "..."], "total": 1500, "page": 1, "page_size": 50, "total_pages": 30 }
```

### `get_metric_metadata`

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `metric` | string | ✅ | 指标名称 |

### `get_metric_labels`

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `metric` | string | ✅ | 指标名称 |

返回该指标的标签键及一个示例值（通过 `limit=1` 优化性能）。

### `get_label_values`

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `label` | string | ✅ | 标签名称（如 `job`、`instance`、`namespace`） |

```json
{ "label": "job", "values": ["prometheus", "node-exporter", "grafana"], "total": 3 }
```

### `get_alerts`

无参数。返回当前触发的告警列表。若配置了 `RULER_URL`，请求自动路由到 Ruler 组件。

```json
{ "alerts": [...], "total": 5, "firing": 3, "pending": 2 }
```

### `get_rules`

无参数。返回所有规则组（含告警规则和记录规则）。若配置了 `RULER_URL`，请求自动路由到 Ruler 组件。

```json
{ "groups": [...], "total_groups": 3, "total_rules": 12 }
```

### `get_targets`

无参数。返回 `activeTargets` 和 `droppedTargets` 数组。

### `health_check`

无参数。返回服务状态、版本、Prometheus 连通性等信息。

---

## 认证说明

支持三种认证方式，优先级从高到低：

1. **Bearer Token** — 设置 `PROMETHEUS_TOKEN`
2. **Basic Auth** — 同时设置 `PROMETHEUS_USERNAME` + `PROMETHEUS_PASSWORD`
3. **无认证** — 不设置任何凭据

多租户场景下设置 `ORG_ID`，请求头会自动携带 `X-Scope-OrgID`。

> **安全警告**：在 SSE 或 streamable-http 模式下，MCP Server 会监听 HTTP 端口。请勿将该端口直接暴露到公网，建议通过反向代理（如 Nginx）、mTLS、或 Kubernetes NetworkPolicy 限制访问。

---

## 开发

```bash
# 安装依赖（含开发依赖）
uv pip install --system -e ".[dev]"

# 运行测试
pytest

# 带覆盖率
pytest --cov=src --cov-report=term-missing
```

### 项目结构

```
main.py                              # 启动入口
src/monitor_mcp_server/
  config.py                          # 配置定义（环境变量、常量、数据类）
  client.py                          # HTTP 客户端（请求、重试、认证、配置校验）
  tools.py                           # MCP 工具定义与服务器启动
  logging_config.py                  # 结构化日志配置
tests/                               # 测试用例
skills/                              # AI 助手查询技能
```

### 添加新工具

在 `src/monitor_mcp_server/tools.py` 中：

```python
@mcp.tool(description="工具描述")
async def your_tool(param: str) -> Dict[str, Any]:
    """工具说明。"""
    data = await make_prometheus_request("endpoint", params={"key": param})
    return data
```

同时在 `tests/test_tools.py` 中添加对应测试。

---

## Agent Skill（AI 助手查询技能）

项目附带了一个 **Agent Skill**（`skills/monitor-query/SKILL.md`），可让 AI 助手自动完成指标查询。

### 功能

- 自动从用户自然语言中提取查询意图（指标类型、资源级别、筛选条件）
- 智能匹配记录规则指标（含 `:` 的预聚合指标）
- **消歧验证**：自动探测 cluster / namespace / pod 的真实标签值，避免因名称不一致导致空结果
- 以表格形式呈现查询结果
- **多种调用方式**：支持 Cursor CallMcpTool、mcporter CLI、curl 等多种 MCP 调用途径

### 使用方法

1. 将 `skills/monitor-query/` 目录添加到 AI 助手的 Skill 配置中（如 Cursor Agent Skill）
2. 确保 Monitor MCP Server 已启动
3. 向 AI 助手提问，例如：
   - "查询 vm-host-prod 集群中 drama 相关 pod 的 CPU 使用率"
   - "节点 192.168.167.60 的内存使用情况"
   - "最近 6 小时 operation-devops-prod 命名空间内存使用趋势"

---

## 常用 PromQL 示例

```promql
# 服务存活检查
up

# HTTP 请求速率
rate(http_requests_total[5m])

# 节点 CPU 使用率
sum(rate(node_cpu_seconds_total{mode!="idle"}[5m])) by (instance)

# Pod 内存使用（K8s）
sum(container_memory_working_set_bytes{container!="POD",container!=""}) by (pod)

# Pod 重启次数
kube_pod_container_status_restarts_total
```

---

## 许可证

MIT
