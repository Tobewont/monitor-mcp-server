# Monitor Query — Reference

## Namespace 消歧策略

Prometheus 中的 `namespace` 标签通常**不是**简单的 `prod` / `test` / `dev`，而是带有业务前缀的完整名称。

### 典型映射

| 用户说的 | 实际 namespace 示例 |
|---------|-------------------|
| prod / 生产 | `operation-devops-prod`, `public-3d-prod`, `gm-prod`, `novel-prod` |
| test / 测试 | `operation-devops-test`, `gz-3d-test`, `gm-test` |
| dev / 开发 | `public-3d-dev`, `gz-3d-dev`, `public-ag53-dev` |

### 消歧流程

当用户说"prod 命名空间"时：

1. **先用 pod 名模糊搜索**（不限 namespace）：
   ```promql
   group by (cluster, namespace, pod) (<metric>{pod=~".*<app>.*"})
   ```
2. 从结果中确认真实 namespace
3. 再用确认后的 namespace 执行精确查询

当用户指定了 cluster 但 namespace 未知时：
```promql
count by (namespace) (<metric>{cluster="<cluster>"})
```

## Cluster 验证

用户提供的 cluster 名未必精确。验证方法：

```promql
# 列出所有 cluster（该指标下）
count by (cluster) (<metric>)

# 模糊匹配
count by (cluster) (<metric>{cluster=~".*<keyword>.*"})
```

## Range Query 用法

适合趋势分析和历史数据：

**方式 A**（CallMcpTool）：
```
CallMcpTool → server: ${MONITOR_MCP_SERVER_NAME}, toolName: execute_range_query
arguments: {
  "query": "<promql>",
  "start": "2026-04-16T00:00:00Z",
  "end":   "2026-04-16T06:00:00Z",
  "step":  "5m"
}
```

**方式 B**（mcporter）：
```bash
mcporter call '${MONITOR_MCP_SERVER_URL}.execute_range_query(query: "<promql>", start: "2026-04-16T00:00:00Z", end: "2026-04-16T06:00:00Z", step: "5m")' --allow-http
```

> 环境变量 `${MONITOR_MCP_SERVER_NAME}` 和 `${MONITOR_MCP_SERVER_URL}` 的含义见 SKILL.md 中的「环境变量」章节。

### step 选取建议

| 时间跨度 | 推荐 step |
|---------|----------|
| ≤ 1h | `15s` ~ `1m` |
| 1h ~ 6h | `1m` ~ `5m` |
| 6h ~ 24h | `5m` ~ `15m` |
| 1d ~ 7d | `15m` ~ `1h` |
| > 7d | `1h` ~ `6h` |

## PromQL 常用模式

```promql
# Top N（CPU 使用率最高的 10 个 pod）
topk(10, k8s:pod:cpu:used:percent{namespace="operation-devops-prod"})

# 按 namespace 聚合平均值
avg by (namespace) (k8s:pod:memory:used:percent{cluster="vm-host-prod"})

# 按 pod 模糊匹配
k8s:pod:memory:used:percent{pod=~".*drama.*"}

# 多条件组合
k8s:pod:cpu:used:percent{cluster="vm-host-prod", namespace="operation-devops-prod", pod=~".*drama.*"}

# 排除特定 pod
k8s:pod:cpu:used:percent{namespace="operation-devops-prod", pod!~".*test.*"}

# 计算变化率（适用于 counter 类型）
rate(http_requests_total{job="apiserver"}[5m])

# 分位数
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))
```

## 指标分类速查

### K8s 节点
| 指标 | 说明 |
|------|------|
| `k8s:node:memory:used:percent` | 节点内存使用百分比 |
| `k8s:node:cpu:used:percent` | 节点 CPU 使用百分比 |
| `k8s:node:memory:allocatable` | 节点可分配内存 |

### K8s Pod
| 指标 | 说明 |
|------|------|
| `k8s:pod:memory:used:percent` | Pod 内存使用百分比 |
| `k8s:pod:cpu:used:percent` | Pod CPU 使用百分比 |
| `k8s:pod:memory:used` | Pod 内存使用量（bytes）|

### K8s Container
| 指标 | 说明 |
|------|------|
| `k8s:container:memory:used:percent` | 容器内存使用百分比 |
| `k8s:container:cpu:used:percent` | 容器 CPU 使用百分比 |

### 主机（非 K8s）
| 指标 | 说明 |
|------|------|
| `node:memory:used:percent` | 主机内存使用百分比 |
| `node:cpu:used:percent` | 主机 CPU 使用百分比 |
| `node:memory:actuallyused:percent` | 实际内存使用百分比（去 buffer/cache）|

## 常见问题排查

| 现象 | 原因 | 解决 |
|------|------|------|
| 查询返回空 | cluster / namespace / pod 标签不匹配 | 执行 Step 4 消歧验证 |
| 找不到指标 | 未使用记录规则名 | 确认使用含 `:` 的记录规则指标 |
| 超时 | 查询范围太大 | 缩小时间范围或增加 step |
| series_count=0 | 指标不存在或无数据 | `list_metrics` 确认指标名 |
