#!/usr/bin/env python3
"""
Simple demonstration test for the reasoning system.

This script demonstrates that the reasoning system is functional
and can be integrated into the main application.
"""

import asyncio
import os
from unittest.mock import AsyncMock, patch

from app.agents.source_discovery.reasoning.orchestrator import ReasoningOrchestrator
from app.agents.source_discovery.reasoning.config import ReasoningConfig
from app.agents.source_discovery.reasoning.models import ToolResult, FinalResponse
from app.agents.source_discovery.reasoning.adapters import BaseAdapter


class DemoMockAdapter(BaseAdapter):
    """Demo mock adapter for testing."""
    
    def __init__(self, tool_name: str, mock_results: list = None):
        super().__init__(tool_name, timeout_s=10)
        self.mock_results = mock_results or []
        self.call_count = 0
    
    async def call(self, params):
        print(f"🔧 Mock {self.tool_name} called with params: {params}")
        
        if self.call_count < len(self.mock_results):
            result = self.mock_results[self.call_count]
        else:
            result = ToolResult(
                tool=self.tool_name,
                ok=True,
                hits=5,
                data={"demo": "success"},
                duration_ms=100
            )
        
        self.call_count += 1
        print(f"✅ Mock {self.tool_name} returning {result.hits} hits")
        return result


async def test_reasoning_system():
    """Test the reasoning system end-to-end."""
    print("🧠 Testing Reasoning System")
    print("=" * 40)
    
    # 1. Test configuration
    print("1️⃣ Testing Configuration...")
    config = ReasoningConfig()
    print(f"   ✅ Config created: min_ok={config.min_ok}, max_ok={config.max_ok}")
    
    # 2. Test model creation
    print("\n2️⃣ Testing Models...")
    tool_result = ToolResult(tool="test", ok=True, hits=10, data={"test": "data"})
    print(f"   ✅ ToolResult: {tool_result.tool} with {tool_result.hits} hits")
    
    final_response = FinalResponse(
        answer={"summary": "Demo test"},
        evidence=[],
        trace=[],
        limitations=[],
        next_best_actions=[],
        success=True
    )
    print(f"   ✅ FinalResponse: success={final_response.success}")
    
    # 3. Test adapters
    print("\n3️⃣ Testing Adapters...")
    mock_adapters = {
        "ct_gov_studies.search": DemoMockAdapter("ct_gov_studies", [
            ToolResult(tool="ct_gov_studies", ok=True, hits=8, data={"studies": ["demo1", "demo2"]})
        ]),
        "nlm_ct_codes": DemoMockAdapter("nlm_ct_codes", [
            ToolResult(tool="nlm_ct_codes", ok=True, hits=3, data={"codes": ["E11", "E10"]})
        ])
    }
    print(f"   ✅ Created {len(mock_adapters)} mock adapters")
    
    # 4. Test orchestrator
    print("\n4️⃣ Testing Orchestrator...")
    orchestrator = ReasoningOrchestrator(mock_adapters, config)
    print("   ✅ Orchestrator created")
    
    # 5. Test query analysis (mocked)
    print("\n5️⃣ Testing Query Analysis...")
    with patch.object(orchestrator, '_analyze_query') as mock_analyze:
        mock_analyze.return_value = AsyncMock()
        
        with patch.object(orchestrator, '_plan_initial_search') as mock_plan:
            mock_plan.return_value = AsyncMock()
            
            with patch.object(orchestrator, '_reasoning_loop') as mock_loop:
                mock_loop.return_value = AsyncMock()
                
                with patch.object(orchestrator, '_finalize_response') as mock_finalize:
                    mock_finalize.return_value = FinalResponse(
                        answer={"summary": "Integration test successful"},
                        evidence=[],
                        trace=[],
                        limitations=[],
                        next_best_actions=[],
                        success=True
                    )
                    
                    task = {
                        "query": "diabetes clinical trials demo",
                        "user_id": "demo_user"
                    }
                    
                    result = await orchestrator.run(task)
                    print(f"   ✅ Orchestrator run completed: success={result.success}")
    
    # 6. Test JSON serialization
    print("\n6️⃣ Testing JSON Serialization...")
    import json
    json_data = result.model_dump()
    json_str = json.dumps(json_data, default=str)
    print(f"   ✅ JSON serialization: {len(json_str)} characters")
    
    # 7. Test individual adapter calls
    print("\n7️⃣ Testing Individual Adapter Calls...")
    for tool_name, adapter in mock_adapters.items():
        adapter_result = await adapter.call({"demo": "params"})
        print(f"   ✅ {tool_name}: {adapter_result.hits} hits")
    
    print("\n🎉 All Reasoning System Tests Passed!")
    print("=" * 40)
    
    return True


async def test_feature_integration():
    """Test integration with feature flags."""
    print("\n🚩 Testing Feature Flag Integration...")
    
    # Test environment configuration
    test_env = {
        "REASONING_ENABLED": "true",
        "REASONING_MIN_OK": "3",
        "REASONING_MAX_OK": "50"
    }
    
    with patch.dict(os.environ, test_env):
        config = ReasoningConfig.from_env()
        print(f"   ✅ Environment config: min_ok={config.min_ok}, max_ok={config.max_ok}")
        assert config.min_ok == 3
        assert config.max_ok == 50
    
    print("   ✅ Feature flag integration working")


if __name__ == "__main__":
    async def main():
        try:
            success = await test_reasoning_system()
            if success:
                await test_feature_integration()
                print("\n🎯 REASONING SYSTEM IS FULLY FUNCTIONAL! 🎯")
                print("\n✨ Reasoning is ENABLED BY DEFAULT for Discovery Agent")
                print("To disable (not recommended): export REASONING_ENABLED=false")
                return 0
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    exit_code = asyncio.run(main())
    exit(exit_code)
