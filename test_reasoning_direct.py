#!/usr/bin/env python3
"""
Direct test of the reasoning system to debug the error.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent / "surfsense_backend"
sys.path.insert(0, str(project_root))

from app.agents.source_discovery.agent import SourceDiscoveryAgent

async def test_reasoning_system():
    """Test the reasoning system directly."""
    print("🧪 Testing Reasoning System Directly...")
    
    # Create a mock session (we won't actually use DB for this test)
    class MockSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
    
    try:
        # Initialize the discovery agent
        print("📝 Initializing SourceDiscoveryAgent...")
        agent = SourceDiscoveryAgent(
            db_session=MockSession(),
            user_id="test-user-123",
            reasoning_enabled=True
        )
        
        print("🔧 Calling initialize...")
        await agent.initialize()
        
        print("✅ Agent initialized successfully")
        print(f"🧠 Reasoning enabled: {agent.reasoning_enabled}")
        print(f"🔧 Reasoning orchestrator: {agent.reasoning_orchestrator is not None}")
        
        # Test a simple query
        query = "diabetes clinical trials recruiting"
        print(f"🔍 Testing query: '{query}'")
        
        # Test the reasoning system directly
        if agent.reasoning_orchestrator:
            print("🧠 Testing reasoning orchestrator...")
            task = {
                "query": query,
                "chat_history": [],
                "user_id": "test-user-123"
            }
            
            try:
                result = await agent.reasoning_orchestrator.run(task)
                print(f"✅ Reasoning result: success={result.success}")
                print(f"📊 Evidence count: {len(result.evidence)}")
                print(f"📋 Trace events: {len(result.trace)}")
                
                if result.trace:
                    print("🔍 First few trace events:")
                    for i, event in enumerate(result.trace[:3]):
                        print(f"  {i+1}. {event.step}: {event.strategy} - {event.reason}")
                
            except Exception as e:
                print(f"❌ Reasoning orchestrator error: {e}")
                import traceback
                traceback.print_exc()
        
        else:
            print("❌ Reasoning orchestrator not initialized")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_reasoning_system())
