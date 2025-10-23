# Installation Guide

This guide will help you install and set up the Prometheus MCP Server.

## Prerequisites

- Python 3.10 or higher
- Access to a Prometheus server
- [uv](https://github.com/astral-sh/uv) package manager (recommended)

## Installation Options

### Option 1: Direct Installation

1. Clone the repository:

```bash
git clone https://github.com/pab1it0/prometheus-mcp-server.git
cd prometheus-mcp-server
```

2. Create and activate a virtual environment:

```bash
# Using uv (recommended)
uv venv
source .venv/bin/activate  # On Unix/macOS
.venv\Scripts\activate     # On Windows

# Using venv (alternative)
python -m venv venv
source venv/bin/activate  # On Unix/macOS
venv\Scripts\activate     # On Windows
```

3. Install the package:

```bash
# Using uv (recommended)
uv pip install -e .

# Using pip (alternative)
pip install -e .
```

### Option 2: Using Docker

1. Clone the repository:

```bash
git clone https://github.com/pab1it0/prometheus-mcp-server.git
cd prometheus-mcp-server
```

2. Build the Docker image:

```bash
docker build -t prometheus-mcp-server .
```

## Configuration

1. Create a `.env` file in the root directory (you can copy from `.env.template`):

```bash
cp .env.template .env
```

2. Edit the `.env` file with your Prometheus server details:

```env
# Required: Prometheus configuration
PROMETHEUS_URL=http://your-prometheus-server:9090

# Optional: Authentication credentials (if needed)
# Choose one of the following authentication methods if required:

# For basic auth
PROMETHEUS_USERNAME=your_username
PROMETHEUS_PASSWORD=your_password

# For bearer token auth
PROMETHEUS_TOKEN=your_token

# Optional: Custom MCP configuration
# PROMETHEUS_MCP_SERVER_TRANSPORT=stdio # Choose between http, stdio, sse. If undefined, stdio is set as the default transport.
# Optional: Only relevant for non-stdio transports
# PROMETHEUS_MCP_BIND_HOST=localhost # if undefined, 127.0.0.1 is set by default.
# PROMETHEUS_MCP_BIND_PORT=8080 # if undefined, 8080 is set by default.
```

## Running the Server

### Option 1: Directly from Python

After installation and configuration, you can run the server with:

```bash
# If installed with -e flag
python -m prometheus_mcp_server.main

# If installed as a package
prometheus-mcp-server
```

### Option 2: Using Docker

```bash
# Using environment variables directly
docker run -it --rm \
  -e PROMETHEUS_URL=http://your-prometheus-server:9090 \
  -e PROMETHEUS_USERNAME=your_username \
  -e PROMETHEUS_PASSWORD=your_password \
  prometheus-mcp-server

# Using .env file
docker run -it --rm \
  --env-file .env \
  prometheus-mcp-server

# Using docker-compose
docker-compose up
```

## Verifying Installation

When the server starts successfully, you should see output similar to:

```
Loaded environment variables from .env file
Prometheus configuration:
  Server URL: http://your-prometheus-server:9090
Authentication: Using basic auth

Starting Prometheus MCP Server...
Running server in standard mode...
```

The server is now ready to receive MCP requests from clients like Claude Desktop.