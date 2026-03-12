import { create } from 'zustand';
import type { TraceSessionInfo, SessionData } from '../types/trace';
import { fetchTraceProjects, fetchTraceSessions, fetchTraceSession } from '../api/traces';
import { adaptOpenDevMessages } from '../utils/trace/adapter';

interface TraceState {
  projects: string[];
  selectedProject: string | null;
  sessions: TraceSessionInfo[];
  selectedSessionId: string | null;
  sessionData: SessionData | null;
  loading: boolean;
  error: string | null;

  loadProjects: () => Promise<void>;
  selectProject: (project: string) => Promise<void>;
  selectSession: (sessionId: string) => Promise<void>;
  clearSelection: () => void;
}

export const useTraceStore = create<TraceState>((set, get) => ({
  projects: [],
  selectedProject: null,
  sessions: [],
  selectedSessionId: null,
  sessionData: null,
  loading: false,
  error: null,

  loadProjects: async () => {
    try {
      const projects = await fetchTraceProjects();
      set({ projects });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  selectProject: async (project: string) => {
    set({
      selectedProject: project,
      sessions: [],
      selectedSessionId: null,
      sessionData: null,
      loading: true,
      error: null,
    });
    try {
      const sessions = await fetchTraceSessions(project);
      set({ sessions, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  selectSession: async (sessionId: string) => {
    const { selectedProject } = get();
    if (!selectedProject) return;

    set({ selectedSessionId: sessionId, loading: true, error: null });
    try {
      const messages = await fetchTraceSession(selectedProject, sessionId);
      const sessionData = adaptOpenDevMessages(messages, sessionId);
      set({ sessionData, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  clearSelection: () => {
    set({ selectedSessionId: null, sessionData: null });
  },
}));
