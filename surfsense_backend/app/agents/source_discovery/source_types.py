"""
Type definitions for Source Discovery Agent
"""

from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel
from datetime import datetime
import uuid

# Discovery Mode type definition
DiscoveryMode = Literal["BASIC", "DEEP", "COMPREHENSIVE"]

class DiscoveryRequest(BaseModel):
    """Request for source discovery"""
    query: str
    user_id: uuid.UUID
    discovery_mode: Optional[DiscoveryMode] = "BASIC"  # Discovery complexity level
    focus_areas: Optional[List[str]] = None  # e.g., ["clinical_trials", "drug_info", "research_papers"]
    filters: Optional[Dict[str, Any]] = None  # e.g., {"region": "US", "status": "recruiting"}
    max_sources: Optional[int] = 50
    export_format: Optional[Literal["json", "csv", "markdown", "pdf", "excel", "powerpoint", "docx"]] = "json"
    conversation_history: Optional[List[str]] = None  # Previous messages for context


class SourceMetadata(BaseModel):
    """Metadata about a discovered source"""
    source_type: str  # "clinical_trial", "fda_document", "research_paper", etc.
    title: str
    description: Optional[str] = None
    url: Optional[str] = None
    publication_date: Optional[datetime] = None
    relevance_score: float  # 0-1 confidence in relevance
    tags: List[str] = []
    raw_data: Dict[str, Any] = {}  # Original API response


class SourceSuggestion(BaseModel):
    """A suggested source that could be added to the knowledge base"""
    metadata: SourceMetadata
    content_preview: str  # First few lines or summary
    content: Optional[str] = None  # Full content for frontend parsing
    import_recommendation: str  # Why this should be added
    estimated_value: float  # 0-1 estimated value to knowledge base
    processing_notes: Optional[str] = None  # How to process this source


class DiscoveryResult(BaseModel):
    """Result of source discovery operation"""
    request: DiscoveryRequest
    suggestions: List[SourceSuggestion]
    total_found: int
    processing_time_ms: int
    export_path: Optional[str] = None  # Path to exported file if requested
    summary: str  # Human-readable summary of what was found
    next_steps: List[str] = []  # Suggested follow-up actions
    reasoning_steps: List[str] = []  # Sequential thinking steps taken
    terminal_events: List[Dict[str, Any]] = []  # Terminal events for UI display
    advanced_formatting: Optional[Dict[str, Any]] = None  # AI-generated formatting and insights
    smart_follow_ups: Optional[Dict[str, Any]] = None  # AI-generated follow-up questions and suggestions
