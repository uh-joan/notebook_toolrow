#!/usr/bin/env python3
"""Test MCP server connection to Toolrow."""

import asyncio
import logging
import os
from app.toolrow_mcp.client import ToolrowMCPManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_mcp_connection():
    """Test MCP server connection."""
    # Set environment variables
    os.environ['TOOLROW_API_TOKEN'] = 'toolrow_ef3dedc98361680cb8d9e2b91a5f8c119152f63caa5ae7a87de6a568e20d2a82'
    os.environ['TOOLROW_API_BASE'] = 'https://toolrow.ai'

    try:
        logger.info("🔧 Testing Toolrow MCP Manager connection")

        # Initialize MCP manager
        manager = ToolrowMCPManager()

        # List available tools
        logger.info("📋 Listing available tools from MCP server")
        tools = await manager.list_available_tools()

        logger.info(f"✅ Found {len(tools)} tools via MCP:")
        for i, tool in enumerate(tools):
            logger.info(f"  {i+1}. {tool.get('name', 'UNKNOWN')} - {tool.get('description', 'No description')[:50]}...")

        # Test a specific tool call
        if tools:
            test_tool = next((t for t in tools if t.get('name') == 'fda_info'), None)
            if test_tool:
                logger.info("🧪 Testing fda_info tool call")
                result = await manager.invoke_toolrow_tool('fda_info', {
                    'dataset': 'drug_label',
                    'q': 'ozempic',
                    'limit': 1
                })
                logger.info(f"✅ FDA tool test result: {str(result)[:200]}...")
            else:
                logger.warning("⚠️ fda_info tool not found in available tools")

        logger.info("✅ MCP connection test completed")

    except Exception as e:
        logger.error(f"❌ MCP connection test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_mcp_connection())