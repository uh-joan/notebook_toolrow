"""
Test strict JSON output validation.

Tests that the reasoning system produces valid, well-structured
JSON responses that conform to the defined schemas.
"""

import pytest
import asyncio
import json
from pydantic import ValidationError

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "surfsense_backend"))

from app.agents.source_discovery.reasoning.orchestrator import ReasoningOrchestrator
from app.agents.source_discovery.reasoning.config import ReasoningConfig
from app.agents.source_discovery.reasoning.models import (
    FinalResponse, TraceEvent, EvidenceItem, QueryAnalysis, ToolResult
)
# Import MockAdapter from conftest.py
from conftest import MockAdapter


@pytest.fixture
def json_test_config():
    """Create configuration for JSON validation tests."""
    return ReasoningConfig(
        min_ok=3,
        max_ok=50,
        max_rounds=2,
        per_query_timeout_s=5
    )


@pytest.fixture
def json_test_adapters():
    """Create mock adapters with well-structured responses."""
    return {
        "ct_gov_studies.search": MockAdapter("ct_gov_studies", [
            ToolResult(
                tool="ct_gov_studies",
                ok=True,
                hits=5,
                data={
                    "studies": [
                        {
                            "protocolSection": {
                                "identificationModule": {
                                    "nctId": "NCT12345",
                                    "briefTitle": "Test Study 1"
                                },
                                "statusModule": {
                                    "overallStatus": "recruiting"
                                }
                            }
                        }
                    ]
                },
                duration_ms=150
            )
        ]),
        "nlm_ct_codes": MockAdapter("nlm_ct_codes", [
            ToolResult(
                tool="nlm_ct_codes",
                ok=True,
                hits=3,
                data={
                    "results": [
                        {"code": "E11.9", "name": "Type 2 diabetes mellitus without complications"}
                    ]
                },
                duration_ms=75
            )
        ])
    }


@pytest.mark.asyncio
async def test_final_response_schema_validation(json_test_config, json_test_adapters):
    """Test that FinalResponse conforms to its Pydantic schema."""
    orchestrator = ReasoningOrchestrator(json_test_adapters, json_test_config)
    
    task = {
        "query": "diabetes clinical trials",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    # Should be a valid FinalResponse object
    assert isinstance(result, FinalResponse)
    
    # Test serialization to JSON
    json_data = result.model_dump()
    assert isinstance(json_data, dict)
    
    # Test JSON serialization without errors
    json_string = json.dumps(json_data, default=str)
    assert isinstance(json_string, str)
    
    # Test deserialization back to object
    parsed_data = json.loads(json_string)
    reconstructed = FinalResponse(**parsed_data)
    assert isinstance(reconstructed, FinalResponse)


@pytest.mark.asyncio
async def test_trace_event_schema_validation(json_test_config, json_test_adapters):
    """Test that TraceEvent objects conform to schema."""
    orchestrator = ReasoningOrchestrator(json_test_adapters, json_test_config)
    
    task = {
        "query": "medical research",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    # Validate each trace event
    for event in result.trace:
        assert isinstance(event, TraceEvent)
        
        # Required fields should be present
        assert event.step is not None
        assert event.strategy is not None
        assert event.reason is not None
        
        # Test JSON serialization
        event_json = event.model_dump()
        assert isinstance(event_json, dict)
        
        # Verify timestamp is serializable
        if event.timestamp:
            assert "timestamp" in event_json
            assert isinstance(event_json["timestamp"], str)


@pytest.mark.asyncio
async def test_evidence_item_schema_validation(json_test_config, json_test_adapters):
    """Test that EvidenceItem objects conform to schema."""
    orchestrator = ReasoningOrchestrator(json_test_adapters, json_test_config)
    
    task = {
        "query": "clinical trials diabetes",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    # Validate each evidence item
    for evidence in result.evidence:
        assert isinstance(evidence, EvidenceItem)
        
        # Required fields
        assert evidence.source is not None
        
        # Test JSON serialization
        evidence_json = evidence.model_dump()
        assert isinstance(evidence_json, dict)
        
        # Meta field should be a dict
        assert isinstance(evidence_json.get("meta", {}), dict)


@pytest.mark.asyncio
async def test_query_analysis_schema_validation(json_test_config, json_test_adapters):
    """Test that QueryAnalysis objects conform to schema."""
    orchestrator = ReasoningOrchestrator(json_test_adapters, json_test_config)
    
    task = {
        "query": "diabetes type 2 treatment trials",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    if result.query_analysis:
        analysis = result.query_analysis
        assert isinstance(analysis, QueryAnalysis)
        
        # Required fields
        assert analysis.query_type is not None
        assert analysis.intent is not None
        assert analysis.complexity is not None
        
        # Test JSON serialization
        analysis_json = analysis.model_dump()
        assert isinstance(analysis_json, dict)
        
        # Entities should be a dict
        assert isinstance(analysis_json.get("entities", {}), dict)


def test_tool_result_schema_validation():
    """Test ToolResult schema validation."""
    # Test successful result
    success_result = ToolResult(
        tool="test_tool",
        ok=True,
        hits=5,
        data={"test": "data"},
        duration_ms=100
    )
    
    assert isinstance(success_result, ToolResult)
    
    # Test JSON serialization
    result_json = success_result.model_dump()
    assert isinstance(result_json, dict)
    assert result_json["ok"] is True
    assert result_json["hits"] == 5
    
    # Test error result
    error_result = ToolResult(
        tool="test_tool",
        ok=False,
        hits=0,
        data=None,
        error="Test error"
    )
    
    assert isinstance(error_result, ToolResult)
    error_json = error_result.model_dump()
    assert error_json["ok"] is False
    assert error_json["error"] == "Test error"


@pytest.mark.asyncio
async def test_json_serialization_with_special_characters(json_test_config, json_test_adapters):
    """Test JSON handling with special characters and edge cases."""
    # Configure adapter with special characters
    json_test_adapters["ct_gov_studies.search"].mock_results = [
        ToolResult(
            tool="ct_gov_studies",
            ok=True,
            hits=2,
            data={
                "studies": [
                    {
                        "title": "Study with special chars: àáâãäå ñ ç €",
                        "description": "JSON test with \"quotes\" and 'apostrophes'"
                    }
                ]
            }
        )
    ]
    
    orchestrator = ReasoningOrchestrator(json_test_adapters, json_test_config)
    
    task = {
        "query": "special characters test àáâãäå",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    # Should handle special characters in JSON serialization
    json_data = result.model_dump()
    json_string = json.dumps(json_data, ensure_ascii=False, default=str)
    
    # Should be valid JSON
    parsed_back = json.loads(json_string)
    assert isinstance(parsed_back, dict)


@pytest.mark.asyncio
async def test_json_schema_completeness(json_test_config, json_test_adapters):
    """Test that JSON output contains all expected fields."""
    orchestrator = ReasoningOrchestrator(json_test_adapters, json_test_config)
    
    task = {
        "query": "comprehensive test query",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    json_data = result.model_dump()
    
    # Check for required top-level fields
    required_fields = ["answer", "evidence", "trace", "limitations", "next_best_actions", "success"]
    for field in required_fields:
        assert field in json_data, f"Missing required field: {field}"
    
    # Check field types
    assert isinstance(json_data["answer"], dict)
    assert isinstance(json_data["evidence"], list)
    assert isinstance(json_data["trace"], list)
    assert isinstance(json_data["limitations"], list)
    assert isinstance(json_data["next_best_actions"], list)
    assert isinstance(json_data["success"], bool)


def test_pydantic_validation_errors():
    """Test that invalid data raises appropriate Pydantic validation errors."""
    # Test invalid ToolResult
    with pytest.raises(ValidationError):
        ToolResult(
            tool="test",
            ok="not_boolean",  # Should be boolean
            hits="not_int"     # Should be integer
        )
    
    # Test invalid TraceEvent
    with pytest.raises(ValidationError):
        TraceEvent(
            # Missing required fields: step, strategy, reason
            input={},
            outcome={}
        )
    
    # Test invalid EvidenceItem
    with pytest.raises(ValidationError):
        EvidenceItem(
            # Missing required field: source
            title="Test"
        )


@pytest.mark.asyncio
async def test_datetime_serialization(json_test_config, json_test_adapters):
    """Test that datetime fields are properly serialized."""
    orchestrator = ReasoningOrchestrator(json_test_adapters, json_test_config)
    
    task = {
        "query": "datetime test",
        "user_id": "test_user"
    }
    
    result = await orchestrator.run(task)
    
    # Check that trace events with timestamps serialize properly
    for event in result.trace:
        if event.timestamp:
            event_json = event.model_dump()
            timestamp_str = event_json["timestamp"]
            assert isinstance(timestamp_str, str)
            # Should be ISO format
            assert "T" in timestamp_str or "-" in timestamp_str


if __name__ == "__main__":
    # Run specific test
    asyncio.run(test_final_response_schema_validation(
        ReasoningConfig(), {}
    ))
