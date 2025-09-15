"use client";

import { getAnnotationData } from "@llamaindex/chat-ui";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";

interface TerminalEvent {
	id: number;
	text: string;
	type: string;
	timestamp?: string;
}

interface Message {
	id: string;
	role: "user" | "assistant";
	content: string | Array<{type: string; text: string}>;
	data?: any;
}

function parseClaudeStreamingText(textContent: string): TerminalEvent[] {
	const events: TerminalEvent[] = [];
	let eventId = 1;
	
	// Split content by lines and process each line
	const lines = textContent.split('\n').filter(line => line.trim().length > 0);
	
	for (const line of lines) {
		const trimmedLine = line.trim();
		
		// Skip separator lines
		if (trimmedLine.match(/^[─-]+$/)) continue;
		
		// Parse different types of terminal events
		let eventType: string = "info";
		let eventText: string = trimmedLine;
		
		// Determine event type based on content
		if (trimmedLine.includes('🚀 Starting Claude-powered research')) {
			eventType = "info";
			eventText = trimmedLine;
		} else if (trimmedLine.includes('🔄 Connected to')) {
			eventType = "info";
			eventText = trimmedLine;
		} else if (trimmedLine.includes('🧠 Claude is analyzing')) {
			eventType = "reasoning";
			eventText = trimmedLine;
		} else if (trimmedLine.includes('🔧 **Using tool:')) {
			eventType = "info";
			eventText = trimmedLine.replace(/\*\*/g, '');
		} else if (trimmedLine.includes('🚀 **Executing') && trimmedLine.includes('tools in parallel')) {
			eventType = "info";
			eventText = trimmedLine.replace(/\*\*/g, '');
		} else if (trimmedLine.includes('🔍 **Executing research tools**')) {
			eventType = "info";
			eventText = "🔍 Executing research tools...";
		} else if (trimmedLine.includes('📊 **') && trimmedLine.includes('** results:')) {
			eventType = "info";
			const toolMatch = trimmedLine.match(/📊 \*\*([^*]+)\*\* results:/);
			eventText = toolMatch ? `📊 ${toolMatch[1]} results:` : trimmedLine.replace(/\*\*/g, '');
		} else if (trimmedLine.includes('✅') && !trimmedLine.includes('Error')) {
			eventType = "success";
			eventText = trimmedLine;
		} else if (trimmedLine.includes('❌') || trimmedLine.includes('Error')) {
			eventType = "warning";
			eventText = trimmedLine;
		} else if (trimmedLine.includes('🧠 **Claude is synthesizing')) {
			eventType = "reasoning";
			eventText = trimmedLine.replace(/\*\*/g, '');
		} else if (trimmedLine.includes('⚠️')) {
			eventType = "warning";
			eventText = trimmedLine;
		} else if (trimmedLine.includes('📄 **Generating formatted response')) {
			eventType = "info";
			eventText = trimmedLine.replace(/\*\*/g, '');
		} else if (trimmedLine.includes('✨ **Generating follow-up questions')) {
			eventType = "info";
			eventText = trimmedLine.replace(/\*\*/g, '');
		} else if (trimmedLine.match(/^\d+\./)) {
			// Skip numbered follow-up questions
			continue;
		} else if (trimmedLine.includes('Parameters:') || trimmedLine.includes('• **')) {
			eventType = "info";
			eventText = trimmedLine.replace(/\*\*/g, '').replace(/^• /, '');
		}
		
		// Only add meaningful terminal events, skip pure content
		if (eventText && (
			eventText.includes('🚀') || eventText.includes('🔄') || 
			eventText.includes('🧠') || eventText.includes('🔧') || 
			eventText.includes('🔍') || eventText.includes('📊') || 
			eventText.includes('✅') || eventText.includes('❌') || 
			eventText.includes('⚠️') || eventText.includes('📄') || 
			eventText.includes('✨') || eventText.includes('Parameters:')
		)) {
			events.push({
				id: eventId++,
				text: eventText,
				type: eventType,
				timestamp: new Date().toISOString()
			});
		}
	}
	
	// If no events were parsed, add a default event
	if (events.length === 0 && textContent.length > 0) {
		events.push({
			id: 1,
			text: "🔍 Claude Discovery Agent processing query...",
			type: "info",
			timestamp: new Date().toISOString()
		});
	}
	
	return events;
}

export default function DiscoverTerminal({ message, open = false }: { message: Message; open?: boolean }) {
	const [isCollapsed, setIsCollapsed] = useState(!open);
	const [isAutoCollapsing, setIsAutoCollapsing] = useState(false);
	const [hasAutoCollapsed, setHasAutoCollapsed] = useState(false);
	const bottomRef = useRef<HTMLDivElement>(null);

	if (!message || message.role !== "assistant") {
		return null;
	}

	// Check for terminal auto-collapse annotation
	const messageForCollapseCheck = {
		...message,
		content: typeof message.content === 'string' 
			? message.content 
			: Array.isArray(message.content) 
				? message.content.filter(part => part.type === 'text').map(part => part.text).join('')
				: ''
	};
	const collapseAnnotation = getAnnotationData(messageForCollapseCheck, "TERMINAL_COLLAPSE");
	
	// Auto-collapse terminal when completion annotation is received (only once)
	useEffect(() => {
		if (collapseAnnotation && collapseAnnotation.length > 0 && !hasAutoCollapsed) {
			// Check if should auto-collapse
			const shouldAutoCollapse = collapseAnnotation.some((annotation: any) => 
				annotation?.auto_collapse === true || annotation?.data?.auto_collapse === true
			);
			
			if (shouldAutoCollapse) {
				// Mark that auto-collapse has been triggered
				setHasAutoCollapsed(true);
				// Add a small delay for better UX (let user see the completion)
				setIsAutoCollapsing(true);
				setTimeout(() => {
					setIsCollapsed(true);
					setIsAutoCollapsing(false);
				}, 1500); // 1.5 second delay
			}
		}
	}, [collapseAnnotation, hasAutoCollapsed]);

	// Extract terminal events from live annotations (like researcher agent) and fallback to final data
	let events: TerminalEvent[] = [];
	
	// Get the text content from the message
	const textContent = typeof message.content === 'string' 
		? message.content 
		: Array.isArray(message.content) 
			? message.content.filter(part => part.type === 'text').map(part => part.text).join('')
			: '';
	
	// First, try to get live terminal events from annotations (real-time streaming)
	const messageForAnnotation = {
		...message,
		content: textContent
	};
	const liveEvents = getAnnotationData(messageForAnnotation, "TERMINAL_INFO") as TerminalEvent[] | null;
	
	if (liveEvents && liveEvents.length > 0) {
		// Use live events from streaming annotations
		events = liveEvents.map((event: any) => {
			// Handle nested event structure from backend
			const eventData = event.data || event;
			return {
				id: eventData.id || event.id || 0,
				text: eventData.text || event.text || "No text available",
				type: eventData.type || event.type || "info",
				timestamp: eventData.timestamp || event.timestamp
			};
		});
	} else if (textContent && textContent.length > 0) {
		// Parse Claude's streaming text content into terminal events
		events = parseClaudeStreamingText(textContent);
	} else if (message.data?.terminal_events && message.data.terminal_events.length > 0) {
		// Fallback to final terminal events from backend
		events = message.data.terminal_events.map((event: any) => ({
			id: event.id || 0,
			text: event.text || "",
			type: event.type || "info",
			timestamp: event.timestamp
		}));
	} else if (message.data) {
		// Enhanced fallback: generate events from Claude discovery result
		const result = message.data;
		let eventId = 1;

		// Initial query processing
		events.push({
			id: eventId++,
			text: `🚀 Claude Discovery Agent initialized for query: "${result.request?.query || result.query || 'discovery request'}"`,
			type: "info"
		});

		// Query analysis if available
		if (result.query_type || result.complexity) {
			events.push({
				id: eventId++,
				text: `🔍 Query analyzed: Type=${result.query_type || 'general'}, Complexity=${result.complexity || 'moderate'}`,
				type: "info"
			});
		}

		// Tool execution events
		if (result.tools_executed && Array.isArray(result.tools_executed)) {
			result.tools_executed.forEach((tool: any) => {
				events.push({
					id: eventId++,
					text: `🔧 Executing ${tool.name || tool}: ${tool.status || 'processing'}`,
					type: tool.status === 'success' ? 'success' : 'info'
				});
			});
		} else if (result.suggestions && result.suggestions.length > 0) {
			// Legacy format - extract tool usage from suggestions
			const tools = new Set();
			result.suggestions.forEach((suggestion: any) => {
				if (suggestion.metadata?.tags) {
					suggestion.metadata.tags.forEach((tag: string) => tools.add(tag));
				}
			});
			
			events.push({
				id: eventId++,
				text: `🎯 Claude selected ${tools.size} tools: [${Array.from(tools).join(", ")}]`,
				type: "info"
			});

			result.suggestions.forEach((suggestion: any) => {
				const toolName = suggestion.metadata?.tags?.[0] || "unknown_tool";
				const relevance = Math.round((suggestion.metadata?.relevance_score || 0) * 100);
				
				events.push({
					id: eventId++,
					text: `✅ ${toolName.replace("_", " ").toUpperCase()}: SUCCESS - ${relevance}% relevance`,
					type: "success"
				});
			});
		}

		// Performance metrics if available
		if (result.performance_metrics) {
			const metrics = result.performance_metrics;
			events.push({
				id: eventId++,
				text: `📊 Performance: ${metrics.total_duration_ms}ms, ${metrics.token_usage?.total || 0} tokens, ${metrics.tool_metrics?.tools_used || 0} tools`,
				type: "info"
			});
		}

		// Final completion
		events.push({
			id: eventId++,
			text: `🎉 Discovery completed: ${result.total_found || result.suggestions?.length || 0} sources found${result.processing_time_ms ? ` in ${result.processing_time_ms}ms` : ''}`,
			type: "success"
		});
	}

	// Show events count in terminal header

	// Always show terminal even if no events - for debugging
	if (events.length === 0) {
		// Add a default event so terminal shows up
		events = [{
			id: 1,
			text: "⚠️ No discovery events detected - check streaming or try a new query",
			type: "warning"
		}];
	}

	// Auto-scroll to bottom when events change
	useEffect(() => {
		if (bottomRef.current && !isCollapsed) {
			bottomRef.current.scrollTo({
				top: bottomRef.current.scrollHeight,
				behavior: "smooth",
			});
		}
	}, [events.length, isCollapsed]); // Trigger when event count changes

	return (
		<div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden font-mono text-sm shadow-lg mt-4">
			{/* Terminal Header */}
			<Button
				className="w-full bg-gray-800 px-4 py-2 flex items-center gap-2 border-b border-gray-700 cursor-pointer hover:bg-gray-750 transition-colors"
				onClick={() => setIsCollapsed(!isCollapsed)}
				variant="ghost"
				type="button"
			>
				<div className="flex gap-2">
					<div className="w-3 h-3 rounded-full bg-red-500"></div>
					<div className="w-3 h-3 rounded-full bg-yellow-500"></div>
					<div className="w-3 h-3 rounded-full bg-green-500"></div>
				</div>
				<div className="text-gray-400 text-xs ml-2 flex-1">
					Claude Discovery Terminal ({events.length} events)
					{isAutoCollapsing && (
						<span className="ml-2 text-yellow-400 animate-pulse">
							Auto-collapsing...
						</span>
					)}
				</div>
				<div className="text-gray-400">
					{isCollapsed ? (
						<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<title>Expand</title>
							<path
								strokeLinecap="round"
								strokeLinejoin="round"
								strokeWidth={2}
								d="M19 9l-7 7-7-7"
							/>
						</svg>
					) : (
						<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<title>Collapse</title>
							<path
								strokeLinecap="round"
								strokeLinejoin="round"
								strokeWidth={2}
								d="M5 15l7-7 7 7"
							/>
						</svg>
					)}
				</div>
			</Button>

			{/* Terminal Content */}
			{!isCollapsed && (
				<div ref={bottomRef} className="h-64 overflow-y-auto p-4 space-y-1 bg-gray-900">
					{events.map((event, index) => (
						<div key={`${event.id}-${index}`} className="text-green-400 flex items-start">
							<span className="text-blue-400 flex-shrink-0">$</span>
							<span className={`ml-2 flex-shrink-0 ${
								event.type === "info" ? "text-blue-400" : 
								event.type === "success" ? "text-green-400" :
								event.type === "reasoning" ? "text-purple-400" :
								event.type === "warning" ? "text-orange-400" :
								"text-gray-400"
							}`}>
								[{event.type}]
							</span>
							<span className="text-gray-300 ml-2 flex-1">
								{event.timestamp && (
									<span className="text-xs text-gray-500 mr-2">
										{new Date(event.timestamp).toLocaleTimeString()}
									</span>
								)}
								{event.text}
								{event.type !== "success" && event.type !== "warning" && !event.text.endsWith('...') && "..."}
							</span>
						</div>
					))}
					{events.length === 0 && (
						<div className="text-gray-500 italic">No discovery events to display...</div>
					)}
				</div>
			)}
		</div>
	);
}
