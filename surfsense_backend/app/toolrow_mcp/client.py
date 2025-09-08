"""MCP client for communicating with Toolrow MCP server."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Union

from .registry import MCPServerProcess

logger = logging.getLogger(__name__)


class MCPError(Exception):
    """Base exception for MCP client errors."""
    pass


class MCPTimeoutError(MCPError):
    """Raised when MCP operation times out."""
    pass


class MCPServerError(MCPError):
    """Raised when MCP server returns an error."""
    pass


class ToolrowMCPClient:
    """Client for communicating with Toolrow MCP server via JSON-RPC over stdio."""
    
    def __init__(self, server_process: MCPServerProcess):
        self.server_process = server_process
        self.request_id = 0
        self._lock = asyncio.Lock()
    
    def _next_request_id(self) -> int:
        """Get next request ID."""
        self.request_id += 1
        return self.request_id
    
    async def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout_ms: int = 30000) -> Dict[str, Any]:
        """Send a JSON-RPC request to the MCP server."""
        if not self.server_process.is_running():
            raise MCPError("MCP server is not running")
        
        request_id = self._next_request_id()
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method
        }
        
        if params:
            request["params"] = params
        
        request_json = json.dumps(request) + "\n"
        
        async with self._lock:
            try:
                # Send request
                self.server_process.process.stdin.write(request_json)
                self.server_process.process.stdin.flush()
                
                # Wait for response with timeout
                response_line = await asyncio.wait_for(
                    self._read_line(),
                    timeout=timeout_ms / 1000.0
                )
                
                if not response_line:
                    raise MCPError("Empty response from MCP server")
                
                response = json.loads(response_line)
                
                # Check for JSON-RPC error
                if "error" in response:
                    error = response["error"]
                    raise MCPServerError(f"MCP server error: {error.get('message', 'Unknown error')}")
                
                # Verify response ID matches request ID
                if response.get("id") != request_id:
                    raise MCPError(f"Response ID mismatch: expected {request_id}, got {response.get('id')}")
                
                return response.get("result", {})
                
            except asyncio.TimeoutError:
                raise MCPTimeoutError(f"MCP request timeout after {timeout_ms}ms")
            except json.JSONDecodeError as e:
                raise MCPError(f"Invalid JSON response from MCP server: {e}")
            except Exception as e:
                if isinstance(e, (MCPError, MCPTimeoutError, MCPServerError)):
                    raise
                raise MCPError(f"Unexpected error in MCP communication: {e}")
    
    async def _read_line(self) -> str:
        """Read a line from the MCP server stdout."""
        loop = asyncio.get_event_loop()
        
        # Use run_in_executor to make the blocking readline call async
        def read_line():
            if self.server_process.process and self.server_process.process.stdout:
                return self.server_process.process.stdout.readline()
            return None
        
        line = await loop.run_in_executor(None, read_line)
        return line.strip() if line else ""
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from the MCP server."""
        try:
            logger.debug("Requesting tool list from MCP server")
            result = await self._send_request("tools/list")
            tools = result.get("tools", [])
            logger.info(f"MCP server returned {len(tools)} tools")
            return tools
        except Exception as e:
            logger.error(f"Failed to list tools from MCP server: {e}")
            return []
    
    async def invoke_tool(self, tool_name: str, params: Dict[str, Any], timeout_ms: int = 30000) -> Dict[str, Any]:
        """Invoke a specific tool on the MCP server."""
        try:
            logger.debug(f"Invoking MCP tool: {tool_name} with params: {list(params.keys())}")
            
            request_params = {
                "name": tool_name,
                "arguments": params
            }
            
            result = await self._send_request("tools/call", request_params, timeout_ms)
            logger.debug(f"MCP tool {tool_name} completed successfully")
            return result
            
        except Exception as e:
            logger.error(f"Failed to invoke MCP tool {tool_name}: {e}")
            raise
    
    async def health_check(self) -> bool:
        """Perform a health check on the MCP server."""
        try:
            tools = await self.list_tools()
            return isinstance(tools, list)
        except Exception as e:
            logger.debug(f"MCP health check failed: {e}")
            return False
    
    async def get_tool_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get the schema for a specific tool."""
        try:
            tools = await self.list_tools()
            for tool in tools:
                if tool.get("name") == tool_name:
                    return tool
            return None
        except Exception as e:
            logger.error(f"Failed to get schema for tool {tool_name}: {e}")
            return None


class ToolrowMCPManager:
    """High-level manager for Toolrow MCP operations."""
    
    def __init__(self):
        self._client: Optional[ToolrowMCPClient] = None
    
    def get_client(self) -> Optional[ToolrowMCPClient]:
        """Get the Toolrow MCP client."""
        if self._client:
            return self._client
        
        # Import here to avoid circular imports
        from .registry import mcp_registry
        
        server = mcp_registry.get_server("toolrow-gateway")
        if server and server.is_running():
            self._client = ToolrowMCPClient(server)
            return self._client
        
        return None
    
    async def list_available_tools(self) -> List[Dict[str, Any]]:
        """List all available Toolrow tools."""
        client = self.get_client()
        if not client:
            logger.warning("Toolrow MCP client not available")
            return []
        
        return await client.list_tools()
    
    async def invoke_toolrow_tool(self, tool_name: str, params: Dict[str, Any], timeout_ms: int = 30000) -> Dict[str, Any]:
        """Invoke a Toolrow tool with the given parameters."""
        client = self.get_client()
        if not client:
            raise MCPError("Toolrow MCP client not available")
        
        return await client.invoke_tool(tool_name, params, timeout_ms)
    
    async def parallel_invoke(self, tool_calls: List[Dict[str, Any]], timeout_ms: int = 30000) -> List[Dict[str, Any]]:
        """Invoke multiple Toolrow tools in parallel."""
        client = self.get_client()
        if not client:
            raise MCPError("Toolrow MCP client not available")
        
        # Create tasks for parallel execution
        tasks = []
        for tool_call in tool_calls:
            tool_name = tool_call.get("tool")
            params = tool_call.get("params", {})
            
            task = asyncio.create_task(
                client.invoke_tool(tool_name, params, timeout_ms)
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results and handle any exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Tool call {i} failed: {result}")
                processed_results.append({
                    "error": str(result),
                    "tool": tool_calls[i].get("tool"),
                    "params": tool_calls[i].get("params")
                })
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def is_available(self) -> bool:
        """Check if Toolrow MCP is available and working."""
        client = self.get_client()
        if not client:
            return False
        
        return await client.health_check()


# Global manager instance
toolrow_mcp_manager = ToolrowMCPManager()
