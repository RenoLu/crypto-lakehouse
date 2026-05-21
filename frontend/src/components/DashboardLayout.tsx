import { useEffect, useState, type ReactNode } from 'react';
import { RefreshCw } from 'lucide-react';
import { getPollingStatus, triggerPipeline } from '../api/client';

interface DashboardLayoutProps {
  children: ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  const [pollingEnabled, setPollingEnabled] = useState(false);
  const [pollingInterval, setPollingInterval] = useState(0);
  const [triggering, setTriggering] = useState(false);
  const [lastRun, setLastRun] = useState<string | null>(null);

  useEffect(() => {
    getPollingStatus()
      .then(s => {
        setPollingEnabled(s.enabled);
        setPollingInterval(s.interval_seconds);
      })
      .catch(() => {});
  }, []);

  async function handleTrigger() {
    setTriggering(true);
    try {
      const result = await triggerPipeline();
      setLastRun(result.timestamp);
    } catch {
      // ignore
    } finally {
      setTriggering(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-2xl">📊</span>
              <div>
                <h1 className="text-xl font-bold text-white">Crypto Lakehouse</h1>
                <p className="text-xs text-gray-400">AI-Native Trading Data Platform</p>
              </div>
            </div>
            <div className="flex items-center gap-4 text-sm">
              {pollingEnabled && (
                <span className="flex items-center gap-1.5 text-green-400">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-green-400" />
                  Polling every {pollingInterval}s
                </span>
              )}
              <button
                onClick={handleTrigger}
                disabled={triggering}
                className="flex items-center gap-1.5 rounded border border-gray-700 bg-gray-800 px-3 py-1.5 text-xs text-gray-300 hover:border-blue-500 hover:text-blue-400 disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${triggering ? 'animate-spin' : ''}`} />
                {triggering ? 'Running...' : 'Run Pipeline'}
              </button>
              {lastRun && (
                <span className="hidden sm:inline text-xs text-gray-500">
                  Last: {new Date(lastRun).toLocaleTimeString()}
                </span>
              )}
            </div>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {children}
      </main>
    </div>
  );
}
