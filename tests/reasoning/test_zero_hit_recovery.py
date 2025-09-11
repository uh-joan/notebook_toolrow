"""
Test zero-hit recovery strategies.

Tests the system's ability to recover from queries that return
no results using various expansion strategies.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "surfsense_backend"))

from app.agents.source_discovery.reasoning.orchestrator import ReasoningOrchestrator
from app.agents.source_discovery.reasoning.config import ReasoningConfig
from app.agents.source_discovery.reasoning.models import ToolResult, SearchState, FinalResponse
from app.agents.source_discovery.reasoning.adapters import BaseAdapter


# Import MockAdapter from conftest.py
from conftest import MockAdapter


@pytest.fixture
def reasoning_config():
    """Create test configuration."""
    return ReasoningConfig(
        min_ok=5,
        max_ok=100,
        max_rounds=3,
        per_query_timeout_s=5,
        parallel_limit=2
    )


@pytest.fixture
def mock_adapters():
    """Create mock adapters."""
    return {
        "ct_gov_studies.search": MockAdapter("ct_gov_studies", [
            # First call returns zero hits
            ToolResult(tool="ct_gov_studies", ok=True, hits=0, data={}),
            # After expansion, returns some results
            ToolResult(tool="ct_gov_studies", ok=True, hits=8, data={"studies": [{"id": "NCT123"}] * 8})
        ]),
        "ct_gov_studies.suggest": MockAdapter("ct_gov_studies.suggest", [
            ToolResult(tool="ct_gov_studies.suggest", ok=True, hits=3, data=["diabetes mellitus", "diabetic", "T2D"])
        ]),
        "nlm_ct_codes": MockAdapter("nlm_ct_codes", [
            ToolResult(tool="nlm_ct_codes", ok=True, hits=5, data={"results": [
                {"code": "E11", "name": "Type 2 diabetes"},
                {"code": "E10", "name": "Type 1 diabetes"}
            ]})
        ])
    }


@pytest.mark.asyncio
async def test_zero_hit_recovery_with_terminology_suggestion(reasoning_config, mock_adapters):
    """Test zero hit recovery using terminology suggestions."""
    orchestrator = ReasoningOrchestrator(mock_adapters, reasoning_config)
    
    task = {
        "query": "closed-loop insulin delivery systems",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    # Verify that we recovered from zero hits
    assert result.success
    assert len(result.evidence) > 0
    assert any("zero_hit" in str(event.strategy) for event in result.trace)
    
    # Verify expansion strategies were attempted
    expansion_events = [event for event in result.trace if event.step == "expand"]
    assert len(expansion_events) > 0


@pytest.mark.asyncio
async def test_zero_hit_recovery_with_code_mapping(reasoning_config, mock_adapters):
    """Test zero hit recovery using medical code mapping."""
    # Configure mock to return zero hits initially, then success after code mapping
    mock_adapters["ct_gov_studies.search"].mock_results = [
        ToolResult(tool="ct_gov_studies", ok=True, hits=0, data={}),
        ToolResult(tool="ct_gov_studies", ok=True, hits=12, data={"studies": [{"id": f"NCT{i}"} for i in range(12)]})
    ]
    
    orchestrator = ReasoningOrchestrator(mock_adapters, reasoning_config)
    
    task = {
        "query": "diabetes treatment trials",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    assert result.success
    assert len(result.evidence) > 0
    
    # Verify code mapping was attempted
    code_events = [event for event in result.trace if "code" in event.strategy.lower()]
    assert len(code_events) > 0


@pytest.mark.asyncio
async def test_multiple_expansion_rounds(reasoning_config, mock_adapters):
    """Test multiple rounds of expansion when initial strategies fail."""
    # Configure progressive failure then success
    mock_adapters["ct_gov_studies.search"].mock_results = [
        ToolResult(tool="ct_gov_studies", ok=True, hits=0, data={}),  # Initial search
        ToolResult(tool="ct_gov_studies", ok=True, hits=0, data={}),  # First expansion
        ToolResult(tool="ct_gov_studies", ok=True, hits=7, data={"studies": [{"id": f"NCT{i}"} for i in range(7)]})  # Second expansion
    ]
    
    orchestrator = ReasoningOrchestrator(mock_adapters, reasoning_config)
    
    task = {
        "query": "rare disease treatment",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    assert result.success
    
    # Should have multiple rounds
    assert any(event.step == "expand" for event in result.trace)
    
    # Should track multiple rounds
    search_state_rounds = [event for event in result.trace if "round" in str(event.outcome)]
    assert len(search_state_rounds) > 1


@pytest.mark.asyncio
async def test_expansion_timeout_handling(reasoning_config, mock_adapters):
    """Test handling of timeouts during expansion."""
    # Mock a timeout scenario
    mock_adapters["ct_gov_studies.search"].mock_results = [
        ToolResult(tool="ct_gov_studies", ok=True, hits=0, data={}),  # Initial zero hits
        ToolResult(tool="ct_gov_studies", ok=False, hits=0, data=None, error="Timeout")  # Timeout on expansion
    ]
    
    orchestrator = ReasoningOrchestrator(mock_adapters, reasoning_config)
    
    task = {
        "query": "experimental cancer therapy",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    # Should handle gracefully even with timeouts
    assert isinstance(result, FinalResponse)
    assert "timeout" in str(result.limitations).lower() or "error" in str(result.limitations).lower()


@pytest.mark.asyncio
async def test_max_rounds_limit(reasoning_config, mock_adapters):
    """Test that expansion stops at max rounds limit."""
    # Configure to always return zero hits
    zero_result = ToolResult(tool="ct_gov_studies", ok=True, hits=0, data={})
    mock_adapters["ct_gov_studies.search"].mock_results = [zero_result] * 10
    mock_adapters["ct_gov_studies.suggest"].mock_results = [
        ToolResult(tool="ct_gov_studies.suggest", ok=True, hits=2, data=["term1", "term2"])
    ] * 10
    
    orchestrator = ReasoningOrchestrator(mock_adapters, reasoning_config)
    
    task = {
        "query": "impossible to find query",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    # Should respect max rounds limit
    assert not result.success  # Should fail after max rounds
    assert "maximum rounds" in str(result.limitations).lower()


@pytest.mark.asyncio  
async def test_expansion_strategy_selection(reasoning_config, mock_adapters):
    """Test that appropriate expansion strategies are selected based on query type."""
    orchestrator = ReasoningOrchestrator(mock_adapters, reasoning_config)
    
    # Test medical condition query
    task = {
        "query": "diabetes management trials",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    # Should have attempted medical-specific strategies
    trace_strategies = [event.strategy for event in result.trace]
    
    # Should include medical-relevant strategies
    medical_strategies = ["code_mapping", "term_suggestion", "synonym_expansion"]
    used_medical_strategies = [s for s in trace_strategies if any(ms in s for ms in medical_strategies)]
    assert len(used_medical_strategies) > 0


if __name__ == "__main__":
    # Run specific test
    asyncio.run(test_zero_hit_recovery_with_terminology_suggestion(
        ReasoningConfig(), {}
    ))
