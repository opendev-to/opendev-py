export interface ContentBlock {
  type: 'text' | 'tool_use' | 'tool_result' | 'thinking';
  text?: string;
  thinking?: string;
  id?: string;
  name?: string;
  input?: Record<string, unknown>;
  tool_use_id?: string;
  content?: string | ContentBlock[];
}

export interface Message {
  role?: string;
  content?: string | ContentBlock[];
  model?: string;
  id?: string;
  usage?: {
    input_tokens?: number;
    output_tokens?: number;
    cache_read_input_tokens?: number;
    cache_creation_input_tokens?: number;
  };
}

export interface ProgressInner {
  type: 'user' | 'assistant';
  timestamp?: string;
  message?: Message;
}

export interface TraceEvent {
  uuid?: string;
  parentUuid?: string | null;
  type: 'user' | 'assistant' | 'progress' | 'summary' | 'file-history-snapshot' | 'system' | 'queue-operation';
  isSidechain?: boolean;
  sessionId?: string;
  agentId?: string;
  slug?: string;
  timestamp?: string;
  message?: Message;
  data?: {
    message?: ProgressInner;
    type?: string;
    hookEvent?: string;
    hookName?: string;
    agentId?: string;
    prompt?: string;
  };
  parentToolUseID?: string;
  toolUseID?: string;
  version?: string;
  gitBranch?: string;
  cwd?: string;
}

export interface SessionInfo {
  sessionId: string;
  slug?: string;
  firstTimestamp?: string;
  eventCount: number;
  hasSubagents: boolean;
  subagentCount: number;
}

export interface SessionData {
  sessionId: string;
  events: TraceEvent[];
  subagents: Record<string, TraceEvent[]>;
}

export type NodeEventType =
  | 'user'
  | 'assistant'
  | 'tool-call'
  | 'task-call'
  | 'subagent-user'
  | 'subagent-assistant'
  | 'hook-progress'
  | 'summary';

export interface TraceNodeData extends Record<string, unknown> {
  eventType: NodeEventType;
  preview: string;
  tools: string[];
  agentId?: string;
  timestamp?: string;
  event: TraceEvent;
  subagentId?: string;
}

export interface ToolCall extends Record<string, unknown> {
  id: string;
  name: string;
  input: Record<string, unknown>;
  result?: string;
}

export interface ToolNodeData extends Record<string, unknown> {
  eventType: 'tool-call';
  tools: ToolCall[];
  preview: string;
  agentId?: string;
  timestamp?: string;
  assistantEvent: TraceEvent;
  userEvent: TraceEvent;
  subagentId?: string;
}

export interface TaskNodeData extends Record<string, unknown> {
  eventType: 'task-call';
  tools: ToolCall[];
  preview: string;
  taskDescription: string;
  subagentType?: string;
  spawnedSubagentId?: string;
  agentId?: string;
  timestamp?: string;
  assistantEvent: TraceEvent;
  userEvent: TraceEvent;
  subagentId?: string;
}

export type AnyNodeData = TraceNodeData | ToolNodeData | TaskNodeData;

export function getToolNames(ev: AnyNodeData): string[] {
  if (ev.eventType === 'tool-call' || ev.eventType === 'task-call') {
    return (ev as ToolNodeData | TaskNodeData).tools.map(t => t.name);
  }
  return (ev as TraceNodeData).tools;
}

export interface CollapsedNodeData extends Record<string, unknown> {
  chainId: string;
  events: AnyNodeData[];
  count: number;
  subagentId?: string;
}

/** OpenDev ChatMessage JSONL record shape (as returned by the backend). */
export interface OpenDevChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
  tool_calls?: Array<{
    id: string;
    name: string;
    parameters: Record<string, unknown>;
    result?: unknown;
    result_summary?: string;
    timestamp?: string;
    approved?: boolean;
    error?: string;
    nested_tool_calls?: Array<{
      id: string;
      name: string;
      parameters: Record<string, unknown>;
      result?: unknown;
      error?: string;
    }>;
  }>;
  thinking_trace?: string;
  reasoning_content?: string;
  token_usage?: Record<string, unknown>;
  tokens?: number;
}

/** Session info as returned by the traces API. */
export interface TraceSessionInfo {
  session_id: string;
  title: string;
  message_count: number;
  timestamp: string;
  working_dir?: string;
}
