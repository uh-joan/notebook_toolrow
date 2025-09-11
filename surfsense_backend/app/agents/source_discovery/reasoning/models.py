"""
Pydantic models for the reasoning system.

Defines the core data structures for reasoning traces, evidence items,
tool interactions, and final responses.
"""

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from datetime import datetime


class EvidenceItem(BaseModel):
    """Single piece of evidence from a tool search."""
    
    source: str = Field(..., description="Tool that provided this evidence")
    id: Optional[str] = Field(None, description="Unique identifier (NCT, PMID, etc.)")
    title: Optional[str] = Field(None, description="Title or name of the evidence")
    url: Optional[str] = Field(None, description="Direct URL to the source")
    meta: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    relevance_score: Optional[float] = Field(None, description="Computed relevance score")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class TraceEvent(BaseModel):
    """Single step in the reasoning trace."""
    
    step: str = Field(..., description="Type of step (expand, search, refine, chain)")
    strategy: str = Field(..., description="Specific strategy used")
    tool: Optional[str] = Field(None, description="Tool that was called")
    input: Dict[str, Any] = Field(default_factory=dict, description="Input parameters")
    outcome: Dict[str, Any] = Field(default_factory=dict, description="Result summary")
    reason: str = Field(..., description="Why this action was chosen")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: Optional[int] = Field(None, description="Execution time in milliseconds")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ToolQuery(BaseModel):
    """Query to be executed by a tool."""
    
    tool: str = Field(..., description="Tool identifier")
    params: Dict[str, Any] = Field(default_factory=dict, description="Tool parameters")
    timeout_s: Optional[int] = Field(None, description="Custom timeout for this query")
    priority: int = Field(1, description="Execution priority (higher = more important)")


class ToolResult(BaseModel):
    """Result from a tool execution."""
    
    tool: str = Field(..., description="Tool that was executed")
    ok: bool = Field(..., description="Whether execution succeeded")
    hits: int = Field(0, description="Number of results returned")
    data: Any = Field(None, description="Raw result data")
    error: Optional[str] = Field(None, description="Error message if execution failed")
    duration_ms: Optional[int] = Field(None, description="Execution time in milliseconds")
    from_cache: bool = Field(False, description="Whether result came from cache")
    
    class Config:
        arbitrary_types_allowed = True


class QueryAnalysis(BaseModel):
    """Analysis of the user's query to guide strategy selection."""
    
    query_type: str = Field(..., description="Type of query (trials, codes, drugs, literature)")
    entities: Dict[str, List[str]] = Field(default_factory=dict, description="Extracted entities")
    intent: str = Field(..., description="Search intent (precision, recall, balanced)")
    complexity: str = Field(..., description="Query complexity (simple, moderate, complex)")
    suggested_tools: List[str] = Field(default_factory=list, description="Recommended tools")
    confidence: float = Field(0.0, description="Confidence in analysis")


class SearchState(BaseModel):
    """Current state of the reasoning search."""
    
    original_query: str = Field(..., description="Original user query")
    working_terms: List[str] = Field(default_factory=list, description="Current search terms")
    extracted_entities: Dict[str, List[str]] = Field(default_factory=dict)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    attempted_strategies: List[str] = Field(default_factory=list)
    round_number: int = Field(1, description="Current expansion round")
    total_hits: int = Field(0, description="Total results found so far")
    
    def add_evidence(self, items: List[EvidenceItem]) -> None:
        """Add evidence items and update total hits."""
        self.evidence.extend(items)
        self.total_hits += len(items)


class FinalResponse(BaseModel):
    """Final response from the reasoning system."""
    
    answer: Dict[str, Any] = Field(default_factory=dict, description="Structured answer")
    evidence: List[EvidenceItem] = Field(default_factory=list, description="Supporting evidence")
    trace: List[TraceEvent] = Field(default_factory=list, description="Reasoning trace")
    limitations: List[str] = Field(default_factory=list, description="Known limitations")
    next_best_actions: List[str] = Field(default_factory=list, description="Suggested follow-ups")
    query_analysis: Optional[QueryAnalysis] = Field(None, description="Initial query analysis")
    total_duration_ms: Optional[int] = Field(None, description="Total execution time")
    success: bool = Field(True, description="Whether the search was successful")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
