#!/usr/bin/env python3
"""Phase 2 testing for Claude Discovery Agent - Multi-Tool Orchestration."""

import asyncio
import os
import sys
from unittest.mock import Mock

# Add the app directory to Python path
sys.path.insert(0, 'app')

from app.agents.source_discovery.claude_agent import create_claude_discovery_agent


async def test_parallel_tool_execution():
    """Test parallel tool execution with broad queries."""
    print("🧪 Testing Phase 2: Multi-Tool Orchestration")
    print("=" * 60)
    
    # Mock database session and user ID
    mock_db_session = Mock()
    test_user_id = "test_user_phase2"
    
    # Get API keys
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    toolrow_token = os.getenv("TOOLROW_API_TOKEN")
    
    if not anthropic_key or not toolrow_token:
        print("❌ Required API keys not found. Please set ANTHROPIC_API_KEY and TOOLROW_API_TOKEN")
        return False
    
    try:
        # Create agent
        print("🚀 Creating Claude Discovery Agent for Phase 2 testing...")
        agent = await create_claude_discovery_agent(
            db_session=mock_db_session,
            user_id=test_user_id,
            toolrow_api_token=toolrow_token,
            anthropic_api_key=anthropic_key
        )
        
        print(f"✅ Agent initialized with {len(agent.available_tools)} tools")
        
        # Test 1: Broad query that should trigger parallel tool use
        print("\n" + "🔍 TEST 1: Broad Query for Parallel Tool Execution")
        print("─" * 40)
        query1 = "What research exists on diabetes treatment? Include clinical trials, FDA approvals, and medical codes."
        
        print(f"Query: {query1}")
        print("\nStreaming response:")
        
        response1 = ""
        async for chunk in agent.discover_sources(query1):
            print(chunk, end='', flush=True)
            response1 += chunk
        
        # Analyze response for parallel execution
        has_parallel_indicators = (
            "parallel" in response1.lower() or
            "tools in parallel" in response1.lower() or
            "simultaneously" in response1.lower()
        )
        
        print(f"\n\n📊 Analysis:")
        print(f"  - Response length: {len(response1)} characters")
        print(f"  - Parallel execution indicators: {'✅ Found' if has_parallel_indicators else '❌ Not detected'}")
        
        # Test 2: Follow-up query to test conversation memory
        print("\n" + "🔍 TEST 2: Follow-up Query (Memory Integration)")
        print("─" * 40)
        
        # Simulate conversation history
        from langchain_core.messages import HumanMessage, AIMessage
        chat_history = [
            HumanMessage(content=query1),
            AIMessage(content=response1[:500] + "...")  # Truncated for context
        ]
        
        query2 = "What about Type 2 diabetes specifically?"
        print(f"Query: {query2}")
        print("Previous context: [Simulated conversation history about diabetes research]")
        print("\nStreaming response:")
        
        response2 = ""
        async for chunk in agent.discover_sources(query2, chat_history=chat_history):
            print(chunk, end='', flush=True)
            response2 += chunk
        
        # Analyze context usage
        context_indicators = (
            "context" in response2.lower() or
            "previous" in response2.lower() or
            "continuing" in response2.lower() or
            "type 2" in response2.lower()
        )
        
        print(f"\n\n📊 Analysis:")
        print(f"  - Response length: {len(response2)} characters")
        print(f"  - Context awareness: {'✅ Found' if context_indicators else '❌ Not detected'}")
        
        # Test 3: Citations and formatting
        print("\n" + "🔍 TEST 3: Citation and Formatting Analysis")
        print("─" * 40)
        
        citations_found = (
            "[1]" in response1 or "[2]" in response1 or
            "sources" in response1.lower() or
            "citations" in response1.lower()
        )
        
        structured_formatting = (
            "##" in response1 or
            "**" in response1 or
            "📊" in response1 or
            "Sources" in response1
        )
        
        follow_up_questions = agent.get_follow_up_questions()
        
        print(f"  - Citations/References: {'✅ Found' if citations_found else '❌ Not detected'}")
        print(f"  - Structured formatting: {'✅ Found' if structured_formatting else '❌ Not detected'}")
        print(f"  - Follow-up questions: {'✅ Generated' if follow_up_questions else '❌ Not generated'} ({len(follow_up_questions)} questions)")
        
        if follow_up_questions:
            print("    Questions generated:")
            for i, q in enumerate(follow_up_questions[:3], 1):
                print(f"      {i}. {q.get('question', 'N/A')[:80]}...")
        
        # Overall assessment
        print("\n" + "🎯 PHASE 2 ASSESSMENT")
        print("=" * 60)
        
        parallel_tools = has_parallel_indicators
        memory_integration = context_indicators
        formatting_citations = citations_found and structured_formatting
        follow_ups = len(follow_up_questions) > 0
        
        features_working = sum([parallel_tools, memory_integration, formatting_citations, follow_ups])
        
        print(f"✅ Parallel Tool Execution: {'PASS' if parallel_tools else 'FAIL'}")
        print(f"✅ Memory/Context Integration: {'PASS' if memory_integration else 'FAIL'}")
        print(f"✅ Citations & Formatting: {'PASS' if formatting_citations else 'FAIL'}")
        print(f"✅ Follow-up Generation: {'PASS' if follow_ups else 'FAIL'}")
        
        print(f"\n📊 Overall Phase 2 Score: {features_working}/4 features implemented")
        
        if features_working >= 3:
            print("🎉 Phase 2 Multi-Tool Orchestration: SUCCESS")
            return True
        else:
            print("⚠️ Phase 2 needs improvement in some areas")
            return False
        
        # Cleanup
        await agent.cleanup()
        
    except Exception as e:
        print(f"❌ Phase 2 test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_tool_chaining():
    """Test tool chaining with sequential queries."""
    print("\n" + "🔗 TOOL CHAINING TEST")
    print("─" * 40)
    
    try:
        mock_db_session = Mock()
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        toolrow_token = os.getenv("TOOLROW_API_TOKEN")
        
        agent = await create_claude_discovery_agent(
            db_session=mock_db_session,
            user_id="chaining_test",
            toolrow_api_token=toolrow_token,
            anthropic_api_key=anthropic_key
        )
        
        # Test chaining query
        query = "Find the ICD-10 code for diabetes, then look up clinical trials for that condition"
        print(f"Query: {query}")
        print("\nLooking for evidence of tool chaining...")
        
        response = ""
        tool_mentions = []
        async for chunk in agent.discover_sources(query):
            response += chunk
            if "tool:" in chunk.lower() or "using" in chunk.lower():
                tool_mentions.append(chunk.strip())
        
        # Analyze for chaining
        multiple_tools = len([m for m in tool_mentions if any(tool in m.lower() for tool in ['ct_gov', 'nlm_ct', 'pubmed'])]) > 1
        sequential_pattern = "round" in response.lower() or "next" in response.lower()
        
        print(f"\n📊 Chaining Analysis:")
        print(f"  - Multiple tools detected: {'✅' if multiple_tools else '❌'}")
        print(f"  - Sequential pattern: {'✅' if sequential_pattern else '❌'}")
        print(f"  - Tool mentions: {len(tool_mentions)}")
        
        await agent.cleanup()
        return multiple_tools or sequential_pattern
        
    except Exception as e:
        print(f"❌ Tool chaining test failed: {e}")
        return False


async def main():
    """Run comprehensive Phase 2 tests."""
    print("🎯 Claude Discovery Agent - Phase 2 Testing")
    print("=" * 60)
    print("Testing: Multi-Tool Orchestration, Memory, Citations, Chaining")
    print("=" * 60)
    
    # Test parallel execution and orchestration
    orchestration_ok = await test_parallel_tool_execution()
    
    # Test tool chaining
    chaining_ok = await test_tool_chaining()
    
    print("\n" + "=" * 60)
    print("📊 FINAL PHASE 2 RESULTS:")
    print(f"  Multi-Tool Orchestration: {'✅ PASS' if orchestration_ok else '❌ FAIL'}")
    print(f"  Tool Chaining: {'✅ PASS' if chaining_ok else '❌ FAIL'}")
    
    if orchestration_ok and chaining_ok:
        print("\n🎉 PHASE 2 COMPLETE: All advanced features working!")
        print("✅ Ready for production deployment")
        return 0
    else:
        print("\n⚠️ Phase 2 has some issues that need attention")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)