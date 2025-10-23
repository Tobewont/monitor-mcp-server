# 添加 get_metric_labels 工具

## Why

当前 Prometheus MCP Server 缺少一个重要的发现功能：查询特定指标的所有可用标签及其值。用户需要能够探索指标的标签结构，以便构建更精确的 PromQL 查询。

这个功能对于以下场景非常重要：
- 探索未知指标的标签结构
- 构建动态查询和仪表板
- 理解指标的维度和分组可能性
- 调试和故障排除时快速了解可用的标签过滤器

## What Changes

- 添加新的 MCP 工具 `get_metric_labels`
- 工具接受 `metric` 参数（指标名称）
- 返回该指标的所有标签名称及其可能的值列表
- 使用 Prometheus `/api/v1/series` API 获取时间序列数据
- 提供结构化的标签信息，包括统计数据

## Impact

- 受影响的规格：prometheus-tools（新增功能）
- 受影响的代码：
  - `src/prometheus_mcp_server/server.py` - 添加新工具函数
  - `docs/api_reference.md` - 更新 API 文档
  - `tests/test_tools.py` - 添加单元测试
  - `tests/test_mcp_protocol_compliance.py` - 更新协议合规性测试

这是一个**非破坏性**的变更，只添加新功能，不影响现有 API。
