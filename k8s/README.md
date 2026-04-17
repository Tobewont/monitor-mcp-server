# Kubernetes 部署指南

本目录包含将 Monitor MCP Server 部署到 Kubernetes 集群的基础配置。

---

## 前置条件

- Kubernetes 集群 >= 1.24
- `kubectl` 已配置且可访问集群
- 集群内可访问的 Prometheus 或 Thanos Query 服务
- 已构建并推送 Docker 镜像到可拉取的仓库

## 镜像准备

```bash
docker build -t your-registry/monitor-mcp-server:1.0.0 .

docker push your-registry/monitor-mcp-server:1.0.0
```

---

## 包含的资源文件

| 文件 | 说明 |
|------|------|
| `deployment.yaml` | Deployment，含探针、资源限制、安全上下文 |
| `service.yaml` | ClusterIP Service |
| `secret.yaml` | Secret 模板（需替换占位符后使用） |

## 快速部署

```bash
# 1. 修改 deployment.yaml 中的镜像地址和 PROMETHEUS_URL
# 2. 修改 secret.yaml 中的凭据（或通过命令行创建 Secret）

# 通过命令行创建 Secret（推荐，避免凭据入 Git）
kubectl create secret generic monitor-mcp-secret \
  --from-literal=token=your-bearer-token \
  --from-literal=org-id=tenant-1

# 部署
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# 验证
kubectl get pods -l app.kubernetes.io/name=monitor-mcp-server
kubectl logs -l app.kubernetes.io/name=monitor-mcp-server
```

---

## 可选扩展

以下资源可按需手动创建，未作为独立文件提供：

### Namespace

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: monitor-mcp
```

### ConfigMap（外置环境变量）

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: monitor-mcp-config
data:
  PROMETHEUS_URL: "http://thanos-query.monitoring:9090"
  PROMETHEUS_MCP_SERVER_TRANSPORT: "streamable-http"
  PROMETHEUS_MCP_BIND_HOST: "0.0.0.0"
  PROMETHEUS_MCP_BIND_PORT: "8000"
```

### Ingress

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: monitor-mcp-server
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  ingressClassName: nginx
  rules:
  - host: monitor-mcp.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: monitor-mcp-server
            port:
              number: 8000
```

### HorizontalPodAutoscaler

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: monitor-mcp-server
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: monitor-mcp-server
  minReplicas: 1
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

---

## 验证部署

```bash
kubectl get pods -l app.kubernetes.io/name=monitor-mcp-server
kubectl logs deployment/monitor-mcp-server

# 端口转发测试
kubectl port-forward svc/monitor-mcp-server 8000:8000
```

---

## 安全注意事项

- **勿将 secret.yaml 中填入真实凭据后提交到 Git**，推荐使用 `kubectl create secret` 或 SealedSecrets / External Secrets 等方案
- Deployment 已配置 `securityContext`（runAsNonRoot、禁止特权提升）
- HTTP 端口仅在集群内部暴露（ClusterIP），如需外部访问请通过 Ingress 或 NetworkPolicy 控制

---

## 常见场景

### 连接集群内 Prometheus

```yaml
PROMETHEUS_URL: "http://prometheus-server.monitoring.svc.cluster.local:9090"
```

### 连接 Thanos Query

```yaml
PROMETHEUS_URL: "http://thanos-query.monitoring.svc.cluster.local:9090"
```

### 连接需要认证的 Thanos（多租户）

```bash
kubectl create secret generic monitor-mcp-secret \
  --from-literal=token=your-bearer-token \
  --from-literal=org-id=tenant-1
```

---

## 故障排查

| 问题 | 排查方式 |
|------|----------|
| Pod 持续 CrashLoopBackOff | `kubectl logs` 查看启动错误，通常是 `PROMETHEUS_URL` 未配置 |
| 健康检查失败（TCP 探针） | 确认 MCP Server 进程在 8000 端口正常监听；若业务层需验证 Prometheus 连通性，可使用 `health_check` 工具 |
| 连接超时 | 检查 NetworkPolicy 或 Service 之间的网络连通性 |
| 认证失败 (401/403) | 确认 Token/密码正确，多租户场景确认 ORG_ID |
