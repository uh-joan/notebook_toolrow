"use client";

import { Download, Copy, Check, Save, FileText, Database, Eye, FileDown } from "lucide-react";
import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useParams } from "next/navigation";
import DiscoverTerminal from "./DiscoverTerminal";
// import { useToast } from "@/hooks/use-toast";

interface Message {
	id: string;
	role: "user" | "assistant";
	content: string | Array<{type: string; text: string}>;
	data?: {
		suggestions?: Array<{
			id: string;
			title: string;
			description: string;
			relevance_score: number;
			content_preview: string;
			original_data: any;
			format: string;
		}>;
		reasoning_steps?: string[];
		total_found?: number;
		processing_time_ms?: number;
		terminal_events?: any[];
	};
}

interface DiscoverChatMessagesProps {
	messages: Message[];
	isLoading: boolean;
}

export default function DiscoverChatMessages({
	messages,
	isLoading,
}: DiscoverChatMessagesProps) {
	const [copiedId, setCopiedId] = useState<string | null>(null);
	const [savingId, setSavingId] = useState<string | null>(null);
	const [previewData, setPreviewData] = useState<any>(null);
	const params = useParams();
	const searchSpaceId = params.search_space_id as string;
	// const { toast } = useToast();
	const toast = (opts: any) => console.log('Toast:', opts.title, opts.description);


	const handleCopy = async (content: string, messageId: string) => {
		try {
			await navigator.clipboard.writeText(content);
			setCopiedId(messageId);
			setTimeout(() => setCopiedId(null), 2000);
			toast({
				title: "Copied to clipboard",
				description: "Message content has been copied.",
			});
		} catch (error) {
			toast({
				title: "Copy failed",
				description: "Failed to copy content to clipboard.",
				variant: "destructive",
			});
		}
	};

	const handleSaveToSources = async (message: Message, exportFormat: string = "markdown") => {
		if (!message.data?.suggestions || message.data.suggestions.length === 0) {
			toast({
				title: "No sources to save",
				description: "This message doesn't contain any discoverable sources.",
				variant: "destructive",
			});
			return;
		}

		setSavingId(message.id);
		
		try {
			const token = localStorage.getItem("surfsense_bearer_token");
			if (!token) {
				throw new Error("No authentication token found");
			}

			// Save each source suggestion individually
			for (const suggestion of message.data.suggestions) {
				const response = await fetch(`${process.env.NEXT_PUBLIC_FASTAPI_BACKEND_URL}/api/source-discovery/save-source`, {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						"Authorization": `Bearer ${token}`,
					},
					body: JSON.stringify({
						search_space_id: parseInt(searchSpaceId),
						source_suggestion: suggestion,
						export_format: exportFormat
					}),
				});

				if (!response.ok) {
					const errorData = await response.json();
					throw new Error(errorData.detail || `HTTP ${response.status}`);
				}
			}

			toast({
				title: "Sources saved successfully",
				description: `${message.data.suggestions.length} source(s) have been queued for processing and will appear in your documents shortly.`,
			});
		} catch (error) {
			console.error("Failed to save sources:", error);
			toast({
				title: "Failed to save sources",
				description: error instanceof Error ? error.message : "An unknown error occurred.",
				variant: "destructive",
			});
		} finally {
			setSavingId(null);
		}
	};

	// Custom message renderer that adds action buttons to assistant messages
	const renderMessage = (message: Message, index: number) => {
		const isAssistant = message.role === "assistant";
		const isLastMessage = index === messages.length - 1;

		return (
			<div key={message.id || index} className="space-y-2">
				{/* Discovery Terminal for assistant messages - ABOVE content and ALWAYS OPEN for last message */}
				{isAssistant && (
					<div className="mb-4 ml-8">
						{/* Always open terminal for the last (streaming) message, like researcher agent */}
						<DiscoverTerminal message={message} open={isLastMessage} />
					</div>
				)}

				<div className={`p-4 rounded-lg ${
					isAssistant 
						? "bg-muted/50 ml-8" 
						: "bg-primary/10 mr-8"
				}`}>
					<div className="prose prose-sm max-w-none">
						{(() => {
							// Handle both string content and array of text parts (AI SDK format)
							let textContent = '';
							if (typeof message.content === 'string') {
								textContent = message.content;
							} else if (Array.isArray(message.content)) {
								textContent = message.content
									.filter(part => part.type === 'text')
									.map(part => part.text)
									.join('');
							}
							
							return textContent.split('\n').map((line: string, i: number) => {
								if (line.startsWith('**') && line.endsWith('**')) {
									return <strong key={i}>{line.slice(2, -2)}</strong>;
								}
								if (line.startsWith('# ')) {
									return <h1 key={i} className="text-lg font-bold">{line.slice(2)}</h1>;
								}
								if (line.startsWith('## ')) {
									return <h2 key={i} className="text-md font-semibold">{line.slice(3)}</h2>;
								}
								if (line.includes('🔗 [') && line.includes('](')) {
									const linkMatch = line.match(/🔗 \[([^\]]+)\]\(([^)]+)\)/);
									if (linkMatch) {
										return (
											<div key={i}>
												🔗 <a href={linkMatch[2]} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
													{linkMatch[1]}
												</a>
											</div>
										);
									}
								}
								return <div key={i}>{line || <br />}</div>;
							});
						})()}
					</div>
				</div>


				{/* Action buttons for assistant messages */}
				{isAssistant && (
					<div className="flex items-center gap-2 ml-8">
						<Button
							variant="ghost"
							size="sm"
							onClick={() => {
								let textContent = '';
								if (typeof message.content === 'string') {
									textContent = message.content;
								} else if (Array.isArray(message.content)) {
									textContent = message.content
										.filter(part => part.type === 'text')
										.map(part => part.text)
										.join('');
								}
								handleCopy(textContent, message.id);
							}}
							className="h-8 px-2"
						>
							{copiedId === message.id ? (
								<Check className="w-3 h-3" />
							) : (
								<Copy className="w-3 h-3" />
							)}
							<span className="ml-1 text-xs">
								{copiedId === message.id ? "Copied" : "Copy"}
							</span>
						</Button>

						{/* Preview button for discovery results */}
						{message.data?.suggestions && message.data.suggestions.length > 0 && (
							<Dialog>
								<DialogTrigger asChild>
									<Button
										variant="ghost"
										size="sm"
										className="h-8 px-2"
									>
										<Eye className="w-3 h-3" />
										<span className="ml-1 text-xs">Preview</span>
									</Button>
								</DialogTrigger>
								<DialogContent className="max-w-4xl max-h-[80vh]">
									<DialogHeader>
										<DialogTitle>Discovery Results Preview</DialogTitle>
									</DialogHeader>
									<ScrollArea className="h-[60vh]">
										<div className="space-y-4">
											{/* Show reasoning steps if available */}
											{message.data?.reasoning_steps && message.data.reasoning_steps.length > 0 && (
												<Card className="p-4 bg-blue-50 border-blue-200">
													<h3 className="font-medium text-blue-900 mb-2">🧠 Reasoning Process</h3>
													<div className="space-y-1">
														{message.data.reasoning_steps.slice(0, 5).map((step: string, index: number) => (
															<p key={index} className="text-sm text-blue-800">
																{index + 1}. {step.replace(/^\d+\.\s*/, '').replace(/^-\s*/, '')}
															</p>
														))}
														{message.data.reasoning_steps.length > 5 && (
															<p className="text-xs text-blue-600 italic">
																... and {message.data.reasoning_steps.length - 5} more steps
															</p>
														)}
													</div>
												</Card>
											)}
											{message.data.suggestions.map((suggestion: any, index: number) => (
												<Card key={index} className="p-4">
													<div className="space-y-2">
														<div className="flex items-center justify-between">
															<h3 className="font-medium">{suggestion.metadata?.title || `Source ${index + 1}`}</h3>
															<Badge variant="secondary">
																{Math.round((suggestion.metadata?.relevance_score || 0) * 100)}% relevance
															</Badge>
														</div>
														
														{suggestion.metadata?.tags && (
															<div className="flex gap-1">
																{suggestion.metadata.tags.map((tag: string) => (
																	<Badge key={tag} variant="outline" className="text-xs">
																		{tag.replace("_", " ")}
																	</Badge>
																))}
															</div>
														)}
														
														<div className="text-sm text-muted-foreground">
															{suggestion.content_preview}
														</div>
														
														{suggestion.content && (
															<details className="mt-2">
																<summary className="cursor-pointer text-sm font-medium">View full content</summary>
																<pre className="mt-2 p-2 bg-muted rounded text-xs overflow-x-auto">
																	{suggestion.content}
																</pre>
															</details>
														)}
													</div>
												</Card>
											))}
										</div>
									</ScrollArea>
								</DialogContent>
							</Dialog>
						)}

						<Button
							variant="ghost"
							size="sm"
							onClick={() => handleSaveToSources(message, "markdown")}
							disabled={savingId === message.id}
							className="h-8 px-2"
						>
							{savingId === message.id ? (
								<div className="animate-spin h-3 w-3 border border-current border-t-transparent rounded-full" />
							) : (
								<Save className="w-3 h-3" />
							)}
							<span className="ml-1 text-xs">
								{savingId === message.id ? "Saving..." : "Save to Documents"}
							</span>
						</Button>

						{/* CSV Export button for structured data */}
						{message.data?.suggestions?.some((s: any) => {
							try {
								const content = s.content || "";
								const jsonData = JSON.parse(content);
								return jsonData.results && Array.isArray(jsonData.results);
							} catch {
								return false;
							}
						}) && (
							<Button
								variant="ghost"
								size="sm"
								onClick={() => handleSaveToSources(message, "csv")}
								disabled={savingId === message.id}
								className="h-8 px-2"
							>
								{savingId === message.id ? (
									<div className="animate-spin h-3 w-3 border border-current border-t-transparent rounded-full" />
								) : (
									<FileText className="w-3 h-3" />
								)}
								<span className="ml-1 text-xs">
									Export CSV
								</span>
							</Button>
						)}

						{/* DOCX Export button - available for all discovery results */}
						{message.data?.suggestions && message.data.suggestions.length > 0 && (
							<Button
								variant="ghost"
								size="sm"
								onClick={() => handleSaveToSources(message, "docx")}
								disabled={savingId === message.id}
								className="h-8 px-2"
							>
								{savingId === message.id ? (
									<div className="animate-spin h-3 w-3 border border-current border-t-transparent rounded-full" />
								) : (
									<FileDown className="w-3 h-3" />
								)}
								<span className="ml-1 text-xs">
									Export DOCX
								</span>
							</Button>
						)}
					</div>
				)}
			</div>
		);
	};

	return (
		<div className="flex-1 overflow-y-auto p-4 space-y-4">
			{messages.length === 0 ? (
				<div className="text-center text-muted-foreground py-8">
					<div className="space-y-4">
						<h2 className="text-2xl font-bold text-foreground">SourceBook Discover</h2>
						<p className="text-base max-w-2xl mx-auto">
							Fetch live sources via Toolrow MCP (FDA, ct.gov, PubMed, WHO, SEC, codes)—auto-cited with one-click Add to Sources.
						</p>
						<div className="text-sm space-y-1 mt-4">
							<p className="font-medium text-foreground">Try asking::</p>
								<p>"ICD-10 & MeSH for obesity"</p>
								<p>"US FDA drugs for T2D"</p>
								<p>"Phase 2/3 trials recruiting in EU"</p>
								<p>"Latest PubMed reviews on GLP-1"</p>
							
						</div>
					</div>
				</div>
			) : (
				messages.map(renderMessage)
			)}

		</div>
	);
}
