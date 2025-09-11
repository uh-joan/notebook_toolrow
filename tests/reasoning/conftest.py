"""
Shared fixtures and utilities for reasoning tests.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "surfsense_backend"))

from app.agents.source_discovery.reasoning.models import ToolResult
from app.agents.source_discovery.reasoning.adapters import BaseAdapter


class MockAdapter(BaseAdapter):
    """Mock adapter for testing."""
    
    def __init__(self, tool_name: str, mock_results: list = None):
        super().__init__(tool_name, timeout_s=10)
        self.mock_results = mock_results or []
        self.call_count = 0
    
    async def call(self, params):
        result = self.mock_results[self.call_count] if self.call_count < len(self.mock_results) else ToolResult(
            tool=self.tool_name,
            ok=False,
            hits=0,
            data=None,
            error="No more mock results"
        )
        self.call_count += 1
        return result
