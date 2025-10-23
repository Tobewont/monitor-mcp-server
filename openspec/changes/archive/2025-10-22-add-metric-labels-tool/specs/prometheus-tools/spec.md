## ADDED Requirements

### Requirement: Metric Labels Discovery
系统 SHALL 提供获取指定指标所有标签及其可能值的功能。

#### Scenario: 获取存在指标的标签信息
- **WHEN** 用户请求获取一个存在的指标（如 "http_requests_total"）的标签信息
- **THEN** 系统应当返回该指标的所有标签名称及其可能的值列表
- **AND** 返回结果应当包含指标名称、标签字典、时间序列数量和标签数量

#### Scenario: 获取不存在指标的标签信息
- **WHEN** 用户请求获取一个不存在的指标的标签信息
- **THEN** 系统应当返回空的标签字典
- **AND** 返回结果应当包含适当的提示信息说明该指标不存在或无数据

#### Scenario: 处理 API 错误
- **WHEN** Prometheus API 返回错误或网络连接失败
- **THEN** 系统应当返回结构化的错误响应
- **AND** 错误响应应当包含错误信息、指标名称和错误状态

### Requirement: 标签数据格式化
系统 SHALL 将原始的时间序列数据转换为结构化的标签信息。

#### Scenario: 标签值去重和排序
- **WHEN** 多个时间序列包含相同标签的不同值
- **THEN** 系统应当收集所有唯一的标签值
- **AND** 标签值应当按字母顺序排序以保证一致性

#### Scenario: 过滤系统标签
- **WHEN** 处理时间序列数据时
- **THEN** 系统应当排除 "__name__" 标签（因为它就是指标名称本身）
- **AND** 只返回用户定义的标签

### Requirement: 响应数据结构
系统 SHALL 返回标准化的响应格式包含完整的标签信息。

#### Scenario: 成功响应格式
- **WHEN** 成功获取指标标签信息
- **THEN** 响应应当包含以下字段：
  - `metric`: 请求的指标名称
  - `labels`: 标签名称到值列表的映射
  - `series_count`: 找到的时间序列数量
  - `label_count`: 唯一标签的数量

#### Scenario: 错误响应格式
- **WHEN** 发生错误时
- **THEN** 响应应当包含以下字段：
  - `error`: 错误描述信息
  - `metric`: 请求的指标名称
  - `status`: "error" 状态标识
