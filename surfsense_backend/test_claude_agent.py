#!/usr/bin/env python3
"""Simple test script for Claude Discovery Agent."""

import asyncio
import os
import sys
from unittest.mock import Mock

# Add the app directory to Python path
sys.path.insert(0, 'app')

from app.agents.source_discovery.claude_agent import create_claude_discovery_agent


async def test_claude_agent_basic():
    """Test basic Claude agent functionality."""
    print("🧪 Testing Claude Discovery Agent...")
    
    # Mock database session and user ID
    mock_db_session = Mock()
    test_user_id = "test_user_123"
    
    # Check for API keys
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    toolrow_token = os.getenv("TOOLROW_API_TOKEN")
    
    if not anthropic_key:
        print("❌ ANTHROPIC_API_KEY not found. Please set it in environment or .env file")
        print("   You can get one from: https://console.anthropic.com/")
        return False
    
    print("✅ Found ANTHROPIC_API_KEY")
    
    if not toolrow_token:
        print("⚠️ TOOLROW_API_TOKEN not found. Will use fallback tools only")
        print("   You can get one from: https://toolrow.ai/")
    else:
        print("✅ Found TOOLROW_API_TOKEN")
    
    try:
        # Create and initialize agent
        print("\n🚀 Creating Claude Discovery Agent...")
        agent = await create_claude_discovery_agent(
            db_session=mock_db_session,
            user_id=test_user_id,
            toolrow_api_token=toolrow_token,
            anthropic_api_key=anthropic_key
        )
        print("✅ Claude Discovery Agent created successfully")
        
        # Test available tools
        print(f"📊 Available tools: {len(agent.available_tools)}")
        for tool in agent.available_tools:
            print(f"  - {tool['name']}: {tool['description'][:60]}...")
        
        # Test a simple query
        print("\n🔍 Testing research query: 'What are clinical trials for diabetes?'")
        print("─" * 60)
        
        response_chunks = []
        async for chunk in agent.discover_sources("What are clinical trials for diabetes?"):
            print(chunk, end='', flush=True)
            response_chunks.append(chunk)
        
        print("\n" + "─" * 60)
        print("✅ Test completed successfully")
        
        # Cleanup
        await agent.cleanup()
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_claude_agent_tools_only():
    """Test just the tools mapping without full query."""
    print("\n🔧 Testing tool mapping only...")
    
    try:
        from app.agents.source_discovery.claude_tools import ClaudeToolMapper, ClaudeToolRegistry
        
        # Test fallback tools
        fallback_tools = ClaudeToolRegistry.get_fallback_tools()
        print(f"📊 Fallback tools available: {len(fallback_tools)}")
        
        # Test tool mapper if token available
        toolrow_token = os.getenv("TOOLROW_API_TOKEN")
        if toolrow_token:
            print("🔄 Testing Toolrow tool mapping...")
            mapper = ClaudeToolMapper(toolrow_token)
            tools = await mapper.get_claude_tools()
            print(f"📊 Toolrow tools loaded: {len(tools)}")
            
            for tool in tools[:3]:  # Show first 3
                print(f"  - {tool['name']}: {tool['description'][:60]}...")
        else:
            print("⚠️ No TOOLROW_API_TOKEN - using fallback tools only")
        
        print("✅ Tool mapping test completed")
        return True
        
    except Exception as e:
        print(f"❌ Tool mapping test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("🎯 Claude Discovery Agent Test Suite")
    print("=" * 50)
    
    # Test 1: Tools mapping
    tools_ok = await test_claude_agent_tools_only()
    
    # Test 2: Full agent (only if tools work)
    if tools_ok:
        agent_ok = await test_claude_agent_basic()
    else:
        print("⚠️ Skipping full agent test due to tools mapping failure")
        agent_ok = False
    
    print("\n" + "=" * 50)
    if tools_ok and agent_ok:
        print("🎉 All tests passed! Claude Discovery Agent is ready")
        return 0
    else:
        print("❌ Some tests failed. Check the errors above")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)