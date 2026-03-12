import { memo } from 'react';
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import type { ToolNodeData } from '../../types/trace';

export type ToolFlowNode = Node<ToolNodeData, 'toolNode'>;

function ToolNodeComponent({ data, selected }: NodeProps<ToolFlowNode>) {
  const toolCount = data.tools.length;

  return (
    <div
      className={`w-[260px] min-h-[90px] bg-bg-000 border-2 border-accent-main-100 rounded-lg px-2.5 py-2 font-mono text-[11px] cursor-pointer relative overflow-hidden hover-lift ${
        selected ? 'ring-2 ring-accent-main-100 shadow-lg' : 'shadow-sm'
      }`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!w-2 !h-2 !bg-accent-main-100"
      />

      <div className="flex items-center gap-1.5 mb-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-accent-main-100 shrink-0" />
        <span className="text-accent-main-100 font-bold text-[10px] tracking-wider">
          TOOL{toolCount > 1 ? ` \u00d7${toolCount}` : ''}
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

      <div className="flex flex-wrap gap-1 mb-1.5">
        {data.tools.slice(0, 4).map((tool, i) => (
          <span
            key={i}
            className="bg-bg-200 border border-accent-main-100/30 text-accent-main-100 rounded px-1.5 text-[9px] font-semibold"
          >
            {tool.name}
          </span>
        ))}
        {data.tools.length > 4 && (
          <span className="text-text-400 text-[9px]">+{data.tools.length - 4}</span>
        )}
      </div>

      {data.tools[0]?.result && (
        <div className="text-text-400 text-[10px] leading-[1.4] overflow-hidden line-clamp-2 border-t border-border-300/20 pt-1">
          {data.tools[0].result.replace(/\n+/g, ' ').slice(0, 120)}
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
        className="!w-2 !h-2 !bg-accent-main-100"
      />
    </div>
  );
}

export const ToolNode = memo(ToolNodeComponent);
