#!/usr/bin/env python

import os
import json
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
import time
from datetime import datetime, timedelta
from enum import Enum

import dotenv
import requests
from fastmcp import FastMCP
from prometheus_mcp_server.logging_config import get_logger

dotenv.load_dotenv()
mcp = FastMCP("Prometheus MCP")

# Get logger instance
logger = get_logger()

# Health check tool for Docker containers and monitoring
@mcp.tool(description="Health check endpoint for container monitoring and status verification")
async def health_check() -> Dict[str, Any]:
    """Return health status of the MCP server and Prometheus connection.
    
    Returns:
        Health status including service information, configuration, and connectivity
    """
    try:
        health_status = {
            "status": "healthy",
            "service": "prometheus-mcp-server", 
            "version": "1.2.3",
            "timestamp": datetime.utcnow().isoformat(),
            "transport": config.mcp_server_config.mcp_server_transport if config.mcp_server_config else "stdio",
            "configuration": {
                "prometheus_url_configured": bool(config.url),
                "authentication_configured": bool(config.username or config.token),
                "org_id_configured": bool(config.org_id)
            }
        }
        
        # Test Prometheus connectivity if configured
        if config.url:
            try:
                # Quick connectivity test
                make_prometheus_request("query", params={"query": "up", "time": str(int(time.time()))})
                health_status["prometheus_connectivity"] = "healthy"
                health_status["prometheus_url"] = config.url
            except Exception as e:
                health_status["prometheus_connectivity"] = "unhealthy"
                health_status["prometheus_error"] = str(e)
                health_status["status"] = "degraded"
        else:
            health_status["status"] = "unhealthy"
            health_status["error"] = "PROMETHEUS_URL not configured"
        
        logger.info("Health check completed", status=health_status["status"])
        return health_status
        
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "service": "prometheus-mcp-server",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


class TransportType(str, Enum):
    """Supported MCP server transport types."""

    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"

    @classmethod
    def values(cls) -> list[str]:
        """Get all valid transport values."""
        return [transport.value for transport in cls]

@dataclass
class MCPServerConfig:
    """Global Configuration for MCP."""
    mcp_server_transport: TransportType = None
    mcp_bind_host: str = None
    mcp_bind_port: int = None

    def __post_init__(self):
        """Validate mcp configuration."""
        if not self.mcp_server_transport:
            raise ValueError("MCP SERVER TRANSPORT is required")
        if not self.mcp_bind_host:
            raise ValueError(f"MCP BIND HOST is required")
        if not self.mcp_bind_port:
            raise ValueError(f"MCP BIND PORT is required")

@dataclass
class PrometheusConfig:
    url: str
    # Optional credentials
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    # Optional Org ID for multi-tenant setups
    org_id: Optional[str] = None
    # Optional Custom MCP Server Configuration
    mcp_server_config: Optional[MCPServerConfig] = None

config = PrometheusConfig(
    url=os.environ.get("PROMETHEUS_URL", ""),
    username=os.environ.get("PROMETHEUS_USERNAME", ""),
    password=os.environ.get("PROMETHEUS_PASSWORD", ""),
    token=os.environ.get("PROMETHEUS_TOKEN", ""),
    org_id=os.environ.get("ORG_ID", ""),
    mcp_server_config=MCPServerConfig(
        mcp_server_transport=os.environ.get("PROMETHEUS_MCP_SERVER_TRANSPORT", "stdio").lower(),
        mcp_bind_host=os.environ.get("PROMETHEUS_MCP_BIND_HOST", "127.0.0.1"),
        mcp_bind_port=int(os.environ.get("PROMETHEUS_MCP_BIND_PORT", "8080"))
    )
)

def get_prometheus_auth():
    """Get authentication for Prometheus based on provided credentials."""
    if config.token:
        return {"Authorization": f"Bearer {config.token}"}
    elif config.username and config.password:
        return requests.auth.HTTPBasicAuth(config.username, config.password)
    return None

def make_prometheus_request(endpoint, params=None):
    """Make a request to the Prometheus API with proper authentication and headers."""
    if not config.url:
        logger.error("Prometheus configuration missing", error="PROMETHEUS_URL not set")
        raise ValueError("Prometheus configuration is missing. Please set PROMETHEUS_URL environment variable.")

    url = f"{config.url.rstrip('/')}/api/v1/{endpoint}"
    auth = get_prometheus_auth()
    headers = {}

    if isinstance(auth, dict):  # Token auth is passed via headers
        headers.update(auth)
        auth = None  # Clear auth for requests.get if it's already in headers
    
    # Add OrgID header if specified
    if config.org_id:
        headers["X-Scope-OrgID"] = config.org_id

    try:
        logger.debug("Making Prometheus API request", endpoint=endpoint, url=url, params=params)
        
        # Make the request with appropriate headers and auth
        response = requests.get(url, params=params, auth=auth, headers=headers)
        
        response.raise_for_status()
        result = response.json()
        
        if result["status"] != "success":
            error_msg = result.get('error', 'Unknown error')
            logger.error("Prometheus API returned error", endpoint=endpoint, error=error_msg, status=result["status"])
            raise ValueError(f"Prometheus API error: {error_msg}")
        
        data_field = result.get("data", {})
        if isinstance(data_field, dict):
            result_type = data_field.get("resultType")
        else:
            result_type = "list"
        logger.debug("Prometheus API request successful", endpoint=endpoint, result_type=result_type)
        return result["data"]
    
    except requests.exceptions.RequestException as e:
        logger.error("HTTP request to Prometheus failed", endpoint=endpoint, url=url, error=str(e), error_type=type(e).__name__)
        raise
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Prometheus response as JSON", endpoint=endpoint, url=url, error=str(e))
        raise ValueError(f"Invalid JSON response from Prometheus: {str(e)}")
    except Exception as e:
        logger.error("Unexpected error during Prometheus request", endpoint=endpoint, url=url, error=str(e), error_type=type(e).__name__)
        raise

@mcp.tool(description="Execute a PromQL instant query against Prometheus")
async def execute_query(query: str, time: Optional[str] = None) -> Dict[str, Any]:
    """Execute an instant query against Prometheus.
    
    Args:
        query: PromQL query string
        time: Optional RFC3339 or Unix timestamp (default: current time)
        
    Returns:
        Query result with type (vector, matrix, scalar, string) and values
    """
    params = {"query": query}
    if time:
        params["time"] = time
    
    logger.info("Executing instant query", query=query, time=time)
    data = make_prometheus_request("query", params=params)
    
    result = {
        "resultType": data["resultType"],
        "result": data["result"]
    }
    
    logger.info("Instant query completed", 
                query=query, 
                result_type=data["resultType"], 
                result_count=len(data["result"]) if isinstance(data["result"], list) else 1)
    
    return result

@mcp.tool(description="Execute a PromQL range query with start time, end time, and step interval")
async def execute_range_query(query: str, start: str, end: str, step: str) -> Dict[str, Any]:
    """Execute a range query against Prometheus.
    
    Args:
        query: PromQL query string
        start: Start time as RFC3339 or Unix timestamp
        end: End time as RFC3339 or Unix timestamp
        step: Query resolution step width (e.g., '15s', '1m', '1h')
        
    Returns:
        Range query result with type (usually matrix) and values over time
    """
    params = {
        "query": query,
        "start": start,
        "end": end,
        "step": step
    }
    
    logger.info("Executing range query", query=query, start=start, end=end, step=step)
    data = make_prometheus_request("query_range", params=params)
    
    result = {
        "resultType": data["resultType"],
        "result": data["result"]
    }
    
    logger.info("Range query completed", 
                query=query, 
                result_type=data["resultType"], 
                result_count=len(data["result"]) if isinstance(data["result"], list) else 1)
    
    return result

@mcp.tool(description="List all available metrics in Prometheus")
async def list_metrics() -> List[str]:
    """Retrieve a list of all metric names available in Prometheus.
    
    Returns:
        List of metric names as strings, filtered to exclude metrics with underscores
        to reduce token consumption and focus on high-level metrics
    """
    logger.info("Listing available metrics")
    data = make_prometheus_request("label/__name__/values")
    
    # Filter out metrics with underscores to reduce token consumption
    # Keep metrics like 'up', 'node:cpu:used:percent' but exclude 'http_requests_total'
    filtered_metrics = [metric for metric in data if '_' not in metric]
    
    logger.info("Metrics list retrieved and filtered", 
                total_metrics=len(data), 
                filtered_metrics=len(filtered_metrics),
                reduction_percentage=round((1 - len(filtered_metrics)/len(data)) * 100, 1) if data else 0)
    
    return filtered_metrics

@mcp.tool(description="Get metadata for a specific metric")
async def get_metric_metadata(metric: str) -> Dict[str, Any]:
    """Get metadata about a specific metric.
    
    Args:
        metric: The name of the metric to retrieve metadata for
        
    Returns:
        Dictionary containing metadata for the metric
    """
    logger.info("Retrieving metric metadata", metric=metric)
    params = {"metric": metric}
    
    try:
        data = make_prometheus_request("metadata", params=params)
        logger.debug("Raw metadata response", data=data, metric=metric)
        
        # Prometheus metadata API returns data directly, not nested under "metadata" or "data"
        # The response structure is: {"status": "success", "data": {...}}
        # After make_prometheus_request, we get the "data" part directly
        if isinstance(data, dict):
            metadata = data
        else:
            logger.warning("Unexpected metadata response format", data_type=type(data), metric=metric)
            metadata = {"error": "Unexpected response format", "raw_data": data}
        
        logger.info("Metric metadata retrieved", metric=metric, metadata_keys=list(metadata.keys()) if isinstance(metadata, dict) else "non-dict")
        return metadata
        
    except Exception as e:
        logger.error("Failed to retrieve metric metadata", metric=metric, error=str(e), error_type=type(e).__name__)
        return {
            "error": f"Failed to retrieve metadata for metric '{metric}': {str(e)}",
            "metric": metric,
            "status": "error"
        }

@mcp.tool(description="Get all labels and their values for a specific metric")
async def get_metric_labels(metric: str) -> Dict[str, Any]:
    """Get all labels and their values for a specific metric.
    
    Args:
        metric: The name of the metric to retrieve labels for
        
    Returns:
        Dictionary containing all labels and their possible values for the metric
    """
    logger.info("Retrieving metric labels", metric=metric)
    
    try:
        # Use the series API to get time series for this metric with limit for performance
        # Limit to 1 series to minimize token consumption while still getting label structure
        params = {"match[]": metric, "limit": "1"}
        data = make_prometheus_request("series", params=params)
        logger.debug("Raw series response", data=data, metric=metric, limited=True)
        
        if not isinstance(data, list):
            logger.warning("Unexpected series response format", data_type=type(data), metric=metric)
            return {
                "error": "Unexpected response format from series API",
                "metric": metric,
                "raw_data": data
            }
        
        if not data:
            logger.info("No series found for metric", metric=metric)
            return {
                "metric": metric,
                "labels": {},
                "series_count": 0,
                "label_count": 0,
                "limited": False,
                "message": f"No time series found for metric '{metric}'. The metric may not exist or have no data."
            }
        
        # Extract only the label keys (structure) from the first series
        # We only need to know what labels exist, not their values
        labels_result = {}
        if data:
            first_series = data[0]  # Only use the first series
            if isinstance(first_series, dict):
                for label_name, label_value in first_series.items():
                    # Skip the __name__ label as it's the metric name itself
                    if label_name != "__name__":
                        # Only store one example value from the single series
                        labels_result[label_name] = [label_value]
        
        # Always indicate limited=True since we're using limit=1 for performance
        limited = True
        
        result = {
            "metric": metric,
            "labels": labels_result,
            "series_count": len(data),
            "label_count": len(labels_result),
            "limited": limited,
            "note": "Results limited to 1 series with single example value per label to minimize token usage"
        }
        
        logger.info("Metric labels retrieved", 
                   metric=metric, 
                   series_count=len(data),
                   label_count=len(labels_result),
                   label_names=list(labels_result.keys()),
                   limited=limited)
        
        return result
        
    except Exception as e:
        logger.error("Failed to retrieve metric labels", metric=metric, error=str(e), error_type=type(e).__name__)
        return {
            "error": f"Failed to retrieve labels for metric '{metric}': {str(e)}",
            "metric": metric,
            "status": "error"
        }

@mcp.tool(description="Get information about all scrape targets")
async def get_targets() -> Dict[str, List[Dict[str, Any]]]:
    """Get information about all Prometheus scrape targets.
    
    Returns:
        Dictionary with active and dropped targets information
    """
    logger.info("Retrieving scrape targets information")
    data = make_prometheus_request("targets")
    
    result = {
        "activeTargets": data["activeTargets"],
        "droppedTargets": data["droppedTargets"]
    }
    
    logger.info("Scrape targets retrieved", 
                active_targets=len(data["activeTargets"]), 
                dropped_targets=len(data["droppedTargets"]))
    
    return result

if __name__ == "__main__":
    logger.info("Starting Prometheus MCP Server", mode="direct")
    mcp.run()
