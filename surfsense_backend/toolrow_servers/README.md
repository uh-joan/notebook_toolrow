# SurfSense Toolrow Servers

This directory contains the local Node.js implementations for Toolrow integration in SurfSense.

## Files

### `toolrow_mcp_server.js`
- **Purpose**: MCP (Model Context Protocol) server implementation
- **Used by**: `MCPClient` for tool discovery and execution
- **Configuration**: Referenced in `config/mcp_servers.json`
- **Features**: Fetches tools from Toolrow.ai API, converts to MCP format, handles JSON-RPC

### `toolrow_direct.js` 
- **Purpose**: Direct JSON-RPC handler for tool execution
- **Used by**: Python agent as subprocess fallback
- **Features**: Direct API calls to Toolrow.ai, parameter handling, result formatting

### `package.json`
- **Purpose**: Node.js dependencies and scripts
- **Dependencies**: `node-fetch` for HTTP requests to Toolrow.ai API

## Environment Variables

Both servers require:
- `TOOLROW_API_TOKEN`: API token for Toolrow.ai access

## Usage

The servers are automatically invoked by the SurfSense discovery agent:
1. MCP server runs as background process for tool discovery
2. Direct handler used for reliable tool execution via subprocess calls

## API Integration

Both servers integrate with the Toolrow.ai API:
- **Endpoint**: `https://toolrow.ai/v1/tools/schemas`
- **Authentication**: Bearer token via `TOOLROW_API_TOKEN`
- **Features**: Dynamic tool discovery, parameter validation, real-time execution
