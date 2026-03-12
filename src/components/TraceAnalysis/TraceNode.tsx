import { memo } from 'react';
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import type { TraceNodeData, NodeEventType } from '../../types/trace';

export type TraceFlowNode = Node<TraceNodeData, 'traceNode'>;

const TYPE_CONFIG: Record<NodeEventType, { label: string; borderClass: string; dotClass: string }> = {
  'user': {
    label: 'USER',
    borderClass: 'border-accent-secondary-100',
    dotClass: 'bg-accent-secondary-100',
  },
  'assistant': {
    label: 'ASSISTANT',
    borderClass: 'border-success-100',
    dotClass: 'bg-success-100',
  },
  'tool-call': {
    label: 'TOOL',
    borderClass: 'border-accent-main-100',
    dotClass: 'bg-accent-main-100',
  },
  'task-call': {
    label: 'TASK',
    borderClass: 'border-warning-100',
    dotClass: 'bg-warning-100',
  },
  'subagent-user': {
    label: 'SUBAGENT USER',
    borderClass: 'border-purple-500',
    dotClass: 'bg-purple-500',
  },
  'subagent-assistant': {
    label: 'SUBAGENT',
    borderClass: 'border-indigo-500',
    dotClass: 'bg-indigo-500',
  },
  'hook-progress': {
    label: 'HOOK',
    borderClass: 'border-gray-400',
    dotClass: 'bg-gray-400',
  },
  'summary': {
    label: 'SUMMARY',
    borderClass: 'border-gray-400',
    dotClass: 'bg-gray-400',
  },
};

function TraceNodeComponent({ data, selected }: NodeProps<TraceFlowNode>) {
  const config = TYPE_CONFIG[data.eventType] ?? TYPE_CONFIG['user'];
  const preview = data.preview
    ? data.preview.replace(/\n+/g, ' ').slice(0, 120)
    : '';

  return (
    <div
      className={`w-[260px] min-h-[90px] bg-bg-000 border-2 rounded-lg px-2.5 py-2 font-mono text-[11px] cursor-pointer relative overflow-hidden hover-lift ${config.borderClass} ${
        selected ? 'ring-2 ring-accent-main-100 shadow-lg' : 'shadow-sm'
      }`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className={`!w-2 !h-2 ${config.dotClass}`}
      />

      <div className="flex items-center gap-1.5 mb-1.5">
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${config.dotClass}`} />
        <span className="text-text-200 font-bold text-[10px] tracking-wider">
          {config.label}
        </span>
        {data.agentId && (
          <span className="text-text-400 text-[9px] ml-auto">
            agent:{data.agentId.slice(0, 7)}
          </span>
        )}
        {data.subagentId && !data.agentId && (
          <span className="text-text-400 text-[9px] ml-auto">
            sub:{data.subagentId.slice(0, 7)}
          </span>
        )}
      </div>

      <div className="text-text-200 text-[11px] leading-[1.4] overflow-hidden line-clamp-3">
        {preview || <span className="text-text-400 italic">(no content)</span>}
      </div>

      {data.tools.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {data.tools.slice(0, 4).map((tool, i) => (
            <span
              key={i}
              className="bg-bg-200 border border-border-300/20 text-text-400 rounded px-1.5 text-[9px] font-semibold"
            >
              {tool}
            </span>
          ))}
          {data.tools.length > 4 && (
            <span className="text-text-400 text-[9px]">+{data.tools.length - 4}</span>
          )}
        </div>
      )}

      {data.timestamp && (
        <div className="text-text-400 text-[9px] mt-1">
          {new Date(data.timestamp).toLocaleTimeString()}
        </div>
      )}

      <Handle
        type="source"
        position={Position.Bottom}
        className={`!w-2 !h-2 ${config.dotClass}`}
      />
    </div>
  );
}

export const TraceNode = memo(TraceNodeComponent);
