#!/usr/bin/env python3
"""
Test script for the new Source Discovery Agent

This script demonstrates how the Source Discovery Agent works:
1. Finds live data sources via MCP tools
2. Suggests them for import into the knowledge base
3. Formats them for easy ingestion

Usage: python test_source_discovery.py
"""

import asyncio
import json
import logging
from typing import Dict, Any

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_discovery_api():
    """Test the Source Discovery Agent via API calls."""
    import aiohttp
    
    base_url = "http://localhost:8000"
    
    # Test data
    test_queries = [
        {
            "query": "active clinical trials recruiting for obesity treatment in the US",
            "focus_areas": ["clinical_trials"],
            "filters": {"region": "US", "status": "recruiting"},
            "max_sources": 10
        },
        {
            "query": "FDA approved drugs for weight management",
            "focus_areas": ["regulatory"],
            "max_sources": 15
        },
        {
            "query": "recent research papers on GLP-1 agonists for obesity",
            "focus_areas": ["research"],
            "max_sources": 20
        }
    ]
    
    async with aiohttp.ClientSession() as session:
        print("🔍 Testing Source Discovery Agent")
        print("=" * 50)
        
        # First, check service status
        try:
            async with session.get(f"{base_url}/api/source-discovery/status") as response:
                if response.status == 200:
                    status = await response.json()
                    print(f"✅ Service Status: {status['status']}")
                    print(f"📊 Tools Available: {status['tools_available']}")
                    print()
                else:
                    print(f"❌ Service not available (status: {response.status})")
                    return
        except Exception as e:
            print(f"❌ Could not connect to service: {e}")
            return
        
        # Test each query
        for i, test_query in enumerate(test_queries, 1):
            print(f"🔍 Test {i}: {test_query['query']}")
            print("-" * 30)
            
            try:
                # Make discovery request
                async with session.post(
                    f"{base_url}/api/source-discovery/discover",
                    json=test_query,
                    headers={"Authorization": "Bearer fake-token-for-testing"}  # In real usage, get from auth
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        
                        print(f"⏱️  Processing Time: {result.get('processing_time_ms', 0)}ms")
                        print(f"📊 Sources Found: {result.get('total_found', 0)}")
                        print()
                        
                        # Show summary
                        summary = result.get('summary', '')
                        if summary:
                            print("📝 Summary:")
                            print(summary)
                            print()
                        
                        # Show top suggestions
                        suggestions = result.get('suggestions', [])
                        if suggestions:
                            print("🏆 Top Suggestions:")
                            for j, suggestion in enumerate(suggestions[:3], 1):
                                metadata = suggestion.get('metadata', {})
                                print(f"  {j}. {metadata.get('title', 'Unknown')}")
                                print(f"     Type: {metadata.get('source_type', 'unknown')}")
                                print(f"     Value: {suggestion.get('estimated_value', 0):.0%}")
                                print(f"     Recommendation: {suggestion.get('import_recommendation', '')}")
                                print()
                        
                        # Show next steps
                        next_steps = result.get('next_steps', [])
                        if next_steps:
                            print("🎯 Next Steps:")
                            for step in next_steps:
                                print(f"  - {step}")
                            print()
                    
                    elif response.status == 401:
                        print("❌ Authentication required (in real usage)")
                    else:
                        error_text = await response.text()
                        print(f"❌ Request failed (status: {response.status})")
                        print(f"   Error: {error_text}")
                
            except Exception as e:
                print(f"❌ Test {i} failed: {e}")
            
            print("=" * 50)
            print()


async def test_direct_agent():
    """Test the Source Discovery Agent directly (without API layer)."""
    try:
        # Import the agent components
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), 'surfsense_backend'))
        
        from app.agents.source_discovery import SourceDiscoveryAgent, DiscoveryRequest
        from app.toolrow_mcp.client import ToolrowMCPManager
        
        print("🧪 Testing Source Discovery Agent Directly")
        print("=" * 50)
        
        # Initialize agent
        agent = SourceDiscoveryAgent()
        mcp_manager = ToolrowMCPManager()
        
        print("🔧 Initializing MCP Manager...")
        await mcp_manager.initialize()
        
        print("🤖 Initializing Discovery Agent...")
        await agent.initialize(mcp_manager)
        
        # Test discovery
        test_request = DiscoveryRequest(
            query="clinical trials for obesity treatment recruiting in the US",
            user_id=1,  # Mock user ID
            focus_areas=["clinical_trials"],
            filters={"region": "US", "status": "recruiting"},
            max_sources=5
        )
        
        print(f"🔍 Running discovery: {test_request.query}")
        result = await agent.discover_sources(test_request)
        
        print("\n📊 Results:")
        print(f"  - Total found: {result.total_found}")
        print(f"  - Processing time: {result.processing_time_ms}ms")
        print(f"  - Summary: {result.summary}")
        
        if result.suggestions:
            print("\n🏆 Top Suggestions:")
            for i, suggestion in enumerate(result.suggestions[:3], 1):
                print(f"  {i}. {suggestion.metadata.title}")
                print(f"     Type: {suggestion.metadata.source_type}")
                print(f"     Value: {suggestion.estimated_value:.0%}")
        
        print("\n✅ Direct agent test completed!")
        
    except ImportError as e:
        print(f"❌ Could not import agent components: {e}")
        print("   Make sure you're running from the correct directory")
    except Exception as e:
        print(f"❌ Direct agent test failed: {e}")


async def main():
    """Run all tests."""
    print("🚀 Source Discovery Agent Test Suite")
    print("=" * 60)
    print()
    
    # Test 1: Direct agent testing
    await test_direct_agent()
    print("\n" + "=" * 60 + "\n")
    
    # Test 2: API testing (requires running backend)
    await test_discovery_api()


if __name__ == "__main__":
    asyncio.run(main())
