# Project Context

## Purpose
Prometheus MCP Server 是一个 Model Context Protocol (MCP) 服务器，为 AI 助手提供与 Prometheus 监控系统的标准化集成接口。该项目使 AI 助手能够执行 PromQL 查询、分析指标数据、探索可用指标，并监控系统健康状态。

主要目标：
- 为 AI 助手提供对 Prometheus 指标的访问能力
- 支持多种传输协议（stdio、HTTP、SSE）
- 提供安全的身份验证机制
- 实现容器化部署和云原生集成

## Tech Stack
- **Python 3.10+** - 主要编程语言
- **FastMCP** - MCP 协议实现框架
- **prometheus-api-client** - Prometheus API 客户端
- **requests** - HTTP 客户端库
- **structlog** - 结构化日志记录
- **python-dotenv** - 环境变量管理
- **Docker** - 容器化部署
- **uv** - Python 包管理器
- **pytest** - 测试框架

## Project Conventions

### Code Style
- 使用 Python 类型注解（Type Hints）
- 遵循 PEP 8 代码风格规范
- 使用 dataclass 进行配置管理
- 采用异步编程模式（async/await）
- 函数和变量使用 snake_case 命名
- 类名使用 PascalCase 命名
- 常量使用 UPPER_CASE 命名
- 详细的 docstring 文档，包含参数和返回值说明

### Architecture Patterns
- **MCP 工具模式**：每个 Prometheus API 功能封装为独立的 MCP 工具
- **配置驱动**：通过环境变量进行配置管理
- **分层架构**：
  - `main.py` - 入口点和环境设置
  - `server.py` - MCP 服务器实现和工具定义
  - `logging_config.py` - 日志配置
- **错误处理**：统一的异常处理和结构化错误日志
- **认证抽象**：支持多种认证方式（Basic Auth、Bearer Token）
- **传输协议抽象**：支持多种 MCP 传输方式

### Testing Strategy
- **单元测试**：使用 pytest 进行核心功能测试
- **集成测试**：Docker 容器集成测试
- **协议合规性测试**：MCP 协议标准合规性验证
- **覆盖率要求**：最低 80% 代码覆盖率
- **测试文件命名**：`test_*.py` 格式
- **Mock 测试**：使用 pytest-mock 进行外部依赖模拟
- **异步测试**：使用 pytest-asyncio 进行异步代码测试

### Git Workflow
- **主分支**：`main` 分支作为稳定版本
- **功能开发**：使用 feature 分支进行新功能开发
- **版本标签**：使用语义化版本控制（SemVer）
- **提交信息**：清晰描述变更内容和影响
- **代码审查**：通过 Pull Request 进行代码审查
- **自动化**：CI/CD 流水线进行自动测试和部署

## Domain Context

### Prometheus 生态系统
- **PromQL**：Prometheus 查询语言，用于指标数据查询和聚合
- **时间序列数据**：指标数据以时间序列形式存储
- **标签系统**：使用标签（labels）进行指标分类和过滤
- **抓取目标**：Prometheus 从配置的目标收集指标数据
- **多租户支持**：通过 X-Scope-OrgID 头部支持多租户环境

### MCP 协议
- **工具系统**：AI 助手通过工具与外部系统交互
- **传输协议**：支持 stdio、HTTP、SSE 三种传输方式
- **结构化通信**：JSON-RPC 2.0 协议进行通信
- **安全性**：通过环境变量管理敏感配置

### 监控和可观测性
- **指标类型**：Counter、Gauge、Histogram、Summary
- **健康检查**：容器和服务健康状态监控
- **日志记录**：结构化日志用于问题诊断和审计

## Important Constraints

### 技术约束
- **Python 版本**：最低支持 Python 3.10
- **内存使用**：优化内存使用，适合容器环境
- **网络访问**：需要访问 Prometheus 服务器
- **认证安全**：敏感信息通过环境变量传递，不在代码中硬编码

### 业务约束
- **向后兼容性**：API 变更需要保持向后兼容
- **性能要求**：查询响应时间应在合理范围内
- **可靠性**：服务应具备容错能力和优雅降级

### 合规性约束
- **开源许可**：MIT 许可证
- **安全标准**：遵循容器安全最佳实践
- **数据隐私**：不存储或缓存敏感的指标数据

## External Dependencies

### 核心依赖
- **Prometheus 服务器**：目标监控系统，提供 HTTP API
- **MCP 客户端**：Claude Desktop、VS Code、Cursor 等支持 MCP 的 AI 助手

### 运行时依赖
- **Docker 运行时**：容器化部署环境
- **网络连接**：与 Prometheus 服务器的 HTTP/HTTPS 连接
- **证书管理**：HTTPS 连接的 SSL/TLS 证书验证

### 开发依赖
- **GitHub Container Registry**：容器镜像存储
- **GitHub Actions**：CI/CD 流水线
- **Codecov**：代码覆盖率报告

### 可选依赖
- **负载均衡器**：多实例部署时的负载分发
- **服务发现**：动态服务发现和配置
- **监控系统**：服务自身的监控和告警
