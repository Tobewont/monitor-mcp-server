---
name: monitor-query
description: 通过 Monitor MCP Server 智能查询 Prometheus / Thanos / Mimir / VictoriaMetrics 指标。当用户询问系统指标、资源使用率（CPU/内存/磁盘/网络）、应用性能、Kubernetes Pod/Node/Container 指标、告警状态、健康检查或任何监控数据时使用。触发场景如"查询节点内存使用率"、"pod的CPU"、"容器资源情况"、"集群告警"、"服务健康状态"。
---

# Monitor Query Skill

通过 **Monitor MCP Server** 智能查询 Prometheus 兼容后端的指标数据。

本 Skill 支持多种 MCP 调用方式，适配不同客户端环境。

> **进阶参考**：消歧策略、step 选取、PromQL 模式、常见问题排查等深度内容请阅读 [`references/reference.md`](./references/reference.md)。当用户的查询涉及 cluster/namespace/pod 命名歧义、长时间范围趋势分析或非常规 PromQL 时，先查阅 reference 文档。

---

## 环境变量

使用本 Skill 前，需确认以下环境变量已配置（由用户或部署环境提供）：

| 变量 | 说明 | 示例 |
|------|------|------|
| `MONITOR_MCP_SERVER_URL` | MCP Server 的访问地址（SSE 模式路径为 `/sse`，streamable-http 模式路径为 `/mcp`） | `http://monitor.example.com:8000/sse` |
| `MONITOR_MCP_SERVER_NAME` | IDE 中注册的 MCP Server 名称（方式 A 需要） | `user-monitor-mcp-server` |
| `MONITOR_MCP_AUTH_TOKEN` | MCP Server 的认证 Token（可选，需认证时使用） | `Bearer xxxx` |

> 以下示例中的 `${MONITOR_MCP_SERVER_URL}` 和 `${MONITOR_MCP_SERVER_NAME}` 均引用上述变量，请替换为实际值。

---

## MCP 调用方式

根据你的运行环境，选择以下任意一种方式调用 MCP 工具：

### 方式 A：Cursor / IDE 内置 MCP（CallMcpTool）

在 Cursor 等已配置 MCP Server 的 IDE 中，直接通过内置工具调用：

```
CallMcpTool → server: ${MONITOR_MCP_SERVER_NAME}, toolName: <工具名>
arguments: { ... }
```

示例：

```
CallMcpTool → server: ${MONITOR_MCP_SERVER_NAME}, toolName: execute_query
arguments: { "query": "k8s:pod:cpu:used:percent{namespace=\"operation-devops-prod\"}" }
```

### 方式 B：mcporter CLI

通过 `mcporter` 命令行工具连接远程 MCP Server（SSE / streamable-http 模式）：

```bash
# 列出工具
mcporter list ${MONITOR_MCP_SERVER_URL} --allow-http

# 调用工具
mcporter call '${MONITOR_MCP_SERVER_URL}.<工具名>(<参数>)' --allow-http
```

示例：

```bash
# 列出所有指标
mcporter call '${MONITOR_MCP_SERVER_URL}.list_metrics(page_size: 0)' --allow-http --output json

# 获取指标标签
mcporter call '${MONITOR_MCP_SERVER_URL}.get_metric_labels(metric: "k8s:pod:cpu:used:percent")' --allow-http

# 即时查询
mcporter call '${MONITOR_MCP_SERVER_URL}.execute_query(query: "k8s:pod:cpu:used:percent{namespace=\"operation-devops-prod\"}")' --allow-http

# 范围查询
mcporter call '${MONITOR_MCP_SERVER_URL}.execute_range_query(query: "k8s:pod:cpu:used:percent{pod=~\".*drama.*\"}", start: "2026-04-16T00:00:00Z", end: "2026-04-16T06:00:00Z", step: "5m")' --allow-http
```

如果 MCP Server 需要认证：
```bash
mcporter call '${MONITOR_MCP_SERVER_URL}.health_check()' --allow-http --header "Authorization: ${MONITOR_MCP_AUTH_TOKEN}"
```

### 方式 C：curl 直接调用（streamable-http 模式）

对于 streamable-http 传输模式，也可以通过标准 HTTP 请求调用（注意 URL 使用 streamable-http 的 `/mcp` 路径）：

```bash
# 假设 MONITOR_MCP_BASE=http://localhost:8000（不含路径后缀）

# 健康检查
curl -X POST ${MONITOR_MCP_BASE}/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: ${MONITOR_MCP_AUTH_TOKEN}" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"health_check","arguments":{}}}'

# 即时查询
curl -X POST ${MONITOR_MCP_BASE}/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: ${MONITOR_MCP_AUTH_TOKEN}" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"execute_query","arguments":{"query":"up"}}}'
```

> 若无需认证，省略 `-H "Authorization: ..."` 即可。

**选择建议**：IDE 内优先用方式 A；远程调试或脚本场景用方式 B（mcporter）；无 MCP 客户端时用方式 C（curl）。

---

## 查询流程（5 步）

每次用户提出监控相关查询时，严格遵循以下流程：

### Step 1: 提取关键词 & 意图分析

从用户问题中提取：
- **资源级别**：node / pod / container / host（默认 pod）
- **指标类型**：cpu / memory / disk / network / restart 等
- **筛选维度**：cluster / namespace / pod / instance 名称
- **查询类型**：即时查询 / 范围查询 / Top N / 聚合

示例：
- "vm-host-prod 集群 drama 相关 pod 的 CPU" → 级别=pod, 指标=cpu, cluster=vm-host-prod, pod=drama
- "节点 192.168.167.60 内存使用率" → 级别=node, 指标=memory, instance=192.168.167.60

### Step 2: 查找候选指标

使用 `list_metrics` 获取全部指标，在结果中按关键词筛选。

**方式 A**：
```
CallMcpTool → server: ${MONITOR_MCP_SERVER_NAME}, toolName: list_metrics
arguments: { "page": 1, "page_size": 0 }
```

**方式 B**：
```bash
mcporter call '${MONITOR_MCP_SERVER_URL}.list_metrics(page_size: 0)' --allow-http --output json | \
  grep -o '"[^"]*:[^"]*"' | grep -i '<关键词1>' | grep -i '<关键词2>' | head -50
```

**筛选规则**：
1. **优先选择记录规则**（名称含 `:`），如 `k8s:pod:cpu:used:percent`
2. 按"级别 + 指标类型"语义匹配，选出 **1 个最佳指标**
3. 命名模式参考下方「常用指标速查」

### Step 3: 探测标签结构

对选中的指标查询标签，了解可用的筛选维度：

**方式 A**：
```
CallMcpTool → server: ${MONITOR_MCP_SERVER_NAME}, toolName: get_metric_labels
arguments: { "metric": "<指标名>" }
```

**方式 B**：
```bash
mcporter call '${MONITOR_MCP_SERVER_URL}.get_metric_labels(metric: "<指标名>")' --allow-http
```

返回的标签示例值用于：
- 确认 `cluster`、`namespace`、`pod`、`instance` 等标签是否存在
- 发现标签的**真实命名风格**（为 Step 4 做准备）

### Step 4: 验证标签值（关键！消歧步骤）

**不要假设用户提供的标签值与 Prometheus 中完全一致。** 用轻量查询验证：

- **验证 cluster**：`count by (cluster) (<metric>{cluster=~".*<keyword>.*"})`
- **验证 namespace**：`count by (namespace) (<metric>{cluster="<确认后的值>"})`
- **验证 pod**：`group by (pod) (<metric>{namespace="<确认后的值>", pod=~".*<keyword>.*"})`

**方式 A**：
```
CallMcpTool → server: ${MONITOR_MCP_SERVER_NAME}, toolName: execute_query
arguments: { "query": "count by (namespace) (k8s:pod:cpu:used:percent{cluster=\"vm-host-prod\"})" }
```

**方式 B**：
```bash
mcporter call '${MONITOR_MCP_SERVER_URL}.execute_query(query: "count by (namespace) (k8s:pod:cpu:used:percent{cluster=\"vm-host-prod\"})")' --allow-http
```

如果返回空结果，放宽条件逐级排查，向用户说明差异。

### Step 5: 构建 PromQL 并执行

根据前几步确认的真实标签值，构建精确的 PromQL：

**方式 A**：
```
CallMcpTool → server: ${MONITOR_MCP_SERVER_NAME}, toolName: execute_query
arguments: { "query": "<promql>" }
```

**方式 B**：
```bash
mcporter call '${MONITOR_MCP_SERVER_URL}.execute_query(query: "<promql>")' --allow-http
```

范围查询使用 `execute_range_query`，需额外提供 `start`、`end`、`step`。

---

## 指标选择规则

| 优先级 | 规则 | 说明 |
|:------:|------|------|
| 1 | 只选记录规则 | 名称含 `:` 的指标（如 `k8s:pod:memory:used:percent`）|
| 2 | 级别匹配 | 用户说"pod" → pod 级别；说"容器/container" → container 级别；歧义时默认 pod |
| 3 | 语义优先 | 根据描述而非单纯关键词匹配 |
| 4 | 单一选择 | 每次只选 1 个指标，不要返回候选列表 |

## 常用指标速查

| 分类 | 指标 | 说明 |
|------|------|------|
| **K8s Node** | `k8s:node:memory:used:percent` | 节点内存使用率 |
| | `k8s:node:cpu:used:percent` | 节点 CPU 使用率 |
| **K8s Pod** | `k8s:pod:memory:used:percent` | Pod 内存使用率 |
| | `k8s:pod:cpu:used:percent` | Pod CPU 使用率 |
| **K8s Container** | `k8s:container:memory:used:percent` | 容器内存使用率 |
| | `k8s:container:cpu:used:percent` | 容器 CPU 使用率 |
| **Host** | `node:memory:used:percent` | 主机内存使用率 |
| | `node:cpu:used:percent` | 主机 CPU 使用率 |
| | `node:memory:actuallyused:percent` | 实际内存使用率（去 buffer/cache）|

## 标签过滤语法

```promql
# 精确匹配
{cluster="vm-host-prod", namespace="operation-devops-prod"}

# 正则匹配
{pod=~".*drama.*"}
{instance=~"192.168.167.60.*"}

# 组合
{cluster="vm-host-prod", namespace="operation-devops-prod", pod=~".*drama.*"}

# Top N
topk(10, k8s:pod:cpu:used:percent{namespace="operation-devops-prod"})

# 按维度聚合
avg by (namespace) (k8s:pod:memory:used:percent{cluster="vm-host-prod"})
```

---

## 可用 MCP 工具

| 工具 | 参数 | 说明 |
|------|------|------|
| `health_check` | `target?`（all/prometheus/ruler） | 健康检查（含后端连通性）|
| `list_metrics` | `page?`, `page_size?`, `contains?`, `prefix?` | 列出指标（`page_size=0` 返回全部，支持子串/前缀过滤）|
| `get_metric_metadata` | `metric` | 获取指标元数据（类型、描述）|
| `get_metric_labels` | `metric`, `sample_size?` | 获取标签结构（默认采样 10 条序列合并去重，可调，最大 100）|
| `get_label_values` | `label` | 获取标签所有值 |
| `execute_query` | `query`, `time?`, `timeout?` | 即时查询 |
| `execute_range_query` | `query`, `start`, `end`, `step`, `timeout?` | 范围查询 |
| `get_alerts` | `state?`, `severity?`, `label_filters?`, `include_annotations?`, `summary_only?`, `page?`, `page_size?` | 获取告警，支持过滤/分页/聚合摘要（自动按 `RULER_URL` 路由）|
| `get_rules` | `type_filter?`, `group_contains?`, `file_contains?`, `rule_name_contains?`, `include_rules?`, `page?`, `page_size?` | 获取规则，支持过滤/分页/轻量模式（自动按 `RULER_URL` 路由）|
| `get_targets` | `health?`, `job_contains?`, `include_dropped?`, `page?`, `page_size?` | 获取抓取目标，支持过滤/分页 |

---

## 结果呈现

查询结果应以**表格形式**呈现给用户，按使用率从高到低排序：

```markdown
| Pod | CPU 使用率 (%) |
|-----|---------------|
| drama-mysql-0 | 2.04 |
| drama-redis-0 | 0.55 |
| ... | ... |
```

如果结果为空，向用户说明可能原因并建议调整（标签值不匹配、指标不存在等）。
