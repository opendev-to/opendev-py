import { memo } from 'react';
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import type { CollapsedNodeData, NodeEventType } from '../../types/trace';
import { getToolNames } from '../../types/trace';

export type CollapsedFlowNode = Node<CollapsedNodeData, 'collapsedNode'>;

const TYPE_DOT_CLASSES: Record<NodeEventType, string> = {
  user: 'bg-accent-secondary-100',
  assistant: 'bg-success-100',
  'tool-call': 'bg-accent-main-100',
  'task-call': 'bg-warning-100',
  'subagent-user': 'bg-purple-500',
  'subagent-assistant': 'bg-indigo-500',
  'hook-progress': 'bg-gray-400',
  summary: 'bg-gray-400',
};

function CollapsedNodeComponent({ data, selected }: NodeProps<CollapsedFlowNode>) {
  const nodeHeight = (data.nodeHeight as number | undefined) ?? 80;

  const typeCounts: Record<string, number> = {};
  for (const ev of data.events) {
    const t = ev.eventType;
    typeCounts[t] = (typeCounts[t] ?? 0) + 1;
  }

  const allToolNames = data.events.flatMap(ev => getToolNames(ev));
  const uniqueTools = Array.from(new Set(allToolNames));
  const maxTools = Math.max(3, Math.floor((nodeHeight - 60) / 16));
  const shownTools = uniqueTools.slice(0, maxTools);
  const extraTools = uniqueTools.length - shownTools.length;

  return (
    <div
      className={`w-[260px] bg-bg-200 border-2 border-dashed rounded-lg px-2.5 py-2 font-mono text-[11px] cursor-pointer relative overflow-hidden flex flex-col ${
        selected ? 'border-accent-main-100 ring-2 ring-accent-main-100 shadow-lg' : 'border-border-300/50 shadow-sm'
      }`}
      style={{ height: nodeHeight, boxSizing: 'border-box' }}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!w-2 !h-2 !bg-gray-400"
      />

      <div className="flex items-center gap-1.5 mb-1.5 shrink-0">
        <span className="bg-bg-300 border border-border-300/30 text-text-400 rounded-full px-2 text-[10px] font-bold">
          {data.count} events
        </span>
        {data.subagentId && (
          <span className="text-text-400 text-[9px] ml-auto">
            sub:{data.subagentId.slice(0, 7)}
          </span>
        )}
      </div>

      <div className={`flex flex-wrap gap-1 shrink-0 ${shownTools.length > 0 ? 'mb-1.5' : ''}`}>
        {Object.entries(typeCounts).map(([type, count]) => (
          <span
            key={type}
            className="inline-flex items-center gap-1 bg-bg-300 border border-border-300/30 rounded px-1.5 text-[9px] text-text-400"
          >
            <span
              className={`w-[5px] h-[5px] rounded-full shrink-0 ${TYPE_DOT_CLASSES[type as NodeEventType] ?? 'bg-gray-400'}`}
            />
            {type.replace('subagent-', 'sa-')}: {count}
          </span>
        ))}
      </div>

      {shownTools.length > 0 && (
        <div className="flex flex-wrap gap-1 overflow-hidden">
          {shownTools.map((tool, i) => (
            <span
              key={i}
              className="bg-bg-100 border border-border-300/20 text-text-400 rounded px-1.5 text-[9px]"
            >
              {tool}
            </span>
          ))}
          {extraTools > 0 && (
            <span className="text-text-400 text-[9px]">+{extraTools}</span>
          )}
        </div>
      )}

      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2 !h-2 !bg-gray-400"
      />
    </div>
  );
}

export const CollapsedNode = memo(CollapsedNodeComponent);
