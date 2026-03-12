import { useEffect, useRef } from 'react';
import type { AnyNodeData, NodeEventType } from '../../types/trace';
import { getToolNames } from '../../types/trace';

interface Props {
  events: AnyNodeData[];
  selectedIndex: number | null;
  onSelectEvent: (i: number) => void;
  onClose: () => void;
}

const TYPE_CONFIG: Record<NodeEventType, { dotClass: string; label: string }> = {
  user: { dotClass: 'bg-accent-secondary-100', label: 'USER' },
  assistant: { dotClass: 'bg-success-100', label: 'ASST' },
  'tool-call': { dotClass: 'bg-accent-main-100', label: 'TOOL' },
  'task-call': { dotClass: 'bg-warning-100', label: 'TASK' },
  'subagent-user': { dotClass: 'bg-purple-500', label: 'SA-U' },
  'subagent-assistant': { dotClass: 'bg-indigo-500', label: 'SA-A' },
  'hook-progress': { dotClass: 'bg-gray-400', label: 'HOOK' },
  summary: { dotClass: 'bg-gray-400', label: 'SUM' },
};

export function LinearTracePanel({ events, selectedIndex, onSelectEvent, onClose }: Props) {
  const rowRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  useEffect(() => {
    if (selectedIndex === null) return;
    const el = rowRefs.current.get(selectedIndex);
    if (el) {
      el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [selectedIndex]);

  return (
    <div className="w-[280px] h-full bg-bg-100 border-l border-border-300/20 flex flex-col font-sans text-[11px] text-text-200 overflow-hidden shrink-0">
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-border-300/20 bg-bg-000 shrink-0">
        <span className="font-bold text-[11px] text-text-400 tracking-wider uppercase">
          Chain ({events.length} events)
        </span>
        <button onClick={onClose} className="bg-transparent border-none text-text-400 cursor-pointer text-[13px] px-1.5 py-0.5 rounded leading-none hover:text-text-000">
          ✕
        </button>
      </div>

      <div className="overflow-y-auto flex-1">
        {events.map((ev, i) => {
          const cfg = TYPE_CONFIG[ev.eventType] ?? TYPE_CONFIG.user;
          const isSelected = i === selectedIndex;
          const preview = ev.preview
            ? ev.preview.replace(/\n+/g, ' ').slice(0, 120)
            : '(empty)';
          const tools = getToolNames(ev);

          return (
            <div
              key={i}
              ref={(el) => { if (el) rowRefs.current.set(i, el); else rowRefs.current.delete(i); }}
              onClick={() => onSelectEvent(i)}
              className={`flex gap-2 py-1.5 px-2.5 border-b border-border-300/10 cursor-pointer items-start ${
                isSelected ? 'bg-bg-200 border-l-[3px] border-l-accent-main-100' : 'bg-transparent border-l-[3px] border-l-transparent hover:bg-bg-200/50'
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full shrink-0 mt-0.5 ${cfg.dotClass}`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 mb-0.5">
                  <span className={`font-mono text-[9px] font-bold tracking-wider shrink-0 ${isSelected ? 'text-text-200' : 'text-text-400'}`}>
                    {cfg.label}
                  </span>
                  {tools.length > 0 && (
                    <span className="text-[9px] text-text-400 font-mono overflow-hidden text-ellipsis whitespace-nowrap flex-1">
                      {tools.slice(0, 2).join(', ')}{tools.length > 2 ? `+${tools.length - 2}` : ''}
                    </span>
                  )}
                  {ev.timestamp && (
                    <span className="text-[9px] text-text-400 ml-auto shrink-0 font-mono">
                      {new Date(ev.timestamp).toLocaleTimeString()}
                    </span>
                  )}
                </div>
                <div className="text-text-400 text-[10px] leading-[1.4] overflow-hidden line-clamp-2">
                  {preview || <em className="text-text-400">(no content)</em>}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
