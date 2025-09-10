"""Pydantic schemas for ToolRow settings."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ToolrowSettingsBase(BaseModel):
    """Base schema for ToolRow settings."""
    api_token: str
    enabled: bool = True
    max_calls: int = 6
    timeout_ms: int = 30000


class ToolrowSettingsCreate(ToolrowSettingsBase):
    """Schema for creating ToolRow settings."""
    pass


class ToolrowSettingsUpdate(BaseModel):
    """Schema for updating ToolRow settings."""
    api_token: Optional[str] = None
    enabled: Optional[bool] = None
    max_calls: Optional[int] = None
    timeout_ms: Optional[int] = None


class ToolrowSettings(ToolrowSettingsBase):
    """Schema for ToolRow settings response."""
    id: int
    user_id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ToolrowSettingsPublic(BaseModel):
    """Public schema for ToolRow settings (without sensitive data)."""
    enabled: bool
    max_calls: int
    timeout_ms: int
    has_token: bool  # Whether token is configured, but don't expose the actual token
    
    class Config:
        from_attributes = True
