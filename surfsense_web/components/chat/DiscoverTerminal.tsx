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

export default function DiscoverTerminal({ message, open = false }: { message: Message; open?: boolean }) {
	const [isCollapsed, setIsCollapsed] = useState(!open);
	const [isAutoCollapsing, setIsAutoCollapsing] = useState(false);
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
	
	// Auto-collapse terminal when completion annotation is received
	useEffect(() => {
		if (collapseAnnotation && collapseAnnotation.length > 0) {
			// Check if should auto-collapse
			const shouldAutoCollapse = collapseAnnotation.some((annotation: any) => 
				annotation?.auto_collapse === true || annotation?.data?.auto_collapse === true
			);
			
			if (shouldAutoCollapse) {
				// Add a small delay for better UX (let user see the completion)
				setIsAutoCollapsing(true);
				setTimeout(() => {
					setIsCollapsed(true);
					setIsAutoCollapsing(false);
				}, 1500); // 1.5 second delay
			}
		}
	}, [collapseAnnotation]);

	// Extract terminal events from live annotations (like researcher agent) and fallback to final data
	let events: TerminalEvent[] = [];
	
	// First, try to get live terminal events from annotations (real-time streaming)
	// Convert message to the format expected by getAnnotationData
	const messageForAnnotation = {
		...message,
		content: typeof message.content === 'string' 
			? message.content 
			: Array.isArray(message.content) 
				? message.content.filter(part => part.type === 'text').map(part => part.text).join('')
				: ''
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
	} else if (message.data?.terminal_events && message.data.terminal_events.length > 0) {
		// Fallback to final terminal events from backend
		events = message.data.terminal_events.map((event: any) => ({
			id: event.id || 0,
			text: event.text || "",
			type: event.type || "info",
			timestamp: event.timestamp
		}));
	} else if (message.data) {
		// Fallback: generate events from discovery result
		const result = message.data;
		let eventId = 1;

		events.push({
			id: eventId++,
			text: `Starting source discovery for: "${result.request?.query || 'unknown query'}"`,
			type: "info"
		});

		if (result.reasoning_steps && result.reasoning_steps.length > 0) {
			events.push({
				id: eventId++,
				text: `🧠 Sequential reasoning completed with ${result.reasoning_steps.length} steps`,
				type: "info"
			});
		}

		if (result.suggestions && result.suggestions.length > 0) {
			const tools = new Set();
			result.suggestions.forEach((suggestion: any) => {
				if (suggestion.metadata?.tags) {
					suggestion.metadata.tags.forEach((tag: string) => tools.add(tag));
				}
			});
			
			events.push({
				id: eventId++,
				text: `🎯 Selected ${tools.size} tools: [${Array.from(tools).join(", ")}]`,
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

		events.push({
			id: eventId++,
			text: `📊 Discovery completed: ${result.total_found || 0} sources found in ${result.processing_time_ms || 0}ms`,
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
					Discovery Process Terminal ({events.length} events)
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
						<div key={`${event.id}-${index}`} className="text-green-400">
							<span className="text-blue-400">$</span>
							<span className={`ml-2 ${
								event.type === "info" ? "text-yellow-400" : 
								event.type === "success" ? "text-green-400" :
								event.type === "reasoning" ? "text-purple-400" :
								"text-gray-400"
							}`}>
								[{event.type}]
							</span>
							<span className="text-gray-300 ml-4 mt-1 pl-2 border-l-2 border-gray-600">
								{event.text}...
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
