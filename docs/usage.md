# Usage Guide

This guide explains how to use the Prometheus MCP Server with AI assistants like Claude.

## Available Tools

The Prometheus MCP Server provides several tools that AI assistants can use to interact with your Prometheus data:

### Query Tools

#### `execute_query`

Executes an instant PromQL query and returns the current value(s).

**Parameters:**
- `query`: PromQL query string (required)
- `time`: Optional RFC3339 or Unix timestamp (defaults to current time)

**Example Claude prompt:**
```
Use the execute_query tool to check the current value of the 'up' metric.
```

#### `execute_range_query`

Executes a PromQL range query to return values over a time period.

**Parameters:**
- `query`: PromQL query string (required)
- `start`: Start time as RFC3339 or Unix timestamp (required)
- `end`: End time as RFC3339 or Unix timestamp (required)
- `step`: Query resolution step width (e.g., '15s', '1m', '1h') (required)

**Example Claude prompt:**
```
Use the execute_range_query tool to show me the CPU usage over the last hour with 5-minute intervals. Use the query 'rate(node_cpu_seconds_total{mode="user"}[5m])'.
```

### Discovery Tools

#### `list_metrics`

Retrieves a list of all available metric names.

**Example Claude prompt:**
```
Use the list_metrics tool to show me all available metrics in my Prometheus server.
```

#### `get_metric_metadata`

Retrieves metadata about a specific metric.

**Parameters:**
- `metric`: The name of the metric (required)

**Example Claude prompt:**
```
Use the get_metric_metadata tool to get information about the 'http_requests_total' metric.
```

#### `get_targets`

Retrieves information about all Prometheus scrape targets.

**Example Claude prompt:**
```
Use the get_targets tool to check the health of all monitoring targets.
```

## Example Workflows

### Basic Monitoring Check

```
Can you check if all my monitored services are up? Also, show me the top 5 CPU-consuming pods if we're monitoring Kubernetes.
```

Claude might use:
1. `execute_query` with `up` to check service health
2. `execute_query` with a more complex PromQL query to find CPU usage

### Performance Analysis

```
Analyze the memory usage pattern of my application over the last 24 hours. Are there any concerning spikes?
```

Claude might use:
1. `execute_range_query` with appropriate time parameters
2. Analyze the data for patterns and anomalies

### Metric Exploration

```
I'm not sure what metrics are available. Can you help me discover metrics related to HTTP requests and then show me their current values?
```

Claude might use:
1. `list_metrics` to get all metrics
2. Filter for HTTP-related metrics
3. `get_metric_metadata` to understand what each metric represents
4. `execute_query` to fetch current values

## Tips for Effective Use

1. **Be specific about time ranges** when asking for historical data
2. **Specify step intervals** appropriate to your time range (e.g., use smaller steps for shorter periods)
3. **Use metric discovery tools** if you're unsure what metrics are available
4. **Start with simple queries** and gradually build more complex ones
5. **Ask for explanations** if you don't understand the returned data

## PromQL Query Examples

Here are some useful PromQL queries you can use with the tools:

### Basic Queries

- Check if targets are up: `up`
- HTTP request rate: `rate(http_requests_total[5m])`
- CPU usage: `sum(rate(node_cpu_seconds_total{mode!="idle"}[5m])) by (instance)`
- Memory usage: `node_memory_MemTotal_bytes - node_memory_MemFree_bytes - node_memory_Buffers_bytes - node_memory_Cached_bytes`

### Kubernetes-specific Queries

- Pod CPU usage: `sum(rate(container_cpu_usage_seconds_total{container!="POD",container!=""}[5m])) by (pod)`
- Pod memory usage: `sum(container_memory_working_set_bytes{container!="POD",container!=""}) by (pod)`
- Pod restart count: `kube_pod_container_status_restarts_total`

## Limitations

- The MCP server queries your live Prometheus instance, so it only has access to metrics retained in your Prometheus server's storage
- Complex PromQL queries might take longer to execute, especially over large time ranges
- Authentication is passed through from your environment variables, so ensure you're using credentials with appropriate access rights