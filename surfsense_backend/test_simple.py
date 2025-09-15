#!/usr/bin/env python3
"""Simple test for Claude tools mapping only."""

import asyncio
import json
import os
import sys


async def test_toolrow_direct():
    """Test direct Toolrow call."""
    print("🔧 Testing Toolrow direct call...")
    
    # Check environment
    token = os.getenv("TOOLROW_API_TOKEN")
    if not token:
        print("❌ TOOLROW_API_TOKEN not found")
        return False
    
    print("✅ Found TOOLROW_API_TOKEN")
    
    try:
        # Test the toolrow direct script
        import subprocess
        
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {}
        }
        
        env = os.environ.copy()
        env["TOOLROW_API_TOKEN"] = token
        
        cmd = ["node", "toolrow_servers/toolrow_direct.js"]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        
        request_json = json.dumps(request) + "\n"
        stdout, stderr = await process.communicate(input=request_json.encode())
        
        if process.returncode == 0 and stdout:
            response = json.loads(stdout.decode().strip())
            if "result" in response and "tools" in response["result"]:
                tools = response["result"]["tools"]
                print(f"✅ Found {len(tools)} tools from Toolrow")
                
                for tool in tools[:3]:  # Show first 3 tools
                    name = tool.get("name", "unknown")
                    desc = tool.get("description", "No description")
                    print(f"  - {name}: {desc[:60]}...")
                
                return True
        
        print(f"❌ Toolrow call failed: {stderr.decode()}")
        return False
        
    except Exception as e:
        print(f"❌ Error testing Toolrow: {e}")
        return False


async def test_anthropic_basic():
    """Test basic Anthropic API connection."""
    print("\n🤖 Testing Anthropic API...")
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not found")
        return False
    
    print("✅ Found ANTHROPIC_API_KEY")
    
    try:
        import anthropic
        
        client = anthropic.AsyncAnthropic(api_key=api_key)
        
        # Simple test message
        response = await client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[{"role": "user", "content": "Hello! Just testing the API."}]
        )
        
        if response.content and len(response.content) > 0:
            print("✅ Claude API working!")
            print(f"Response: {response.content[0].text[:50]}...")
            return True
        else:
            print("❌ Empty response from Claude")
            return False
            
    except anthropic.AuthenticationError:
        print("❌ Invalid ANTHROPIC_API_KEY")
        return False
    except Exception as e:
        print(f"❌ Error testing Anthropic: {e}")
        return False


async def main():
    """Run basic tests."""
    print("🎯 Basic Claude Discovery Agent Tests")
    print("=" * 50)
    
    # Test Anthropic API first
    anthropic_ok = await test_anthropic_basic()
    
    # Test Toolrow if token available
    toolrow_ok = await test_toolrow_direct()
    
    print("\n" + "=" * 50)
    print("📊 Test Results:")
    print(f"  Anthropic API: {'✅ Working' if anthropic_ok else '❌ Failed'}")
    print(f"  Toolrow API:   {'✅ Working' if toolrow_ok else '❌ Failed'}")
    
    if anthropic_ok:
        print("\n🎉 Claude Discovery Agent prerequisites are ready!")
        if not toolrow_ok:
            print("⚠️ Note: Will use fallback tools without Toolrow")
        return 0
    else:
        print("\n❌ Claude API is required for the discovery agent")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)