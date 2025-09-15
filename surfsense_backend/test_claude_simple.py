#!/usr/bin/env python3
"""Simple test of Claude Discovery Agent Phase 2 features."""

import asyncio
import os
import anthropic
from langchain_core.messages import HumanMessage, AIMessage


async def test_claude_direct():
    """Test Claude's tool use capabilities directly."""
    print("🧪 Testing Claude Tool Use Directly")
    print("=" * 50)
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY required")
        return False
    
    client = anthropic.AsyncAnthropic(api_key=api_key)
    
    # Define a simple tool
    tools = [
        {
            "name": "search_database",
            "description": "Search a medical database for information",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "database": {"type": "string", "description": "Database to search"}
                },
                "required": ["query", "database"]
            }
        },
        {
            "name": "get_codes",
            "description": "Get medical codes for conditions",
            "input_schema": {
                "type": "object", 
                "properties": {
                    "condition": {"type": "string", "description": "Medical condition"}
                },
                "required": ["condition"]
            }
        }
    ]
    
    # Test query that should trigger multiple tools
    query = "Find information about diabetes treatment including clinical trials and medical codes"
    
    print(f"Query: {query}")
    print("\nClaude Response:")
    
    try:
        response = await client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=2000,
            temperature=0.1,
            messages=[{"role": "user", "content": query}],
            tools=tools
        )
        
        print(f"\n📊 Response Analysis:")
        print(f"  - Content blocks: {len(response.content)}")
        
        tool_uses = []
        text_content = ""
        
        for block in response.content:
            if block.type == "text":
                text_content += block.text
                print(f"  - Text: {block.text[:100]}...")
            elif block.type == "tool_use":
                tool_uses.append(block)
                print(f"  - Tool use: {block.name} with {block.input}")
        
        print(f"\n✅ Results:")
        print(f"  - Tools requested: {len(tool_uses)}")
        print(f"  - Text response length: {len(text_content)}")
        print(f"  - Parallel tool use: {'Yes' if len(tool_uses) > 1 else 'No'}")
        
        return len(tool_uses) > 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


async def test_conversation_memory():
    """Test conversation memory handling."""
    print("\n🧠 Testing Conversation Memory")
    print("=" * 50)
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY required")
        return False
    
    client = anthropic.AsyncAnthropic(api_key=api_key)
    
    # Simulate conversation history
    messages = [
        {"role": "user", "content": "Tell me about diabetes research"},
        {"role": "assistant", "content": "Diabetes research encompasses clinical trials, treatment studies, and epidemiological research. There are ongoing studies on Type 1, Type 2, and gestational diabetes."},
        {"role": "user", "content": "What about Type 2 specifically?"}
    ]
    
    print("Conversation context:")
    for i, msg in enumerate(messages):
        print(f"  {i+1}. {msg['role']}: {msg['content'][:60]}...")
    
    try:
        response = await client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1000,
            temperature=0.1,
            messages=messages
        )
        
        response_text = response.content[0].text if response.content else ""
        
        # Check for context awareness
        context_indicators = [
            "type 2" in response_text.lower(),
            "specifically" in response_text.lower(),
            any(word in response_text.lower() for word in ["previously", "mentioned", "earlier", "as discussed"])
        ]
        
        print(f"\n✅ Memory Test Results:")
        print(f"  - Response length: {len(response_text)}")
        print(f"  - Type 2 focus: {'Yes' if context_indicators[0] else 'No'}")
        print(f"  - Context awareness: {'Yes' if any(context_indicators) else 'No'}")
        print(f"  - Response preview: {response_text[:200]}...")
        
        return any(context_indicators)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


async def main():
    """Run simplified Phase 2 tests."""
    print("🎯 Simplified Phase 2 Testing")
    print("=" * 60)
    
    # Test Claude's tool capabilities
    tool_use_ok = await test_claude_direct()
    
    # Test conversation memory
    memory_ok = await test_conversation_memory()
    
    print("\n" + "=" * 60)
    print("📊 SIMPLIFIED PHASE 2 RESULTS:")
    print(f"  Tool Use Capability: {'✅ Working' if tool_use_ok else '❌ Issues'}")
    print(f"  Conversation Memory: {'✅ Working' if memory_ok else '❌ Issues'}")
    
    if tool_use_ok and memory_ok:
        print("\n🎉 Core Claude capabilities confirmed!")
        print("✅ Phase 2 foundation is solid")
        return 0
    else:
        print("\n⚠️ Some core capabilities need attention")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)