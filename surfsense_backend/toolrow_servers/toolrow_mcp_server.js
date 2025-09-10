#!/usr/bin/env node

/**
 * ToolRow MCP Server - Dynamic Implementation
 * Fetches tools dynamically from ToolRow.ai API
 * Based on the reference implementation in packages/toolrow-mcp-server/index.js
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { 
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';

// Configuration
const API_TOKEN = process.env.TOOLROW_API_TOKEN;
const API_BASE = process.env.TOOLROW_API_BASE || 'https://toolrow.ai';
 
// Cache for tools to avoid repeated API calls
let toolsCache = null;
let toolsCacheTimestamp = null;
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

// Create server instance with dynamic capabilities
let server = null;

// Fetch tools with schemas from ToolRow API
async function fetchToolsFromAPI() {
  try {
    const fetch = (await import('node-fetch')).default;
    
    const response = await fetch(
      `${API_BASE}/v1/tools/schemas?api_token=${API_TOKEN}`,
      {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      }
    );

    const result = await response.json();
    
    if (result.success && result.data && result.data.tools) {
      return result.data.tools;
    } else {
      // Silent error handling - don't log to console as it breaks MCP JSON protocol
      return [];
    }
  } catch (error) {
    // Silent error handling - don't log to console as it breaks MCP JSON protocol
    return [];
  }
}

// Get tools with caching
async function getTools() {
  const now = Date.now();
  
  // Return cached tools if still valid
  if (toolsCache && toolsCacheTimestamp && (now - toolsCacheTimestamp) < CACHE_TTL) {
    return toolsCache;
  }
  
  // Fetch fresh tools
  const tools = await fetchToolsFromAPI();
  toolsCache = tools;
  toolsCacheTimestamp = now;
  
  return tools;
}

// Convert ToolRow tool to MCP tool format - fully dynamic with error handling
function convertToMCPTool(toolrowTool) {
  const { tool_name, name, description, input_schema, examples } = toolrowTool;
  
  // Use tool_name if available, otherwise fall back to name
  const toolName = tool_name || name;
  
  // All ToolRow tools should have dynamic schemas from discovery service
  if (!input_schema) {
    throw new Error(`Missing input_schema for tool ${toolName}. Check ToolRow MCP discovery service.`);
  }
  
  const mcpTool = {
    name: toolName,
    description: description,
    inputSchema: input_schema,
  };
  
  // Add examples if provided by the backend
  if (examples && examples.length > 0) {
    mcpTool.examples = examples;
    // Removed console.log to prevent issues with Claude MCP processing
  }
  
  return mcpTool;
}

// Initialize server with dynamic tool capabilities
async function createServerWithDynamicCapabilities() {
  // Fetch tools to populate capabilities
  const toolrowTools = await fetchToolsFromAPI();
  const mcpTools = toolrowTools.map(convertToMCPTool);
  
  // Create tools capability object with actual tool schemas
  const toolsCapability = {};
  mcpTools.forEach(tool => {
    toolsCapability[tool.name] = {
      description: tool.description,
      inputSchema: tool.inputSchema
    };
  });

  server = new Server(
    {
      name: 'toolrow',
      version: '1.0.0',
    },
    {
      capabilities: {
        tools: toolsCapability,
      },
    }
  );
  
  return server;
}

// List tools handler - dynamically fetch from API
function setupRequestHandlers() {
server.setRequestHandler(ListToolsRequestSchema, async () => {
  try {
    const toolrowTools = await getTools();
    const mcpTools = toolrowTools.map(convertToMCPTool);
    
    return {
      tools: mcpTools,
    };
  } catch (error) {
    // Silent error handling - don't log to console as it breaks MCP JSON protocol
    return {
      tools: [],
    };
  }
});

// Call tool handler - route to appropriate ToolRow API endpoint
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    // Get the tools to find which MCP this tool belongs to
    const toolrowTools = await getTools();
    const toolInfo = toolrowTools.find(t => t.tool_name === name);
    
    if (!toolInfo) {
      throw new Error(`Tool not found: ${name}`);
    }
    
    const mcp_key = toolInfo.mcp_key;
    const tool_name = toolInfo.tool_name;
    
    // Validate and prepare arguments
    const requestBody = args || {};
    
    // Use dynamic import for node-fetch
    const fetch = (await import('node-fetch')).default;
    
    const response = await fetch(
      `${API_BASE}/v1/${mcp_key}/${tool_name}?api_token=${API_TOKEN}`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      }
    );

    // Check if response is ok
    if (!response.ok) {
      const errorText = await response.text();
      // Silent error handling - don't log to console as it breaks MCP JSON protocol
      throw new Error(`ToolRow API error (${response.status}): ${errorText}`);
    }

    let result;
    try {
      result = await response.json();
    } catch (jsonError) {
      // Silent error handling - don't log to console as it breaks MCP JSON protocol
      throw new Error(`Failed to parse JSON response: ${jsonError.message}. Response status: ${response.status}`);
    }

    // Ensure result exists before processing
    if (!result) {
      // Silent error handling - don't log to console as it breaks MCP JSON protocol
      throw new Error('Received null or undefined response from ToolRow API');
    }

    if (result.success && result.result && result.result[0] && result.result[0].text) {
      // ToolRow API returns formatted text results
      const formattedText = result.result[0].text;
      
      return {
        content: [
          {
            type: 'text',
            text: formattedText,
          },
        ],
      };
    } else if (result.success && result.data) {
      // Handle other response formats
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify(result.data, null, 2),
          },
        ],
      };
    } else {
      return {
        content: [
          {
            type: 'text',
            text: `Tool execution failed: ${result.message || 'Unknown error'}`,
          },
        ],
        isError: true,
      };
    }
  } catch (error) {
    return {
      content: [
        {
          type: 'text',
          text: `Error executing tool ${name}: ${error.message}`,
        },
      ],
      isError: true,
    };
  }
});
}

// Start the server
async function main() {
  // Create server with dynamic capabilities
  await createServerWithDynamicCapabilities();
  
  // Setup request handlers
  setupRequestHandlers();
  
  // Connect to transport
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // Silent error handling - don't log to console as it breaks MCP JSON protocol
}

main().catch((error) => {
  // Silent error handling - don't log to console as it breaks MCP JSON protocol
  process.exit(1);
});