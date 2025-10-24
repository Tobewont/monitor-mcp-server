## MODIFIED Requirements

### Requirement: Metric Labels Discovery
系统 SHALL 提供获取指定指标标签结构的功能，并 SHALL 通过限制查询结果数量来优化性能和降低 token 消耗。

#### Scenario: 获取存在指标的标签信息
- **WHEN** 用户请求获取一个存在的指标（如 "http_requests_total"）的标签信息
- **THEN** 系统应当返回该指标的所有标签名称及其示例值
- **AND** 返回结果应当包含指标名称、标签字典、时间序列数量和标签数量
- **AND** 系统应当限制查询的时间序列数量以优化性能
- **AND** 每个标签只显示一个来自单一时间序列的示例值以最小化 token 消耗

#### Scenario: 获取不存在指标的标签信息
- **WHEN** 用户请求获取一个不存在的指标的标签信息
- **THEN** 系统应当返回空的标签字典
- **AND** 返回结果应当包含适当的提示信息说明该指标不存在或无数据

#### Scenario: 处理 API 错误
- **WHEN** Prometheus API 返回错误或网络连接失败
- **THEN** 系统应当返回结构化的错误响应
- **AND** 错误响应应当包含错误信息、指标名称和错误状态

#### Scenario: 性能优化限制
- **WHEN** 指标有大量时间序列数据
- **THEN** 系统应当限制查询结果数量（默认 1 个系列）
- **AND** 返回结果应当包含 `limited` 字段指示是否应用了限制
- **AND** 系统应当从单一时间序列中提取所有标签键和对应的示例值
- **AND** 每个标签只保留一个示例值，足以了解标签结构用于匹配判断

### Requirement: Metrics List Optimization
系统 SHALL 提供获取所有可用指标名称的功能，并 SHALL 通过过滤指标名称来降低 token 消耗。

#### Scenario: 获取过滤后的指标列表
- **WHEN** 用户请求获取所有可用指标列表
- **THEN** 系统应当返回所有不包含下划线的指标名称
- **AND** 系统应当过滤掉包含下划线的指标（如 "http_requests_total"）
- **AND** 系统应当保留简洁的指标名称（如 "up", "node:cpu:used:percent"）
- **AND** 系统应当记录过滤前后的指标数量和减少百分比

#### Scenario: 空指标列表处理
- **WHEN** Prometheus 中没有符合过滤条件的指标
- **THEN** 系统应当返回空列表
- **AND** 系统应当正确记录过滤统计信息

### Requirement: 标签数据格式化
系统 SHALL 将原始的时间序列数据转换为结构化的标签信息，并 SHALL 优化处理大量数据的性能。

#### Scenario: 标签值去重和排序
- **WHEN** 多个时间序列包含相同标签的不同值
- **THEN** 系统应当收集所有唯一的标签值
- **AND** 标签值应当按字母顺序排序以保证一致性

#### Scenario: 过滤系统标签
- **WHEN** 处理时间序列数据时
- **THEN** 系统应当排除 "__name__" 标签（因为它就是指标名称本身）
- **AND** 只返回用户定义的标签

#### Scenario: 高效数据处理
- **WHEN** 处理限制数量的时间序列数据时
- **THEN** 系统应当使用高效的算法收集标签信息
- **AND** 避免不必要的内存分配和数据复制

### Requirement: 响应数据结构
系统 SHALL 返回标准化的响应格式包含完整的标签信息和性能相关的元数据。

#### Scenario: 成功响应格式
- **WHEN** 成功获取指标标签信息
- **THEN** 响应应当包含以下字段：
  - `metric`: 请求的指标名称
  - `labels`: 标签名称到值列表的映射
  - `series_count`: 找到的时间序列数量
  - `label_count`: 唯一标签的数量
  - `limited`: 布尔值，指示是否应用了查询限制

#### Scenario: 错误响应格式
- **WHEN** 发生错误时
- **THEN** 响应应当包含以下字段：
  - `error`: 错误描述信息
  - `metric`: 请求的指标名称
  - `status`: "error" 状态标识
