import { useEffect } from 'react';
import { useTraceStore } from '../../stores/trace';
import type { TraceSessionInfo } from '../../types/trace';

function formatProjectName(name: string): string {
  const parts = name.replace(/^-/, '').split('-');
  return parts[parts.length - 1] || name;
}

function formatTimestamp(ts?: string): string {
  if (!ts) return '';
  const d = new Date(ts);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function TraceProjectSidebar() {
  const projects = useTraceStore(s => s.projects);
  const selectedProject = useTraceStore(s => s.selectedProject);
  const sessions = useTraceStore(s => s.sessions);
  const selectedSessionId = useTraceStore(s => s.selectedSessionId);
  const loading = useTraceStore(s => s.loading);
  const loadProjects = useTraceStore(s => s.loadProjects);
  const selectProject = useTraceStore(s => s.selectProject);
  const selectSession = useTraceStore(s => s.selectSession);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  return (
    <div className="w-60 h-full bg-bg-100 border-r border-border-300/20 flex flex-col font-sans shrink-0">
      {/* Projects */}
      <div className="py-3 flex flex-col">
        <div className="px-4 mb-1.5 text-[10px] font-bold text-text-400 uppercase tracking-wider flex items-center gap-1.5">
          Projects
        </div>
        {projects.length === 0 && (
          <div className="px-4 text-[11px] text-text-400 italic">No projects found</div>
        )}
        {projects.map(p => (
          <button
            key={p}
            onClick={() => selectProject(p)}
            className={`flex items-center gap-2 px-4 py-1.5 w-full text-left border-none cursor-pointer font-sans text-xs ${
              selectedProject === p
                ? 'bg-accent-main-100/10 text-text-000 border-l-2 border-l-accent-main-100'
                : 'bg-transparent text-text-200 border-l-2 border-l-transparent hover:bg-bg-200'
            }`}
            title={p}
          >
            <span className="text-xs shrink-0">📁</span>
            <span className="overflow-hidden text-ellipsis whitespace-nowrap flex-1">
              {formatProjectName(p)}
            </span>
          </button>
        ))}
      </div>

      {/* Sessions */}
      {selectedProject && (
        <div className="py-3 flex flex-col flex-1 overflow-y-auto border-t border-border-300/20">
          <div className="px-4 mb-1.5 text-[10px] font-bold text-text-400 uppercase tracking-wider flex items-center gap-1.5">
            Sessions
            {sessions.length > 0 && (
              <span className="bg-bg-200 text-text-400 rounded-full px-1.5 text-[9px]">
                {sessions.length}
              </span>
            )}
          </div>
          {loading && !selectedSessionId && (
            <div className="px-4 text-[11px] text-text-400 italic">Loading\u2026</div>
          )}
          {sessions.map((s: TraceSessionInfo) => (
            <button
              key={s.session_id}
              onClick={() => selectSession(s.session_id)}
              className={`flex flex-col px-4 py-2 w-full text-left border-none cursor-pointer font-sans gap-0.5 ${
                selectedSessionId === s.session_id
                  ? 'bg-accent-main-100/10 border-l-2 border-l-success-100'
                  : 'bg-transparent border-l-2 border-l-transparent hover:bg-bg-200'
              }`}
            >
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] font-semibold text-text-200 overflow-hidden text-ellipsis whitespace-nowrap flex-1 font-mono">
                  {s.title || s.session_id.slice(0, 12)}
                </span>
              </div>
              <div className="text-[10px] text-text-400 font-mono">
                <span>{s.message_count} msgs</span>
                {s.timestamp && (
                  <span className="ml-1.5">{formatTimestamp(s.timestamp)}</span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
