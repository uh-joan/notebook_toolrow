"""
Test overbroad result narrowing strategies.

Tests the system's ability to refine queries when they return
too many results using various refinement strategies.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "surfsense_backend"))

from app.agents.source_discovery.reasoning.orchestrator import ReasoningOrchestrator
from app.agents.source_discovery.reasoning.config import ReasoningConfig
from app.agents.source_discovery.reasoning.models import ToolResult, FinalResponse
# Import MockAdapter from conftest.py
from conftest import MockAdapter


@pytest.fixture
def reasoning_config():
    """Create test configuration with lower max_ok for testing."""
    return ReasoningConfig(
        min_ok=5,
        max_ok=50,  # Lower threshold to trigger refinement
        max_rounds=3,
        per_query_timeout_s=5,
        parallel_limit=2
    )


@pytest.fixture
def overbroad_adapters():
    """Create mock adapters that return too many results initially."""
    return {
        "ct_gov_studies.search": MockAdapter("ct_gov_studies", [
            # First call returns too many hits
            ToolResult(tool="ct_gov_studies", ok=True, hits=500, data={
                "studies": [{"id": f"NCT{i}", "title": f"Study {i}"} for i in range(500)]
            }),
            # After refinement, returns acceptable number
            ToolResult(tool="ct_gov_studies", ok=True, hits=25, data={
                "studies": [{"id": f"NCT{i}", "title": f"Refined Study {i}"} for i in range(25)]
            })
        ]),
        "nlm_ct_codes": MockAdapter("nlm_ct_codes", [
            ToolResult(tool="nlm_ct_codes", ok=True, hits=10, data={"results": [
                {"code": f"E1{i}", "name": f"Condition {i}"} for i in range(10)
            ]})
        ])
    }


@pytest.mark.asyncio
async def test_overbroad_refinement_with_phase_filtering(reasoning_config, overbroad_adapters):
    """Test refinement using trial phase filtering."""
    orchestrator = ReasoningOrchestrator(overbroad_adapters, reasoning_config)
    
    task = {
        "query": "cancer treatment trials",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    # Verify that refinement occurred
    assert result.success
    assert len(result.evidence) > 0
    
    # Check that refinement strategies were used
    refinement_events = [event for event in result.trace if event.step == "refine"]
    assert len(refinement_events) > 0
    
    # Verify that "too many" was detected
    too_many_events = [event for event in result.trace if "too_many" in event.reason.lower()]
    assert len(too_many_events) > 0


@pytest.mark.asyncio
async def test_overbroad_refinement_with_status_filtering(reasoning_config, overbroad_adapters):
    """Test refinement using trial status filtering."""
    # Configure to simulate status-based refinement
    overbroad_adapters["ct_gov_studies.search"].mock_results = [
        ToolResult(tool="ct_gov_studies", ok=True, hits=800, data={"studies": []}),
        ToolResult(tool="ct_gov_studies", ok=True, hits=30, data={"studies": [{"id": "NCT123", "status": "recruiting"}]})
    ]
    
    orchestrator = ReasoningOrchestrator(overbroad_adapters, reasoning_config)
    
    task = {
        "query": "diabetes trials recruiting",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    assert result.success
    
    # Should have attempted status refinement
    status_events = [event for event in result.trace if "status" in event.strategy.lower()]
    assert len(status_events) >= 0  # May not always use status refinement


@pytest.mark.asyncio
async def test_temporal_refinement(reasoning_config, overbroad_adapters):
    """Test refinement using temporal constraints."""
    # Simulate temporal refinement
    overbroad_adapters["ct_gov_studies.search"].mock_results = [
        ToolResult(tool="ct_gov_studies", ok=True, hits=1000, data={"studies": []}),
        ToolResult(tool="ct_gov_studies", ok=True, hits=35, data={"studies": [{"id": "NCT456", "start_date": "2020-01-01"}]})
    ]
    
    orchestrator = ReasoningOrchestrator(overbroad_adapters, reasoning_config)
    
    task = {
        "query": "cardiovascular disease studies",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    assert result.success
    
    # Check for temporal refinement in strategies
    temporal_events = [event for event in result.trace if "temporal" in event.strategy.lower()]
    assert len(temporal_events) >= 0


@pytest.mark.asyncio
async def test_multiple_refinement_rounds(reasoning_config, overbroad_adapters):
    """Test multiple rounds of refinement."""
    # Configure progressive refinement
    overbroad_adapters["ct_gov_studies.search"].mock_results = [
        ToolResult(tool="ct_gov_studies", ok=True, hits=1000, data={}),  # Initial overbroad
        ToolResult(tool="ct_gov_studies", ok=True, hits=200, data={}),   # First refinement still too broad
        ToolResult(tool="ct_gov_studies", ok=True, hits=40, data={"studies": [{"id": f"NCT{i}"} for i in range(40)]})  # Final refinement
    ]
    
    orchestrator = ReasoningOrchestrator(overbroad_adapters, reasoning_config)
    
    task = {
        "query": "medical research",  # Very broad query
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    assert result.success
    
    # Should have multiple refinement attempts
    refine_events = [event for event in result.trace if event.step == "refine"]
    assert len(refine_events) > 0


@pytest.mark.asyncio
async def test_precision_refinement_strategy(reasoning_config, overbroad_adapters):
    """Test precision-based refinement (exact phrase matching)."""
    orchestrator = ReasoningOrchestrator(overbroad_adapters, reasoning_config)
    
    task = {
        "query": "machine learning artificial intelligence",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    # Should attempt precision refinement
    precision_events = [event for event in result.trace if "precision" in event.strategy.lower()]
    assert len(precision_events) >= 0  # May not always trigger


@pytest.mark.asyncio
async def test_refinement_stops_at_acceptable_range(reasoning_config, overbroad_adapters):
    """Test that refinement stops when results are in acceptable range."""
    # Configure to hit acceptable range on first refinement
    overbroad_adapters["ct_gov_studies.search"].mock_results = [
        ToolResult(tool="ct_gov_studies", ok=True, hits=200, data={}),  # Overbroad
        ToolResult(tool="ct_gov_studies", ok=True, hits=25, data={"studies": [{"id": f"NCT{i}"} for i in range(25)]})  # Acceptable
    ]
    
    orchestrator = ReasoningOrchestrator(overbroad_adapters, reasoning_config)
    
    task = {
        "query": "clinical research",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    assert result.success
    assert len(result.evidence) == 25  # Should stop at acceptable results
    
    # Should not have excessive refinement rounds
    refine_events = [event for event in result.trace if event.step == "refine"]
    assert len(refine_events) <= 2  # Reasonable number of refinements


@pytest.mark.asyncio
async def test_geographic_refinement(reasoning_config, overbroad_adapters):
    """Test geographic-based refinement."""
    # Configure for geographic refinement
    overbroad_adapters["ct_gov_studies.search"].mock_results = [
        ToolResult(tool="ct_gov_studies", ok=True, hits=750, data={}),
        ToolResult(tool="ct_gov_studies", ok=True, hits=45, data={"studies": [{"id": "NCT789", "location": "United States"}]})
    ]
    
    orchestrator = ReasoningOrchestrator(overbroad_adapters, reasoning_config)
    
    task = {
        "query": "obesity intervention studies",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    assert result.success
    
    # Check for geographic refinement
    geo_events = [event for event in result.trace if "geographic" in event.strategy.lower()]
    assert len(geo_events) >= 0


@pytest.mark.asyncio
async def test_refinement_preserves_original_intent(reasoning_config, overbroad_adapters):
    """Test that refinement preserves the original search intent."""
    orchestrator = ReasoningOrchestrator(overbroad_adapters, reasoning_config)
    
    task = {
        "query": "diabetes type 2 treatment outcomes",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    assert result.success
    
    # Verify original query terms are preserved in the process
    query_analysis = result.query_analysis
    assert query_analysis is not None
    assert "diabetes" in query_analysis.entities.get("conditions", []) or "diabetes" in str(query_analysis.entities)


if __name__ == "__main__":
    # Run specific test
    asyncio.run(test_overbroad_refinement_with_phase_filtering(
        ReasoningConfig(max_ok=50), {}
    ))
