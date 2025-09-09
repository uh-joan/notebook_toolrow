"""Type definitions for Toolrow MCP integration."""

from typing import Dict, List, Literal, Optional, TypedDict


# Provider and Kind type definitions
Provider = Literal[
    'fda',
    'ct_gov', 
    'pubmed',
    'sec',
    'who',
    'codes'
]

Kind = Literal[
    'drug_label',
    'trial',
    'article', 
    'filing',
    'indicator'
]

# Artifact type for downloaded files
class Artifact(TypedDict):
    """Represents a downloaded file artifact."""
    type: Literal['pdf', 'html', 'json', 'csv']
    path: str
    uri: Optional[str]


# Main entity record from Toolrow MCP
class EntityRecord(TypedDict, total=False):
    """Normalized entity record from Toolrow MCP tools."""
    provider: Provider
    kind: Kind
    canonical_id: str
    title: str
    uri: str
    summary: str
    metadata: Dict
    artifacts: List[Artifact]


# Coverage and intent types
class Intent(TypedDict, total=False):
    """Detected intent from user query."""
    category: Literal[
        'drug_search',
        'trial_search', 
        'literature_search',
        'filing_search',
        'health_data'
    ]
    entities: List[str]  # Extracted entities (drug names, conditions, etc.)
    conditions: List[str]  # Medical conditions
    regions: List[str]  # Geographic regions (US, EU, etc.)
    time_range: Optional[str]  # Time range for searches
    confidence: float  # Confidence score 0-1
    requires_completeness_check: bool  # True for comprehensive queries


# Tool call definitions
class ToolCall(TypedDict):
    """Represents a call to a Toolrow MCP tool."""
    tool: str
    params: Dict
    timeout_ms: Optional[int]


# Answer payload from research orchestrator
class AnswerPayload(TypedDict, total=False):
    """Complete answer payload from research orchestrator."""
    answer: str
    citations: List[Dict]  # Mix of document and live citations
    coverage: float  # RAG coverage score 0-1
    live_candidates: List[EntityRecord]  # Live results from MCP
    tool_invocations: List[ToolCall]  # Tools that were called
    errors: List[str]  # Any errors that occurred


# Source reference types for database
class SourceRefMode(TypedDict):
    """Source reference modes."""
    mode: Literal['live', 'snapshot']


# Citation types
class DocumentCitation(TypedDict):
    """Citation for a document source."""
    type: Literal['doc']
    source_id: str
    title: str
    excerpt: str


class LiveCitation(TypedDict):
    """Citation for a live MCP source."""
    type: Literal['live']
    provider: Provider
    kind: Kind
    canonical_id: str
    title: str
    params_hash: str
    uri: Optional[str]


# Union type for all citation types
Citation = DocumentCitation | LiveCitation


# Response types for API endpoints
class ResearchAskRequest(TypedDict):
    """Request for research ask endpoint."""
    question: str
    selected_source_ids: List[str]
    toolrow_enabled: bool
    search_space_id: int  # Using search_space as notebook


class ResearchAskResponse(TypedDict):
    """Response from research ask endpoint."""
    answer: str
    citations: List[Citation]
    coverage: float
    live_candidates: List[EntityRecord]
    tool_invocations: List[ToolCall]


# Source management types
class AddLiveSourceRequest(TypedDict):
    """Request to add a live source."""
    provider: Provider
    kind: Kind
    params: Dict
    ttl_sec: int
    search_space_id: int


class PromoteSnapshotRequest(TypedDict):
    """Request to promote entities to snapshots."""
    entity_records: List[EntityRecord]
    search_space_id: int


class RefreshSourceResponse(TypedDict):
    """Response from refreshing a source."""
    delta: Dict[str, int]  # added, removed, changed counts
    new_hash: str


# MCP server types
class MCPServerInfo(TypedDict):
    """Information about an MCP server."""
    name: str
    status: Literal['running', 'stopped', 'error']
    tools: List[Dict]


class MCPToolSchema(TypedDict):
    """Schema for an MCP tool."""
    name: str
    description: str
    inputSchema: Dict  # JSON schema for input parameters


# Error types
class MCPErrorInfo(TypedDict):
    """Information about an MCP error."""
    tool: str
    params: Dict
    error: str
    timestamp: str
