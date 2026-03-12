/**
 * Adapter: transforms OpenDev ChatMessage JSONL records into the TraceEvent shape
 * that the graph algorithms (buildGraph / collapseGraph) expect.
 */
import type { TraceEvent, ContentBlock, SessionData, OpenDevChatMessage } from '../../types/trace';

function makeUuid(index: number, suffix?: string): string {
  // Deterministic pseudo-uuid from line index for stable graph IDs
  const base = `opendev-${String(index).padStart(6, '0')}`;
  return suffix ? `${base}-${suffix}` : base;
}

function stringifyResult(result: unknown): string {
  if (result === null || result === undefined) return '';
  if (typeof result === 'string') return result;
  try {
    return JSON.stringify(result, null, 2);
  } catch {
    return String(result);
  }
}

/**
 * Convert an array of OpenDev ChatMessage records into TraceEvent[] + SessionData.
 */
export function adaptOpenDevMessages(
  messages: OpenDevChatMessage[],
  sessionId: string,
): SessionData {
  const events: TraceEvent[] = [];
  let prevUuid: string | null = null;

  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];

    if (msg.role === 'system') continue;

    if (msg.role === 'user') {
      const uuid = makeUuid(i, 'user');
      const contentBlocks: ContentBlock[] = [];

      if (msg.content) {
        contentBlocks.push({ type: 'text', text: msg.content });
      }

      events.push({
        uuid,
        parentUuid: prevUuid,
        type: 'user',
        timestamp: msg.timestamp,
        message: {
          role: 'user',
          content: contentBlocks.length > 0 ? contentBlocks : msg.content,
        },
      });
      prevUuid = uuid;
    }

    if (msg.role === 'assistant') {
      const uuid = makeUuid(i, 'assistant');
      const contentBlocks: ContentBlock[] = [];

      // Add thinking block if present
      if (msg.thinking_trace) {
        contentBlocks.push({ type: 'thinking', thinking: msg.thinking_trace });
      }
      if (msg.reasoning_content) {
        contentBlocks.push({ type: 'thinking', thinking: msg.reasoning_content });
      }

      // Add text content
      if (msg.content) {
        contentBlocks.push({ type: 'text', text: msg.content });
      }

      // Add tool_use blocks for each tool call
      const toolCalls = msg.tool_calls ?? [];
      for (const tc of toolCalls) {
        contentBlocks.push({
          type: 'tool_use',
          id: tc.id,
          name: tc.name,
          input: tc.parameters,
        });
      }

      // Map token_usage to the expected shape
      const usage = msg.token_usage ? {
        input_tokens: (msg.token_usage.input_tokens ?? msg.token_usage.prompt_tokens ?? 0) as number,
        output_tokens: (msg.token_usage.output_tokens ?? msg.token_usage.completion_tokens ?? 0) as number,
        cache_read_input_tokens: (msg.token_usage.cache_read_input_tokens ?? 0) as number,
        cache_creation_input_tokens: (msg.token_usage.cache_creation_input_tokens ?? 0) as number,
      } : undefined;

      events.push({
        uuid,
        parentUuid: prevUuid,
        type: 'assistant',
        timestamp: msg.timestamp,
        message: {
          role: 'assistant',
          content: contentBlocks.length > 0 ? contentBlocks : msg.content,
          model: (msg.metadata?.model ?? msg.metadata?.provider) as string | undefined,
          usage,
        },
      });
      prevUuid = uuid;

      // If there are tool calls, synthesize a "user" event with tool_result blocks
      if (toolCalls.length > 0) {
        const resultUuid = makeUuid(i, 'tool-result');
        const resultBlocks: ContentBlock[] = [];

        for (const tc of toolCalls) {
          const resultText = tc.error
            ? `Error: ${tc.error}`
            : stringifyResult(tc.result);

          resultBlocks.push({
            type: 'tool_result',
            tool_use_id: tc.id,
            content: resultText,
          });
        }

        events.push({
          uuid: resultUuid,
          parentUuid: uuid,
          type: 'user',
          timestamp: msg.timestamp,
          message: {
            role: 'user',
            content: resultBlocks,
          },
        });
        prevUuid = resultUuid;
      }
    }
  }

  return {
    sessionId,
    events,
    subagents: {},
  };
}
