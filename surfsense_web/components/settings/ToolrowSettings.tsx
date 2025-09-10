"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Progress } from "@/components/ui/progress";
import { 
	Settings, 
	Zap, 
	Server, 
	Activity, 
	RefreshCw, 
	CheckCircle, 
	XCircle, 
	AlertTriangle,
	Database,
	Clock,
	Info
} from "lucide-react";
import { useToolrowStatus, useToolrowTools } from "@/hooks/use-toolrow";

interface ToolrowSettingsProps {
	searchSpaceId?: string;
}

function ServerStatusCard({ 
	name, 
	status, 
	tools_count, 
	last_restart, 
	error, 
	onRestart 
}: {
	name: string;
	status: 'running' | 'stopped' | 'error';
	tools_count: number;
	last_restart?: string;
	error?: string;
	onRestart: (name: string) => Promise<void>;
}) {
	const [restarting, setRestarting] = useState(false);

	const getStatusInfo = () => {
		switch (status) {
			case 'running':
				return { 
					icon: CheckCircle, 
					color: 'text-green-600', 
					bgColor: 'bg-green-50',
					label: 'Running' 
				};
			case 'stopped':
				return { 
					icon: XCircle, 
					color: 'text-gray-600', 
					bgColor: 'bg-gray-50',
					label: 'Stopped' 
				};
			case 'error':
				return { 
					icon: AlertTriangle, 
					color: 'text-red-600', 
					bgColor: 'bg-red-50',
					label: 'Error' 
				};
		}
	};

	const { icon: StatusIcon, color, bgColor, label } = getStatusInfo();

	const handleRestart = async () => {
		try {
			setRestarting(true);
			await onRestart(name);
		} catch (err) {
			console.error('Failed to restart server:', err);
		} finally {
			setRestarting(false);
		}
	};

	return (
		<Card>
			<CardHeader className="pb-3">
				<div className="flex items-center justify-between">
					<div className="flex items-center gap-2">
						<Server className="h-4 w-4" />
						<CardTitle className="text-sm font-medium capitalize">
							{name.replace('-', ' ')}
						</CardTitle>
					</div>
					<Badge variant="outline" className={`${bgColor} border-0`}>
						<StatusIcon className={`h-3 w-3 mr-1 ${color}`} />
						{label}
					</Badge>
				</div>
			</CardHeader>
			<CardContent className="space-y-3">
				<div className="grid grid-cols-2 gap-4 text-sm">
					<div>
						<span className="text-muted-foreground">Tools Available:</span>
						<span className="ml-2 font-medium">{tools_count}</span>
					</div>
					{last_restart && (
						<div>
							<span className="text-muted-foreground">Last Restart:</span>
							<span className="ml-2 font-medium text-xs">
								{new Date(last_restart).toLocaleString()}
							</span>
						</div>
					)}
				</div>

				{error && (
					<Alert className="border-red-200 bg-red-50">
						<AlertTriangle className="h-4 w-4 text-red-600" />
						<AlertDescription className="text-red-800 text-xs">
							{error}
						</AlertDescription>
					</Alert>
				)}

				<div className="flex gap-2">
					<Button
						size="sm"
						variant="outline"
						onClick={handleRestart}
						disabled={restarting}
						className="flex-1"
					>
						{restarting ? (
							<RefreshCw className="h-3 w-3 mr-1 animate-spin" />
						) : (
							<RefreshCw className="h-3 w-3 mr-1" />
						)}
						Restart
					</Button>
				</div>
			</CardContent>
		</Card>
	);
}

function ToolCard({ tool }: { tool: any }) {
	return (
		<Card className="h-full">
			<CardHeader className="pb-3">
				<div className="flex items-start justify-between gap-2">
					<div className="flex-1 min-w-0">
						<CardTitle className="text-sm font-medium line-clamp-2">
							{tool.name}
						</CardTitle>
						<div className="flex items-center gap-2 mt-1">
							<Badge variant="outline" className="text-xs">
								{tool.provider}
							</Badge>
							<Badge variant="secondary" className="text-xs">
								{tool.category}
							</Badge>
						</div>
					</div>
				</div>
			</CardHeader>
			<CardContent className="pt-0">
				<CardDescription className="text-xs line-clamp-3 leading-relaxed">
					{tool.description}
				</CardDescription>
				{tool.parameters && Object.keys(tool.parameters).length > 0 && (
					<div className="mt-2">
						<span className="text-xs text-muted-foreground">
							Parameters: {Object.keys(tool.parameters).join(', ')}
						</span>
					</div>
				)}
			</CardContent>
		</Card>
	);
}

export default function ToolrowSettings({ searchSpaceId }: ToolrowSettingsProps) {
	// Initialize state from localStorage immediately to prevent flash
	const [toolrowEnabled, setToolrowEnabled] = useState(() => {
		if (typeof window !== 'undefined') {
			const saved = localStorage.getItem('toolrow_settings');
			if (saved) {
				try {
					const settings = JSON.parse(saved);
					return settings.enabled || false;
				} catch (error) {
					console.error('Error loading Toolrow settings:', error);
				}
			}
		}
		return false;
	});
	
	const [apiToken, setApiToken] = useState(() => {
		if (typeof window !== 'undefined') {
			const saved = localStorage.getItem('toolrow_settings');
			if (saved) {
				try {
					const settings = JSON.parse(saved);
					return settings.apiToken || '';
				} catch (error) {
					console.error('Error loading Toolrow settings:', error);
				}
			}
		}
		return '';
	});
	
	const [maxCalls, setMaxCalls] = useState(() => {
		if (typeof window !== 'undefined') {
			const saved = localStorage.getItem('toolrow_settings');
			if (saved) {
				try {
					const settings = JSON.parse(saved);
					return settings.maxCalls || 6;
				} catch (error) {
					console.error('Error loading Toolrow settings:', error);
				}
			}
		}
		return 6;
	});
	
	const [timeout, setTimeoutValue] = useState(() => {
		if (typeof window !== 'undefined') {
			const saved = localStorage.getItem('toolrow_settings');
			if (saved) {
				try {
					const settings = JSON.parse(saved);
					return settings.timeout || 30000;
				} catch (error) {
					console.error('Error loading Toolrow settings:', error);
				}
			}
		}
		return 30000;
	});
	
	const { status: serverStatus, loading: statusLoading, error: statusError, refresh: refreshStatus, restartServer } = useToolrowStatus();
	const { tools, loading: toolsLoading, error: toolsError, refresh: refreshTools } = useToolrowTools();

	// Load settings from database on mount
	useEffect(() => {
		const loadSettings = async () => {
			try {
				const token = localStorage.getItem("surfsense_bearer_token");
				if (!token) return;

				const response = await fetch(`${process.env.NEXT_PUBLIC_FASTAPI_BACKEND_URL}/api/v1/toolrow-settings/`, {
					method: "GET",
					headers: {
						"Authorization": `Bearer ${token}`,
					},
				});

				if (response.ok) {
					const settings = await response.json();
					if (settings) {
						setToolrowEnabled(settings.enabled);
						setMaxCalls(settings.max_calls);
						setTimeoutValue(settings.timeout_ms);
						// Don't load the actual token for security, just show if it exists
						if (settings.has_token) {
							setApiToken("***CONFIGURED***"); // Placeholder to show token exists
						}
					}
				}
			} catch (error) {
				console.error("Failed to load ToolRow settings:", error);
			}
		};

		loadSettings();
	}, []);

	// Listen for storage changes from other tabs (simplified since we initialize from localStorage)
	useEffect(() => {
		const handleStorageChange = (e: StorageEvent) => {
			if (e.key === 'toolrow_settings') {
				const saved = localStorage.getItem('toolrow_settings');
				if (saved) {
					try {
						const settings = JSON.parse(saved);
						setToolrowEnabled(settings.enabled || false);
						setApiToken(settings.apiToken || '');
						setMaxCalls(settings.maxCalls || 6);
						setTimeoutValue(settings.timeout || 30000);
					} catch (error) {
						console.error('Error loading Toolrow settings:', error);
					}
				}
			}
		};

		window.addEventListener('storage', handleStorageChange);
		return () => window.removeEventListener('storage', handleStorageChange);
	}, []);

	// Save settings to database
	const saveSettings = async () => {
		try {
			const token = localStorage.getItem("surfsense_bearer_token");
			if (!token) return;

			const response = await fetch(`${process.env.NEXT_PUBLIC_FASTAPI_BACKEND_URL}/api/v1/toolrow-settings/`, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					"Authorization": `Bearer ${token}`,
				},
				body: JSON.stringify({
					api_token: apiToken,
					enabled: toolrowEnabled,
					max_calls: maxCalls,
					timeout_ms: timeout,
				}),
			});

			if (!response.ok) {
				throw new Error(`Failed to save settings: ${response.statusText}`);
			}

			console.log("✅ ToolRow settings saved successfully");
		} catch (error) {
			console.error("❌ Failed to save ToolRow settings:", error);
		}
	};

	useEffect(() => {
		// Auto-save when settings change (with debounce)
		const timeoutId = setTimeout(() => {
			if (apiToken.trim()) { // Only save if token is provided
				saveSettings();
			}
		}, 1000);

		return () => clearTimeout(timeoutId);
	}, [toolrowEnabled, apiToken, maxCalls, timeout]);

	const isConfigured = apiToken.trim() !== '';
	const hasRunningServers = Array.isArray(serverStatus) && serverStatus.some(server => server.status === 'running');

	return (
		<div className="space-y-6">
			<div className="flex items-center gap-2">
				<Zap className="h-5 w-5" />
				<h2 className="text-lg font-semibold">Discovery Agent - Live Data</h2>
				<Badge variant="outline" className="text-xs">
					{toolrowEnabled && isConfigured ? 'Enabled' : 'Disabled'}
				</Badge>
			</div>

			<Card>
				<CardHeader>
					<CardTitle className="text-base flex items-center gap-2">
						<Settings className="h-4 w-4" />
						Configuration
					</CardTitle>
					<CardDescription>
						Configure Toolrow MCP for the Discovery Agent to fetch live external data from clinical trials, FDA, PubMed, and more.
					</CardDescription>
				</CardHeader>
				<CardContent className="space-y-4">
					<div className="flex items-center justify-between">
						<div>
							<Label htmlFor="toolrow-enabled" className="text-sm font-medium">
								Enable Toolrow Integration
							</Label>
							<p className="text-xs text-muted-foreground mt-1">
								Allow Discovery Agent to access external APIs for live data discovery
							</p>
						</div>
						<Switch
							id="toolrow-enabled"
							checked={toolrowEnabled}
							onCheckedChange={setToolrowEnabled}
						/>
					</div>

					{toolrowEnabled && (
						<>
							<div className="space-y-2">
								<Label htmlFor="api-token">API Token</Label>
								<Input
									id="api-token"
									type="password"
									placeholder="Enter your Toolrow API token"
									value={apiToken}
									onChange={(e) => setApiToken(e.target.value)}
								/>
								<p className="text-xs text-muted-foreground">
									Get your API token from <a href="https://toolrow.ai" className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">toolrow.ai</a>
								</p>
							</div>

							<div className="grid grid-cols-2 gap-4">
								<div className="space-y-2">
									<Label htmlFor="max-calls">Max Calls per Query</Label>
									<Input
										id="max-calls"
										type="number"
										min="1"
										max="20"
										value={maxCalls}
										onChange={(e) => setMaxCalls(Number(e.target.value))}
									/>
								</div>
								<div className="space-y-2">
									<Label htmlFor="timeout">Timeout (ms)</Label>
									<Input
										id="timeout"
										type="number"
										min="5000"
										max="60000"
										step="5000"
										value={timeout}
										onChange={(e) => setTimeoutValue(Number(e.target.value))}
									/>
								</div>
							</div>

							{!isConfigured && (
								<Alert>
									<Info className="h-4 w-4" />
									<AlertDescription>
										Please configure your API token to enable live data features.
									</AlertDescription>
								</Alert>
							)}
						</>
					)}
				</CardContent>
			</Card>

			{toolrowEnabled && isConfigured && (
				<Tabs defaultValue="status" className="w-full">
					<TabsList className="grid w-full grid-cols-2">
						<TabsTrigger value="status" className="flex items-center gap-2">
							<Activity className="h-4 w-4" />
							Server Status
						</TabsTrigger>
						<TabsTrigger value="tools" className="flex items-center gap-2">
							<Database className="h-4 w-4" />
							Available Tools
						</TabsTrigger>
					</TabsList>

					<TabsContent value="status" className="space-y-4">
						<div className="flex items-center justify-between">
							<h3 className="text-sm font-medium">MCP Servers</h3>
							<Button
								size="sm"
								variant="outline"
								onClick={refreshStatus}
								disabled={statusLoading}
							>
								{statusLoading ? (
									<RefreshCw className="h-3 w-3 animate-spin" />
								) : (
									<RefreshCw className="h-3 w-3" />
								)}
							</Button>
						</div>

						{statusError && (
							<Alert className="border-red-200 bg-red-50">
								<AlertTriangle className="h-4 w-4 text-red-600" />
								<AlertDescription className="text-red-800">
									{statusError}
								</AlertDescription>
							</Alert>
						)}

						{statusLoading ? (
							<div className="space-y-2">
								<div className="flex items-center gap-2 text-sm text-muted-foreground">
									<Clock className="h-4 w-4 animate-spin" />
									Checking server status...
								</div>
								<Progress value={0} className="h-2" />
							</div>
						) : Array.isArray(serverStatus) && serverStatus.length > 0 ? (
							<div className="grid gap-4">
								{serverStatus.map((server) => (
									<ServerStatusCard
										key={server.name}
										{...server}
										onRestart={restartServer}
									/>
								))}
							</div>
						) : (
							<div className="text-center py-8 text-muted-foreground">
								<Server className="h-8 w-8 mx-auto mb-2 opacity-50" />
								<p>No MCP servers configured</p>
							</div>
						)}
					</TabsContent>

					<TabsContent value="tools" className="space-y-4">
						<div className="flex items-center justify-between">
							<h3 className="text-sm font-medium">Available Tools</h3>
							<Button
								size="sm"
								variant="outline"
								onClick={refreshTools}
								disabled={toolsLoading}
							>
								{toolsLoading ? (
									<RefreshCw className="h-3 w-3 animate-spin" />
								) : (
									<RefreshCw className="h-3 w-3" />
								)}
							</Button>
						</div>

						{toolsError && (
							<Alert className="border-red-200 bg-red-50">
								<AlertTriangle className="h-4 w-4 text-red-600" />
								<AlertDescription className="text-red-800">
									{toolsError}
								</AlertDescription>
							</Alert>
						)}

						{toolsLoading ? (
							<div className="space-y-2">
								<div className="flex items-center gap-2 text-sm text-muted-foreground">
									<Clock className="h-4 w-4 animate-spin" />
									Loading available tools...
								</div>
								<Progress value={0} className="h-2" />
							</div>
						) : tools.length > 0 ? (
							<div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
								{tools.map((tool, index) => (
									<ToolCard key={index} tool={tool} />
								))}
							</div>
						) : (
							<div className="text-center py-8 text-muted-foreground">
								<Database className="h-8 w-8 mx-auto mb-2 opacity-50" />
								<p>No tools available</p>
								{!hasRunningServers && (
									<p className="text-xs mt-1">Start MCP servers to see available tools</p>
								)}
							</div>
						)}
					</TabsContent>
				</Tabs>
			)}
		</div>
	);
}
