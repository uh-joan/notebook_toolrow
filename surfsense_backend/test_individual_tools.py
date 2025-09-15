#!/usr/bin/env python3
"""Test each individual Toolrow MCP tool."""

import asyncio
import logging
import os
import json
from app.toolrow_mcp.client import ToolrowMCPManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_individual_tools():
    """Test each tool individually."""
    # Set environment variables
    os.environ['TOOLROW_API_TOKEN'] = 'toolrow_ef3dedc98361680cb8d9e2b91a5f8c119152f63caa5ae7a87de6a568e20d2a82'
    os.environ['TOOLROW_API_BASE'] = 'https://toolrow.ai'

    # Initialize MCP manager
    manager = ToolrowMCPManager()

    # Test cases for each tool
    test_cases = [
        {
            "name": "fda_info",
            "params": {
                "dataset": "drug_label",
                "q": "wegovy",
                "limit": 1
            },
            "description": "FDA drug information lookup"
        },
        {
            "name": "ct_gov_studies",
            "params": {
                "method": "search",
                "condition": "obesity",
                "filters": {"status": "recruiting"},
                "pageSize": 2
            },
            "description": "ClinicalTrials.gov search"
        },
        {
            "name": "nlm_ct_codes",
            "params": {
                "method": "icd-10-cm",
                "terms": "obesity",
                "limit": 3
            },
            "description": "NLM Clinical Tables (ICD codes)"
        },
        {
            "name": "pubmed_articles",
            "params": {
                "method": "search",
                "q": "semaglutide obesity",
                "limit": 2
            },
            "description": "PubMed literature search"
        },
        {
            "name": "sec-edgar",
            "params": {
                "method": "search_companies",
                "query": "Novo Nordisk",
                "limit": 1
            },
            "description": "SEC EDGAR company search"
        },
        {
            "name": "who-health",
            "params": {
                "method": "search_indicators",
                "keywords": "obesity",
                "top": 2
            },
            "description": "WHO Global Health Observatory"
        }
    ]

    results = {}

    for test_case in test_cases:
        tool_name = test_case["name"]
        params = test_case["params"]
        description = test_case["description"]

        logger.info(f"\n🧪 Testing {tool_name} ({description})")
        logger.info(f"📋 Parameters: {json.dumps(params, indent=2)}")

        try:
            result = await manager.invoke_toolrow_tool(tool_name, params, timeout_ms=15000)

            if isinstance(result, dict):
                result_preview = str(result)[:300] + "..." if len(str(result)) > 300 else str(result)
            else:
                result_preview = str(result)[:300] + "..." if len(str(result)) > 300 else str(result)

            logger.info(f"✅ {tool_name} SUCCESS")
            logger.info(f"📊 Result preview: {result_preview}")
            results[tool_name] = {"status": "SUCCESS", "preview": result_preview}

        except Exception as e:
            logger.error(f"❌ {tool_name} FAILED: {e}")
            results[tool_name] = {"status": "FAILED", "error": str(e)}

    # Summary
    logger.info("\n" + "="*50)
    logger.info("🎯 TOOL TEST SUMMARY")
    logger.info("="*50)

    success_count = 0
    for tool_name, result in results.items():
        status = result["status"]
        if status == "SUCCESS":
            success_count += 1
            logger.info(f"✅ {tool_name}: {status}")
        else:
            logger.info(f"❌ {tool_name}: {status} - {result.get('error', '')}")

    logger.info(f"\n🎉 {success_count}/{len(test_cases)} tools working properly")

    return results

if __name__ == "__main__":
    asyncio.run(test_individual_tools())