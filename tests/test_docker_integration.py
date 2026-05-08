"""Tests for Docker integration and container functionality."""

import os
import time
import socket
import urllib.error
import urllib.request
import pytest
import subprocess
import json
import tempfile
from pathlib import Path
from typing import Dict, Any
import docker
from unittest.mock import patch


@pytest.fixture(scope="module")
def docker_client():
    """Create a Docker client for testing."""
    try:
        client = docker.from_env()
        # Test Docker connection
        client.ping()
        return client
    except Exception as e:
        pytest.skip(f"Docker not available: {e}")


@pytest.fixture(scope="module") 
def docker_image(docker_client):
    """Build the Docker image for testing."""
    # Build the Docker image
    image_tag = "monitor-mcp-server:test"
    
    # Get the project root directory
    project_root = Path(__file__).parent.parent
    
    try:
        # Build the image
        image, logs = docker_client.images.build(
            path=str(project_root),
            tag=image_tag,
            rm=True,
            forcerm=True
        )
        
        # Print build logs for debugging
        for log in logs:
            if 'stream' in log:
                print(log['stream'], end='')
        
        yield image_tag
        
    except Exception as e:
        pytest.skip(f"Failed to build Docker image: {e}")
    
    finally:
        # Cleanup: remove the test image
        try:
            docker_client.images.remove(image_tag, force=True)
        except:
            pass  # Image might already be removed


class TestDockerBuild:
    """Test Docker image build and basic functionality."""
    
    def test_docker_image_builds_successfully(self, docker_image):
        """Test that Docker image builds without errors."""
        assert docker_image is not None
    
    def test_docker_image_has_no_extra_labels(self, docker_client, docker_image):
        """Test that Docker image has minimal labels (no bloat)."""
        image = docker_client.images.get(docker_image)
        labels = image.attrs['Config']['Labels'] or {}
        
        bloat_labels = [
            'org.opencontainers.image.title',
            'mcp.server.name',
            'mcp.server.transport.http',
        ]
        for label in bloat_labels:
            assert label not in labels, f"不应包含无用 label: {label}"
    
    def test_docker_image_exposes_correct_port(self, docker_client, docker_image):
        """Test that Docker image exposes the correct port."""
        image = docker_client.images.get(docker_image)
        exposed_ports = image.attrs['Config']['ExposedPorts']
        
        assert '8000/tcp' in exposed_ports
    
    def test_docker_image_has_workdir(self, docker_client, docker_image):
        """Test that Docker image has correct working directory."""
        image = docker_client.images.get(docker_image)
        workdir = image.attrs['Config']['WorkingDir']
        
        assert workdir == '/app'


class TestDockerContainerStdio:
    """Test Docker container running in stdio mode."""
    
    def test_container_starts_with_missing_prometheus_url(self, docker_client, docker_image):
        """Test container behavior when PROMETHEUS_URL is not set."""
        container = docker_client.containers.run(
            docker_image,
            environment={},
            detach=True,
            remove=True
        )
        
        try:
            # Wait for container to exit with timeout
            # Container with missing PROMETHEUS_URL should exit quickly with error
            result = container.wait(timeout=10)
            
            # Check that it exited with non-zero status (indicating configuration error)
            assert result['StatusCode'] != 0
            
            # The fact that it exited quickly with non-zero status indicates
            # the missing PROMETHEUS_URL was detected properly
            
        finally:
            try:
                container.stop()
                container.remove()
            except:
                pass  # Container might already be auto-removed
    
    def test_container_starts_with_valid_config(self, docker_client, docker_image):
        """Test container starts successfully with valid configuration."""
        container = docker_client.containers.run(
            docker_image,
            environment={
                'PROMETHEUS_URL': 'http://mock-prometheus:9090',
                'PROMETHEUS_MCP_SERVER_TRANSPORT': 'stdio'
            },
            detach=True,
            remove=True
        )
        
        try:
            # In stdio mode without TTY/stdin, containers exit immediately after startup
            # This is expected behavior - the server starts successfully then exits
            result = container.wait(timeout=10)
            
            # Check that it exited with zero status (successful startup and normal exit)
            assert result['StatusCode'] == 0
            
            # The fact that it exited with code 0 indicates successful configuration
            # and normal termination (no stdin available in detached container)
            
        finally:
            try:
                container.stop()
                container.remove()
            except:
                pass  # Container might already be auto-removed


class TestDockerContainerHTTP:
    """Test Docker container running in HTTP mode."""
    
    def test_container_http_mode_binds_to_port(self, docker_client, docker_image):
        """Test container in HTTP mode binds to the correct port."""
        container = docker_client.containers.run(
            docker_image,
            environment={
                'PROMETHEUS_URL': 'http://mock-prometheus:9090',
                'PROMETHEUS_MCP_SERVER_TRANSPORT': 'streamable-http',
                'PROMETHEUS_MCP_BIND_HOST': '0.0.0.0',
                'PROMETHEUS_MCP_BIND_PORT': '8000'
            },
            ports={'8000/tcp': 8000},
            detach=True,
            remove=True
        )
        
        try:
            # Wait for the container to start
            time.sleep(3)
            
            # Container should be running
            container.reload()
            assert container.status == 'running'
            
            # 验证端口可达即可，不强求 HTTP 200（FastMCP streamable-http 的入口在 /mcp）
            try:
                with socket.create_connection(("127.0.0.1", 8000), timeout=5):
                    pass
            except OSError:
                pytest.fail("HTTP port not accessible")
            try:
                urllib.request.urlopen('http://localhost:8000/mcp', timeout=5)
            except urllib.error.HTTPError:
                pass
            except urllib.error.URLError:
                pass
            
        finally:
            try:
                container.stop()
                container.remove()
            except:
                pass
    
    def test_container_health_check_stdio_mode(self, docker_client, docker_image):
        """Test Docker health check in stdio mode."""
        container = docker_client.containers.run(
            docker_image,
            environment={
                'PROMETHEUS_URL': 'http://mock-prometheus:9090',
                'PROMETHEUS_MCP_SERVER_TRANSPORT': 'stdio'
            },
            detach=True,
            remove=True
        )
        
        try:
            # In stdio mode, container will exit quickly since no stdin is available
            # Test verifies that the container starts up properly (health check design)
            result = container.wait(timeout=10)
            
            # Container should exit with code 0 (successful startup and normal termination)
            assert result['StatusCode'] == 0
            
            # The successful exit indicates the server started properly
            # In stdio mode without stdin, immediate exit is expected behavior
            
        finally:
            try:
                container.stop()
                container.remove()
            except:
                pass  # Container might already be auto-removed


class TestDockerEnvironmentVariables:
    """Test Docker container environment variable handling."""
    
    def test_all_environment_variables_accepted(self, docker_client, docker_image):
        """Test that container accepts all expected environment variables."""
        env_vars = {
            'PROMETHEUS_URL': 'http://test-prometheus:9090',
            'PROMETHEUS_USERNAME': 'testuser',
            'PROMETHEUS_PASSWORD': 'testpass',
            'PROMETHEUS_TOKEN': 'test-token',
            'ORG_ID': 'test-org',
            'PROMETHEUS_MCP_SERVER_TRANSPORT': 'streamable-http',
            'PROMETHEUS_MCP_BIND_HOST': '0.0.0.0',
            'PROMETHEUS_MCP_BIND_PORT': '8000'
        }
        
        container = docker_client.containers.run(
            docker_image,
            environment=env_vars,
            detach=True,
            remove=True
        )
        
        try:
            # Wait for the container to start
            time.sleep(3)
            
            # Container should be running
            container.reload()
            assert container.status == 'running'
            
            # Check logs don't contain environment variable errors
            logs = container.logs().decode('utf-8')
            assert 'environment variable is invalid' not in logs
            assert 'configuration missing' not in logs.lower()
            
        finally:
            try:
                container.stop()
                container.remove()
            except:
                pass
    
    def test_invalid_transport_mode_fails(self, docker_client, docker_image):
        """Test that invalid transport mode causes container to fail."""
        container = docker_client.containers.run(
            docker_image,
            environment={
                'PROMETHEUS_URL': 'http://test-prometheus:9090',
                'PROMETHEUS_MCP_SERVER_TRANSPORT': 'invalid-transport'
            },
            detach=True,
            remove=True
        )
        
        try:
            # Wait for container to exit with timeout
            # Container with invalid transport should exit quickly with error
            result = container.wait(timeout=10)
            
            # Check that it exited with non-zero status (indicating configuration error)
            assert result['StatusCode'] != 0
            
            # The fact that it exited quickly with non-zero status indicates
            # the invalid transport was detected properly
            
        finally:
            try:
                container.stop()
                container.remove()
            except:
                pass  # Container might already be auto-removed
    
    def test_invalid_port_falls_back_to_default(self, docker_client, docker_image):
        """非法端口会被 _safe_parse_port 兜底到默认 8000，容器应正常启动。

        设计选择：端口解析失败时打印警告并使用默认端口，避免因配置笔误导致
        容器立即崩溃；如需严格失败可修改 _safe_parse_port 重新抛错。
        """
        container = docker_client.containers.run(
            docker_image,
            environment={
                'PROMETHEUS_URL': 'http://test-prometheus:9090',
                'PROMETHEUS_MCP_SERVER_TRANSPORT': 'streamable-http',
                'PROMETHEUS_MCP_BIND_HOST': '0.0.0.0',
                'PROMETHEUS_MCP_BIND_PORT': 'invalid-port',
            },
            detach=True,
            remove=True,
        )

        try:
            time.sleep(3)
            container.reload()
            assert container.status == 'running', (
                f"非法端口应回退到默认 8000 后容器仍在运行，实际状态: {container.status}"
            )
            logs = container.logs().decode('utf-8', errors='ignore')
            assert 'invalid-port' in logs or '默认端口' in logs or 'default' in logs.lower(), (
                "应在日志中输出关于非法端口的告警"
            )
        finally:
            try:
                container.stop()
                container.remove()
            except Exception:
                pass


class TestDockerSecurity:
    """Test Docker security features."""
    
    def test_container_has_app_directory(self, docker_client, docker_image):
        """Test that container has /app directory with source files."""
        container = docker_client.containers.run(
            docker_image,
            environment={
                'PROMETHEUS_URL': 'http://test-prometheus:9090',
                'PROMETHEUS_MCP_SERVER_TRANSPORT': 'streamable-http'
            },
            detach=True,
            remove=True
        )
        
        try:
            time.sleep(2)
            
            result = container.exec_run('ls /app/main.py')
            assert result.exit_code == 0
            
        finally:
            try:
                container.stop()
                container.remove()
            except:
                pass