"""API routes for ToolRow settings management."""

import logging
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..users import current_active_user, User
from ..db import get_async_session, ToolrowSettings
from ..schemas.toolrow_settings import (
    ToolrowSettingsCreate,
    ToolrowSettingsUpdate,
    ToolrowSettings as ToolrowSettingsSchema,
    ToolrowSettingsPublic
)
from ..toolrow_mcp.registry import mcp_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/toolrow-settings", tags=["toolrow-settings"])


@router.get("/", response_model=Optional[ToolrowSettingsPublic])
async def get_toolrow_settings(
    user: User = Depends(current_active_user),
    db_session: AsyncSession = Depends(get_async_session)
):
    """Get current user's ToolRow settings (public view)."""
    try:
        # Get user's ToolRow settings
        result = await db_session.execute(
            select(ToolrowSettings).where(ToolrowSettings.user_id == user.id)
        )
        settings = result.scalar_one_or_none()
        
        if not settings:
            return None
        
        return ToolrowSettingsPublic(
            enabled=settings.enabled,
            max_calls=settings.max_calls,
            timeout_ms=settings.timeout_ms,
            has_token=bool(settings.api_token and len(settings.api_token.strip()) > 0)
        )
        
    except Exception as e:
        logger.error(f"Failed to get ToolRow settings for user {user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get ToolRow settings")


@router.post("/", response_model=ToolrowSettingsPublic)
async def create_or_update_toolrow_settings(
    settings_data: ToolrowSettingsCreate,
    user: User = Depends(current_active_user),
    db_session: AsyncSession = Depends(get_async_session)
):
    """Create or update ToolRow settings for current user."""
    try:
        # Check if settings already exist
        result = await db_session.execute(
            select(ToolrowSettings).where(ToolrowSettings.user_id == user.id)
        )
        existing_settings = result.scalar_one_or_none()
        
        if existing_settings:
            # Update existing settings
            existing_settings.api_token = settings_data.api_token
            existing_settings.enabled = settings_data.enabled
            existing_settings.max_calls = settings_data.max_calls
            existing_settings.timeout_ms = settings_data.timeout_ms
            settings = existing_settings
        else:
            # Create new settings
            settings = ToolrowSettings(
                user_id=user.id,
                api_token=settings_data.api_token,
                enabled=settings_data.enabled,
                max_calls=settings_data.max_calls,
                timeout_ms=settings_data.timeout_ms
            )
            db_session.add(settings)
        
        await db_session.commit()
        await db_session.refresh(settings)
        
        # Restart MCP server with new token
        await _restart_toolrow_mcp_server(settings_data.api_token)
        
        logger.info(f"ToolRow settings {'updated' if existing_settings else 'created'} for user {user.id}")
        
        return ToolrowSettingsPublic(
            enabled=settings.enabled,
            max_calls=settings.max_calls,
            timeout_ms=settings.timeout_ms,
            has_token=bool(settings.api_token and len(settings.api_token.strip()) > 0)
        )
        
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Failed to save ToolRow settings for user {user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to save ToolRow settings")


@router.patch("/", response_model=ToolrowSettingsPublic)
async def update_toolrow_settings(
    settings_update: ToolrowSettingsUpdate,
    user: User = Depends(current_active_user),
    db_session: AsyncSession = Depends(get_async_session)
):
    """Update specific fields of ToolRow settings."""
    try:
        # Get existing settings
        result = await db_session.execute(
            select(ToolrowSettings).where(ToolrowSettings.user_id == user.id)
        )
        settings = result.scalar_one_or_none()
        
        if not settings:
            raise HTTPException(status_code=404, detail="ToolRow settings not found")
        
        # Update only provided fields
        update_data = settings_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(settings, field, value)
        
        await db_session.commit()
        await db_session.refresh(settings)
        
        # Restart MCP server if token was updated
        if "api_token" in update_data:
            await _restart_toolrow_mcp_server(settings.api_token)
        
        logger.info(f"ToolRow settings updated for user {user.id}")
        
        return ToolrowSettingsPublic(
            enabled=settings.enabled,
            max_calls=settings.max_calls,
            timeout_ms=settings.timeout_ms,
            has_token=bool(settings.api_token and len(settings.api_token.strip()) > 0)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Failed to update ToolRow settings for user {user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update ToolRow settings")


@router.delete("/")
async def delete_toolrow_settings(
    user: User = Depends(current_active_user),
    db_session: AsyncSession = Depends(get_async_session)
):
    """Delete ToolRow settings for current user."""
    try:
        # Get and delete settings
        result = await db_session.execute(
            select(ToolrowSettings).where(ToolrowSettings.user_id == user.id)
        )
        settings = result.scalar_one_or_none()
        
        if not settings:
            raise HTTPException(status_code=404, detail="ToolRow settings not found")
        
        await db_session.delete(settings)
        await db_session.commit()
        
        # Restart MCP server without token (will fail gracefully)
        await _restart_toolrow_mcp_server(None)
        
        logger.info(f"ToolRow settings deleted for user {user.id}")
        
        return {"message": "ToolRow settings deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Failed to delete ToolRow settings for user {user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete ToolRow settings")


async def _restart_toolrow_mcp_server(api_token: Optional[str]):
    """Restart the ToolRow MCP server with new API token."""
    try:
        import os
        
        # Set environment variable BEFORE restarting the MCP server
        if api_token:
            os.environ["TOOLROW_API_TOKEN"] = api_token
            logger.info("✅ Set TOOLROW_API_TOKEN environment variable")
        elif "TOOLROW_API_TOKEN" in os.environ:
            del os.environ["TOOLROW_API_TOKEN"]
            logger.info("🗑️ Removed TOOLROW_API_TOKEN environment variable")
        
        # Restart the ToolRow MCP server
        server = mcp_registry.get_server("toolrow-gateway")
        if server:
            logger.info("Restarting ToolRow MCP server with updated token...")
            success = await server.restart()
            if success:
                logger.info("✅ ToolRow MCP server restarted successfully")
                
                # Give server time to initialize and load tools
                await asyncio.sleep(2)
                
                # Verify tools are loaded
                from ..toolrow_mcp.client import ToolrowMCPManager
                mcp_manager = ToolrowMCPManager()
                tools = await mcp_manager.list_available_tools()
                logger.info(f"🔧 ToolRow MCP server now has {len(tools)} tools available")
                
            else:
                logger.warning("⚠️ Failed to restart ToolRow MCP server")
        else:
            logger.warning("ToolRow MCP server not found in registry")
            
    except Exception as e:
        logger.error(f"Failed to restart ToolRow MCP server: {e}")
        # Don't raise - this is not critical for the API call


async def get_user_toolrow_token(user_id: str, db_session: AsyncSession) -> Optional[str]:
    """Helper function to get user's ToolRow API token."""
    try:
        result = await db_session.execute(
            select(ToolrowSettings.api_token)
            .where(ToolrowSettings.user_id == user_id)
            .where(ToolrowSettings.enabled == True)
        )
        token = result.scalar_one_or_none()
        return token
    except Exception as e:
        logger.error(f"Failed to get ToolRow token for user {user_id}: {e}")
        return None
