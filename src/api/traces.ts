import type { OpenDevChatMessage, TraceSessionInfo } from '../types/trace';

const API_BASE = '/api';

export async function fetchTraceProjects(): Promise<string[]> {
  const response = await fetch(`${API_BASE}/traces/projects`);
  if (!response.ok) throw new Error(`API error: ${response.statusText}`);
  return response.json();
}

export async function fetchTraceSessions(project: string): Promise<TraceSessionInfo[]> {
  const response = await fetch(`${API_BASE}/traces/projects/${encodeURIComponent(project)}/sessions`);
  if (!response.ok) throw new Error(`API error: ${response.statusText}`);
  return response.json();
}

export async function fetchTraceSession(
  project: string,
  sessionId: string,
): Promise<OpenDevChatMessage[]> {
  const response = await fetch(
    `${API_BASE}/traces/projects/${encodeURIComponent(project)}/sessions/${encodeURIComponent(sessionId)}`,
  );
  if (!response.ok) throw new Error(`API error: ${response.statusText}`);
  return response.json();
}
