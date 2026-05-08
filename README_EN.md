# Monitor MCP Server

![python](https://img.shields.io/badge/python-3.12%2B-blue) ![license](https://img.shields.io/badge/license-MIT-green)

English | **[中文](README.md)**

A Monitor MCP Server based on the [MCP (Model Context Protocol)](https://modelcontextprotocol.io), providing query and analysis capabilities for **Prometheus**, **Thanos**, **Mimir**, and **VictoriaMetrics** metrics.

> Declare the backend with `BACKEND_TYPE` and the server picks the right API path prefix automatically (Mimir uses `/prometheus/api/v1`). For most deployments only `PROMETHEUS_URL` is required; only VictoriaMetrics needs an additional `RULER_URL` pointing at vmalert.

---

## Features

| Tool | Description |
|------|-------------|
| `execute_query` | Execute a PromQL instant query (custom timeout supported) |
| `execute_range_query` | Execute a PromQL range query with start/end/step (custom timeout supported) |
| `list_metrics` | List available metric names (paginated, default 50 per page) |
| `get_metric_metadata` | Get type, help text, and other metadata for a metric |
| `get_metric_labels` | Get label structure for a metric (samples 10 series by default, max 100) |
| `get_label_values` | Get all values for a given label name |
| `get_alerts` | Get currently firing alerts (routes via `RULER_URL` if configured) |
| `get_rules` | Get all alerting & recording rules (routes via `RULER_URL` if configured) |
| `get_targets` | Get scrape target health status |
| `health_check` | Server health check including backend connectivity |

---

## Quick Start

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|:--------:|---------|
| `PROMETHEUS_URL` | Query endpoint (Prometheus / Thanos Query / Mimir Gateway / VM vmselect) | ✅ | — |
| `BACKEND_TYPE` | Backend type: `prometheus` / `thanos` / `mimir` / `victoriametrics` | | `prometheus` |
| `RULER_URL` | Standalone alert/rule endpoint; required only for VictoriaMetrics (point at vmalert), leave empty for other backends | | — |
| `PROMETHEUS_USERNAME` | Basic Auth username | | — |
| `PROMETHEUS_PASSWORD` | Basic Auth password | | — |
| `PROMETHEUS_TOKEN` | Bearer token (takes precedence over Basic Auth) | | — |
| `ORG_ID` | Multi-tenant Org ID (Thanos / Mimir, etc.) | | — |
| `PROMETHEUS_MCP_SERVER_TRANSPORT` | Transport: `stdio` / `sse` / `streamable-http` | | `stdio` |
| `PROMETHEUS_MCP_BIND_HOST` | Bind address for SSE / streamable-http | | `127.0.0.1` |
| `PROMETHEUS_MCP_BIND_PORT` | Bind port for SSE / streamable-http | | `8000` |
| `LOG_LEVEL` | Log level: `DEBUG` / `INFO` / `WARNING` / `ERROR` | | `INFO` |

### Backend Adaptation Cheat Sheet

| Backend | `BACKEND_TYPE` | `PROMETHEUS_URL` | `RULER_URL` | Notes |
|---|---|---|---|---|
| Prometheus (native) | `prometheus` (default) | Prometheus address | **leave empty** | Single binary, all APIs on one URL |
| Thanos | `thanos` | **Thanos Query** address | **leave empty** | Thanos Query (v0.13+) aggregates alerts/rules from all Ruler replicas |
| Grafana Mimir | `mimir` | Mimir Gateway address | **leave empty** | Gateway routes paths; `/prometheus/api/v1` prefix is added automatically; setting `ORG_ID` is recommended |
| VictoriaMetrics | `victoriametrics` | vmselect address | **point at vmalert** | vmselect does not expose alerts/rules; vmalert must be queried separately |

> **Common pitfall**: in a multi-replica Thanos Ruler setup, pointing `RULER_URL` at a single Ruler instance means `get_alerts` / `get_rules` only see the shard evaluated by that replica. **The correct approach is to leave `RULER_URL` empty** so requests go through Thanos Query and return the aggregated full picture.

> **Mimir microservices mode**: if your deployment bypasses the Gateway and talks to query-frontend directly, query-frontend will not forward alerts/rules to the Ruler. In that case point `RULER_URL` at the Mimir Ruler. The recommended approach is still to expose a unified entry through the Gateway.

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

All configuration is provided via the `.env` file or environment variables; see the table above.

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

### Build the Docker image

```bash
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
      # TCP-only check; the streamable-http endpoint lives at /mcp, the root path may not respond
      test: ["CMD", "python", "-c", "import socket,sys; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',8000)); s.close()"]
      interval: 30s
      timeout: 10s
      retries: 3
```
</details>

<details>
<summary><b>Kubernetes</b></summary>

The project ships with a basic K8s deployment (Deployment, Service, Secret); other resources (Namespace, ConfigMap, Ingress, HPA) are provided as inline examples in `k8s/README.md`.

See **[k8s/README.md](k8s/README.md)** for full details.

Quick preview:

```bash
# Deploy (edit configs under k8s/ first)
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
| `query` | string | ✅ | PromQL expression |
| `time` | string | | Evaluation timestamp (RFC3339 or Unix) |
| `timeout` | int | | Request timeout in seconds (default 30) |

```json
{ "resultType": "vector", "result": [{ "metric": {"__name__": "up"}, "value": [1617898448, "1"] }] }
```

### `execute_range_query`

Execute a PromQL range query.

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `query` | string | ✅ | PromQL expression |
| `start` | string | ✅ | Start time |
| `end` | string | ✅ | End time |
| `step` | string | ✅ | Step (e.g. `15s`, `1m`, `1h`) |
| `timeout` | int | | Request timeout in seconds (default 30) |

### `list_metrics`

List available metric names with pagination.

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `page` | int | | Page number, starting from 1 (default 1) |
| `page_size` | int | | Items per page (default 50, max 500; set to 0 for all) |
| `contains` | string | | Keep only metric names containing the substring (case-insensitive) |
| `prefix` | string | | Keep only metric names starting with the prefix (case-insensitive) |

```json
{ "metrics": ["up", "go_goroutines", "..."], "total": 1500, "page": 1, "page_size": 50, "total_pages": 30 }
```

### `get_metric_metadata`

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `metric` | string | ✅ | Metric name |

Returns `{ "metric": ..., "metadata": {...} }`. On failure returns a structured error object with `status=error`.

### `get_metric_labels`

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `metric` | string | ✅ | Metric name |
| `sample_size` | int | | Number of time series to sample (default 10, max 100, min 1) |

Fetches the first N series via the series API and merges/de-duplicates label values across them. This shows multiple values for enumerated labels while keeping payload size under control. Note: the `limit` parameter requires Prometheus 2.33+; older versions ignore it.

### `get_label_values`

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `label` | string | ✅ | Label name (e.g. `job`, `instance`, `namespace`) |

```json
{ "label": "job", "values": ["prometheus", "node-exporter", "grafana"], "total": 3 }
```

### `get_alerts`

Returns currently active alerts with filtering, pagination, and per-alertname summaries. Routing: uses `RULER_URL` if set, otherwise falls back to `PROMETHEUS_URL`.

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `state` | string | | State filter: `all` (default) / `firing` / `pending` |
| `severity` | string | | Keep only entries matching this severity label (empty = no filter) |
| `label_filters` | string(JSON) | | Equality filter on labels, e.g. `'{"job":"node-agent","namespace":"prod"}'` |
| `include_annotations` | bool | | Whether to keep the `annotations` field in detail output (default true; turning off saves tokens) |
| `summary_only` | bool | | When true, group by `alertname` and return per-rule state/severity distribution |
| `page` | int | | Page number (only effective when `summary_only=false` and `page_size>0`) |
| `page_size` | int | | Items per page (default 0 = return all; max 500) |

```json
{ "alerts": [...], "total": 5, "source_total": 5, "firing": 3, "pending": 2,
  "page": 1, "page_size": 0, "total_pages": 1, "filters": {...} }
```

### `get_rules`

Returns all alerting and recording rules with type/name filtering, pagination, and a lightweight mode. Routing same as `get_alerts`.

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `type_filter` | string | | Rule type: `all` (default) / `alerting` / `recording` |
| `group_contains` | string | | Keep only groups whose `name` contains the substring (case-insensitive) |
| `file_contains` | string | | Keep only groups whose `file` contains the substring |
| `rule_name_contains` | string | | Keep only rules whose `name` contains the substring |
| `include_rules` | bool | | When false, return group-level summary only (no `rules` array); ideal for large catalogs |
| `page` | int | | Page number (applied at group level) |
| `page_size` | int | | Groups per page (default 0 = all; max 500) |

```json
{ "groups": [...], "total_groups": 3, "total_rules": 12,
  "total_alerting": 8, "total_recording": 4, "page": 1, "page_size": 0,
  "total_pages": 1, "filters": {...} }
```

### `get_targets`

Returns scrape targets with filtering and pagination.

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `health` | string | | Health filter: `all` (default) / `up` / `down` / `unknown` |
| `job_contains` | string | | Keep only targets whose `labels.job` contains the substring (case-insensitive) |
| `include_dropped` | bool | | Whether to return the `droppedTargets` array (default true; turn off to reduce payload) |
| `page` | int | | Page number (applied to `activeTargets`) |
| `page_size` | int | | Items per page (default 0 = all; max 500) |

Response includes `activeTargets`, `droppedTargets` (empty + `dropped_omitted: true` when `include_dropped=false`), `health_counts` (distribution by health), and other fields.

### `health_check`

Server self-health check including backend connectivity probing.

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `target` | string | | Probe target: `all` (default; checks both Prometheus and Ruler) / `prometheus` / `ruler` |

Response fields:

- `status`: `healthy` / `degraded` / `unhealthy`
- `timestamp`: UTC ISO8601 timestamp
- `prometheus`: `{ url, dedicated, connectivity, error? }` (returned when `target` includes prometheus)
- `ruler`: `{ url, dedicated, connectivity, error? }` (returned when `target` includes ruler and the URL resolves)

```json
{
  "status": "healthy",
  "timestamp": "2026-05-08T01:23:45+00:00",
  "prometheus": { "url": "http://prometheus:9090", "dedicated": true, "connectivity": "healthy" }
}
```

---

## Authentication

Three authentication methods, in order of precedence:

1. **Bearer Token** — set `PROMETHEUS_TOKEN`
2. **Basic Auth** — set both `PROMETHEUS_USERNAME` and `PROMETHEUS_PASSWORD`
3. **None** — leave all credential variables unset

For multi-tenant setups, set `ORG_ID` to include `X-Scope-OrgID` in requests.

> **Security warning**: in SSE or streamable-http mode the MCP Server listens on an HTTP port. Do not expose this port directly to the public internet. Use a reverse proxy (e.g. Nginx), mTLS, or a Kubernetes NetworkPolicy to restrict access.

#### Minimal Kubernetes NetworkPolicy template

Allow only namespaces labelled `role: mcp-clients` to reach the MCP Server; everything else is denied:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: monitor-mcp-server
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: monitor-mcp-server
  policyTypes: ["Ingress"]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              role: mcp-clients
      ports:
        - protocol: TCP
          port: 8000
```

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
skills/                              # AI assistant query skills
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

## Agent Skill (AI Assistant Query Skill)

This project ships with an **Agent Skill** (`skills/monitor-query/SKILL.md`) that lets AI assistants query metrics intelligently.

### Capabilities

- Automatically extracts query intent from natural language (metric type, resource level, filters)
- Smart selection of recording-rule metrics (pre-aggregated metrics containing `:`)
- **Label disambiguation**: probes real `cluster` / `namespace` / `pod` values to avoid empty results
- Presents results in a clean table format
- **Multiple invocation methods**: supports Cursor CallMcpTool, mcporter CLI, and curl

### Usage

1. Add the `skills/monitor-query/` directory to your AI assistant's Skill configuration (e.g. Cursor Agent Skill)
2. Make sure the Monitor MCP Server is running
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

MIT License - see the [LICENSE](./LICENSE) file for details
