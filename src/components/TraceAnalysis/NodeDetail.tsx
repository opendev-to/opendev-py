import { useState } from 'react';
import type { TraceNodeData, ToolNodeData, TaskNodeData } from '../../types/trace';
import type { ContentBlock } from '../../types/trace';

function toYaml(val: unknown, depth = 0): string {
  const ind = '  '.repeat(depth);
  const ind1 = '  '.repeat(depth + 1);

  if (val === null || val === undefined) return 'null';
  if (typeof val === 'boolean') return val ? 'true' : 'false';
  if (typeof val === 'number') return Number.isFinite(val) ? String(val) : 'null';

  if (typeof val === 'string') {
    if (val === '') return '""';
    if (val.includes('\n')) {
      return `|\n${val.split('\n').map(l => ind1 + l).join('\n')}`;
    }
    const needsQuote = /^[\s:#\-\[\]{},&*!|>'"%@`?]/.test(val)
      || /^(true|false|null|yes|no|on|off|\d)/.test(val)
      || /\s$/.test(val);
    return needsQuote ? JSON.stringify(val) : val;
  }

  if (Array.isArray(val)) {
    if (val.length === 0) return '[]';
    return val.map(item => {
      if (item !== null && typeof item === 'object') {
        const lines = toYaml(item, depth + 1).split('\n');
        const first = lines[0].slice(ind1.length);
        const rest = lines.slice(1).join('\n');
        return rest ? `${ind}- ${first}\n${rest}` : `${ind}- ${first}`;
      }
      return `${ind}- ${toYaml(item, 0)}`;
    }).join('\n');
  }

  if (typeof val === 'object') {
    const entries = Object.entries(val as Record<string, unknown>).filter(([, v]) => v !== undefined);
    if (entries.length === 0) return '{}';
    return entries.map(([k, v]) => {
      if (typeof v === 'string' && v.includes('\n')) {
        return `${ind}${k}: ${toYaml(v, depth + 1)}`;
      }
      if (v !== null && typeof v === 'object') {
        const s = toYaml(v, depth + 1);
        const isEmpty = Array.isArray(v) ? (v as unknown[]).length === 0 : Object.keys(v as object).length === 0;
        return isEmpty ? `${ind}${k}: ${s}` : `${ind}${k}:\n${s}`;
      }
      return `${ind}${k}: ${toYaml(v, 0)}`;
    }).join('\n');
  }

  return String(val);
}

interface Props {
  data: TraceNodeData | ToolNodeData | TaskNodeData | null;
  onClose: () => void;
}

function renderThinking(content: string | ContentBlock[] | undefined): React.ReactNode {
  const blocks = Array.isArray(content) ? content.filter(b => b.type === 'thinking') : [];
  if (blocks.length === 0) return <em className="text-text-400">No thinking</em>;
  return blocks.map((block, i) => (
    <pre key={i} className="m-0 p-2 bg-bg-300 border border-purple-300/30 rounded text-[11px] leading-relaxed text-purple-700 font-mono whitespace-pre-wrap break-words overflow-wrap-anywhere mb-2 last:mb-0">
      {block.thinking || ''}
    </pre>
  ));
}

function renderContent(content: string | ContentBlock[] | undefined): React.ReactNode {
  if (!content) return <em className="text-text-400">No content</em>;
  if (typeof content === 'string') {
    return <pre className="m-0 p-2 bg-bg-300 border border-border-300/20 rounded text-[11px] leading-relaxed text-text-200 font-mono whitespace-pre-wrap break-words overflow-wrap-anywhere">{content}</pre>;
  }

  const nonThinking = content.filter(b => b.type !== 'thinking');
  if (nonThinking.length === 0) return <em className="text-text-400">No content</em>;

  return nonThinking.map((block, i) => {
    if (block.type === 'text') {
      return (
        <div key={i} className="mb-2">
          <pre className="m-0 p-2 bg-bg-300 border border-border-300/20 rounded text-[11px] leading-relaxed text-text-200 font-mono whitespace-pre-wrap break-words overflow-wrap-anywhere">{block.text}</pre>
        </div>
      );
    }
    if (block.type === 'tool_use') {
      return (
        <div key={i} className="mb-2 border border-accent-secondary-100/20 rounded-md overflow-hidden bg-bg-100">
          <div className="flex items-center gap-2 px-2 py-1 bg-bg-200 border-b border-border-300/20">
            <span className="text-[9px] font-bold tracking-wider text-accent-secondary-100">TOOL CALL</span>
            <span className="text-[11px] font-semibold text-accent-secondary-100 font-mono">{block.name}</span>
            <span className="text-[9px] text-text-400 ml-auto font-mono">{block.id?.slice(-8)}</span>
          </div>
          <pre className="m-0 p-2 text-[11px] leading-relaxed text-text-200 font-mono whitespace-pre-wrap break-words overflow-wrap-anywhere">{JSON.stringify(block.input, null, 2)}</pre>
        </div>
      );
    }
    if (block.type === 'tool_result') {
      const resultContent = block.content;
      const text = typeof resultContent === 'string'
        ? resultContent
        : Array.isArray(resultContent)
          ? resultContent.map(b => (b as ContentBlock).text || '').join('\n')
          : '';
      return (
        <div key={i} className="mb-2 border border-accent-main-100/20 rounded-md overflow-hidden bg-bg-100">
          <div className="flex items-center gap-2 px-2 py-1 bg-bg-200 border-b border-border-300/20">
            <span className="text-[9px] font-bold tracking-wider text-accent-main-100">TOOL RESULT</span>
            <span className="text-[9px] text-text-400 ml-auto font-mono">{block.tool_use_id?.slice(-8)}</span>
          </div>
          <pre className="m-0 p-2 text-[11px] leading-relaxed text-text-200 font-mono whitespace-pre-wrap break-words overflow-wrap-anywhere max-h-[200px] overflow-y-auto">{text}</pre>
        </div>
      );
    }
    return null;
  });
}

export function NodeDetail({ data, onClose }: Props) {
  const [tab, setTab] = useState<'content' | 'raw'>('content');

  if (!data) return null;

  const { title, rawObject, bodyContent } = (() => {
    if (data.eventType === 'task-call') {
      const taskData = data as TaskNodeData;
      const aEvent = taskData.assistantEvent;
      return {
        title: 'Task Detail',
        rawObject: { assistantEvent: taskData.assistantEvent, userEvent: taskData.userEvent },
        bodyContent: (
          <>
            <div className="px-3.5 py-2 border-b border-border-300/20">
              <div className="flex flex-col gap-1">
                <MetaRow label="Type" value="task-call" />
                {taskData.subagentType && <MetaRow label="Subagent type" value={taskData.subagentType} />}
                {taskData.spawnedSubagentId && <MetaRow label="Spawned" value={taskData.spawnedSubagentId} mono />}
                {aEvent.uuid && <MetaRow label="UUID" value={aEvent.uuid.slice(0, 16) + '\u2026'} mono />}
                {aEvent.agentId && <MetaRow label="Agent ID" value={aEvent.agentId} mono />}
                {taskData.subagentId && <MetaRow label="Subagent" value={taskData.subagentId} mono />}
                {aEvent.timestamp && <MetaRow label="Time" value={new Date(aEvent.timestamp).toLocaleString()} />}
                {aEvent.message?.model && <MetaRow label="Model" value={aEvent.message.model} />}
                {aEvent.message?.usage && (
                  <MetaRow
                    label="Tokens"
                    value={`\u2191${aEvent.message.usage.input_tokens ?? 0} \u2193${aEvent.message.usage.output_tokens ?? 0}${aEvent.message.usage.cache_read_input_tokens ? ` cache\u2191${aEvent.message.usage.cache_read_input_tokens}` : ''}`}
                  />
                )}
              </div>
            </div>
            {taskData.tools.map((tool, i) => (
              <div key={i} className="px-3.5 py-2 border-b border-border-300/20">
                <div className="text-[10px] font-bold text-warning-100 tracking-wider uppercase mb-2">TASK PROMPT</div>
                <pre className="m-0 p-2 bg-bg-300 border border-border-300/20 rounded text-[11px] leading-relaxed text-text-200 font-mono whitespace-pre-wrap break-words overflow-wrap-anywhere">{taskData.taskDescription}</pre>
                {tool.result !== undefined && (
                  <div className="mt-2 border border-warning-100/20 rounded-md overflow-hidden bg-bg-100">
                    <div className="flex items-center gap-2 px-2 py-1 bg-bg-200 border-b border-border-300/20">
                      <span className="text-[9px] font-bold tracking-wider text-warning-100">RESULT</span>
                    </div>
                    <pre className="m-0 p-2 text-[11px] leading-relaxed text-text-200 font-mono whitespace-pre-wrap break-words overflow-wrap-anywhere max-h-[300px] overflow-y-auto">{tool.result}</pre>
                  </div>
                )}
              </div>
            ))}
          </>
        ),
      };
    }

    if (data.eventType === 'tool-call') {
      const toolData = data as ToolNodeData;
      const aEvent = toolData.assistantEvent;
      return {
        title: 'Tool Call Detail',
        rawObject: { assistantEvent: toolData.assistantEvent, userEvent: toolData.userEvent },
        bodyContent: (
          <>
            <div className="px-3.5 py-2 border-b border-border-300/20">
              <div className="flex flex-col gap-1">
                <MetaRow label="Type" value="tool-call" />
                <MetaRow label="Tools" value={toolData.tools.length.toString()} />
                {aEvent.uuid && <MetaRow label="UUID" value={aEvent.uuid.slice(0, 16) + '\u2026'} mono />}
                {aEvent.parentUuid && <MetaRow label="Parent" value={aEvent.parentUuid.slice(0, 16) + '\u2026'} mono />}
                {aEvent.agentId && <MetaRow label="Agent ID" value={aEvent.agentId} mono />}
                {toolData.subagentId && <MetaRow label="Subagent" value={toolData.subagentId} mono />}
                {aEvent.timestamp && <MetaRow label="Time" value={new Date(aEvent.timestamp).toLocaleString()} />}
                {aEvent.message?.model && <MetaRow label="Model" value={aEvent.message.model} />}
                {aEvent.message?.usage && (
                  <MetaRow
                    label="Tokens"
                    value={`\u2191${aEvent.message.usage.input_tokens ?? 0} \u2193${aEvent.message.usage.output_tokens ?? 0}${aEvent.message.usage.cache_read_input_tokens ? ` cache\u2191${aEvent.message.usage.cache_read_input_tokens}` : ''}`}
                  />
                )}
              </div>
            </div>
            {toolData.tools.map((tool, i) => (
              <div key={i} className="px-3.5 py-2 border-b border-border-300/20">
                <div className="mb-2 border border-accent-secondary-100/20 rounded-md overflow-hidden bg-bg-100">
                  <div className="flex items-center gap-2 px-2 py-1 bg-bg-200 border-b border-border-300/20">
                    <span className="text-[9px] font-bold tracking-wider text-accent-secondary-100">TOOL CALL</span>
                    <span className="text-[11px] font-semibold text-accent-secondary-100 font-mono">{tool.name}</span>
                    <span className="text-[9px] text-text-400 ml-auto font-mono">{tool.id.slice(-8)}</span>
                  </div>
                  <pre className="m-0 p-2 text-[11px] leading-relaxed text-text-200 font-mono whitespace-pre-wrap break-words overflow-wrap-anywhere">{JSON.stringify(tool.input, null, 2)}</pre>
                </div>
                {tool.result !== undefined && (
                  <div className="border border-accent-main-100/20 rounded-md overflow-hidden bg-bg-100">
                    <div className="flex items-center gap-2 px-2 py-1 bg-bg-200 border-b border-border-300/20">
                      <span className="text-[9px] font-bold tracking-wider text-accent-main-100">TOOL RESULT</span>
                    </div>
                    <pre className="m-0 p-2 text-[11px] leading-relaxed text-text-200 font-mono whitespace-pre-wrap break-words overflow-wrap-anywhere max-h-[200px] overflow-y-auto">{tool.result}</pre>
                  </div>
                )}
              </div>
            ))}
          </>
        ),
      };
    }

    const traceData = data as TraceNodeData;
    const event = traceData.event;
    const innerMsg = event.data?.message;
    return {
      title: 'Event Detail',
      rawObject: event,
      bodyContent: (
        <>
          <div className="px-3.5 py-2 border-b border-border-300/20">
            <div className="flex flex-col gap-1">
              <MetaRow label="Type" value={event.type} />
              {traceData.eventType !== event.type && <MetaRow label="Inner type" value={traceData.eventType} />}
              {event.uuid && <MetaRow label="UUID" value={event.uuid.slice(0, 16) + '\u2026'} mono />}
              {event.parentUuid && <MetaRow label="Parent" value={event.parentUuid.slice(0, 16) + '\u2026'} mono />}
              {event.agentId && <MetaRow label="Agent ID" value={event.agentId} mono />}
              {traceData.subagentId && <MetaRow label="Subagent" value={traceData.subagentId} mono />}
              {event.timestamp && <MetaRow label="Time" value={new Date(event.timestamp).toLocaleString()} />}
              {event.message?.model && <MetaRow label="Model" value={event.message.model} />}
              {event.message?.usage && (
                <MetaRow
                  label="Tokens"
                  value={`\u2191${event.message.usage.input_tokens ?? 0} \u2193${event.message.usage.output_tokens ?? 0}${event.message.usage.cache_read_input_tokens ? ` cache\u2191${event.message.usage.cache_read_input_tokens}` : ''}`}
                />
              )}
            </div>
          </div>
          {(traceData.eventType === 'assistant' || traceData.eventType === 'subagent-assistant') ? (
            <>
              <div className="px-3.5 py-2 border-b border-border-300/20">
                <div className="text-[10px] font-bold text-purple-600 tracking-wider uppercase mb-2">Thinking</div>
                {renderThinking(event.message?.content)}
              </div>
              <div className="px-3.5 py-2 border-b border-border-300/20">
                <div className="text-[10px] font-bold text-text-400 tracking-wider uppercase mb-2">Content</div>
                {renderContent(event.message?.content)}
              </div>
            </>
          ) : event.message?.content && (
            <div className="px-3.5 py-2 border-b border-border-300/20">
              <div className="text-[10px] font-bold text-text-400 tracking-wider uppercase mb-2">Content</div>
              {renderContent(event.message.content)}
            </div>
          )}
          {innerMsg && (
            <div className="px-3.5 py-2 border-b border-border-300/20">
              <div className="text-[10px] font-bold text-text-400 tracking-wider uppercase mb-2">
                Subagent message ({innerMsg.type})
                {innerMsg.message?.model && (
                  <span className="text-text-400 ml-2 text-[10px] normal-case font-normal">{innerMsg.message.model}</span>
                )}
              </div>
              {innerMsg.type === 'assistant' ? (
                <>
                  <div className="text-[10px] font-bold text-purple-600 tracking-wider uppercase mb-2 mt-1.5">Thinking</div>
                  {renderThinking(innerMsg.message?.content)}
                  <div className="text-[10px] font-bold text-text-400 tracking-wider uppercase mb-2 mt-2">Content</div>
                  {renderContent(innerMsg.message?.content)}
                </>
              ) : renderContent(innerMsg.message?.content)}
            </div>
          )}
        </>
      ),
    };
  })();

  return (
    <div className="w-[380px] h-full bg-bg-000 border-l border-border-300/30 flex flex-col font-sans text-xs text-text-200 overflow-hidden shrink-0">
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-border-300/20 bg-bg-000 shrink-0">
        <span className="font-bold text-xs text-text-400 tracking-wider uppercase">{title}</span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setTab('content')}
            className={`border text-[10px] font-semibold px-2 py-0.5 rounded tracking-wide cursor-pointer ${
              tab === 'content'
                ? 'bg-bg-200 text-text-200 border-border-300/30'
                : 'bg-transparent text-text-400 border-border-300/20'
            }`}
          >
            Content
          </button>
          <button
            onClick={() => setTab('raw')}
            className={`border text-[10px] font-semibold px-2 py-0.5 rounded tracking-wide cursor-pointer ${
              tab === 'raw'
                ? 'bg-bg-200 text-text-200 border-border-300/30'
                : 'bg-transparent text-text-400 border-border-300/20'
            }`}
          >
            Raw
          </button>
          <button onClick={onClose} className="bg-transparent border-none text-text-400 cursor-pointer text-sm px-1.5 py-0.5 rounded leading-none ml-1 hover:text-text-000">
            ✕
          </button>
        </div>
      </div>
      <div className="overflow-y-auto flex-1 py-2">
        {tab === 'raw'
          ? (
            <div className="px-3.5 py-2">
              <pre className="m-0 p-2 bg-bg-300 border border-border-300/20 rounded text-[11px] leading-relaxed text-text-200 font-mono whitespace-pre-wrap break-words overflow-wrap-anywhere">{toYaml(rawObject)}</pre>
            </div>
          )
          : bodyContent
        }
      </div>
    </div>
  );
}

function MetaRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex gap-2 items-start">
      <span className="text-text-400 w-[72px] shrink-0 text-[11px]">{label}</span>
      <span className={`text-text-200 text-[11px] break-all ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  );
}
