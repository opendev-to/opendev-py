import { memo } from 'react';
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import type { TaskNodeData } from '../../types/trace';

export type TaskFlowNode = Node<TaskNodeData, 'taskNode'>;

function TaskNodeComponent({ data, selected }: NodeProps<TaskFlowNode>) {
  const taskCount = data.tools.length;

  return (
    <div
      className={`w-[260px] min-h-[90px] bg-bg-000 border-2 border-warning-100 rounded-lg px-2.5 py-2 font-mono text-[11px] cursor-pointer relative overflow-hidden hover-lift ${
        selected ? 'ring-2 ring-accent-main-100 shadow-lg' : 'shadow-sm'
      }`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!w-2 !h-2 !bg-warning-100"
      />

      <div className="flex items-center gap-1.5 mb-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-warning-100 shrink-0" />
        <span className="text-warning-100 font-bold text-[10px] tracking-wider">
          TASK{taskCount > 1 ? ` \u00d7${taskCount}` : ''}
        </span>
        {data.subagentType && (
          <span className="bg-bg-200 border border-warning-100/30 text-warning-100 rounded px-1.5 text-[9px] font-semibold">
            {data.subagentType}
          </span>
        )}
        {data.spawnedSubagentId && (
          <span className="text-text-400 text-[9px] ml-auto">
            ↳ {data.spawnedSubagentId.slice(0, 7)}
          </span>
        )}
      </div>

      <div className="text-text-200 text-[11px] leading-[1.4] overflow-hidden line-clamp-3">
        {data.taskDescription
          ? data.taskDescription.replace(/\n+/g, ' ').slice(0, 160)
          : <span className="text-text-400 italic">(no description)</span>
        }
      </div>

      {data.tools[0]?.result && (
        <div className="text-text-400 text-[10px] leading-[1.4] overflow-hidden line-clamp-1 border-t border-border-300/20 pt-1 mt-1">
          {data.tools[0].result.replace(/\n+/g, ' ').slice(0, 100)}
        </div>
      )}

      {data.timestamp && (
        <div className="text-text-400 text-[9px] mt-1">
          {new Date(data.timestamp).toLocaleTimeString()}
        </div>
      )}

      <Handle
        id="source-right"
        type="source"
        position={Position.Right}
        className="!w-2 !h-2 !bg-warning-100"
      />
      <Handle
        id="source-bottom"
        type="source"
        position={Position.Bottom}
        className="!w-2 !h-2 !bg-warning-100"
      />
    </div>
  );
}

export const TaskNode = memo(TaskNodeComponent);
