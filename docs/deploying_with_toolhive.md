# Deploying Prometheus MCP Server with Toolhive in Kubernetes

This guide explains how to deploy the Prometheus MCP server in a Kubernetes cluster using the Toolhive operator.

## Overview

The Toolhive operator provides a Kubernetes-native way to manage MCP servers. It automates the deployment, configuration, and lifecycle management of MCP servers in your Kubernetes cluster. This guide focuses specifically on deploying the Prometheus MCP server, which allows AI agents to query Prometheus metrics.

## Prerequisites

Before you begin, make sure you have:

- A Kubernetes cluster
- Helm (v3.10 minimum, v3.14+ recommended)
- kubectl
- A Prometheus instance running in your cluster

For detailed instructions on setting up a Kubernetes cluster and installing the Toolhive operator, refer to the [Toolhive Kubernetes Operator Tutorial](https://codegate-docs-git-website-refactor-stacklok.vercel.app/toolhive/tutorials/toolhive-operator).

## Deploying the Prometheus MCP Server

### Step 1: Install the Toolhive Operator

Follow the instructions in the [Toolhive Kubernetes Operator Tutorial](https://codegate-docs-git-website-refactor-stacklok.vercel.app/toolhive/tutorials/toolhive-operator) to install the Toolhive operator in your Kubernetes cluster.

### Step 2: Create the Prometheus MCP Server Resource

Create a YAML file named `mcpserver_prometheus.yaml` with the following content:

```yaml
apiVersion: toolhive.stacklok.dev/v1alpha1
kind: MCPServer
metadata:
  name: prometheus
  namespace: toolhive-system
spec:
  image: ghcr.io/pab1it0/prometheus-mcp-server:latest
  transport: stdio
  port: 8080
  permissionProfile:
    type: builtin
    name: network
  podTemplateSpec:
    spec:
      containers:
        - name: mcp
          securityContext:
            allowPrivilegeEscalation: false
            runAsNonRoot: false
            runAsUser: 0
            runAsGroup: 0
            capabilities:
              drop:
              - ALL
          resources:
            limits:
              cpu: "500m"
              memory: "512Mi"
            requests:
              cpu: "100m"
              memory: "128Mi"
          env:
            - name: PROMETHEUS_URL
              value: "http://prometheus-server.monitoring.svc.cluster.local:80"  # Default value, can be overridden
      securityContext:
        runAsNonRoot: false
        runAsUser: 0
        runAsGroup: 0
        seccompProfile:
          type: RuntimeDefault
  resources:
    limits:
      cpu: "100m"
      memory: "128Mi"
    requests:
      cpu: "50m"
      memory: "64Mi"
```

> **Important**: Make sure to update the `PROMETHEUS_URL` environment variable to point to your Prometheus server's URL in your Kubernetes cluster.

### Step 3: Apply the MCP Server Resource

Apply the YAML file to your cluster:

```bash
kubectl apply -f mcpserver_prometheus.yaml
```

### Step 4: Verify the Deployment

Check that the MCP server is running:

```bash
kubectl get mcpservers -n toolhive-system
```

You should see output similar to:

```
NAME         STATUS    URL                                                  AGE
prometheus   Running   http://prometheus-mcp-proxy.toolhive-system.svc.cluster.local:8080   30s
```

## Using the Prometheus MCP Server with Copilot

Once the Prometheus MCP server is deployed, you can use it with GitHub Copilot or other AI agents that support the Model Context Protocol.

### Example: Querying Prometheus Metrics

When asking Copilot about Prometheus metrics, you might see responses like:

**Query**: "What is the rate of requests on the Prometheus server?"

**Response**:

```json
{
  "resultType": "vector",
  "result": [
    {
      "metric": {
        "__name__": "up",
        "instance": "localhost:9090",
        "job": "prometheus"
      },
      "value": [
        1749034117.048,
        "1"
      ]
    }
  ]
}
```

This shows that the Prometheus server is up and running (value "1").

## Troubleshooting

If you encounter issues with the Prometheus MCP server:

1. Check the MCP server status:
   ```bash
   kubectl get mcpservers -n toolhive-system
   ```

2. Check the MCP server logs:
   ```bash
   kubectl logs -n toolhive-system deployment/prometheus-mcp
   ```

3. Verify the Prometheus URL is correct in the MCP server configuration.

4. Ensure your Prometheus server is accessible from the MCP server pod.

## Configuration Options

The Prometheus MCP server can be configured with the following environment variables:

- `PROMETHEUS_URL`: The URL of your Prometheus server (required)
- `PORT`: The port on which the MCP server listens (default: 8080)

## Available Metrics and Queries

The Prometheus MCP server provides access to all metrics available in your Prometheus instance. Some common queries include:

- `up`: Check if targets are up
- `rate(http_requests_total[5m])`: Request rate over the last 5 minutes
- `sum by (job) (rate(http_requests_total[5m]))`: Request rate by job

For more information on PromQL (Prometheus Query Language), refer to the [Prometheus documentation](https://prometheus.io/docs/prometheus/latest/querying/basics/).

## Conclusion

By following this guide, you've deployed a Prometheus MCP server in your Kubernetes cluster using the Toolhive operator. This server allows AI agents like GitHub Copilot to query your Prometheus metrics, enabling powerful observability and monitoring capabilities through natural language.
