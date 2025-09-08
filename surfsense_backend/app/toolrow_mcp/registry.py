"""MCP process registry for managing Toolrow server lifecycle."""

import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import config

logger = logging.getLogger(__name__)


class MCPServerProcess:
    """Manages a single MCP server process."""
    
    def __init__(self, name: str, server_config: Dict[str, Any]):
        self.name = name
        self.config = server_config
        self.process: Optional[subprocess.Popen] = None
        self.last_restart_time = 0.0
        self.restart_count = 0
        self.max_restarts = 5
        self.restart_backoff = [1, 2, 5, 10, 30]  # seconds
        
    async def start(self) -> bool:
        """Start the MCP server process."""
        if self.process and self.process.poll() is None:
            logger.warning(f"MCP server {self.name} is already running")
            return True
            
        try:
            # Prepare environment variables
            env = os.environ.copy()
            for env_var in self.config.get("env", []):
                if env_var in os.environ:
                    env[env_var] = os.environ[env_var]
                else:
                    logger.warning(f"Environment variable {env_var} not found for MCP server {self.name}")
            
            # Start the process
            command = [self.config["command"]] + self.config.get("args", [])
            logger.info(f"Starting MCP server {self.name} with command: {' '.join(command)}")
            
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=0  # Unbuffered for real-time communication
            )
            
            # Give the process a moment to start
            await asyncio.sleep(1)
            
            # Check if process started successfully
            if self.process.poll() is None:
                logger.info(f"MCP server {self.name} started successfully with PID {self.process.pid}")
                return True
            else:
                stderr = self.process.stderr.read() if self.process.stderr else "No error output"
                logger.error(f"MCP server {self.name} failed to start: {stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to start MCP server {self.name}: {e}")
            return False
    
    async def stop(self):
        """Stop the MCP server process."""
        if self.process and self.process.poll() is None:
            logger.info(f"Stopping MCP server {self.name}")
            self.process.terminate()
            
            # Wait for graceful shutdown
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning(f"MCP server {self.name} did not stop gracefully, killing")
                self.process.kill()
                self.process.wait()
                
            logger.info(f"MCP server {self.name} stopped")
        
        self.process = None
    
    def is_running(self) -> bool:
        """Check if the MCP server process is running."""
        return self.process is not None and self.process.poll() is None
    
    async def restart(self) -> bool:
        """Restart the MCP server process with backoff."""
        current_time = asyncio.get_event_loop().time()
        
        # Implement restart backoff
        if self.restart_count < len(self.restart_backoff):
            backoff_time = self.restart_backoff[self.restart_count]
        else:
            backoff_time = self.restart_backoff[-1]
        
        if current_time - self.last_restart_time < backoff_time:
            logger.info(f"Waiting {backoff_time}s before restarting MCP server {self.name}")
            await asyncio.sleep(backoff_time)
        
        await self.stop()
        
        if self.restart_count >= self.max_restarts:
            logger.error(f"MCP server {self.name} has reached maximum restart attempts ({self.max_restarts})")
            return False
        
        self.restart_count += 1
        self.last_restart_time = current_time
        
        return await self.start()


class MCPRegistry:
    """Registry for managing multiple MCP server processes."""
    
    def __init__(self):
        self.servers: Dict[str, MCPServerProcess] = {}
        self.config_path = Path(__file__).parent.parent.parent / "config" / "mcp_servers.json"
        self._health_check_task: Optional[asyncio.Task] = None
        
    async def load_config(self) -> Dict[str, Any]:
        """Load MCP server configuration from JSON file."""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"MCP server config file not found: {self.config_path}")
            return {"mcpServers": {}}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in MCP server config: {e}")
            return {"mcpServers": {}}
    
    async def initialize(self):
        """Initialize all MCP servers from configuration."""
        if not config.TOOLROW_MCP_ENABLED:
            logger.info("Toolrow MCP is disabled, skipping server initialization")
            return
        
        server_config = await self.load_config()
        
        for name, config_data in server_config.get("mcpServers", {}).items():
            logger.info(f"Initializing MCP server: {name}")
            server_process = MCPServerProcess(name, config_data)
            self.servers[name] = server_process
            
            # Start the server
            success = await server_process.start()
            if not success:
                logger.error(f"Failed to start MCP server: {name}")
        
        # Start health check task
        if self.servers:
            self._health_check_task = asyncio.create_task(self._health_check_loop())
    
    async def shutdown(self):
        """Shutdown all MCP servers."""
        logger.info("Shutting down all MCP servers")
        
        # Stop health check task
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Stop all servers
        for server in self.servers.values():
            await server.stop()
        
        self.servers.clear()
        logger.info("All MCP servers shut down")
    
    def get_server(self, name: str) -> Optional[MCPServerProcess]:
        """Get an MCP server by name."""
        return self.servers.get(name)
    
    def get_server_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all MCP servers."""
        status = {}
        for name, server in self.servers.items():
            status[name] = {
                "running": server.is_running(),
                "restart_count": server.restart_count,
                "pid": server.process.pid if server.process else None,
                "config": server.config
            }
        return status
    
    async def restart_server(self, name: str) -> bool:
        """Restart a specific MCP server."""
        server = self.servers.get(name)
        if not server:
            logger.error(f"MCP server {name} not found")
            return False
        
        return await server.restart()
    
    async def _health_check_loop(self):
        """Periodic health check for all MCP servers."""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                for name, server in self.servers.items():
                    if not server.is_running():
                        logger.warning(f"MCP server {name} is not running, attempting restart")
                        await server.restart()
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in MCP health check: {e}")
                await asyncio.sleep(10)  # Brief pause before retry


# Global registry instance
mcp_registry = MCPRegistry()
