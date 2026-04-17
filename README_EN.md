# Monitor MCP Server

[中文文档](README.md)

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server that gives AI assistants the ability to query and analyze metrics from **Prometheus**, **Thanos**, **Mimir**, and **VictoriaMetrics**.

> These systems share a compatible HTTP Query API (`/api/v1/*`), so a single server covers them all. Point `PROMETHEUS_URL` at the query endpoint and optionally set `RULER_URL` for alerts/rules.

---

## Features

| Tool | Description |
|------|-------------|
| `execute_query` | Run a PromQL instant query (custom timeout supported) |
| `execute_range_query` | Run a PromQL range query with start/end/step (custom timeout supported) |
| `list_metrics` | List available metric names (paginated, default 50 per page) |
| `get_metric_metadata` | Get type, help text, and other metadata for a metric |
| `get_metric_labels` | Get label structure for a metric (limited to 1 series to save tokens) |
| `get_label_values` | Get all values for a given label name |
| `get_alerts` | Get currently firing alerts (routes to `RULER_URL` if configured) |
| `get_rules` | Get all alerting & recording rules (routes to `RULER_URL` if configured) |
| `get_targets` | Get scrape target health status |
| `health_check` | Server health check including backend connectivity |

---

## Quick Start

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|:--------:|---------|
| `PROMETHEUS_URL` | Query endpoint (Prometheus / Thanos Query / Mimir / VM) | Yes | — |
| `RULER_URL` | Alert/rule endpoint (Thanos Ruler / Mimir Ruler / vmalert); falls back to `PROMETHEUS_URL` | | — |
| `PROMETHEUS_USERNAME` | Basic Auth username | | — |
| `PROMETHEUS_PASSWORD` | Basic Auth password | | — |
| `PROMETHEUS_TOKEN` | Bearer token (takes precedence over Basic Auth) | | — |
| `ORG_ID` | Multi-tenant Org ID (Thanos / Mimir) | | — |
| `PROMETHEUS_MCP_SERVER_TRANSPORT` | Transport: `stdio` / `sse` / `streamable-http` | | `stdio` |
| `PROMETHEUS_MCP_BIND_HOST` | Bind address for SSE / streamable-http | | `127.0.0.1` |
| `PROMETHEUS_MCP_BIND_PORT` | Bind port for SSE / streamable-http | | `8000` |
| `LOG_LEVEL` | Log level: `DEBUG` / `INFO` / `WARNING` / `ERROR` | | `INFO` |

### Run Locally

```bash
git clone <repo-url> && cd monitor-mcp-server

# Install dependencies (uv recommended)
pip install uv
uv pip install --system .

# Configure
cp env.example .env
# Edit .env — at minimum set PROMETHEUS_URL

# Start
python main.py
```

### Docker

```bash
# stdio mode (default)
docker run -i --rm -e PROMETHEUS_URL=http://your-prometheus:9090 monitor-mcp-server

# streamable-http mode
docker run --rm -p 8000:8000 \
  -e PROMETHEUS_URL=http://your-prometheus:9090 \
  -e PROMETHEUS_MCP_SERVER_TRANSPORT=streamable-http \
  -e PROMETHEUS_MCP_BIND_HOST=0.0.0.0 \
  monitor-mcp-server

# With auth + debug logging
docker run -i --rm \
  -e PROMETHEUS_URL=http://your-prometheus:9090 \
  -e PROMETHEUS_TOKEN=your-token \
  -e LOG_LEVEL=DEBUG \
  monitor-mcp-server
```

```bash
# Build
docker build -t monitor-mcp-server .
```

---

## MCP Client Configuration

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

Or run directly with Python:

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

Basic K8s manifests (Deployment, Service, Secret) are provided in the `k8s/` directory. Additional resources (Namespace, ConfigMap, Ingress, HPA) are available as inline examples in `k8s/README.md`.

See **[k8s/README.md](k8s/README.md)** for details.

```bash
# Deploy (edit k8s/ configs first)
kubectl apply -f k8s/

# Verify
kubectl get pods -l app.kubernetes.io/name=monitor-mcp-server
```
</details>

---

## API Reference

### `execute_query`

Execute a PromQL instant query.

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `query` | string | Yes | PromQL expression |
| `time` | string | | Evaluation timestamp (RFC3339 or Unix) |
| `timeout` | int | | Request timeout in seconds (default 30) |

```json
{ "resultType": "vector", "result": [{ "metric": {"__name__": "up"}, "value": [1617898448, "1"] }] }
```

### `execute_range_query`

Execute a PromQL range query.

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `query` | string | Yes | PromQL expression |
| `start` | string | Yes | Start time |
| `end` | string | Yes | End time |
| `step` | string | Yes | Step (e.g. `15s`, `1m`, `1h`) |
| `timeout` | int | | Request timeout in seconds (default 30) |

### `list_metrics`

List available metric names with pagination.

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `page` | int | | Page number, starting from 1 (default 1) |
| `page_size` | int | | Items per page (default 50, max 500; set to 0 for all) |

```json
{ "metrics": ["up", "go_goroutines", "..."], "total": 1500, "page": 1, "page_size": 50, "total_pages": 30 }
```

### `get_metric_metadata`

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `metric` | string | Yes | Metric name |

### `get_metric_labels`

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `metric` | string | Yes | Metric name |

Returns label keys with one sample value per label (via `limit=1` for minimal payload).

### `get_label_values`

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `label` | string | Yes | Label name (e.g. `job`, `instance`, `namespace`) |

```json
{ "label": "job", "values": ["prometheus", "node-exporter", "grafana"], "total": 3 }
```

### `get_alerts`

No parameters. Returns currently firing alerts. Routed to Ruler if `RULER_URL` is set.

```json
{ "alerts": [...], "total": 5, "firing": 3, "pending": 2 }
```

### `get_rules`

No parameters. Returns all rule groups (alerting + recording). Routed to Ruler if `RULER_URL` is set.

```json
{ "groups": [...], "total_groups": 3, "total_rules": 12 }
```

### `get_targets`

No parameters. Returns `activeTargets` and `droppedTargets`.

### `health_check`

No parameters. Returns service status, version, and Prometheus connectivity info.

---

## Authentication

Three authentication methods, in order of precedence:

1. **Bearer Token** — set `PROMETHEUS_TOKEN`
2. **Basic Auth** — set both `PROMETHEUS_USERNAME` and `PROMETHEUS_PASSWORD`
3. **None** — leave all credential variables unset

For multi-tenant setups, set `ORG_ID` to include `X-Scope-OrgID` in requests.

> **Security Warning**: In SSE or streamable-http mode, the MCP Server listens on an HTTP port. Do not expose this port directly to the public internet. Use a reverse proxy (e.g. Nginx), mTLS, or Kubernetes NetworkPolicy to restrict access.

---

## Development

```bash
# Install with dev dependencies
uv pip install --system -e ".[dev]"

# Run tests
pytest

# With coverage
pytest --cov=src --cov-report=term-missing
```

### Project Structure

```
main.py                              # Entry point
src/monitor_mcp_server/
  config.py                          # Configuration (env vars, constants, dataclasses)
  client.py                          # HTTP client (requests, retry, auth, validation)
  tools.py                           # MCP tool definitions & server startup
  logging_config.py                  # Structured logging
tests/                               # Test suite
skills/                              # Cursor Agent Skills
```

### Adding a New Tool

In `src/monitor_mcp_server/tools.py`:

```python
@mcp.tool(description="Tool description")
async def your_tool(param: str) -> Dict[str, Any]:
    """Tool docstring."""
    data = await make_prometheus_request("endpoint", params={"key": param})
    return data
```

Add corresponding tests in `tests/test_tools.py`.

---

## Agent Skill (Cursor AI Query Skill)

This project ships with a **Cursor Agent Skill** (`skills/monitor-query/SKILL.md`) that enables AI assistants to query metrics intelligently.

### Capabilities

- Automatically extracts query intent from natural language (metric type, resource level, filters)
- Smart selection of recording-rule metrics (pre-aggregated metrics containing `:`)
- **Label disambiguation**: probes real `cluster` / `namespace` / `pod` values to avoid empty results
- Presents results in a clean table format
- **Multiple invocation methods**: supports Cursor CallMcpTool, mcporter CLI, and curl

### Usage

1. Add the `skills/monitor-query/` directory to your Cursor Agent Skill configuration
2. Make sure the Monitor MCP Server service is running (registered as your configured MCP server name)
3. Ask your AI assistant questions like:
   - "Query CPU usage for drama pods in the vm-host-prod cluster"
   - "Show memory usage for node 192.168.167.60"
   - "Memory usage trend in operation-devops-prod over the last 6 hours"

---

## Common PromQL Examples

```promql
# Service liveness
up

# HTTP request rate
rate(http_requests_total[5m])

# Node CPU usage
sum(rate(node_cpu_seconds_total{mode!="idle"}[5m])) by (instance)

# Pod memory usage (K8s)
sum(container_memory_working_set_bytes{container!="POD",container!=""}) by (pod)

# Pod restart count
kube_pod_container_status_restarts_total
```

---

## License

MIT
