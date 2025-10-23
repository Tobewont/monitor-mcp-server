# Contributing Guide

Thank you for your interest in contributing to the Prometheus MCP Server project! This guide will help you get started with contributing to the project.

## Prerequisites

- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) package manager (recommended)
- Git
- A Prometheus server for testing (you can use a local Docker instance for development)

## Development Environment Setup

1. Fork the repository on GitHub.

2. Clone your fork to your local machine:

```bash
git clone https://github.com/YOUR_USERNAME/prometheus-mcp-server.git
cd prometheus-mcp-server
```

3. Create and activate a virtual environment:

```bash
# Using uv (recommended)
uv venv
source .venv/bin/activate  # On Unix/macOS
.venv\Scripts\activate     # On Windows

# Using venv (alternative)
python -m venv venv
source venv/bin/activate  # On Unix/macOS
venv\Scripts\activate     # On Windows
```

4. Install the package in development mode with testing dependencies:

```bash
# Using uv (recommended)
uv pip install -e ".[dev]"

# Using pip (alternative)
pip install -e ".[dev]"
```

5. Create a local `.env` file for development and testing:

```bash
cp .env.template .env
# Edit the .env file with your Prometheus server details
```

## Running Tests

The project uses pytest for testing. Run the test suite with:

```bash
pytest
```

For more detailed test output with coverage information:

```bash
pytest --cov=src --cov-report=term-missing
```

## Code Style

This project follows PEP 8 Python coding standards. Some key points:

- Use 4 spaces for indentation (no tabs)
- Maximum line length of 100 characters
- Use descriptive variable names
- Write docstrings for all functions, classes, and modules

### Pre-commit Hooks

The project uses pre-commit hooks to ensure code quality. Install them with:

```bash
pip install pre-commit
pre-commit install
```

## Pull Request Process

1. Create a new branch for your feature or bugfix:

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-description
```

2. Make your changes and commit them with clear, descriptive commit messages.

3. Write or update tests to cover your changes.

4. Ensure all tests pass before submitting your pull request.

5. Update documentation to reflect any changes.

6. Push your branch to your fork:

```bash
git push origin feature/your-feature-name
```

7. Open a pull request against the main repository.

## Adding New Features

When adding new features to the Prometheus MCP Server, follow these guidelines:

1. **Start with tests**: Write tests that describe the expected behavior of the feature.

2. **Document thoroughly**: Add docstrings and update relevant documentation files.

3. **Maintain compatibility**: Ensure new features don't break existing functionality.

4. **Error handling**: Implement robust error handling with clear error messages.

### Adding a New Tool

To add a new tool to the MCP server:

1. Add the tool function in `server.py` with the `@mcp.tool` decorator:

```python
@mcp.tool(description="Description of your new tool")
async def your_new_tool(param1: str, param2: int = 0) -> Dict[str, Any]:
    """Detailed docstring for your tool.
    
    Args:
        param1: Description of param1
        param2: Description of param2, with default
        
    Returns:
        Description of the return value
    """
    # Implementation
    # ...
    return result
```

2. Add tests for your new tool in `tests/test_tools.py`.

3. Update the documentation to include your new tool.

## Reporting Issues

When reporting issues, please include:

- A clear, descriptive title
- A detailed description of the issue
- Steps to reproduce the bug, if applicable
- Expected and actual behavior
- Python version and operating system
- Any relevant logs or error messages

## Feature Requests

Feature requests are welcome! When proposing new features:

- Clearly describe the feature and the problem it solves
- Explain how it aligns with the project's goals
- Consider implementation details and potential challenges
- Indicate if you're willing to work on implementing it

## Questions and Discussions

For questions or discussions about the project, feel free to open a discussion on GitHub.

Thank you for contributing to the Prometheus MCP Server project!