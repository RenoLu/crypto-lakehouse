import { useState, type ReactNode } from 'react';
import { RefreshCw, Sun, Moon } from 'lucide-react';
import { useRefresh, useNow } from '../refresh';
import { useTheme } from '../theme';
import AssistantBubble from './AssistantBubble';

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const { lastUpdated, refresh, live } = useRefresh();
  const { theme, toggle } = useTheme();
  const now = useNow();
  const ago = Math.max(0, Math.round((now - lastUpdated) / 1000));
  const [spin, setSpin] = useState(false);

  const onRefresh = () => {
    setSpin(true);
    refresh();
    window.setTimeout(() => setSpin(false), 700);
  };

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-term-border bg-term-bg/85 backdrop-blur">
        <div className="mx-auto flex max-w-[1500px] items-center justify-between px-4 py-2.5 sm:px-6">
          <div className="flex items-center gap-2.5">
            <span className="grid h-6 w-6 place-items-center rounded-sm bg-term-accent/15 text-xs text-term-accent ring-1 ring-term-accent/30">
              ◆
            </span>
            <span className="font-mono text-sm font-semibold tracking-tight text-term-text">CRYPTO·LAKEHOUSE</span>
            <span className="hidden rounded-sm border border-term-border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.2em] text-term-muted sm:inline-block">
              terminal
            </span>
          </div>

          <div className="flex items-center gap-3 sm:gap-4">
            <span
              title={live ? 'Streaming in real time' : 'Auto-refresh (polling)'}
              className={`flex items-center gap-1.5 font-mono text-xs ${live ? 'text-term-up' : 'text-term-accent'}`}
            >
              <span className={`h-1.5 w-1.5 animate-pulse rounded-full ${live ? 'bg-term-up' : 'bg-term-accent'}`} />
              {live ? 'LIVE' : 'LIVE·POLL'}
            </span>
            <span className="hidden font-mono text-xs text-term-muted sm:inline">updated {ago}s ago</span>
            <button
              onClick={onRefresh}
              className="flex items-center gap-1.5 rounded-sm border border-term-border bg-term-panel px-2.5 py-1 font-mono text-xs text-term-muted transition-colors hover:border-term-accent/60 hover:text-term-accent"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${spin ? 'animate-spin' : ''}`} />
              <span className="hidden sm:inline">refresh</span>
            </button>
            <button
              onClick={toggle}
              aria-label="Toggle theme"
              className="grid h-7 w-7 place-items-center rounded-sm border border-term-border bg-term-panel text-term-muted transition-colors hover:border-term-accent/60 hover:text-term-accent"
            >
              {theme === 'dark' ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1500px] px-4 py-4 sm:px-6">{children}</main>

      <AssistantBubble />
    </div>
  );
}
