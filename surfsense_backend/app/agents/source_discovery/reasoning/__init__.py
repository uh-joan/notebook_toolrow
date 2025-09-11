"""
Reasoning package for Source Discovery Agent.

This package provides advanced reasoning capabilities including:
- Query expansion and refinement strategies
- Tool chaining and orchestration
- Deterministic retry logic
- Comprehensive result tracing
"""

from .models import FinalResponse, TraceEvent, EvidenceItem, ToolQuery, ToolResult
from .config import ReasoningConfig
from .utils import is_zero, too_few, too_many, year_window, dedupe
from .orchestrator import ReasoningOrchestrator
from .adapters import create_adapters
from .logging import reasoning_logger, configure_reasoning_logging

__all__ = [
    "FinalResponse",
    "TraceEvent", 
    "EvidenceItem",
    "ToolQuery",
    "ToolResult",
    "ReasoningConfig",
    "ReasoningOrchestrator",
    "create_adapters",
    "reasoning_logger",
    "configure_reasoning_logging",
    "is_zero",
    "too_few", 
    "too_many",
    "year_window",
    "dedupe"
]
