#!/usr/bin/env node

/**
 * ToolRow Direct JSON-RPC Handler
 * Handles direct JSON-RPC calls without MCP transport layer
 * Fetches tools dynamically from ToolRow.ai API
 */

// Configuration
const API_TOKEN = process.env.TOOLROW_API_TOKEN;
const API_BASE = process.env.TOOLROW_API_BASE || 'https://toolrow.ai';

// Cache for tools to avoid repeated API calls
let toolsCache = null;
let toolsCacheTimestamp = null;
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

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
      return [];
    }
  } catch (error) {
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

// Convert ToolRow tool to MCP tool format
function convertToMCPTool(toolrowTool) {
  const { tool_name, name, description, input_schema, examples } = toolrowTool;
  
  // Use tool_name if available, otherwise fall back to name
  const toolName = tool_name || name;
  
  // Check if we have the required fields
  if (!toolName || !description) {
    console.error('Missing required fields in tool:', toolrowTool);
    return null;
  }
  
  const mcpTool = {
    name: toolName,
    description: description,
    inputSchema: input_schema || {},
  };
  
  // Add examples if provided by the backend
  if (examples && examples.length > 0) {
    mcpTool.examples = examples;
  }
  
  return mcpTool;
}

// Execute tool via ToolRow API
async function executeToolViaAPI(toolName, args) {
  try {
    // Get the tools to find which MCP this tool belongs to
    const toolrowTools = await getTools();
    const toolInfo = toolrowTools.find(t => t.tool_name === toolName);
    
    if (!toolInfo) {
      throw new Error(`Tool not found: ${toolName}`);
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
      throw new Error(`ToolRow API error (${response.status}): ${errorText}`);
    }

    let result;
    try {
      result = await response.json();
    } catch (jsonError) {
      throw new Error(`Failed to parse JSON response: ${jsonError.message}. Response status: ${response.status}`);
    }

    // Ensure result exists before processing
    if (!result) {
      throw new Error('Received null or undefined response from ToolRow API');
    }

    if (result.success && result.result && result.result[0] && result.result[0].text) {
      // ToolRow API returns formatted text results
      const formattedText = result.result[0].text;
      
      return {
        type: 'text',
        text: formattedText,
      };
    } else if (result.success && result.data) {
      // Handle other response formats
      return {
        type: 'text',
        text: JSON.stringify(result.data, null, 2),
      };
    } else {
      return {
        type: 'text',
        text: `Tool execution failed: ${result.message || 'Unknown error'}`,
      };
    }
  } catch (error) {
    return {
      type: 'text',
      text: `Error executing tool ${toolName}: ${error.message}`,
    };
  }
}

// Handle JSON-RPC request
async function handleRequest(request) {
  try {
    const { method, params, id } = request;
    
    if (method === 'tools/list') {
      const toolrowTools = await getTools();
      const mcpTools = toolrowTools.map(convertToMCPTool).filter(tool => tool !== null);
      
      return {
        jsonrpc: '2.0',
        id: id,
        result: {
          tools: mcpTools
        }
      };
    }
    
    if (method === 'tools/call') {
      const { name, arguments: args } = params;
      
      // Execute the tool via ToolRow API
      const toolResult = await executeToolViaAPI(name, args);
      
      return {
        jsonrpc: '2.0',
        id: id,
        result: {
          content: [toolResult]
        }
      };
    }
    
    return {
      jsonrpc: '2.0',
      id: id,
      error: {
        code: -32601,
        message: `Method not found: ${method}`
      }
    };
    
  } catch (error) {
    return {
      jsonrpc: '2.0',
      id: request.id || null,
      error: {
        code: -32603,
        message: `Internal error: ${error.message}`
      }
    };
  }
}

// Read stdin and process request
async function main() {
  let input = '';
  
  process.stdin.setEncoding('utf8');
  
  for await (const chunk of process.stdin) {
    input += chunk;
  }
  
  if (input.trim()) {
    try {
      const request = JSON.parse(input.trim());
      const response = await handleRequest(request);
      console.log(JSON.stringify(response));
    } catch (error) {
      const errorResponse = {
        jsonrpc: '2.0',
        id: null,
        error: {
          code: -32700,
          message: `Parse error: ${error.message}`
        }
      };
      console.log(JSON.stringify(errorResponse));
    }
  }
}

main().catch(error => {
  process.exit(1);
});