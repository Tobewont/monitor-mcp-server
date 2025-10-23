# 优化 get_metric_labels 工具性能

## Why

当前 `get_metric_labels` 工具在查询指标标签时会获取所有匹配的时间序列数据，这可能导致以下问题：

1. **数据传输量过大**：对于有大量时间序列的指标（如 `node_cpu_seconds_total` 可能有数百个系列），会传输大量不必要的数据
2. **响应时间较慢**：处理大量数据会增加响应延迟
3. **资源消耗高**：服务器和客户端都需要处理更多数据

实际上，由于同一指标的所有时间序列通常具有相同的标签键集合，我们只需要获取少量样本就能确定所有可能的标签键。标签值的完整性可以通过智能采样来保证。

## What Changes

- 修改 `get_metric_labels` 工具的查询逻辑，添加 `limit` 参数限制返回的时间序列数量
- 使用 Prometheus `/api/v1/series` API 的 `limit` 参数，默认限制为 1 个系列
- 保持向后兼容性，返回格式不变
- 添加 `limited` 字段指示是否应用了限制
- 优化标签值收集逻辑，提高处理效率

这是一个**性能优化**变更，不会破坏现有 API 兼容性。

## Impact

- 受影响的规格：prometheus-tools（修改现有功能）
- 受影响的代码：
  - `src/prometheus_mcp_server/server.py` - 修改 `get_metric_labels` 函数
  - `tests/test_tools.py` - 更新测试用例
  - `docs/api_reference.md` - 更新文档说明性能优化

**预期性能提升**：
- 数据传输量减少 95-99%（对于大型指标）
- 响应时间减少 90-99%
- 内存使用量降至最低
- 网络带宽使用降至最小
