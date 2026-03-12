import { useCallback, useEffect, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type ReactFlowInstance,
  type Edge,
  type Node,
} from '@xyflow/react';
import type { SessionData, TraceNodeData, ToolNodeData, TaskNodeData, CollapsedNodeData } from '../../types/trace';
import { buildGraph, layoutGraph, mergeToolCallNodes } from '../../utils/trace/buildGraph';
import { collapseGraph, type AnyFlowNode } from '../../utils/trace/collapseGraph';
import { TraceNode } from './TraceNode';
import { CollapsedNode } from './CollapsedNode';
import { ToolNode } from './ToolNode';
import { TaskNode } from './TaskNode';
import { NodeDetail } from './NodeDetail';
import { LinearTracePanel } from './LinearTracePanel';
import { SearchPanel } from './SearchPanel';

const nodeTypes = {
  traceNode: TraceNode,
  collapsedNode: CollapsedNode,
  toolNode: ToolNode,
  taskNode: TaskNode,
};

interface Props {
  sessionData: SessionData | null;
  loading: boolean;
}

const NODE_TYPE_COLORS: Record<string, string> = {
  user: 'hsl(var(--accent-secondary-100))',
  assistant: 'hsl(var(--success-100))',
  'tool-call': 'hsl(var(--accent-main-100))',
  'task-call': 'hsl(var(--warning-100))',
  'subagent-user': '#a855f7',
  'subagent-assistant': '#818cf8',
  'hook-progress': '#9ca3af',
  summary: '#9ca3af',
};

const NODE_TYPE_DOT_CLASSES: Record<string, string> = {
  user: 'bg-accent-secondary-100',
  assistant: 'bg-success-100',
  'tool-call': 'bg-accent-main-100',
  'task-call': 'bg-warning-100',
  'subagent-user': 'bg-purple-500',
  'subagent-assistant': 'bg-indigo-500',
  'hook-progress': 'bg-gray-400',
  summary: 'bg-gray-400',
};

export function DAGView({ sessionData, loading }: Props) {
  const [nodes, setNodes, onNodesChange] = useNodesState<AnyFlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance<AnyFlowNode> | null>(null);
  const [selectedChain, setSelectedChain] = useState<CollapsedNodeData | null>(null);
  const [selectedEventIndex, setSelectedEventIndex] = useState<number | null>(null);
  const [directSelectedData, setDirectSelectedData] = useState<TraceNodeData | ToolNodeData | TaskNodeData | null>(null);

  const [stats, setStats] = useState<{
    total: number;
    chains: number;
    junctions: number;
    byType: Record<string, number>;
  }>({ total: 0, chains: 0, junctions: 0, byType: {} });

  useEffect(() => {
    if (!sessionData) {
      setNodes([]);
      setEdges([]);
      setSelectedChain(null);
      setSelectedEventIndex(null);
      setDirectSelectedData(null);
      setStats({ total: 0, chains: 0, junctions: 0, byType: {} });
      return;
    }

    const { nodes: rawNodes, edges: rawEdges } = buildGraph(sessionData);
    const { nodes: mergedNodes, edges: mergedEdges } = mergeToolCallNodes(rawNodes, rawEdges);
    const { nodes: collapsedNodes, edges: collapsedEdges } = collapseGraph(mergedNodes, mergedEdges);
    const { nodes: layouted, edges: layoutedEdges } = layoutGraph(collapsedNodes, collapsedEdges);

    const byType: Record<string, number> = {};
    rawNodes.forEach(n => {
      const t = n.data.eventType;
      byType[t] = (byType[t] || 0) + 1;
    });

    const chainCount = collapsedNodes.filter(n => n.type === 'collapsedNode').length;
    const junctionCount = collapsedNodes.filter(n => n.type === 'traceNode').length;

    setNodes(layouted);
    setEdges(layoutedEdges);
    setSelectedChain(null);
    setSelectedEventIndex(null);
    setDirectSelectedData(null);
    setStats({ total: rawNodes.length, chains: chainCount, junctions: junctionCount, byType });
  }, [sessionData, setNodes, setEdges]);

  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    if (node.type === 'collapsedNode') {
      setSelectedChain(node.data as CollapsedNodeData);
      setSelectedEventIndex(null);
      setDirectSelectedData(null);
    } else if (node.type === 'toolNode') {
      setDirectSelectedData(node.data as ToolNodeData);
      setSelectedChain(null);
      setSelectedEventIndex(null);
    } else if (node.type === 'taskNode') {
      setDirectSelectedData(node.data as TaskNodeData);
      setSelectedChain(null);
      setSelectedEventIndex(null);
    } else {
      setDirectSelectedData(node.data as TraceNodeData);
      setSelectedChain(null);
      setSelectedEventIndex(null);
    }
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedChain(null);
    setSelectedEventIndex(null);
    setDirectSelectedData(null);
  }, []);

  const handleSelectEvent = useCallback((i: number) => {
    setSelectedEventIndex(i);
  }, []);

  const handleCloseLinearPanel = useCallback(() => {
    setSelectedChain(null);
    setSelectedEventIndex(null);
  }, []);

  const handleCloseDetail = useCallback(() => {
    setSelectedEventIndex(null);
    setDirectSelectedData(null);
  }, []);

  const handleSearchSelect = useCallback((nodeId: string, eventIndex?: number) => {
    const node = nodes.find(n => n.id === nodeId);
    if (!node) return;

    if (node.type === 'collapsedNode') {
      setSelectedChain(node.data as CollapsedNodeData);
      setSelectedEventIndex(eventIndex ?? null);
      setDirectSelectedData(null);
    } else if (node.type === 'toolNode') {
      setDirectSelectedData(node.data as ToolNodeData);
      setSelectedChain(null);
      setSelectedEventIndex(null);
    } else if (node.type === 'taskNode') {
      setDirectSelectedData(node.data as TaskNodeData);
      setSelectedChain(null);
      setSelectedEventIndex(null);
    } else {
      setDirectSelectedData(node.data as TraceNodeData);
      setSelectedChain(null);
      setSelectedEventIndex(null);
    }

    setNodes(nds => nds.map(n => ({ ...n, selected: n.id === nodeId })));
    rfInstance?.fitView({ nodes: [{ id: nodeId }], duration: 300, padding: 0.5 });
  }, [nodes, rfInstance, setNodes]);

  const detailData: TraceNodeData | ToolNodeData | TaskNodeData | null =
    selectedChain && selectedEventIndex !== null
      ? (selectedChain.events[selectedEventIndex] ?? null)
      : directSelectedData;

  if (loading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-bg-100 font-sans">
        <div className="w-8 h-8 border-[3px] border-border-300/30 border-t-accent-secondary-100 rounded-full animate-spin" />
        <span className="text-text-400 mt-3 text-[13px]">Loading trace\u2026</span>
      </div>
    );
  }

  if (!sessionData) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-bg-100 font-sans">
        <div className="text-5xl mb-4 opacity-20">\u25c8</div>
        <span className="text-text-400 text-sm">Select a session to visualize its trace DAG</span>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-bg-100">
      {/* Stats bar */}
      <div className="flex items-center gap-3 px-4 py-1.5 bg-bg-200 border-b border-border-300/20 font-sans shrink-0">
        <span className="text-[11px] font-bold text-text-200">{stats.total} events</span>
        <span className="text-[10px] text-text-400">
          {stats.chains} chains \u00b7 {stats.junctions} junctions
        </span>
        {Object.entries(stats.byType).map(([type, count]) => (
          <span key={type} className="text-[10px] text-text-400 flex items-center">
            <span
              className={`inline-block w-1.5 h-1.5 rounded-full mr-1 ${NODE_TYPE_DOT_CLASSES[type] || 'bg-gray-400'}`}
            />
            {type}: {count}
          </span>
        ))}
        <span className="ml-auto text-text-400 text-[10px] font-mono">
          {sessionData.sessionId.slice(0, 16)}\u2026
        </span>
      </div>

      {/* Main layout */}
      <div className="flex flex-1 overflow-hidden">
        <SearchPanel nodes={nodes} onSelectNode={handleSearchSelect} />
        <div className="flex-1 react-flow-wrapper">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            onInit={setRfInstance}
            nodeTypes={nodeTypes}
            nodesDraggable={false}
            fitView
            fitViewOptions={{ padding: 0.2, maxZoom: 1.5 }}
            minZoom={0.05}
            maxZoom={3}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="hsl(var(--border-300) / 0.3)" gap={24} size={1} />
            <Controls />
            <MiniMap
              nodeColor={(n) => {
                if (n.type === 'collapsedNode') return 'hsl(var(--border-300))';
                const data = n.data as TraceNodeData | ToolNodeData | TaskNodeData;
                return NODE_TYPE_COLORS[data?.eventType] || '#9ca3af';
              }}
              maskColor="rgba(255,255,255,0.6)"
            />
          </ReactFlow>
        </div>

        {selectedChain && (
          <LinearTracePanel
            events={selectedChain.events}
            selectedIndex={selectedEventIndex}
            onSelectEvent={handleSelectEvent}
            onClose={handleCloseLinearPanel}
          />
        )}

        {detailData && (
          <NodeDetail data={detailData} onClose={handleCloseDetail} />
        )}
      </div>
    </div>
  );
}
