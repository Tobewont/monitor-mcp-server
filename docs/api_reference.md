# API Reference

This document provides detailed information about the API endpoints and functions provided by the Prometheus MCP Server.

## MCP Tools

### Query Tools

#### `execute_query`

Executes a PromQL instant query against Prometheus.

**Description**: Retrieves current values for a given PromQL expression.

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | The PromQL query expression |
| `time` | string | No | Evaluation timestamp (RFC3339 or Unix timestamp) |

**Returns**: Object with `resultType` and `result` fields.

```json
{
  "resultType": "vector",
  "result": [
    {
      "metric": { "__name__": "up", "job": "prometheus", "instance": "localhost:9090" },
      "value": [1617898448.214, "1"]
    }
  ]
}
```

#### `execute_range_query`

Executes a PromQL range query with start time, end time, and step interval.

**Description**: Retrieves values for a given PromQL expression over a time range.

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | The PromQL query expression |
| `start` | string | Yes | Start time (RFC3339 or Unix timestamp) |
| `end` | string | Yes | End time (RFC3339 or Unix timestamp) |
| `step` | string | Yes | Query resolution step (e.g., "15s", "1m", "1h") |

**Returns**: Object with `resultType` and `result` fields.

```json
{
  "resultType": "matrix",
  "result": [
    {
      "metric": { "__name__": "up", "job": "prometheus", "instance": "localhost:9090" },
      "values": [
        [1617898400, "1"],
        [1617898415, "1"],
        [1617898430, "1"]
      ]
    }
  ]
}
```

### Discovery Tools

#### `list_metrics`

List all available metrics in Prometheus.

**Description**: Retrieves a list of all metric names available in the Prometheus server.

**Parameters**: None

**Returns**: Array of metric names.

```json
["up", "go_goroutines", "http_requests_total", ...]
```

#### `get_metric_metadata`

Get metadata for a specific metric.

**Description**: Retrieves metadata information about a specific metric.

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `metric` | string | Yes | The name of the metric |

**Returns**: Dictionary containing metadata for the metric.

```json
{
  "up": [
    {
      "type": "gauge",
      "help": "Up indicates if the scrape was successful",
      "unit": ""
    }
  ]
}
```

#### `get_metric_labels`

Get all labels and their values for a specific metric.

**Description**: Retrieves all labels and their keys for a specific metric by querying the time series data. For maximum performance optimization, this tool limits the query to 1 time series sample, which is sufficient to discover all label keys. This dramatically reduces data transfer while providing complete label structure information.

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `metric` | string | Yes | The name of the metric |

**Returns**: Dictionary containing labels and their values for the metric.

```json
{
  "metric": "http_requests_total",
  "labels": {
    "job": ["api"],
    "method": ["GET"],
    "status": ["200"]
  },
  "series_count": 1,
  "label_count": 3,
  "limited": true
}
```

**Response Fields**:
- `metric`: The requested metric name
- `labels`: Dictionary mapping label names to arrays of sample values (from 1 series)
- `series_count`: Number of time series returned (limited to 1 for maximum performance)
- `label_count`: Number of unique labels found
- `limited`: Boolean indicating if the query was limited (true when series_count >= 1)

**Performance Note**: This tool is optimized to query only 1 time series sample, which dramatically reduces response time and data transfer to the absolute minimum while still discovering all label keys. This provides complete label structure information with minimal overhead.

**Empty response (when metric doesn't exist)**:
```json
{
  "metric": "nonexistent_metric",
  "labels": {},
  "series_count": 0,
  "message": "No time series found for metric 'nonexistent_metric'. The metric may not exist or have no data."
}
```

#### `get_targets`

Get information about all scrape targets.

**Description**: Retrieves the current state of all Prometheus scrape targets.

**Parameters**: None

**Returns**: Object with `activeTargets` and `droppedTargets` arrays.

```json
{
  "activeTargets": [
    {
      "discoveredLabels": {
        "__address__": "localhost:9090",
        "__metrics_path__": "/metrics",
        "__scheme__": "http",
        "job": "prometheus"
      },
      "labels": {
        "instance": "localhost:9090",
        "job": "prometheus"
      },
      "scrapePool": "prometheus",
      "scrapeUrl": "http://localhost:9090/metrics",
      "lastError": "",
      "lastScrape": "2023-04-08T12:00:45.123Z",
      "lastScrapeDuration": 0.015,
      "health": "up"
    }
  ],
  "droppedTargets": []
}
```

## Prometheus API Endpoints

The MCP server interacts with the following Prometheus API endpoints:

### `/api/v1/query`

Used by `execute_query` to perform instant queries.

### `/api/v1/query_range`

Used by `execute_range_query` to perform range queries.

### `/api/v1/label/__name__/values`

Used by `list_metrics` to retrieve all metric names.

### `/api/v1/metadata`

Used by `get_metric_metadata` to retrieve metadata about metrics.

### `/api/v1/series`

Used by `get_metric_labels` to retrieve time series data and extract labels.

### `/api/v1/targets`

Used by `get_targets` to retrieve information about scrape targets.

## Error Handling

All tools return standardized error responses when problems occur:

1. **Connection errors**: When the server cannot connect to Prometheus
2. **Authentication errors**: When credentials are invalid or insufficient
3. **Query errors**: When a PromQL query is invalid or fails to execute
4. **Not found errors**: When requested metrics or data don't exist

Error messages are descriptive and include the specific issue that occurred.

## Result Types

Prometheus returns different result types depending on the query:

### Instant Query Result Types

- **Vector**: A set of time series, each with a single sample (most common for instant queries)
- **Scalar**: A single numeric value
- **String**: A string value

### Range Query Result Types

- **Matrix**: A set of time series, each with multiple samples over time (most common for range queries)

## Time Formats

Time parameters accept either:

1. **RFC3339 timestamps**: `2023-04-08T12:00:00Z`
2. **Unix timestamps**: `1617869245.324`

If not specified, the current time is used for instant queries.