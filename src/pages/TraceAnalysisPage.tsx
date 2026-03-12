import { TopBar } from '../components/Layout/TopBar';
import { TraceProjectSidebar } from '../components/TraceAnalysis/TraceProjectSidebar';
import { DAGView } from '../components/TraceAnalysis/DAGView';
import { useTraceStore } from '../stores/trace';

export function TraceAnalysisPage() {
  const sessionData = useTraceStore(s => s.sessionData);
  const loading = useTraceStore(s => s.loading);
  const selectedSessionId = useTraceStore(s => s.selectedSessionId);

  return (
    <div className="h-screen flex flex-col bg-bg-100">
      <TopBar />
      <div className="flex-1 flex overflow-hidden">
        <TraceProjectSidebar />
        <main className="flex-1 flex flex-col overflow-hidden bg-bg-000">
          <DAGView
            sessionData={selectedSessionId ? sessionData : null}
            loading={loading && !!selectedSessionId}
          />
        </main>
      </div>
    </div>
  );
}
