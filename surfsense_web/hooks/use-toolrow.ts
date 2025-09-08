import { useState, useEffect } from 'react';
import { apiClient as api } from '@/lib/api';
import type { ToolrowCoverage, ToolrowInvocation } from '@/components/chat/types';

interface ToolrowServerStatus {
  name: string;
  status: 'running' | 'stopped' | 'error';
  tools_count: number;
  last_restart?: string;
  error?: string;
}

interface ToolrowTool {
  name: string;
  description: string;
  provider: string;
  category: string;
  parameters: Record<string, any>;
}

export function useToolrowStatus() {
  const [status, setStatus] = useState<ToolrowServerStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await api.get<{ servers: ToolrowServerStatus[] }>('/toolrow/health');
      setStatus(response.servers || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch Toolrow status');
      setStatus([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const restartServer = async (serverName: string) => {
    try {
      await api.post(`/toolrow/restart/${serverName}`);
      await fetchStatus(); // Refresh status after restart
    } catch (err) {
      throw new Error(err instanceof Error ? err.message : 'Failed to restart server');
    }
  };

  return {
    status,
    loading,
    error,
    refresh: fetchStatus,
    restartServer,
  };
}

export function useToolrowTools() {
  const [tools, setTools] = useState<ToolrowTool[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTools = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await api.get<{ tools: ToolrowTool[] }>('/toolrow/tools');
      setTools(response.tools || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch Toolrow tools');
      setTools([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTools();
  }, []);

  return {
    tools,
    loading,
    error,
    refresh: fetchTools,
  };
}

export function useToolrowCoverage(searchSpaceId: string) {
  const [coverage, setCoverage] = useState<ToolrowCoverage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const checkCoverage = async (query: string) => {
    if (!query.trim()) return;

    try {
      setLoading(true);
      setError(null);
      const response = await api.get<ToolrowCoverage>(`/research/coverage/${searchSpaceId}?query=${encodeURIComponent(query)}`);
      setCoverage(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to check coverage');
      setCoverage(null);
    } finally {
      setLoading(false);
    }
  };

  return {
    coverage,
    loading,
    error,
    checkCoverage,
  };
}

export function useToolrowInvoke() {
  const [invocations, setInvocations] = useState<ToolrowInvocation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const invoke = async (tool: string, params: Record<string, any>) => {
    try {
      setLoading(true);
      setError(null);
      
      const newInvocation: ToolrowInvocation = {
        tool,
        params,
        status: 'pending',
      };
      
      setInvocations(prev => [...prev, newInvocation]);

      const response = await api.post<{ result: any; execution_time_ms?: number }>('/toolrow/invoke', {
        tool,
        params,
      });

      const completedInvocation: ToolrowInvocation = {
        tool,
        params,
        status: 'completed',
        result: response.result,
        execution_time_ms: response.execution_time_ms,
      };

      setInvocations(prev => 
        prev.map(inv => 
          inv.tool === tool && inv.status === 'pending' 
            ? completedInvocation 
            : inv
        )
      );

      return response;
    } catch (err) {
      const failedInvocation: ToolrowInvocation = {
        tool,
        params,
        status: 'failed',
        error: err instanceof Error ? err.message : 'Unknown error',
      };

      setInvocations(prev => 
        prev.map(inv => 
          inv.tool === tool && inv.status === 'pending' 
            ? failedInvocation 
            : inv
        )
      );

      throw err;
    } finally {
      setLoading(false);
    }
  };

  const clearInvocations = () => {
    setInvocations([]);
  };

  return {
    invocations,
    loading,
    error,
    invoke,
    clearInvocations,
  };
}
