#!/usr/bin/env python3
"""
Test script for AI-powered intent detection and parameter building.
"""

import asyncio
import sys
import os

# Add the backend to Python path
sys.path.append('/Users/joan.saez-pons/code/SurfSense/surfsense_backend')

from app.research.orchestrator import ResearchOrchestrator
from app.research.routing import AIIntentDetector, HybridIntentDetector, ToolRouter
from app.toolrow_mcp.client import toolrow_mcp_manager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_ai_intent_detection():
    """Test AI intent detection with various queries."""
    print("🤖 Testing AI Intent Detection...")
    
    test_queries = [
        "What drugs are approved for obesity in the US?",
        "What medical devices are available for diabetes?",
        "What are the safety concerns with weight loss medications?",
        "What clinical trials are running for cancer treatments?",
        "What's the market size for cardiovascular drugs?"
    ]
    
    # Create a mock LLM instance (we'll skip actual LLM calls for now)
    # In a real test, you'd get the actual LLM instance
    orchestrator = ResearchOrchestrator(intent_mode="hybrid")
    
    for query in test_queries:
        print(f"\n📝 Query: {query}")
        try:
            # This will use pattern-based detection since we don't have LLM context
            intent = await orchestrator.detect_intent(query)
            print(f"✅ Intent: {intent}")
        except Exception as e:
            print(f"❌ Error: {e}")

async def test_tool_routing():
    """Test tool routing and parameter building."""
    print("\n🛣️ Testing Tool Routing...")
    
    # Mock intent for testing
    mock_intent = {
        "category": "drug_search",
        "entities": ["drugs", "obesity"],
        "conditions": ["obesity"],
        "regions": ["US"],
        "time_range": None,
        "confidence": 0.9,
        "requires_completeness_check": True
    }
    
    mock_canonicalized = {
        "codes": [],
        "entities": ["obesity", "drugs"]
    }
    
    try:
        # Test schema discovery
        print("🔍 Testing schema discovery...")
        if await toolrow_mcp_manager.is_available():
            tools = await toolrow_mcp_manager.list_available_tools()
            print(f"📋 Available tools: {[tool.get('name', 'unknown') for tool in tools]}")
            
            # Test tool routing
            router = ToolRouter()
            await router.discover_tool_schemas(toolrow_mcp_manager)
            
            tool_calls = await router.route(mock_intent, mock_canonicalized)
            print(f"🎯 Tool calls generated: {len(tool_calls)}")
            
            for i, tool_call in enumerate(tool_calls, 1):
                print(f"  {i}. Tool: {tool_call['tool']}")
                print(f"     Params: {tool_call['params']}")
                print(f"     Timeout: {tool_call.get('timeout_ms', 30000)}ms")
        else:
            print("⚠️ Toolrow MCP not available - skipping routing test")
            
    except Exception as e:
        print(f"❌ Tool routing error: {e}")
        import traceback
        traceback.print_exc()

async def test_mcp_call():
    """Test actual MCP call with built parameters."""
    print("\n📞 Testing MCP Call...")
    
    try:
        if await toolrow_mcp_manager.is_available():
            # Test a simple tool call
            result = await toolrow_mcp_manager.invoke_toolrow_tool(
                tool_name="fda_info",
                params={
                    "method": "search",
                    "search_term": "obesity drugs"
                },
                timeout_ms=10000
            )
            print(f"✅ MCP call successful!")
            print(f"📊 Result type: {type(result)}")
            print(f"📝 Result keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
        else:
            print("⚠️ Toolrow MCP not available - skipping MCP call test")
            
    except Exception as e:
        print(f"❌ MCP call error: {e}")
        import traceback
        traceback.print_exc()

async def test_full_workflow():
    """Test the complete research workflow."""
    print("\n🔄 Testing Full Research Workflow...")
    
    try:
        orchestrator = ResearchOrchestrator(intent_mode="hybrid")
        
        # Mock minimal parameters for testing
        question = "What drugs are approved for obesity in the US?"
        document_ids = []  # Empty for this test
        user_id = "test_user"
        search_space_id = 1
        
        # We can't easily test the full workflow without a real database session
        # But we can test individual components
        print(f"📝 Question: {question}")
        
        # Test intent detection
        intent = await orchestrator.detect_intent(question)
        print(f"🎯 Intent: {intent}")
        
        # Test canonicalization
        canonicalized = await orchestrator.canonicalize_query(question)
        print(f"📝 Canonicalized: {canonicalized}")
        
        # Test tool routing
        if orchestrator.tool_router:
            tool_calls = await orchestrator.route_tools(intent, canonicalized, toolrow_mcp_manager)
            print(f"🛣️ Tool calls: {len(tool_calls)}")
            for tool_call in tool_calls:
                print(f"  - {tool_call['tool']}: {tool_call['params']}")
        
    except Exception as e:
        print(f"❌ Full workflow error: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """Run all tests."""
    print("🧪 Starting AI Routing System Tests...\n")
    
    await test_ai_intent_detection()
    await test_tool_routing() 
    await test_mcp_call()
    await test_full_workflow()
    
    print("\n🎉 Test suite completed!")

if __name__ == "__main__":
    asyncio.run(main())
