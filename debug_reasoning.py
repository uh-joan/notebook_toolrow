#!/usr/bin/env python3
"""
Debug script to identify the specific error in reasoning system
"""

import asyncio
import sys
import os
from pathlib import Path
import traceback

# Add the project root to the path
project_root = Path(__file__).parent / "surfsense_backend"
sys.path.insert(0, str(project_root))

from app.agents.source_discovery.reasoning.orchestrator import ReasoningOrchestrator
from app.agents.source_discovery.reasoning.config import ReasoningConfig
from app.agents.source_discovery.reasoning.adapters import create_adapters

async def debug_reasoning():
    """Debug the reasoning system step by step."""
    print("🔍 Debugging Reasoning System...")
    
    try:
        # Step 1: Test config
        print("\n1️⃣ Testing ReasoningConfig...")
        config = ReasoningConfig()
        print(f"✅ Config created: timeout={config.total_timeout_s}s, max_rounds={config.max_rounds}")
        
        # Step 2: Test adapters
        print("\n2️⃣ Testing Adapters...")
        toolrow_token = 'toolrow_ef3dedc98361680cb8d9e2b91a5f8c119152f63caa5ae7a87de6a568e20d2a82'
        adapters = create_adapters(toolrow_token)
        print(f"✅ Adapters created: {len(adapters)} adapters")
        print(f"   Adapter keys: {list(adapters.keys())}")
        
        # Step 3: Test orchestrator creation
        print("\n3️⃣ Testing Orchestrator...")
        orchestrator = ReasoningOrchestrator(adapters, config)
        print("✅ Orchestrator created successfully")
        
        # Step 4: Test a simple task
        print("\n4️⃣ Testing Simple Task...")
        task = {
            "query": "diabetes codes",
            "chat_history": [],
            "user_id": "test-user"
        }
        
        print(f"🔍 Running task: {task['query']}")
        result = await orchestrator.run(task)
        print(f"✅ Task completed: success={result.success}")
        print(f"📊 Evidence count: {len(result.evidence)}")
        print(f"📋 Trace events: {len(result.trace)}")
        
        if not result.success:
            print("❌ Task failed - checking trace for details...")
            for i, event in enumerate(result.trace):
                print(f"   {i+1}. {event.step}: {event.strategy} - {event.reason}")
                if event.outcome:
                    print(f"      Outcome: {event.outcome}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\n🔍 Full traceback:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_reasoning())
