"use client";

import { type CreateMessage, type Message, useChat } from "@ai-sdk/react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";
import DiscoverChatInterface from "@/components/chat/DiscoverChatInterface";
import type { DiscoveryMode } from "@/components/chat";
import { useDiscoverChatAPI, useDiscoverChatState } from "../../../../../hooks/useDiscoverChat";

interface DiscoverMessage {
	id: string;
	role: "user" | "assistant";
	content: string;
	data?: any;
}

export default function DiscoverPage() {
	const { search_space_id, chat_id } = useParams();
	const router = useRouter();

	const chatIdParam = Array.isArray(chat_id) ? chat_id[0] : chat_id;
	const isNewChat = !chatIdParam;
	
	// Debug: Track why isNewChat might be incorrectly true

	const {
		token,
		isLoading,
		setIsLoading,
		selectedTools,
		setSelectedTools,
		discoveryMode,
		setDiscoveryMode,
	} = useDiscoverChatState({
		search_space_id: search_space_id as string,
		chat_id: chatIdParam,
	});

	const { fetchChatDetails, updateChat, createChat } = useDiscoverChatAPI({
		token,
		search_space_id: search_space_id as string,
	});

	// Memoize selected tools to prevent infinite re-renders
	const toolList = useMemo(() => {
		return selectedTools;
	}, [selectedTools]);

	// Unified localStorage management for discovery chat state
	interface DiscoveryChatState {
		selectedTools: string[];
		discoveryMode: DiscoveryMode;
	}

	const getChatStateStorageKey = (searchSpaceId: string, chatId: string) =>
		`surfsense_discovery_chat_state_${searchSpaceId}_${chatId}`;

	const storeChatState = (searchSpaceId: string, chatId: string, state: DiscoveryChatState) => {
		const key = getChatStateStorageKey(searchSpaceId, chatId);
		localStorage.setItem(key, JSON.stringify(state));
	};

	const restoreChatState = (searchSpaceId: string, chatId: string): DiscoveryChatState | null => {
		const key = getChatStateStorageKey(searchSpaceId, chatId);
		const stored = localStorage.getItem(key);
		if (stored) {
			localStorage.removeItem(key); // Clean up after restoration
			try {
				return JSON.parse(stored);
			} catch (error) {
				console.error("Error parsing stored discovery chat state:", error);
				return null;
			}
		}
		return null;
	};

	const originalHandler = useChat({
		api: `${process.env.NEXT_PUBLIC_FASTAPI_BACKEND_URL}/api/source-discovery/claude-chat`,
		streamProtocol: "data",
		initialMessages: [],
		headers: {
			...(token && { Authorization: `Bearer ${token}` }),
		},
		body: {
			data: {
				search_space_id: search_space_id,
				selected_tools: toolList,
				discovery_mode: discoveryMode,
				max_sources: 20,
				disable_auto_save: true, // Prevent duplicate chat creation
			},
		},
		onError: (error) => {
			console.error("Claude discovery chat error:", error);
		},
	});

	// Keep reference to original handler for loadChatData
	const handler = originalHandler;


	const customHandlerAppend = async (
		message: Message | CreateMessage,
		chatRequestOptions?: { data?: any }
	) => {
		const newChatId = await createChat(message.content, selectedTools);
		
		if (newChatId) {
			// Store chat state before navigation
			storeChatState(search_space_id as string, newChatId, {
				selectedTools,
				discoveryMode,
			});
			router.replace(`/dashboard/${search_space_id}/discover/${newChatId}`);
		}
		return newChatId;
	};

	useEffect(() => {
		if (token && !isNewChat && chatIdParam) {
			setIsLoading(true);
			loadChatData(chatIdParam);
		}
	}, [token, isNewChat, chatIdParam]);

	// Restore chat state from localStorage on page load
	useEffect(() => {
		if (chatIdParam && search_space_id) {
			const restoredState = restoreChatState(search_space_id as string, chatIdParam);
			if (restoredState) {
				setSelectedTools(restoredState.selectedTools);
				if (restoredState.discoveryMode) {
					setDiscoveryMode(restoredState.discoveryMode);
				}
			}
		}
	}, [
		chatIdParam,
		search_space_id,
		setSelectedTools,
		setDiscoveryMode,
	]);

	const loadChatData = async (chatId: string) => {
		try {
			const chatData = await fetchChatDetails(chatId);
			if (!chatData) return;

			// Update configuration from chat data
			if (chatData.initial_connectors && Array.isArray(chatData.initial_connectors)) {
				setSelectedTools(chatData.initial_connectors);
			}

			// Load existing messages
			if (chatData.messages && Array.isArray(chatData.messages)) {
				if (chatData.messages.length === 1 && chatData.messages[0].role === "user") {
					// Single user message - append to trigger discovery response
					// Use original handler directly to avoid routing confusion
					originalHandler.append({
						role: "user",
						content: chatData.messages[0].content,
					});
				} else if (chatData.messages.length > 1) {
					// Multiple messages - set them all
					originalHandler.setMessages(chatData.messages);
				}
			}
		} finally {
			setIsLoading(false);
		}
	};

	// Auto-update chat when messages change (only for existing chats)
	useEffect(() => {
		if (
			!isNewChat &&
			chatIdParam &&
			originalHandler.status === "ready" &&
			originalHandler.messages.length > 0 &&
			originalHandler.messages[originalHandler.messages.length - 1]?.role === "assistant"
		) {
			updateChat(chatIdParam, originalHandler.messages, selectedTools);
		}
	}, [originalHandler.messages, originalHandler.status, chatIdParam, isNewChat]);


	if (isLoading) {
		return (
			<div className="flex items-center justify-center h-full">
				<div>Loading discovery chat...</div>
			</div>
		);
	}

	return (
		<div className="flex h-full flex-col">
			<DiscoverChatInterface
				messages={originalHandler.messages as DiscoverMessage[]}
				isLoading={originalHandler.isLoading}
				selectedTools={selectedTools}
				onToolSelectionChange={setSelectedTools}
				discoveryMode={discoveryMode}
				onDiscoveryModeChange={setDiscoveryMode}
				handler={{
					...originalHandler,
					append: isNewChat ? customHandlerAppend : originalHandler.append,
				}}
			/>
		</div>
	);
}