#!/usr/bin/env python3
"""Add the correct FDA tool to the toolrow_tools_schema.json file."""

import json
from pathlib import Path

# The complete FDA tool schema from the npm package
fda_tool = {
    "name": "fda_info",
    "description": "Unified tool for FDA drug and medical device information lookup. Access drug labels, adverse events, regulatory information, recalls, shortages, and device registration data from the openFDA database.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["lookup_drug", "lookup_device"],
                "description": "The operation to perform: lookup_drug (search across multiple relevant fields, or search a specific field if field parameter is provided), lookup_device (search device registration and listing data)"
            },
            "search_term": {
                "type": "string",
                "description": "Search term to look for in the FDA database. Can be a drug name (generic or brand), manufacturer name, dosage form, marketing status, or any other searchable value. Supports wildcards (*), phrase matches (\"term\"), boolean operators (AND, OR), field combinations, and special modifiers (_missing_, _exists_)."
            },
            "search_type": {
                "type": "string",
                "enum": ["general", "label", "adverse_events", "recalls", "shortages", "device_registration", "device_pma", "device_510k", "device_udi", "device_recalls", "device_adverse_events", "device_classification"],
                "default": "general",
                "description": "Type of information to retrieve. For drugs: \"general\" for comprehensive search, \"label\" for prescribing information, \"adverse_events\" for safety data, \"recalls\" for drug recalls, \"shortages\" for supply shortages. For devices: \"device_registration\" for medical device registration and listing data, \"device_pma\" for Pre-Market Approval (PMA) decisions and submissions, \"device_510k\" for 510(k) premarket notification clearances, \"device_udi\" for Unique Device Identifier (UDI) database information, \"device_recalls\" for device recalls and enforcement reports, \"device_adverse_events\" for medical device adverse event reports, \"device_classification\" for device classification and regulatory information"
            },
            "limit": {
                "type": "integer",
                "default": 10,
                "minimum": 1,
                "maximum": 100,
                "description": "Maximum number of records to return (default: 10, max: 100). Note: openFDA supports paging through up to 26,000 total hits using skip/limit parameters.",
                "examples": [1, 5, 10, 25, 50, 100]
            }
        },
        "required": ["method", "search_term"],
        "additionalProperties": False
    }
}

# Load current schema
base_dir = Path("app/agents/source_discovery")
schema_file = base_dir / "toolrow_tools_schema.json"

with open(schema_file, 'r') as f:
    tools_data = json.load(f)

# Add FDA tool
tools_data.append(fda_tool)

# Write back
with open(schema_file, 'w') as f:
    json.dump(tools_data, f, indent=2)

print(f"Added FDA tool to {schema_file}")
print(f"Total tools now: {len(tools_data)}")

# Print tool names for verification
tool_names = [tool.get('name', 'UNKNOWN') for tool in tools_data]
print(f"All tool names: {', '.join(tool_names)}")