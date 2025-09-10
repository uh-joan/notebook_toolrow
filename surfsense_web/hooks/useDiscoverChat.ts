import type { Message } from "@ai-sdk/react";
import { useCallback, useEffect, useState } from "react";
import type { DiscoveryMode } from "@/components/chat";

interface UseDiscoverChatStateProps {
	search_space_id: string;
	chat_id?: string;
}

export function useDiscoverChatState({ chat_id }: UseDiscoverChatStateProps) {
	const [token, setToken] = useState<string | null>(null);
	const [isLoading, setIsLoading] = useState(false);
	const [currentChatId, setCurrentChatId] = useState<string | null>(chat_id || null);

	// Discovery configuration state
	const [selectedTools, setSelectedTools] = useState<string[]>([]);
	const [discoveryMode, setDiscoveryMode] = useState<DiscoveryMode>("BASIC");

	useEffect(() => {
		const bearerToken = localStorage.getItem("surfsense_bearer_token");
		setToken(bearerToken);
	}, []);

	return {
		token,
		setToken,
		isLoading,
		setIsLoading,
		currentChatId,
		setCurrentChatId,
		selectedTools,
		setSelectedTools,
		discoveryMode,
		setDiscoveryMode,
	};
}

interface UseDiscoverChatAPIProps {
	token: string | null;
	search_space_id: string;
}

export function useDiscoverChatAPI({ token, search_space_id }: UseDiscoverChatAPIProps) {
	const fetchChatDetails = useCallback(
		async (chatId: string) => {
			if (!token) return null;

			try {
				const response = await fetch(
					`${process.env.NEXT_PUBLIC_FASTAPI_BACKEND_URL}/api/v1/chats/${Number(chatId)}`,
					{
						method: "GET",
						headers: {
							"Content-Type": "application/json",
							Authorization: `Bearer ${token}`,
						},
					}
				);

				if (!response.ok) {
					throw new Error(`Failed to fetch chat details: ${response.statusText}`);
				}

				return await response.json();
			} catch (err) {
				console.error("Error fetching discovery chat details:", err);
				return null;
			}
		},
		[token]
	);

	const createChat = useCallback(
		async (
			initialMessage: string,
			selectedTools: string[]
		): Promise<string | null> => {
			if (!token) {
				console.error("Authentication token not found");
				return null;
			}

			try {
				const response = await fetch(
					`${process.env.NEXT_PUBLIC_FASTAPI_BACKEND_URL}/api/v1/chats/`,
					{
						method: "POST",
						headers: {
							"Content-Type": "application/json",
							Authorization: `Bearer ${token}`,
						},
						body: JSON.stringify({
							type: "DISCOVERY",
							title: initialMessage.slice(0, 50) + (initialMessage.length > 50 ? "..." : ""),
							initial_connectors: selectedTools,
							messages: [
								{
									role: "user",
									content: initialMessage,
								},
							],
							search_space_id: Number(search_space_id),
						}),
					}
				);

				if (!response.ok) {
					throw new Error(`Failed to create discovery chat: ${response.statusText}`);
				}

				const data = await response.json();
				return data.id;
			} catch (err) {
				console.error("Error creating discovery chat:", err);
				return null;
			}
		},
		[token, search_space_id]
	);

	const updateChat = useCallback(
		async (
			chatId: string,
			messages: Message[],
			selectedTools: string[]
		) => {
			if (!token) return;

			try {
				const userMessages = messages.filter((msg) => msg.role === "user");
				if (userMessages.length === 0) return;

				const title = userMessages[0].content.slice(0, 50) + (userMessages[0].content.length > 50 ? "..." : "");

				const response = await fetch(
					`${process.env.NEXT_PUBLIC_FASTAPI_BACKEND_URL}/api/v1/chats/${Number(chatId)}`,
					{
						method: "PUT",
						headers: {
							"Content-Type": "application/json",
							Authorization: `Bearer ${token}`,
						},
						body: JSON.stringify({
							type: "DISCOVERY",
							title: title,
							initial_connectors: selectedTools,
							messages: messages,
							search_space_id: Number(search_space_id),
						}),
					}
				);

				if (!response.ok) {
					throw new Error(`Failed to update discovery chat: ${response.statusText}`);
				}
			} catch (err) {
				console.error("Error updating discovery chat:", err);
			}
		},
		[token, search_space_id]
	);

	return {
		fetchChatDetails,
		createChat,
		updateChat,
	};
}
