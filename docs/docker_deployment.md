# Docker Deployment Guide

This guide covers deploying the Prometheus MCP Server using Docker, including Docker Compose configurations, environment setup, and best practices for production deployments.

## Table of Contents

- [Quick Start](#quick-start)
- [Environment Variables](#environment-variables)
- [Transport Modes](#transport-modes)
- [Docker Compose Examples](#docker-compose-examples)
- [Production Deployment](#production-deployment)
- [Security Considerations](#security-considerations)
- [Monitoring and Health Checks](#monitoring-and-health-checks)
- [Troubleshooting](#troubleshooting)

## Quick Start

### Pull from Docker Hub (Recommended)

```bash
# Pull the official image from Docker MCP registry
docker pull mcp/prometheus-mcp-server:latest
```

### Run with Docker

```bash
# Basic stdio mode (default)
docker run --rm \
  -e PROMETHEUS_URL=http://your-prometheus:9090 \
  mcp/prometheus-mcp-server:latest

# HTTP mode with port mapping
docker run --rm -p 8080:8080 \
  -e PROMETHEUS_URL=http://your-prometheus:9090 \
  -e PROMETHEUS_MCP_SERVER_TRANSPORT=http \
  -e PROMETHEUS_MCP_BIND_HOST=0.0.0.0 \
  mcp/prometheus-mcp-server:latest
```

### Build from Source

```bash
# Clone the repository
git clone https://github.com/pab1it0/prometheus-mcp-server.git
cd prometheus-mcp-server

# Build the Docker image
docker build -t prometheus-mcp-server:local .

# Run the locally built image
docker run --rm \
  -e PROMETHEUS_URL=http://your-prometheus:9090 \
  prometheus-mcp-server:local
```

## Environment Variables

### Required Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `PROMETHEUS_URL` | Base URL of your Prometheus server | `http://prometheus:9090` |

### Authentication (Optional)

| Variable | Description | Example |
|----------|-------------|---------|
| `PROMETHEUS_USERNAME` | Username for basic authentication | `admin` |
| `PROMETHEUS_PASSWORD` | Password for basic authentication | `secretpassword` |
| `PROMETHEUS_TOKEN` | Bearer token (takes precedence over basic auth) | `eyJhbGciOiJIUzI1NiIs...` |

### Multi-tenancy (Optional)

| Variable | Description | Example |
|----------|-------------|---------|
| `ORG_ID` | Organization ID for multi-tenant setups | `tenant-1` |

### MCP Server Configuration

| Variable | Default | Description | Options |
|----------|---------|-------------|---------|
| `PROMETHEUS_MCP_SERVER_TRANSPORT` | `stdio` | Transport protocol | `stdio`, `http`, `sse` |
| `PROMETHEUS_MCP_BIND_HOST` | `127.0.0.1` | Host to bind (HTTP/SSE modes) | `0.0.0.0`, `127.0.0.1` |
| `PROMETHEUS_MCP_BIND_PORT` | `8080` | Port to bind (HTTP/SSE modes) | `1024-65535` |

## Transport Modes

The Prometheus MCP Server supports three transport modes:

### 1. STDIO Mode (Default)

Best for local development and CLI integration:

```bash
docker run --rm \
  -e PROMETHEUS_URL=http://prometheus:9090 \
  -e PROMETHEUS_MCP_SERVER_TRANSPORT=stdio \
  mcp/prometheus-mcp-server:latest
```

### 2. HTTP Mode

Best for web applications and remote access:

```bash
docker run --rm -p 8080:8080 \
  -e PROMETHEUS_URL=http://prometheus:9090 \
  -e PROMETHEUS_MCP_SERVER_TRANSPORT=http \
  -e PROMETHEUS_MCP_BIND_HOST=0.0.0.0 \
  -e PROMETHEUS_MCP_BIND_PORT=8080 \
  mcp/prometheus-mcp-server:latest
```

### 3. Server-Sent Events (SSE) Mode

Best for real-time applications:

```bash
docker run --rm -p 8080:8080 \
  -e PROMETHEUS_URL=http://prometheus:9090 \
  -e PROMETHEUS_MCP_SERVER_TRANSPORT=sse \
  -e PROMETHEUS_MCP_BIND_HOST=0.0.0.0 \
  -e PROMETHEUS_MCP_BIND_PORT=8080 \
  mcp/prometheus-mcp-server:latest
```

## Docker Compose Examples

### Basic Setup with Prometheus

```yaml
version: '3.8'
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    
  prometheus-mcp-server:
    image: mcp/prometheus-mcp-server:latest
    depends_on:
      - prometheus
    environment:
      - PROMETHEUS_URL=http://prometheus:9090
      - PROMETHEUS_MCP_SERVER_TRANSPORT=stdio
    restart: unless-stopped
```

### HTTP Mode with Authentication

```yaml
version: '3.8'
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--web.basic-auth-users=/etc/prometheus/web.yml'
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - ./web.yml:/etc/prometheus/web.yml
    
  prometheus-mcp-server:
    image: mcp/prometheus-mcp-server:latest
    ports:
      - "8080:8080"
    depends_on:
      - prometheus
    environment:
      - PROMETHEUS_URL=http://prometheus:9090
      - PROMETHEUS_USERNAME=admin
      - PROMETHEUS_PASSWORD=secretpassword
      - PROMETHEUS_MCP_SERVER_TRANSPORT=http
      - PROMETHEUS_MCP_BIND_HOST=0.0.0.0
      - PROMETHEUS_MCP_BIND_PORT=8080
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### Multi-tenant Setup

```yaml
version: '3.8'
services:
  prometheus-mcp-tenant1:
    image: mcp/prometheus-mcp-server:latest
    ports:
      - "8081:8080"
    environment:
      - PROMETHEUS_URL=http://prometheus:9090
      - PROMETHEUS_TOKEN=${TENANT1_TOKEN}
      - ORG_ID=tenant-1
      - PROMETHEUS_MCP_SERVER_TRANSPORT=http
      - PROMETHEUS_MCP_BIND_HOST=0.0.0.0
    restart: unless-stopped
    
  prometheus-mcp-tenant2:
    image: mcp/prometheus-mcp-server:latest
    ports:
      - "8082:8080"
    environment:
      - PROMETHEUS_URL=http://prometheus:9090
      - PROMETHEUS_TOKEN=${TENANT2_TOKEN}
      - ORG_ID=tenant-2
      - PROMETHEUS_MCP_SERVER_TRANSPORT=http
      - PROMETHEUS_MCP_BIND_HOST=0.0.0.0
    restart: unless-stopped
```

### Production Setup with Secrets

```yaml
version: '3.8'
services:
  prometheus-mcp-server:
    image: mcp/prometheus-mcp-server:latest
    ports:
      - "8080:8080"
    environment:
      - PROMETHEUS_URL=http://prometheus:9090
      - PROMETHEUS_MCP_SERVER_TRANSPORT=http
      - PROMETHEUS_MCP_BIND_HOST=0.0.0.0
    secrets:
      - prometheus_token
    environment:
      - PROMETHEUS_TOKEN_FILE=/run/secrets/prometheus_token
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: '0.5'
        reservations:
          memory: 128M
          cpus: '0.25'

secrets:
  prometheus_token:
    external: true
```

## Production Deployment

### Resource Requirements

#### Minimum Requirements
- **CPU**: 0.1 cores
- **Memory**: 64MB
- **Storage**: 100MB (for container image)

#### Recommended for Production
- **CPU**: 0.25 cores
- **Memory**: 128MB
- **Storage**: 200MB

### Docker Compose Production Example

```yaml
version: '3.8'
services:
  prometheus-mcp-server:
    image: mcp/prometheus-mcp-server:latest
    ports:
      - "8080:8080"
    environment:
      - PROMETHEUS_URL=https://prometheus.example.com
      - PROMETHEUS_TOKEN_FILE=/run/secrets/prometheus_token
      - PROMETHEUS_MCP_SERVER_TRANSPORT=http
      - PROMETHEUS_MCP_BIND_HOST=0.0.0.0
      - ORG_ID=production
    secrets:
      - prometheus_token
    restart: unless-stopped
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 256M
          cpus: '0.5'
        reservations:
          memory: 128M
          cpus: '0.25'
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
        window: 120s
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "3"

secrets:
  prometheus_token:
    external: true
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus-mcp-server
  labels:
    app: prometheus-mcp-server
spec:
  replicas: 2
  selector:
    matchLabels:
      app: prometheus-mcp-server
  template:
    metadata:
      labels:
        app: prometheus-mcp-server
    spec:
      containers:
      - name: prometheus-mcp-server
        image: mcp/prometheus-mcp-server:latest
        ports:
        - containerPort: 8080
        env:
        - name: PROMETHEUS_URL
          value: "http://prometheus:9090"
        - name: PROMETHEUS_MCP_SERVER_TRANSPORT
          value: "http"
        - name: PROMETHEUS_MCP_BIND_HOST
          value: "0.0.0.0"
        - name: PROMETHEUS_TOKEN
          valueFrom:
            secretKeyRef:
              name: prometheus-token
              key: token
        resources:
          limits:
            memory: "256Mi"
            cpu: "500m"
          requests:
            memory: "128Mi"
            cpu: "250m"
        livenessProbe:
          httpGet:
            path: /
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: prometheus-mcp-server
spec:
  selector:
    app: prometheus-mcp-server
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
  type: ClusterIP
```

## Security Considerations

### 1. Network Security

```yaml
# Use internal networks for container communication
version: '3.8'
networks:
  internal:
    driver: bridge
    internal: true
  external:
    driver: bridge

services:
  prometheus-mcp-server:
    networks:
      - internal
      - external
    # Only expose necessary ports externally
```

### 2. Secrets Management

```bash
# Create Docker secrets for sensitive data
echo "your-prometheus-token" | docker secret create prometheus_token -

# Use secrets in compose
version: '3.8'
services:
  prometheus-mcp-server:
    secrets:
      - prometheus_token
    environment:
      - PROMETHEUS_TOKEN_FILE=/run/secrets/prometheus_token
```

### 3. User Permissions

The container runs as non-root user `app` (UID 1000) by default. No additional configuration needed.

### 4. TLS/HTTPS

```yaml
# Use HTTPS for Prometheus URL
environment:
  - PROMETHEUS_URL=https://prometheus.example.com
  - PROMETHEUS_TOKEN_FILE=/run/secrets/prometheus_token
```

## Monitoring and Health Checks

### Built-in Health Checks

The Docker image includes built-in health checks:

```bash
# Check container health
docker ps
# Look for "healthy" status

# Manual health check
docker exec <container-id> curl -f http://localhost:8080/ || echo "unhealthy"
```

### Custom Health Check

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

### Prometheus Metrics

The server itself doesn't expose Prometheus metrics, but you can monitor it using standard container metrics.

### Logging

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "100m"
    max-file: "3"
```

View logs:
```bash
docker logs prometheus-mcp-server
docker logs -f prometheus-mcp-server  # Follow logs
```

## Troubleshooting

### Common Issues

#### 1. Connection Refused

```bash
# Check if Prometheus URL is accessible from container
docker run --rm -it mcp/prometheus-mcp-server:latest /bin/bash
curl -v http://your-prometheus:9090/api/v1/status/config
```

#### 2. Authentication Failures

```bash
# Test authentication
curl -H "Authorization: Bearer your-token" \
  http://your-prometheus:9090/api/v1/status/config

# Or with basic auth
curl -u username:password \
  http://your-prometheus:9090/api/v1/status/config
```

#### 3. Permission Errors

```bash
# Check container user
docker exec container-id id
# Should show: uid=1000(app) gid=1000(app)
```

#### 4. Port Binding Issues

```bash
# Check port availability
netstat -tulpn | grep 8080

# Use different port
docker run -p 8081:8080 ...
```

### Debug Mode

```bash
# Run with verbose logging
docker run --rm \
  -e PROMETHEUS_URL=http://prometheus:9090 \
  -e PYTHONUNBUFFERED=1 \
  mcp/prometheus-mcp-server:latest
```

### Container Inspection

```bash
# Inspect container configuration
docker inspect prometheus-mcp-server

# Check resource usage
docker stats prometheus-mcp-server

# Access container shell
docker exec -it prometheus-mcp-server /bin/bash
```

### Common Environment Variable Issues

| Issue | Solution |
|-------|----------|
| `PROMETHEUS_URL not set` | Set the `PROMETHEUS_URL` environment variable |
| `Invalid transport` | Use `stdio`, `http`, or `sse` |
| `Invalid port` | Use a valid port number (1024-65535) |
| `Connection refused` | Check network connectivity to Prometheus |
| `Authentication failed` | Verify credentials or token |

### Getting Help

1. Check the [GitHub Issues](https://github.com/pab1it0/prometheus-mcp-server/issues)
2. Review container logs: `docker logs <container-name>`
3. Test Prometheus connectivity manually
4. Verify environment variables are set correctly
5. Check Docker network configuration

For production deployments, consider implementing monitoring and alerting for the MCP server container health and performance.