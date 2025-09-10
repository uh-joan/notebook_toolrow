#!/usr/bin/env python3
"""
Simple test to check if the backend is running and MCP is working.
"""

import asyncio
import aiohttp
import json

async def test_backend_health():
    """Test if the backend is running."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('http://localhost:8000/health') as response:
                if response.status == 200:
                    print("✅ Backend is running")
                    return True
                else:
                    print(f"❌ Backend health check failed: {response.status}")
                    return False
    except Exception as e:
        print(f"❌ Backend connection failed: {e}")
        return False

async def test_research_endpoint():
    """Test the research endpoint with our obesity query."""
    try:
        async with aiohttp.ClientSession() as session:
            # Test data for research endpoint
            test_data = {
                "question": "What drugs are approved for obesity in the US?",
                "document_ids": [],
                "search_space_id": 1,
                "user_id": "test_user"
            }
            
            async with session.post(
                'http://localhost:8000/research/rag-then-mcp',
                json=test_data,
                headers={'Content-Type': 'application/json'}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    print("✅ Research endpoint working")
                    print(f"📊 Answer length: {len(result.get('answer', ''))}")
                    print(f"📚 Citations: {len(result.get('citations', []))}")
                    print(f"🔍 Coverage: {result.get('coverage', 0)}")
                    print(f"🌐 Live candidates: {len(result.get('live_candidates', []))}")
                    print(f"🔧 Tool invocations: {len(result.get('tool_invocations', []))}")
                    
                    # Check if we got live data
                    if result.get('tool_invocations'):
                        print("🎉 MCP tools were invoked!")
                        for inv in result.get('tool_invocations', []):
                            print(f"  - Tool: {inv.get('tool', 'unknown')}")
                            print(f"    Status: {inv.get('status', 'unknown')}")
                    else:
                        print("⚠️ No MCP tools were invoked")
                    
                    return True
                else:
                    print(f"❌ Research endpoint failed: {response.status}")
                    text = await response.text()
                    print(f"Error: {text}")
                    return False
    except Exception as e:
        print(f"❌ Research endpoint test failed: {e}")
        return False

async def main():
    """Run the simple tests."""
    print("🧪 Running Simple Backend Tests...\n")
    
    # Test 1: Backend health
    backend_ok = await test_backend_health()
    
    if backend_ok:
        # Test 2: Research endpoint with our obesity query
        await test_research_endpoint()
    else:
        print("❌ Backend not running - start it first with: cd surfsense_backend && uv run main.py")
    
    print("\n🎉 Simple test completed!")

if __name__ == "__main__":
    asyncio.run(main())
