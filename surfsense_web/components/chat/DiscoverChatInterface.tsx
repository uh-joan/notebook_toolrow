"use client";

import React from "react";
import { ChatSection as LlamaIndexChatSection } from "@llamaindex/chat-ui";
import DiscoverChatMessages from "@/components/chat/DiscoverChatMessages";
import { DiscoverChatInputUI } from "@/components/chat/DiscoverChatInput";
import type { DiscoveryMode } from "@/components/chat";

interface Message {
	id: string;
	role: "user" | "assistant";
	content: string;
	data?: any;
}

interface DiscoverChatInterfaceProps {
	messages: Message[];
	isLoading: boolean;
	selectedTools: string[];
	onToolSelectionChange: (tools: string[]) => void;
	discoveryMode?: DiscoveryMode;
	onDiscoveryModeChange?: (mode: DiscoveryMode) => void;
	handler: any; // useChat handler with append method
}

export default function DiscoverChatInterface({
	messages,
	isLoading,
	selectedTools,
	onToolSelectionChange,
	discoveryMode,
	onDiscoveryModeChange,
	handler,
}: DiscoverChatInterfaceProps) {
	return (
		<LlamaIndexChatSection handler={handler} className="flex h-full">
			<div className="flex flex-1 flex-col">
				<DiscoverChatMessages 
					messages={messages}
					isLoading={isLoading}
				/>
				<div className="border-t p-4">
					<DiscoverChatInputUI
						onToolSelectionChange={onToolSelectionChange}
						selectedTools={selectedTools}
						discoveryMode={discoveryMode}
						onDiscoveryModeChange={onDiscoveryModeChange}
					/>
				</div>
			</div>
		</LlamaIndexChatSection>
	);
}
