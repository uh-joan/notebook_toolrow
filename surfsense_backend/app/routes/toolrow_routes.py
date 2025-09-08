"""Toolrow MCP API routes for development and testing."""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import User, get_async_session
from app.toolrow_mcp.client import toolrow_mcp_manager
from app.toolrow_mcp.registry import mcp_registry
from app.users import current_active_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/toolrow", tags=["toolrow"])


class ToolInvokeRequest(BaseModel):
    """Request model for tool invocation."""
    tool: str
    params: Dict[str, Any]
    timeout_ms: int = 30000


class ServerStatusResponse(BaseModel):
    """Response model for server status."""
    name: str
    running: bool
    restart_count: int
    pid: int | None
    tools: List[Dict[str, Any]] = []


@router.get("/servers", response_model=List[ServerStatusResponse])
async def get_server_status(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Get status of all MCP servers."""
    try:
        status = mcp_registry.get_server_status()
        
        servers = []
        for name, server_info in status.items():
            # Get tools if server is running
            tools = []
            if server_info["running"]:
                try:
                    tools = await toolrow_mcp_manager.list_available_tools()
                except Exception as e:
                    logger.error(f"Failed to get tools for server {name}: {e}")
            
            servers.append(ServerStatusResponse(
                name=name,
                running=server_info["running"],
                restart_count=server_info["restart_count"],
                pid=server_info["pid"],
                tools=tools
            ))
        
        return servers
        
    except Exception as e:
        logger.error(f"Failed to get server status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get server status: {e}")


@router.post("/restart/{server_name}")
async def restart_server(
    server_name: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Restart a specific MCP server (development only)."""
    try:
        success = await mcp_registry.restart_server(server_name)
        
        if success:
            return {"message": f"Server {server_name} restarted successfully"}
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to restart server {server_name}"
            )
            
    except Exception as e:
        logger.error(f"Failed to restart server {server_name}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to restart server {server_name}: {e}"
        )


@router.post("/invoke")
async def invoke_tool(
    request: ToolInvokeRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Invoke a Toolrow MCP tool (development/testing)."""
    try:
        if not await toolrow_mcp_manager.is_available():
            raise HTTPException(
                status_code=503,
                detail="Toolrow MCP is not available"
            )
        
        result = await toolrow_mcp_manager.invoke_toolrow_tool(
            tool_name=request.tool,
            params=request.params,
            timeout_ms=request.timeout_ms
        )
        
        return {
            "tool": request.tool,
            "params": request.params,
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Failed to invoke tool {request.tool}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to invoke tool {request.tool}: {e}"
        )


@router.get("/tools")
async def list_tools(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """List all available Toolrow tools."""
    try:
        if not await toolrow_mcp_manager.is_available():
            raise HTTPException(
                status_code=503,
                detail="Toolrow MCP is not available"
            )
        
        tools = await toolrow_mcp_manager.list_available_tools()
        
        return {
            "tools": tools,
            "count": len(tools)
        }
        
    except Exception as e:
        logger.error(f"Failed to list tools: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list tools: {e}"
        )


@router.get("/health")
async def health_check():
    """Check health of Toolrow MCP integration."""
    try:
        is_available = await toolrow_mcp_manager.is_available()
        server_status = mcp_registry.get_server_status()
        
        return {
            "available": is_available,
            "servers": server_status
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "available": False,
            "error": str(e),
            "servers": {}
        }
