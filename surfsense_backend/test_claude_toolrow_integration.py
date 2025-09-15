#!/usr/bin/env python3
"""
Simple test to understand Claude API + Toolrow integration
Step-by-step approach to identify the correct pattern
"""

import asyncio
import json
import logging
import os
import subprocess
from typing import Dict, List, Any

import anthropic

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ClaudeToolrowTest:
    """Simple test class to explore Claude + Toolrow integration patterns"""
    
    def __init__(self):
        self.anthropic_client = None
        self.toolrow_token = os.environ.get("TOOLROW_API_TOKEN")
        
    async def step1_get_toolrow_tools_direct(self) -> List[Dict[str, Any]]:
        """Step 1: Get Toolrow tools using hardcoded simplified schema"""
        logger.info("🔧 STEP 1: Using simplified hardcoded schema from toolrow_tools_schema.json")
        
        try:
            schema_file = "app/agents/source_discovery/toolrow_tools_schema.json"
            with open(schema_file, 'r') as f:
                tools_data = json.load(f)
            
            logger.info(f"✅ Found {len(tools_data)} tools via simplified hardcoded schema")
            
            for i, tool in enumerate(tools_data[:2]):  # Show first 2 tools
                logger.info(f"  Tool {i}: {tool.get('name')} - {tool.get('description', '')[:50]}...")
                logger.info(f"  Schema keys: {list(tool.get('input_schema', {}).keys())}")
            
            return tools_data
            
        except Exception as e:
            logger.error(f"❌ Simplified schema load failed: {e}")
            return []
    
    def step2_convert_tools_for_claude(self, toolrow_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Step 2: Convert Toolrow tools to Claude API format"""
        logger.info("🔧 STEP 2: Converting Toolrow tools to Claude API format")
        
        claude_tools = []
        for i, tool in enumerate(toolrow_tools):
            # Get the input schema (simplified schema uses "input_schema" not "inputSchema")
            input_schema = tool.get("input_schema", {})
            
            # Log the original tool structure
            if i == 0:
                logger.info(f"  Original tool structure: {json.dumps(tool, indent=2)}")
            
            # Convert to Claude format - try different approaches
            claude_tool_v1 = {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "input_schema": input_schema if input_schema else {}  # Direct mapping
            }
            
            claude_tool_v2 = {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": input_schema
                }
            }
            
            claude_tool_v3 = {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "type": "custom",
                "custom": {
                    "input_schema": input_schema
                }
            }
            
            # Use the custom format that Claude expects
            claude_tool_custom = {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "type": "custom",
                "custom": {
                    "input_schema": input_schema
                }
            }
            
            claude_tools.append(claude_tool_custom)
            
            if i == 0:
                logger.info(f"  Converted to Claude format: {json.dumps(claude_tool_custom, indent=2)}")
        
        logger.info(f"✅ Converted {len(claude_tools)} tools to Claude format")
        return claude_tools
    
    async def step3_test_claude_api_call(self, claude_tools: List[Dict[str, Any]]):
        """Step 3: Test different ways to call Claude API with tools"""
        logger.info("🔧 STEP 3: Testing Claude API with converted tools")
        
        # Initialize Claude client
        claude_key = os.environ.get("ANTHROPIC_API_KEY")
        if not claude_key:
            logger.error("❌ ANTHROPIC_API_KEY not found in environment")
            return
        
        self.anthropic_client = anthropic.AsyncAnthropic(api_key=claude_key)
        
        # Test different approaches
        approaches = [
            ("Simple tools parameter", lambda tools: {"tools": tools}),
            ("Function calling format", lambda tools: {"tools": [self._convert_to_function_format(t) for t in tools]}),
            ("Custom tool format", lambda tools: {"tools": [self._convert_to_custom_format(t) for t in tools]})
        ]
        
        for approach_name, converter in approaches:
            logger.info(f"  Testing approach: {approach_name}")
            
            try:
                tools_param = converter(claude_tools[:1])  # Test with just one tool first
                
                logger.info(f"  Tool format being sent: {json.dumps(tools_param['tools'][0], indent=2)}")
                
                response = await self.anthropic_client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=100,
                    messages=[
                        {"role": "user", "content": "Hello, what tools do you have available?"}
                    ],
                    **tools_param
                )
                
                logger.info(f"  ✅ {approach_name}: SUCCESS - Claude accepted the tools")
                logger.info(f"  Response: {response.content[0].text[:100]}...")
                
                return True
                
            except Exception as e:
                logger.error(f"  ❌ {approach_name}: FAILED - {str(e)}")
                continue
        
        return False
    
    def _convert_to_function_format(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """Convert tool to function calling format"""
        return {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool.get("input_schema", {})
            }
        }
    
    def _convert_to_custom_format(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """Convert tool to custom format"""
        return {
            "name": tool["name"],
            "description": tool["description"],
            "type": "custom",
            "custom": {
                "input_schema": tool.get("input_schema", {})
            }
        }
    
    async def step4_test_tool_execution(self, claude_tools: List[Dict[str, Any]]):
        """Step 4: Test actually calling a tool through Claude"""
        logger.info("🔧 STEP 4: Testing tool execution through Claude")
        
        if not self.anthropic_client:
            logger.error("❌ Claude client not initialized")
            return
        
        # Find a simple tool to test with
        test_tool = None
        for tool in claude_tools:
            if tool["name"] in ["nlm_ct_codes", "ct_gov_studies"]:  # Common tools
                test_tool = tool
                break
        
        if not test_tool:
            logger.error("❌ No suitable test tool found")
            return
        
        logger.info(f"  Testing with tool: {test_tool['name']}")
        
        try:
            response = await self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                messages=[
                    {"role": "user", "content": "Use the nlm_ct_codes tool to find ICD-10 codes for diabetes"}
                ],
                tools=[test_tool]
            )
            
            logger.info(f"✅ Tool execution test completed")
            logger.info(f"Response: {response.content}")
            
        except Exception as e:
            logger.error(f"❌ Tool execution failed: {e}")
    
    async def run_complete_test(self):
        """Run the complete test sequence"""
        logger.info("🚀 Starting Claude + Toolrow integration test")
        
        # Step 1: Get tools from Toolrow
        toolrow_tools = await self.step1_get_toolrow_tools_direct()
        if not toolrow_tools:
            logger.error("❌ Cannot proceed without Toolrow tools")
            return
        
        # Step 2: Convert tools for Claude
        claude_tools = self.step2_convert_tools_for_claude(toolrow_tools)
        
        # Step 3: Test Claude API acceptance
        api_success = await self.step3_test_claude_api_call(claude_tools)
        if not api_success:
            logger.error("❌ Cannot proceed - Claude API rejected all tool formats")
            return
        
        # Step 4: Test tool execution
        await self.step4_test_tool_execution(claude_tools)
        
        logger.info("🎉 Test sequence completed!")

async def main():
    """Main test function"""
    test = ClaudeToolrowTest()
    await test.run_complete_test()

if __name__ == "__main__":
    asyncio.run(main())