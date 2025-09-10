"""
Source Discovery Agent

A specialized agent for discovering and suggesting new data sources via MCP tools.
This agent focuses on live data retrieval and source enrichment, separate from 
the main researcher agent which handles RAG over existing documents.
"""

from .agent import SourceDiscoveryAgent, create_discovery_agent
from .source_types import DiscoveryRequest, DiscoveryResult, SourceSuggestion

__all__ = ["SourceDiscoveryAgent", "create_discovery_agent", "DiscoveryRequest", "DiscoveryResult", "SourceSuggestion"]
